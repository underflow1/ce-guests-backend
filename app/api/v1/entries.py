import logging
import time
from datetime import datetime, timedelta
from typing import Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models.entry import Entry
from app.models.pass_model import Pass
from app.models.user import User
from app.models.visit_goal import VisitGoal
from app.models.entry_meeting_reason import EntryMeetingReason
from app.models.reason import Reason
from app.models.state_reason_option import StateReasonOption
from app.schemas.entry import (
    EntryCreate,
    EntryUpdate,
    EntryDetailsUpdate,
    EntryResultUpdate,
    EntryMoveUpdate,
    EntryResponse,
    EntriesListResponse,
    ResponsibleAutocompleteResponse,
    ReferenceDates,
    CalendarDay,
)
from app.api.deps import get_current_user, get_current_active_admin, get_user_permissions, require_permission
from app.services.auth import get_current_timestamp
from app.services.entry_events import (
    broadcast_entry_event_with_data,
    get_active_week_offsets,
)
from app.services.workdays import (
    get_previous_workday,
    get_next_workday,
    get_week_structure,
    get_week_start,
    format_date,
)
from pytz import timezone
from app.config import settings
from app.services.pass_integration import (
    PassIntegrationAmbiguousError,
    PassIntegrationDisabledError,
    PassIntegrationError,
    order_external_pass,
    revoke_external_pass,
)

router = APIRouter()
logger = logging.getLogger(__name__)
tz = timezone(settings.TIMEZONE)

# Entry state machine (первичный источник бизнес-логики)
STATE_DRAFT = 10
STATE_CANCELLED = 20
STATE_ARRIVED = 30
STATE_REFUSED = 40
STATE_PENDING = 50
STATE_EMPLOYED = 60


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

    if new_state == STATE_ARRIVED:
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
        joinedload(Entry.passes),
        joinedload(Entry.visit_goals),
        joinedload(Entry.meeting_reason).joinedload(EntryMeetingReason.reason),
    ).filter(Entry.id == entry.id).first()
    response = build_entry_response(entry)

    data_by_week_offset = get_entries_data_for_active_offsets(db)
    actor = build_actor_display(current_user)
    broadcast_entry_event_with_data(
        event_type="entry_updated",
        change_data={"entry": response.dict(), "actor": actor},
        data_by_week_offset=data_by_week_offset,
    )
    return response


@router.patch("/entries/{entry_id}/result", response_model=EntryResponse)
def set_entry_result(
    entry_id: str,
    payload: EntryResultUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Атомарная установка state:
    - 10 -> 20/30/40/50/60
    - 30/40/50/60 -> 40/50/60
    """
    entry = db.query(Entry).filter(Entry.id == entry_id).first()
    if not entry or entry.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена")

    permissions = get_user_permissions(current_user)
    can_set = "can_set_meeting_result" in permissions
    can_change = "can_change_meeting_result" in permissions
    can_mark_arrived = "can_mark_arrived" in permissions
    can_mark_cancelled = "can_mark_cancelled" in permissions

    current_state = int(getattr(entry, "state", STATE_DRAFT) or STATE_DRAFT)
    next_state = int(payload.state)
    if current_state == STATE_DRAFT:
        if next_state == STATE_ARRIVED:
            if not can_mark_arrived:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Недостаточно прав: требуется право 'can_mark_arrived'",
                )
        elif next_state == STATE_CANCELLED:
            if not can_mark_cancelled:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Недостаточно прав: требуется право 'can_mark_cancelled'",
                )
        elif next_state in (STATE_REFUSED, STATE_PENDING, STATE_EMPLOYED):
            if not can_set:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Недостаточно прав: требуется право 'can_set_meeting_result'",
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Из состояния 'черновик' доступны только переходы в 20, 30, 40, 50 или 60",
            )
    elif current_state in (STATE_ARRIVED, STATE_REFUSED, STATE_PENDING, STATE_EMPLOYED):
        if next_state not in (STATE_REFUSED, STATE_PENDING, STATE_EMPLOYED):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный state результата")
        if current_state == STATE_ARRIVED and not can_set:
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
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Установка state недоступна для текущего состояния",
        )

    timestamp = get_current_timestamp()

    # Причину храним отдельно от entries (только для 40/50)
    if next_state in (STATE_REFUSED, STATE_PENDING):
        active_reasons = (
            db.query(Reason)
            .join(StateReasonOption, StateReasonOption.reason_id == Reason.id)
            .filter(StateReasonOption.state == next_state, Reason.is_active == 1)
            .all()
        )
        active_reason_ids = {r.id for r in active_reasons}

        if active_reason_ids and payload.reason_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Нужно выбрать причину результата",
            )

        if payload.reason_id is not None:
            reason = db.query(Reason).filter(Reason.id == payload.reason_id).first()
            if not reason:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Причина результата не найдена",
                )
            if reason.is_active != 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Выбрана неактивная причина результата",
                )
            allowed = (
                db.query(StateReasonOption)
                .filter(StateReasonOption.state == next_state, StateReasonOption.reason_id == reason.id)
                .first()
            )
            if not allowed:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Причина результата не разрешена для выбранного state",
                )

            if entry.meeting_reason is None:
                entry.meeting_reason = EntryMeetingReason(entry_id=entry.id, reason_id=reason.id)
            else:
                entry.meeting_reason.reason_id = reason.id
        else:
            entry.meeting_reason = None
    elif next_state in (STATE_DRAFT, STATE_CANCELLED, STATE_ARRIVED, STATE_EMPLOYED):
        if payload.reason_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Для выбранного state причина не требуется",
            )
        entry.meeting_reason = None
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный state")

    _apply_state(entry, next_state)
    entry.updated_at = timestamp
    entry.updated_by = current_user.id
    db.commit()
    db.refresh(entry)

    entry = db.query(Entry).options(
        joinedload(Entry.passes),
        joinedload(Entry.visit_goals),
        joinedload(Entry.meeting_reason).joinedload(EntryMeetingReason.reason),
    ).filter(Entry.id == entry.id).first()
    response = build_entry_response(entry)

    data_by_week_offset = get_entries_data_for_active_offsets(db)
    actor = build_actor_display(current_user)
    event_type = (
        "entry_arrived"
        if next_state == STATE_ARRIVED
        else "visit_cancelled"
        if next_state == STATE_CANCELLED
        else "result_set"
    )
    broadcast_entry_event_with_data(
        event_type=event_type,
        change_data={"entry": response.dict(), "actor": actor},
        data_by_week_offset=data_by_week_offset,
    )
    return response


@router.patch("/entries/{entry_id}/rollback", response_model=EntryResponse)
def rollback_entry_state(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("can_view")),
):
    """Единый откат состояния:
    - 20/30 -> 10
    - 40/50/60 -> 30
    """
    entry = db.query(Entry).filter(Entry.id == entry_id).first()
    if not entry or entry.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена")

    permissions = get_user_permissions(current_user)
    current_state = int(getattr(entry, "state", STATE_DRAFT) or STATE_DRAFT)
    rollback_target = None
    if current_state == STATE_CANCELLED:
        if "can_unmark_cancelled" not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав: требуется право 'can_unmark_cancelled'",
            )
        rollback_target = STATE_DRAFT
    elif current_state == STATE_ARRIVED:
        if "can_unmark_arrived" not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав: требуется право 'can_unmark_arrived'",
            )
        rollback_target = STATE_DRAFT
    elif current_state in (STATE_REFUSED, STATE_PENDING, STATE_EMPLOYED):
        if current_state in (STATE_REFUSED, STATE_EMPLOYED) and "can_rollback_meeting_result" not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав: требуется право 'can_rollback_meeting_result'",
            )
        rollback_target = STATE_ARRIVED
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Откат недоступен для текущего состояния",
        )

    timestamp = get_current_timestamp()
    _apply_state(entry, rollback_target)
    entry.updated_at = timestamp
    entry.updated_by = current_user.id
    db.commit()
    db.refresh(entry)

    entry = db.query(Entry).options(
        joinedload(Entry.passes),
        joinedload(Entry.visit_goals),
        joinedload(Entry.meeting_reason).joinedload(EntryMeetingReason.reason),
    ).filter(Entry.id == entry.id).first()
    response = build_entry_response(entry)

    data_by_week_offset = get_entries_data_for_active_offsets(db)
    actor = build_actor_display(current_user)
    broadcast_entry_event_with_data(
        event_type="entry_rollback",
        change_data={"entry": response.dict(), "actor": actor},
        data_by_week_offset=data_by_week_offset,
    )
    return response


def build_entry_response(entry: Entry) -> EntryResponse:
    active_pass = get_active_pass_for_entry(entry)
    pass_status = getattr(active_pass, "status", None)
    pass_external_id = getattr(active_pass, "external_id", None)

    state = int(getattr(entry, "state", STATE_DRAFT) or STATE_DRAFT)

    reason_obj = getattr(entry, "meeting_reason", None)
    reason_id = getattr(reason_obj, "reason_id", None) if reason_obj is not None else None
    reason_name = None
    try:
        reason_rel = getattr(reason_obj, "reason", None) if reason_obj is not None else None
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
        pass_external_id=pass_external_id,
        pass_status=pass_status,
        visit_goal_ids=[goal.id for goal in (entry.visit_goals or [])],
        result_reason_id=reason_id,
        result_reason_name=reason_name,
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


def _is_date_within_range(target: datetime, start: datetime, end: datetime) -> bool:
    return start <= target <= end


def get_entries_data(db: Session, today: Optional[str] = None, week_offset: int = 0) -> dict:
    """
    Единая функция для получения данных недели (entries, reference_dates, calendar_structure)
    Используется в GET /entries и для формирования WebSocket событий
    """
    start_time = time.time()
    try:
        # Определяем опорную "сегодняшнюю" дату
        if today:
            today_date = parse_date(today)
            reference_date = tz.localize(today_date.replace(hour=0, minute=0, second=0, microsecond=0))
        else:
            reference_date = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)

        # Нижняя панель может смотреть смещенную неделю.
        # Верхние reference_dates всегда считаются от текущей даты.
        bottom_reference_date = reference_date + timedelta(days=(int(week_offset) * 7))

        # Получаем структуру недели для нижней панели
        calendar_start = time.time()
        calendar_structure = get_week_structure(bottom_reference_date)
        calendar_time = time.time() - calendar_start
        logger.debug(f"get_week_structure заняло: {calendar_time:.3f}с")

        # Находим предыдущий и следующий рабочие дни относительно текущей даты
        workdays_start = time.time()
        previous_workday = get_previous_workday(reference_date)
        next_workday = get_next_workday(reference_date)
        workdays_time = time.time() - workdays_start
        logger.debug(f"get_workdays (previous/next) заняло: {workdays_time:.3f}с")

        # Формируем объединение интересующих диапазонов:
        # - текущая неделя (для верхних панелей)
        # - выбранная пользователем неделя (для нижней панели)
        # - соседние рабочие дни (если вне указанных недель)
        current_week_start = get_week_start(reference_date)
        current_week_end = current_week_start + timedelta(days=6)
        bottom_week_start = get_week_start(bottom_reference_date)
        bottom_week_end = bottom_week_start + timedelta(days=6)

        current_week_dates = {
            format_date(current_week_start + timedelta(days=day_offset))
            for day_offset in range(7)
        }
        bottom_week_dates = {
            format_date(bottom_week_start + timedelta(days=day_offset))
            for day_offset in range(7)
        }
        target_dates = set(current_week_dates) | set(bottom_week_dates)

        if (
            not _is_date_within_range(previous_workday, current_week_start, current_week_end)
            and not _is_date_within_range(previous_workday, bottom_week_start, bottom_week_end)
        ):
            target_dates.add(format_date(previous_workday))

        if (
            not _is_date_within_range(next_workday, current_week_start, current_week_end)
            and not _is_date_within_range(next_workday, bottom_week_start, bottom_week_end)
        ):
            target_dates.add(format_date(next_workday))

        # Получаем записи в целевых диапазонах, которые не удалены
        db_start = time.time()
        entries = db.query(Entry).options(
            joinedload(Entry.passes),
            joinedload(Entry.visit_goals),
            joinedload(Entry.meeting_reason).joinedload(EntryMeetingReason.reason),
        ).filter(
            and_(
                Entry.deleted_at.is_(None),
                func.substr(Entry.datetime, 1, 10).in_(sorted(target_dates)),
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
        logger.info(
            f"get_entries_data(week_offset={week_offset}) выполнено за {total_time:.3f}с "
            f"(calendar: {calendar_time:.3f}с, workdays: {workdays_time:.3f}с, DB: {db_time:.3f}с)"
        )

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


def get_entries_data_for_active_offsets(
    db: Session,
    today: Optional[str] = None,
    include_week_offset: int = 0,
) -> dict[int, dict]:
    offsets = get_active_week_offsets()
    offsets.add(int(include_week_offset))
    data_by_week_offset: dict[int, dict] = {}
    for offset in sorted(offsets):
        data_by_week_offset[offset] = get_entries_data(db, today=today, week_offset=offset)
    return data_by_week_offset



@router.get("/entries", response_model=EntriesListResponse)
def get_entries(
    today: str = Query(None, description="Текущая дата в формате YYYY-MM-DD (опционально)"),
    week_offset: int = Query(0, description="Смещение недели для нижней панели (0=текущая, -1=предыдущая, +1=следующая)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("can_view")),
):
    """
    Получить записи за текущую неделю + соседние рабочие дни,
    если они выходят за пределы недели
    Возвращает только не удаленные записи
    """
    try:
        data = get_entries_data(db, today=today, week_offset=week_offset)
        
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
        joinedload(Entry.passes),
        joinedload(Entry.visit_goals),
        joinedload(Entry.meeting_reason).joinedload(EntryMeetingReason.reason),
    ).filter(Entry.id == entry.id).first()
    response = build_entry_response(entry)
    
    # Отправляем WebSocket событие с полными данными недели
    data_by_week_offset = get_entries_data_for_active_offsets(db)
    actor = build_actor_display(current_user)
    broadcast_entry_event_with_data(
        event_type="entry_created",
        change_data={"entry": response.dict(), "actor": actor},
        data_by_week_offset=data_by_week_offset,
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
        joinedload(Entry.passes),
        joinedload(Entry.visit_goals),
        joinedload(Entry.meeting_reason).joinedload(EntryMeetingReason.reason),
    ).filter(Entry.id == entry.id).first()
    response = build_entry_response(entry)
    
    data_by_week_offset = get_entries_data_for_active_offsets(db)
    actor = build_actor_display(current_user)

    if edit_fields_changed:
        # Отправляем WebSocket событие entry_updated с полными данными недели
        # (PUT используется только для изменения name/responsible)
        broadcast_entry_event_with_data(
            event_type="entry_updated",
            change_data={"entry": response.dict(), "actor": actor},
            data_by_week_offset=data_by_week_offset,
        )
    
    return response


def _entry_date_from_datetime(datetime_str: str) -> str:
    # ожидаем ISO: YYYY-MM-DDTHH:MM:SS
    if "T" in datetime_str:
        return datetime_str.split("T", 1)[0]
    return datetime_str[:10]


def get_active_pass_for_entry(entry: Entry) -> Optional[Pass]:
    entry_date = _entry_date_from_datetime(getattr(entry, "datetime", ""))
    candidates = [
        p for p in (getattr(entry, "passes", None) or [])
        if getattr(p, "status", None) == "ordered" and getattr(p, "date", None) == entry_date
    ]
    candidates.sort(key=lambda p: getattr(p, "created_at", "") or "", reverse=True)
    return candidates[0] if candidates else None


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
    today_date = datetime.now(tz).strftime("%Y-%m-%d")
    if pass_date < today_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя заказать пропуск на прошедшую дату",
        )
    request_id = str(uuid.uuid4())

    try:
        external_id = order_external_pass(
            db=db,
            entry_name=entry.name,
            pass_date=pass_date,
        )
    except PassIntegrationAmbiguousError as exc:
        entry_snapshot = build_entry_response(entry)
        data_by_week_offset = get_entries_data_for_active_offsets(db)
        actor = build_actor_display(current_user)
        broadcast_entry_event_with_data(
            event_type="pass_order_failed",
            change_data={"entry": entry_snapshot.dict(), "actor": actor},
            data_by_week_offset=data_by_week_offset,
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except PassIntegrationDisabledError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except PassIntegrationError as exc:
        entry_snapshot = build_entry_response(entry)
        data_by_week_offset = get_entries_data_for_active_offsets(db)
        actor = build_actor_display(current_user)
        broadcast_entry_event_with_data(
            event_type="pass_order_failed",
            change_data={"entry": entry_snapshot.dict(), "actor": actor},
            data_by_week_offset=data_by_week_offset,
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    new_pass = Pass(
        id=str(uuid.uuid4()),
        entry_id=entry.id,
        date=pass_date,
        request_id=request_id,
        external_id=external_id,
        status="ordered",
        created_at=timestamp,
        updated_at=None,
        updated_by=None,
    )
    db.add(new_pass)
    db.flush()

    entry.updated_at = timestamp
    entry.updated_by = current_user.id

    db.commit()

    # Подгружаем passes для корректного ответа
    entry = db.query(Entry).options(
        joinedload(Entry.passes),
        joinedload(Entry.visit_goals),
        joinedload(Entry.meeting_reason).joinedload(EntryMeetingReason.reason),
    ).filter(Entry.id == entry.id).first()
    response = build_entry_response(entry)

    data_by_week_offset = get_entries_data_for_active_offsets(db)
    actor = build_actor_display(current_user)
    broadcast_entry_event_with_data(
        event_type="pass_ordered",
        change_data={"entry": response.dict(), "actor": actor},
        data_by_week_offset=data_by_week_offset,
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
        joinedload(Entry.passes),
        joinedload(Entry.visit_goals),
        joinedload(Entry.meeting_reason).joinedload(EntryMeetingReason.reason),
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

    active_pass = get_active_pass_for_entry(entry)
    if active_pass is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Текущий пропуск отсутствует")

    external_id = getattr(active_pass, "external_id", None)
    if external_id:
        try:
            revoke_external_pass(db=db, external_id=str(external_id))
        except PassIntegrationDisabledError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
        except PassIntegrationError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    timestamp = get_current_timestamp()
    active_pass.status = "revoked"
    active_pass.updated_at = timestamp
    active_pass.updated_by = current_user.id

    entry.updated_at = timestamp
    entry.updated_by = current_user.id

    db.commit()

    entry = db.query(Entry).options(
        joinedload(Entry.passes),
        joinedload(Entry.visit_goals),
        joinedload(Entry.meeting_reason).joinedload(EntryMeetingReason.reason),
    ).filter(Entry.id == entry.id).first()
    response = build_entry_response(entry)

    data_by_week_offset = get_entries_data_for_active_offsets(db)
    actor = build_actor_display(current_user)
    broadcast_entry_event_with_data(
        event_type="pass_revoked",
        change_data={"entry": response.dict(), "actor": actor},
        data_by_week_offset=data_by_week_offset,
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
        target_datetime = datetime.fromisoformat(entry_data.datetime.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="datetime должен быть в формате ISO 8601 (YYYY-MM-DDTHH:MM:SS)",
        )

    if target_datetime.date() < datetime.now(tz).date():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя переносить запись на прошедшую дату",
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
        joinedload(Entry.passes),
        joinedload(Entry.visit_goals),
        joinedload(Entry.meeting_reason).joinedload(EntryMeetingReason.reason),
    ).filter(Entry.id == entry.id).first()
    response = build_entry_response(entry)
    
    # Отправляем WebSocket событие entry_moved с полными данными недели
    data_by_week_offset = get_entries_data_for_active_offsets(db)
    actor = build_actor_display(current_user)
    broadcast_entry_event_with_data(
        event_type="entry_moved",
        change_data={"entry": response.dict(), "actor": actor},
        data_by_week_offset=data_by_week_offset,
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
    data_by_week_offset = get_entries_data_for_active_offsets(db)
    actor = build_actor_display(current_user)
    broadcast_entry_event_with_data(
        event_type="entries_deleted_all",
        change_data={"deleted_count": deleted_count, "actor": actor},
        data_by_week_offset=data_by_week_offset,
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
    data_by_week_offset = get_entries_data_for_active_offsets(db)
    actor = build_actor_display(current_user)
    broadcast_entry_event_with_data(
        event_type="entry_deleted",
        change_data={"entry": entry_snapshot.dict(), "actor": actor},
        data_by_week_offset=data_by_week_offset,
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


