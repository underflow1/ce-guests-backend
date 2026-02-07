import logging
import time
from datetime import datetime, timedelta
from typing import Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models.entry import Entry
from app.models.pass_model import Pass
from app.models.user import User
from app.models.visit_goal import VisitGoal
from app.models.meeting_result import MeetingResult
from app.models.meeting_result_reason import MeetingResultReason
from app.models.entry_meeting_reason import EntryMeetingReason
from app.schemas.entry import (
    EntryCreate,
    EntryUpdate,
    EntryDetailsUpdate,
    EntryMeetingResultUpdate,
    EntryCompletedUpdate,
    VisitCancelledUpdate,
    EntryMoveUpdate,
    EntryResponse,
    EntriesListResponse,
    ResponsibleAutocompleteResponse,
    ReferenceDates,
    CalendarDay,
)
from app.api.deps import get_current_user, get_current_active_admin, get_user_permissions, require_permission
from app.services.auth import get_current_timestamp
from app.services.entry_events import broadcast_entry_event, broadcast_entry_event_with_data
from app.services.workdays import (
    get_previous_workday,
    get_next_workday,
    get_week_structure,
    get_week_start,
    format_date,
)
from pytz import timezone
from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)
tz = timezone(settings.TIMEZONE)

# Entry state machine (первичный источник бизнес-логики)
STATE_DRAFT = 10
STATE_CANCELLED = 20
STATE_COMPLETED = 30
STATE_REFUSED = 40
STATE_PENDING = 50
STATE_EMPLOYED = 60


def _state_from_meeting_result_code(code: Optional[int]) -> int:
    if code == 3:
        return STATE_REFUSED
    if code == 1:
        return STATE_PENDING
    if code == 2:
        return STATE_EMPLOYED
    return STATE_COMPLETED


def _apply_state(entry: Entry, new_state: int) -> None:
    """
    Единая точка, где state приводит остальные поля к консистентному виду.
    Причина результата встречи хранится отдельно (EntryMeetingReason) и
    должна быть выставлена ДО вызова, если new_state=40/50.
    """
    entry.state = int(new_state)

    if new_state == STATE_DRAFT:
        entry.meeting_reason = None
        return

    if new_state == STATE_CANCELLED:
        entry.meeting_reason = None
        return

    if new_state == STATE_COMPLETED:
        entry.meeting_reason = None
        return

    # 40/50/60: meeting_reason может быть задана (только для 40/50)
    if new_state == STATE_EMPLOYED:
        entry.meeting_reason = None


def parse_date(date_str: str) -> datetime:
    """Парсинг даты из формата YYYY-MM-DD"""
    return datetime.strptime(date_str, "%Y-%m-%d")


@router.patch("/entries/{entry_id}/details", response_model=EntryResponse)
def update_entry_details(
    entry_id: str,
    payload: EntryDetailsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("can_edit_entry")),
):
    """Атомарное обновление деталей визита (только state=10)."""
    entry = db.query(Entry).options(joinedload(Entry.visit_goals)).filter(Entry.id == entry_id).first()
    if not entry or entry.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена")

    if int(getattr(entry, "state", STATE_DRAFT) or STATE_DRAFT) != STATE_DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Детали визита можно редактировать только в состоянии 'черновик'",
        )

    timestamp = get_current_timestamp()
    visit_goals = resolve_visit_goals(db, entry, payload.visit_goal_ids)

    entry.name = payload.name
    entry.responsible = payload.responsible
    entry.visit_goals = visit_goals
    entry.updated_at = timestamp
    entry.updated_by = current_user.id
    db.commit()
    db.refresh(entry)

    entry = db.query(Entry).options(
        joinedload(Entry.current_pass),
        joinedload(Entry.visit_goals),
        joinedload(Entry.meeting_reason).joinedload(EntryMeetingReason.meeting_result_reason),
    ).filter(Entry.id == entry.id).first()
    response = build_entry_response(entry)

    data = get_entries_data(db)
    actor = build_actor_display(current_user)
    broadcast_entry_event_with_data(
        event_type="entry_updated",
        change_data={"entry": response.dict(), "actor": actor},
        data=data,
    )
    return response


@router.patch("/entries/{entry_id}/meeting-result", response_model=EntryResponse)
def set_entry_meeting_result(
    entry_id: str,
    payload: EntryMeetingResultUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Атомарная установка/смена результата встречи (state=30/40/50/60)."""
    entry = db.query(Entry).filter(Entry.id == entry_id).first()
    if not entry or entry.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена")

    permissions = get_user_permissions(current_user)
    can_set = "can_set_meeting_result" in permissions
    can_change = "can_change_meeting_result" in permissions

    current_state = int(getattr(entry, "state", STATE_DRAFT) or STATE_DRAFT)
    if current_state not in (STATE_COMPLETED, STATE_REFUSED, STATE_PENDING, STATE_EMPLOYED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Результат встречи можно устанавливать только после отметки 'принят'",
        )
    if current_state == STATE_COMPLETED and not can_set:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав: требуется право 'can_set_meeting_result'",
        )
    if current_state in (STATE_REFUSED, STATE_EMPLOYED) and not can_change:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав: требуется право 'can_change_meeting_result'",
        )
    if current_state == STATE_PENDING and not can_set:
        # Переквалификация из временного статуса разрешена всем, кто умеет ставить результат
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав: требуется право 'can_set_meeting_result'",
        )

    # Валидируем соответствие результата/причины
    meeting_result, meeting_reason = resolve_meeting_result(
        db,
        entry,
        payload.meeting_result_id,
        payload.meeting_result_reason_id,
    )
    if meeting_result is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нужно выбрать результат встречи")

    next_state = _state_from_meeting_result_code(meeting_result.code)
    if next_state not in (STATE_REFUSED, STATE_PENDING, STATE_EMPLOYED):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный код результата встречи")

    timestamp = get_current_timestamp()

    # Причину храним отдельно от entries
    if meeting_reason is not None:
        if entry.meeting_reason is None:
            entry.meeting_reason = EntryMeetingReason(
                entry_id=entry.id,
                meeting_result_reason_id=meeting_reason.id,
            )
        else:
            entry.meeting_reason.meeting_result_reason_id = meeting_reason.id
    else:
        entry.meeting_reason = None

    _apply_state(entry, next_state)
    entry.updated_at = timestamp
    entry.updated_by = current_user.id
    db.commit()
    db.refresh(entry)

    entry = db.query(Entry).options(
        joinedload(Entry.current_pass),
        joinedload(Entry.visit_goals),
        joinedload(Entry.meeting_reason).joinedload(EntryMeetingReason.meeting_result_reason),
    ).filter(Entry.id == entry.id).first()
    response = build_entry_response(entry)

    data = get_entries_data(db)
    actor = build_actor_display(current_user)
    broadcast_entry_event_with_data(
        event_type="meeting_result_set",
        change_data={"entry": response.dict(), "actor": actor},
        data=data,
    )
    return response


@router.patch("/entries/{entry_id}/meeting-result/rollback", response_model=EntryResponse)
def rollback_entry_meeting_result(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("can_rollback_meeting_result")),
):
    """Откат результата встречи в состояние 'гость принят' (40/50/60 -> 30)."""
    entry = db.query(Entry).filter(Entry.id == entry_id).first()
    if not entry or entry.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена")

    current_state = int(getattr(entry, "state", STATE_DRAFT) or STATE_DRAFT)
    if current_state not in (STATE_REFUSED, STATE_PENDING, STATE_EMPLOYED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Откат результата возможен только после установки результата",
        )

    timestamp = get_current_timestamp()
    _apply_state(entry, STATE_COMPLETED)
    entry.updated_at = timestamp
    entry.updated_by = current_user.id
    db.commit()
    db.refresh(entry)

    entry = db.query(Entry).options(
        joinedload(Entry.current_pass),
        joinedload(Entry.visit_goals),
        joinedload(Entry.meeting_reason).joinedload(EntryMeetingReason.meeting_result_reason),
    ).filter(Entry.id == entry.id).first()
    response = build_entry_response(entry)

    data = get_entries_data(db)
    actor = build_actor_display(current_user)
    broadcast_entry_event_with_data(
        event_type="meeting_result_rollback",
        change_data={"entry": response.dict(), "actor": actor},
        data=data,
    )
    return response


def build_entry_response(entry: Entry) -> EntryResponse:
    pass_status = None
    try:
        if getattr(entry, "current_pass", None) is not None:
            pass_status = entry.current_pass.status
    except Exception:
        pass_status = None

    state = int(getattr(entry, "state", STATE_DRAFT) or STATE_DRAFT)

    # Результат встречи выводим из state (meeting_result_id в entries больше нет)
    meeting_result_code = None
    meeting_result_name = None
    if state == STATE_REFUSED:
        meeting_result_code = 3
        meeting_result_name = "Отказ"
    elif state == STATE_PENDING:
        meeting_result_code = 1
        meeting_result_name = "Не оформлен"
    elif state == STATE_EMPLOYED:
        meeting_result_code = 2
        meeting_result_name = "Трудоустроен"

    reason_obj = getattr(entry, "meeting_reason", None)
    reason_id = getattr(reason_obj, "meeting_result_reason_id", None) if reason_obj is not None else None
    reason_name = None
    try:
        reason_rel = getattr(reason_obj, "meeting_result_reason", None) if reason_obj is not None else None
        reason_name = getattr(reason_rel, "name", None) if reason_rel is not None else None
    except Exception:
        reason_name = None

    return EntryResponse(
        id=entry.id,
        name=entry.name,
        responsible=entry.responsible,
        datetime=entry.datetime,
        created_by=entry.created_by,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        updated_by=entry.updated_by,
        state=state,
        current_pass_id=getattr(entry, "current_pass_id", None),
        pass_status=pass_status,
        visit_goal_ids=[goal.id for goal in (entry.visit_goals or [])],
        meeting_result_name=meeting_result_name,
        meeting_result_code=meeting_result_code,
        meeting_result_reason_id=reason_id,
        meeting_result_reason_name=reason_name,
    )


def build_actor_display(user: User) -> str:
    if user.full_name:
        return user.full_name
    return user.username


def resolve_visit_goals(db: Session, entry: Optional[Entry], visit_goal_ids: list[str]) -> list[VisitGoal]:
    if not visit_goal_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нужно выбрать хотя бы одну цель визита",
        )

    unique_ids = list(dict.fromkeys(visit_goal_ids))
    goals = db.query(VisitGoal).filter(VisitGoal.id.in_(unique_ids)).all()
    if len(goals) != len(unique_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Некоторые цели визита не найдены",
        )

    existing_ids = {goal.id for goal in (entry.visit_goals or [])} if entry else set()
    inactive_new = [goal for goal in goals if not goal.is_active and goal.id not in existing_ids]
    if inactive_new:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Выбраны неактивные цели визита",
        )

    return goals


def resolve_meeting_result(
    db: Session,
    entry: Optional[Entry],
    meeting_result_id: Optional[str],
    meeting_result_reason_id: Optional[str],
) -> tuple[Optional[MeetingResult], Optional[MeetingResultReason]]:
    if meeting_result_id is None:
        if meeting_result_reason_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Причина результата встречи не может быть указана без результата",
            )
        return None, None

    result = db.query(MeetingResult).filter(MeetingResult.id == meeting_result_id).first()
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Результат встречи не найден",
        )

    if not result.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Выбран неактивный результат встречи",
        )
    
    # Запрещаем выбирать статусы с code <= 0 как результат встречи
    # (это служебные статусы, не результаты встречи)
    if result.code is not None and result.code <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Этот статус нельзя выбрать как результат встречи. Используйте функцию отмены визита для отмены встречи.",
        )

    active_reasons = (
        db.query(MeetingResultReason)
        .filter(
            MeetingResultReason.meeting_result_id == meeting_result_id,
            MeetingResultReason.is_active == 1,
        )
        .all()
    )
    active_reason_ids = {reason.id for reason in active_reasons}

    if active_reason_ids:
        if meeting_result_reason_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Нужно выбрать причину результата встречи",
            )
        reason = (
            db.query(MeetingResultReason)
            .filter(MeetingResultReason.id == meeting_result_reason_id)
            .first()
        )
        if not reason or reason.meeting_result_id != meeting_result_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Причина результата встречи не найдена",
            )
        if not reason.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Выбрана неактивная причина результата встречи",
            )
        return result, reason

    if meeting_result_reason_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для выбранного результата встречи причина не требуется",
        )

    reason = None
    if meeting_result_reason_id is not None:
        reason = (
            db.query(MeetingResultReason)
            .filter(MeetingResultReason.id == meeting_result_reason_id)
            .first()
        )
        if reason and reason.meeting_result_id != meeting_result_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Причина результата встречи не найдена",
            )

    return result, reason


def get_entries_data(db: Session, today: Optional[str] = None) -> dict:
    """
    Единая функция для получения данных недели (entries, reference_dates, calendar_structure)
    Используется в GET /entries и для формирования WebSocket событий
    """
    start_time = time.time()
    try:
        # Определяем текущую дату
        if today:
            today_date = parse_date(today)
            reference_date = tz.localize(today_date.replace(hour=0, minute=0, second=0, microsecond=0))
        else:
            reference_date = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Получаем структуру текущей недели
        calendar_start = time.time()
        calendar_structure = get_week_structure(reference_date)
        calendar_time = time.time() - calendar_start
        logger.debug(f"get_week_structure заняло: {calendar_time:.3f}с")
        
        # Находим предыдущий и следующий рабочие дни
        workdays_start = time.time()
        previous_workday = get_previous_workday(reference_date)
        next_workday = get_next_workday(reference_date)
        workdays_time = time.time() - workdays_start
        logger.debug(f"get_workdays (previous/next) заняло: {workdays_time:.3f}с")
        
        # Определяем диапазон дат для получения записей
        # Текущая неделя (понедельник - воскресенье)
        week_start = get_week_start(reference_date)
        week_end = week_start + timedelta(days=6)
        
        # Добавляем предыдущий/следующий рабочие дни, если они вне текущей недели
        date_from = week_start
        date_to = week_end
        if previous_workday < week_start:
            date_from = previous_workday
        if next_workday > week_end:
            date_to = next_workday
        
        # Форматируем для фильтрации (datetime хранится как TEXT в ISO формате)
        date_from_str = date_from.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        date_to_str = date_to.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
        
        # Получаем записи в диапазоне дат, которые не удалены
        db_start = time.time()
        entries = db.query(Entry).options(
            joinedload(Entry.current_pass),
            joinedload(Entry.visit_goals),
            joinedload(Entry.meeting_reason).joinedload(EntryMeetingReason.meeting_result_reason),
        ).filter(
            and_(
                Entry.datetime >= date_from_str,
                Entry.datetime <= date_to_str,
                Entry.deleted_at.is_(None)
            )
        ).order_by(Entry.datetime).all()
        db_time = time.time() - db_start
        logger.debug(f"DB запрос занял: {db_time:.3f}с")
        
        # Преобразуем calendar_structure в список CalendarDay
        calendar_days = [
            CalendarDay(
                date=day["date"],
                weekday=day["weekday"],
                is_workday=day["is_workday"],
            )
            for day in calendar_structure
        ]
        
        # Формируем entries как список словарей
        entries_list = [build_entry_response(entry).dict() for entry in entries]
        
        total_time = time.time() - start_time
        logger.info(f"get_entries_data выполнено за {total_time:.3f}с (calendar: {calendar_time:.3f}с, workdays: {workdays_time:.3f}с, DB: {db_time:.3f}с)")
        
        return {
            "entries": entries_list,
            "reference_dates": {
                "previous_workday": format_date(previous_workday),
                "next_workday": format_date(next_workday),
            },
            "calendar_structure": [day.dict() for day in calendar_days],
        }
    except ValueError as e:
        logger.error(f"Ошибка при получении данных недели: {str(e)}")
        raise



@router.get("/entries", response_model=EntriesListResponse)
def get_entries(
    today: str = Query(None, description="Текущая дата в формате YYYY-MM-DD (опционально)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("can_view")),
):
    """
    Получить записи за текущую неделю + соседние рабочие дни,
    если они выходят за пределы недели
    Возвращает только не удаленные записи
    """
    try:
        data = get_entries_data(db, today)
        
        return EntriesListResponse(
            entries=[EntryResponse(**entry) for entry in data["entries"]],
            reference_dates=ReferenceDates(**data["reference_dates"]),
            calendar_structure=[CalendarDay(**day) for day in data["calendar_structure"]],
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Неверный формат даты: {str(e)}",
        )


@router.post("/entries", response_model=EntryResponse, status_code=status.HTTP_201_CREATED)
def create_entry(
    entry_data: EntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("can_add")),
):
    """Создать новую запись"""
    # Валидация datetime формата уже в схеме
    
    # Проверяем что datetime в правильном формате
    try:
        datetime.fromisoformat(entry_data.datetime.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="datetime должен быть в формате ISO 8601 (YYYY-MM-DDTHH:MM:SS)",
        )
    
    timestamp = get_current_timestamp()
    visit_goals = resolve_visit_goals(db, None, entry_data.visit_goal_ids)
    
    entry = Entry(
        name=entry_data.name,
        responsible=entry_data.responsible,
        datetime=entry_data.datetime,
        created_by=current_user.id,
        created_at=timestamp,
        # всегда создаем черновик
        state=STATE_DRAFT,
    )
    _apply_state(entry, entry.state)
    
    db.add(entry)
    db.flush()
    entry.visit_goals = visit_goals
    db.commit()
    db.refresh(entry)
    
    logger.info(f"Создана запись: ID={entry.id}, name='{entry.name}', datetime={entry.datetime}, user='{current_user.username}'")
    
    entry = db.query(Entry).options(
        joinedload(Entry.current_pass),
        joinedload(Entry.visit_goals),
        joinedload(Entry.meeting_reason).joinedload(EntryMeetingReason.meeting_result_reason),
    ).filter(Entry.id == entry.id).first()
    response = build_entry_response(entry)
    
    # Отправляем WebSocket событие с полными данными недели
    data = get_entries_data(db)
    actor = build_actor_display(current_user)
    broadcast_entry_event_with_data(
        event_type="entry_created",
        change_data={"entry": response.dict(), "actor": actor},
        data=data,
    )
    
    return response


@router.put("/entries/{entry_id}", response_model=EntryResponse)
def update_entry(
    entry_id: str,
    entry_data: EntryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Обновить детали визита (только черновик). Результат встречи ставится отдельно."""
    entry = db.query(Entry).filter(Entry.id == entry_id).first()
    
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Запись не найдена",
        )
    
    if entry.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Запись удалена",
        )
    
    permissions = get_user_permissions(current_user)
    can_edit_entry = "can_edit_entry" in permissions

    existing_goal_ids = {goal.id for goal in (entry.visit_goals or [])}
    incoming_goal_ids = set(entry_data.visit_goal_ids)
    visit_goals_changed = existing_goal_ids != incoming_goal_ids
    name_changed = entry_data.name != entry.name
    responsible_changed = (entry_data.responsible or "") != (entry.responsible or "")
    edit_fields_changed = name_changed or responsible_changed or visit_goals_changed

    if edit_fields_changed and not can_edit_entry:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав: требуется право 'can_edit_entry'",
        )
    # Детали можно править только в state=10
    if int(getattr(entry, "state", STATE_DRAFT) or STATE_DRAFT) != STATE_DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Детали визита можно редактировать только в состоянии 'черновик'",
        )

    timestamp = get_current_timestamp()
    visit_goals = resolve_visit_goals(db, entry, entry_data.visit_goal_ids)

    if edit_fields_changed:
        entry.name = entry_data.name
        entry.responsible = entry_data.responsible
        entry.visit_goals = visit_goals
    if edit_fields_changed:
        entry.updated_at = timestamp
        entry.updated_by = current_user.id
    
    db.commit()
    db.refresh(entry)
    
    logger.info(f"Обновлена запись: ID={entry.id}, name='{entry.name}', datetime={entry.datetime}, user='{current_user.username}'")
    
    entry = db.query(Entry).options(
        joinedload(Entry.current_pass),
        joinedload(Entry.visit_goals),
        joinedload(Entry.meeting_reason).joinedload(EntryMeetingReason.meeting_result_reason),
    ).filter(Entry.id == entry.id).first()
    response = build_entry_response(entry)
    
    data = get_entries_data(db)
    actor = build_actor_display(current_user)

    if edit_fields_changed:
        # Отправляем WebSocket событие entry_updated с полными данными недели
        # (PUT используется только для изменения name/responsible)
        broadcast_entry_event_with_data(
            event_type="entry_updated",
            change_data={"entry": response.dict(), "actor": actor},
            data=data,
        )
    
    return response


@router.patch("/entries/{entry_id}/completed", response_model=EntryResponse)
def mark_entry_completed(
    entry_id: str,
    entry_data: EntryCompletedUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Отметить гостя как пришедшего (state 10 <-> 30)"""
    entry = db.query(Entry).filter(Entry.id == entry_id).first()
    
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Запись не найдена",
        )
    
    if entry.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Запись удалена",
        )

    permissions = get_user_permissions(current_user)
    if entry_data.completed:
        if "can_mark_completed" not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав: требуется право 'can_mark_completed'",
            )
    else:
        if "can_unmark_completed" not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав: требуется право 'can_unmark_completed'",
            )
    
    current_state = int(getattr(entry, "state", STATE_DRAFT) or STATE_DRAFT)
    timestamp = get_current_timestamp()

    if entry_data.completed:
        if current_state != STATE_DRAFT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Отметить 'принят' можно только из состояния 'черновик'",
            )
        _apply_state(entry, STATE_COMPLETED)
    else:
        if current_state != STATE_COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Снять 'принят' можно только из состояния 'гость принят'",
            )
        _apply_state(entry, STATE_DRAFT)

    entry.updated_at = timestamp
    entry.updated_by = current_user.id
    
    db.commit()
    db.refresh(entry)
    
    logger.info(
        f"Обновлена отметка прихода: ID={entry.id}, state={getattr(entry, 'state', None)}, user='{current_user.username}'"
    )
    
    entry = db.query(Entry).options(
        joinedload(Entry.current_pass),
        joinedload(Entry.visit_goals),
        joinedload(Entry.meeting_reason).joinedload(EntryMeetingReason.meeting_result_reason),
    ).filter(Entry.id == entry.id).first()
    response = build_entry_response(entry)
    
    event_type = "entry_completed" if entry_data.completed else "entry_uncompleted"
    
    # Отправляем WebSocket событие с полными данными недели
    data = get_entries_data(db)
    actor = build_actor_display(current_user)
    broadcast_entry_event_with_data(
        event_type=event_type,
        change_data={"entry": response.dict(), "actor": actor},
        data=data,
    )
    
    return response


@router.patch("/entries/{entry_id}/cancelled", response_model=EntryResponse)
def mark_visit_cancelled(
    entry_id: str,
    entry_data: VisitCancelledUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Отметить визит как отмененный (state 10 <-> 20)"""
    entry = db.query(Entry).filter(Entry.id == entry_id).first()

    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена")

    if entry.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запись удалена")

    permissions = get_user_permissions(current_user)
    if entry_data.cancelled:
        if "can_mark_cancelled" not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав: требуется право 'can_mark_cancelled'",
            )
    else:
        if "can_unmark_cancelled" not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав: требуется право 'can_unmark_cancelled'",
            )

    current_state = int(getattr(entry, "state", STATE_DRAFT) or STATE_DRAFT)
    timestamp = get_current_timestamp()

    if entry_data.cancelled:
        if current_state != STATE_DRAFT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Отменить визит можно только из состояния 'черновик'",
            )
        _apply_state(entry, STATE_CANCELLED)
    else:
        if current_state != STATE_CANCELLED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Снять отмену можно только из состояния 'отменена'",
            )
        _apply_state(entry, STATE_DRAFT)

    entry.updated_at = timestamp
    entry.updated_by = current_user.id

    db.commit()
    db.refresh(entry)

    entry = db.query(Entry).options(
        joinedload(Entry.current_pass),
        joinedload(Entry.visit_goals),
        joinedload(Entry.meeting_reason).joinedload(EntryMeetingReason.meeting_result_reason),
    ).filter(Entry.id == entry.id).first()
    response = build_entry_response(entry)

    event_type = "visit_cancelled" if entry_data.cancelled else "visit_uncancelled"
    data = get_entries_data(db)
    actor = build_actor_display(current_user)
    broadcast_entry_event_with_data(
        event_type=event_type,
        change_data={"entry": response.dict(), "actor": actor},
        data=data,
    )

    return response


def _entry_date_from_datetime(datetime_str: str) -> str:
    # ожидаем ISO: YYYY-MM-DDTHH:MM:SS
    if "T" in datetime_str:
        return datetime_str.split("T", 1)[0]
    return datetime_str[:10]


@router.put("/entries/{entry_id}/pass", response_model=EntryResponse)
def order_pass(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Заказать пропуск (создаёт запись passes и назначает её текущей)"""
    entry = db.query(Entry).filter(Entry.id == entry_id).first()

    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена")
    if entry.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запись удалена")
    current_state = int(getattr(entry, "state", STATE_DRAFT) or STATE_DRAFT)
    if current_state in (STATE_CANCELLED, STATE_REFUSED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Заказ пропуска недоступен в текущем состоянии записи",
        )

    permissions = get_user_permissions(current_user)
    if "can_mark_pass" not in permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав: требуется право 'can_mark_pass'",
        )

    timestamp = get_current_timestamp()
    pass_date = _entry_date_from_datetime(entry.datetime)
    request_id = str(uuid.uuid4())

    # На текущем этапе внешнюю интеграцию не реализуем (external_id заполним позже)
    new_pass = Pass(
        id=str(uuid.uuid4()),
        entry_id=entry.id,
        date=pass_date,
        request_id=request_id,
        external_id=None,
        status="ordered",
        created_at=timestamp,
        updated_at=None,
        updated_by=None,
    )
    db.add(new_pass)
    db.flush()

    entry.current_pass_id = new_pass.id
    entry.updated_at = timestamp
    entry.updated_by = current_user.id

    db.commit()

    # Подгружаем current_pass для корректного ответа
    entry = db.query(Entry).options(
        joinedload(Entry.current_pass),
        joinedload(Entry.visit_goals),
        joinedload(Entry.meeting_reason).joinedload(EntryMeetingReason.meeting_result_reason),
    ).filter(Entry.id == entry.id).first()
    response = build_entry_response(entry)

    data = get_entries_data(db)
    actor = build_actor_display(current_user)
    broadcast_entry_event_with_data(
        event_type="pass_ordered",
        change_data={"entry": response.dict(), "actor": actor},
        data=data,
    )

    return response


@router.delete("/entries/{entry_id}/pass", response_model=EntryResponse)
def revoke_pass(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Отозвать текущий пропуск (ставим status=revoked у текущей записи passes)"""
    entry = db.query(Entry).options(
        joinedload(Entry.current_pass),
        joinedload(Entry.visit_goals),
        joinedload(Entry.meeting_reason).joinedload(EntryMeetingReason.meeting_result_reason),
    ).filter(Entry.id == entry_id).first()

    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена")
    if entry.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запись удалена")

    permissions = get_user_permissions(current_user)
    if "can_revoke_pass" not in permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав: требуется право 'can_revoke_pass'",
        )

    if not entry.current_pass_id or entry.current_pass is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Текущий пропуск отсутствует")

    timestamp = get_current_timestamp()
    entry.current_pass.status = "revoked"
    entry.current_pass.updated_at = timestamp
    entry.current_pass.updated_by = current_user.id

    entry.updated_at = timestamp
    entry.updated_by = current_user.id

    db.commit()

    entry = db.query(Entry).options(
        joinedload(Entry.current_pass),
        joinedload(Entry.visit_goals),
        joinedload(Entry.meeting_reason).joinedload(EntryMeetingReason.meeting_result_reason),
    ).filter(Entry.id == entry.id).first()
    response = build_entry_response(entry)

    data = get_entries_data(db)
    actor = build_actor_display(current_user)
    broadcast_entry_event_with_data(
        event_type="pass_revoked",
        change_data={"entry": response.dict(), "actor": actor},
        data=data,
    )

    return response


@router.patch("/entries/{entry_id}/move", response_model=EntryResponse)
def move_entry(
    entry_id: str,
    entry_data: EntryMoveUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Переместить запись (изменить дату/время через drag&drop)"""
    entry = db.query(Entry).filter(Entry.id == entry_id).first()
    
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Запись не найдена",
        )
    
    if entry.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Запись удалена",
        )
    if int(getattr(entry, "state", STATE_DRAFT) or STATE_DRAFT) != STATE_DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Перемещение возможно только в состоянии 'черновик'",
        )

    # Проверяем права доступа - требуется can_move_entry
    permissions = get_user_permissions(current_user)
    if "can_move_entry" not in permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав: требуется право 'can_move_entry'",
        )
    
    # Валидация datetime формата уже в схеме
    try:
        datetime.fromisoformat(entry_data.datetime.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="datetime должен быть в формате ISO 8601 (YYYY-MM-DDTHH:MM:SS)",
        )
    
    timestamp = get_current_timestamp()
    
    # Обновляем только datetime
    entry.datetime = entry_data.datetime
    entry.updated_at = timestamp
    entry.updated_by = current_user.id
    
    db.commit()
    db.refresh(entry)
    
    logger.info(
        f"Перемещена запись: ID={entry.id}, datetime={entry.datetime}, user='{current_user.username}'"
    )
    
    entry = db.query(Entry).options(
        joinedload(Entry.current_pass),
        joinedload(Entry.visit_goals),
        joinedload(Entry.meeting_reason).joinedload(EntryMeetingReason.meeting_result_reason),
    ).filter(Entry.id == entry.id).first()
    response = build_entry_response(entry)
    
    # Отправляем WebSocket событие entry_moved с полными данными недели
    data = get_entries_data(db)
    actor = build_actor_display(current_user)
    broadcast_entry_event_with_data(
        event_type="entry_moved",
        change_data={"entry": response.dict(), "actor": actor},
        data=data,
    )
    
    return response


@router.delete("/entries/all")
def delete_all_entries(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """Удалить все записи (жёсткое удаление из БД, только для админов)"""
    # Получаем все записи (включая уже удаленные)
    entries = db.query(Entry).all()
    
    # Жёстко удаляем все записи из БД
    deleted_count = len(entries)
    for entry in entries:
        db.delete(entry)
    
    db.commit()
    
    logger.info(f"Жёстко удалены все записи ({deleted_count} шт.) пользователем '{current_user.username}'")
    
    # Отправляем WebSocket событие entries_deleted_all с полными данными недели
    # (entries будет пустым массивом после удаления)
    data = get_entries_data(db)
    actor = build_actor_display(current_user)
    broadcast_entry_event_with_data(
        event_type="entries_deleted_all",
        change_data={"deleted_count": deleted_count, "actor": actor},
        data=data,
    )
    
    return {
        "success": True,
        "deleted_count": deleted_count,
    }


@router.delete("/entries/{entry_id}")
def delete_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("can_delete_entry")),
):
    """Удалить запись (мягкое удаление)"""
    entry = db.query(Entry).filter(Entry.id == entry_id).first()
    
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Запись не найдена",
        )
    
    if entry.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Запись уже удалена",
        )
    # Удаление: админу можно везде, остальным — только в state=10
    if not bool(getattr(current_user, "is_admin", 0)):
        if int(getattr(entry, "state", STATE_DRAFT) or STATE_DRAFT) != STATE_DRAFT:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Удаление доступно только для черновиков",
            )
    
    timestamp = get_current_timestamp()
    
    entry_snapshot = build_entry_response(entry)
    entry.deleted_at = timestamp
    entry.deleted_by = current_user.id
    
    db.commit()
    
    logger.info(f"Удалена запись: ID={entry.id}, name='{entry.name}', user='{current_user.username}'")
    
    # Отправляем WebSocket событие entry_deleted с полными данными недели
    data = get_entries_data(db)
    actor = build_actor_display(current_user)
    broadcast_entry_event_with_data(
        event_type="entry_deleted",
        change_data={"entry": entry_snapshot.dict(), "actor": actor},
        data=data,
    )
    
    return {"success": True}


@router.get("/entries/responsible-autocomplete", response_model=ResponsibleAutocompleteResponse)
def get_responsible_autocomplete(
    q: str = Query(..., description="Поисковый запрос (минимум 3 символа)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Получить варианты автокомплита для поля "Ответственный"
    Ищет в записях текущего пользователя по первым символам (case-insensitive)
    """
    if len(q) < 3:
        return ResponsibleAutocompleteResponse(suggestions=[])
    
    # Получаем последние N записей пользователя (не удаленные)
    # Сортируем по created_at DESC для получения самых свежих
    recent_entries = db.query(Entry).filter(
        and_(
            Entry.created_by == current_user.id,
            Entry.deleted_at.is_(None),
            Entry.responsible.isnot(None),
            Entry.responsible != "",
        )
    ).order_by(Entry.created_at.desc()).limit(settings.AUTOCOMPLETE_LOOKUP_LIMIT).all()
    
    # Фильтруем по началу строки (case-insensitive) и собираем уникальные значения
    query_lower = q.lower()
    suggestions_set = set()
    
    for entry in recent_entries:
        if entry.responsible and entry.responsible.lower().startswith(query_lower):
            suggestions_set.add(entry.responsible)
    
    # Сортируем по алфавиту и возвращаем список
    suggestions = sorted(list(suggestions_set))
    
    logger.debug(f"Автокомплит для '{q}': найдено {len(suggestions)} вариантов для пользователя '{current_user.username}'")
    
    return ResponsibleAutocompleteResponse(suggestions=suggestions)


