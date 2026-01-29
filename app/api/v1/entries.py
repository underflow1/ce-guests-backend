import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.database import get_db
from app.models.entry import Entry
from app.models.user import User
from app.schemas.entry import (
    EntryCreate,
    EntryUpdate,
    EntryCompletedUpdate,
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


def parse_date(date_str: str) -> datetime:
    """Парсинг даты из формата YYYY-MM-DD"""
    return datetime.strptime(date_str, "%Y-%m-%d")


def build_entry_response(entry: Entry) -> EntryResponse:
    return EntryResponse(
        id=entry.id,
        name=entry.name,
        responsible=entry.responsible,
        datetime=entry.datetime,
        created_by=entry.created_by,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        updated_by=entry.updated_by,
        is_completed=bool(entry.is_completed),
    )


def get_entries_data(db: Session, today: Optional[str] = None) -> dict:
    """
    Единая функция для получения данных недели (entries, reference_dates, calendar_structure)
    Используется в GET /entries и для формирования WebSocket событий
    """
    try:
        # Определяем текущую дату
        if today:
            today_date = parse_date(today)
            reference_date = tz.localize(today_date.replace(hour=0, minute=0, second=0, microsecond=0))
        else:
            reference_date = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Получаем структуру текущей недели
        calendar_structure = get_week_structure(reference_date)
        
        # Находим предыдущий и следующий рабочие дни
        previous_workday = get_previous_workday(reference_date)
        next_workday = get_next_workday(reference_date)
        
        # Определяем диапазон дат для получения записей
        # Текущая неделя (понедельник - воскресенье)
        week_start = get_week_start(reference_date)
        week_end = week_start + timedelta(days=6)
        
        # Добавляем предыдущий рабочий день, если он не в текущей неделе
        date_from = week_start
        if previous_workday < week_start:
            date_from = previous_workday
        
        # Форматируем для фильтрации (datetime хранится как TEXT в ISO формате)
        date_from_str = date_from.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        date_to_str = week_end.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
        
        # Получаем записи в диапазоне дат, которые не удалены
        entries = db.query(Entry).filter(
            and_(
                Entry.datetime >= date_from_str,
                Entry.datetime <= date_to_str,
                Entry.deleted_at.is_(None)
            )
        ).order_by(Entry.datetime).all()
        
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
        entries_list = [
            EntryResponse(
                id=entry.id,
                name=entry.name,
                responsible=entry.responsible,
                datetime=entry.datetime,
                created_by=entry.created_by,
                created_at=entry.created_at,
                updated_at=entry.updated_at,
                updated_by=entry.updated_by,
                is_completed=bool(entry.is_completed),
            ).dict()
            for entry in entries
        ]
        
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
    Получить записи за текущую неделю + предыдущий рабочий день (если не в текущей неделе)
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
    
    entry = Entry(
        name=entry_data.name,
        responsible=entry_data.responsible,
        datetime=entry_data.datetime,
        created_by=current_user.id,
        created_at=timestamp,
        is_completed=1 if entry_data.is_completed else 0,
    )
    
    db.add(entry)
    db.commit()
    db.refresh(entry)
    
    logger.info(f"Создана запись: ID={entry.id}, name='{entry.name}', datetime={entry.datetime}, user='{current_user.username}'")
    
    response = build_entry_response(entry)
    
    # Отправляем WebSocket событие с полными данными недели
    data = get_entries_data(db)
    broadcast_entry_event_with_data(
        event_type="entry_created",
        change_data={"entry": response.dict()},
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
    """Обновить запись"""
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
    
    # Проверяем права доступа - для всех операций изменения записи требуется can_edit_entry
    permissions = get_user_permissions(current_user)
    
    if "can_edit_entry" not in permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав: требуется право 'can_edit_entry'",
        )
    
    timestamp = get_current_timestamp()
    
    # Обновляем только name и responsible (datetime и is_completed меняются через отдельные роуты)
    entry.name = entry_data.name
    entry.responsible = entry_data.responsible
    entry.updated_at = timestamp
    entry.updated_by = current_user.id
    
    db.commit()
    db.refresh(entry)
    
    logger.info(f"Обновлена запись: ID={entry.id}, name='{entry.name}', datetime={entry.datetime}, user='{current_user.username}'")
    
    response = build_entry_response(entry)
    
    # Отправляем WebSocket событие entry_updated с полными данными недели
    # (PUT используется только для изменения name/responsible)
    data = get_entries_data(db)
    broadcast_entry_event_with_data(
        event_type="entry_updated",
        change_data={"entry": response.dict()},
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
    """Отметить гостя как пришедшего (меняем только is_completed)"""
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
    if entry_data.is_completed:
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
    
    timestamp = get_current_timestamp()
    
    entry.is_completed = 1 if entry_data.is_completed else 0
    entry.updated_at = timestamp
    entry.updated_by = current_user.id
    
    db.commit()
    db.refresh(entry)
    
    logger.info(
        f"Обновлена отметка прихода: ID={entry.id}, is_completed={entry.is_completed}, user='{current_user.username}'"
    )
    
    response = build_entry_response(entry)
    
    # Определяем тип события в зависимости от значения is_completed
    event_type = "entry_completed" if entry_data.is_completed else "entry_uncompleted"
    
    # Отправляем WebSocket событие с полными данными недели
    data = get_entries_data(db)
    broadcast_entry_event_with_data(
        event_type=event_type,
        change_data={"entry": response.dict()},
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
    
    response = build_entry_response(entry)
    
    # Отправляем WebSocket событие entry_moved с полными данными недели
    data = get_entries_data(db)
    broadcast_entry_event_with_data(
        event_type="entry_moved",
        change_data={"entry": response.dict()},
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
    broadcast_entry_event_with_data(
        event_type="entries_deleted_all",
        change_data={"deleted_count": deleted_count},
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
    
    timestamp = get_current_timestamp()
    
    entry_snapshot = build_entry_response(entry)
    entry.deleted_at = timestamp
    entry.deleted_by = current_user.id
    
    db.commit()
    
    logger.info(f"Удалена запись: ID={entry.id}, name='{entry.name}', user='{current_user.username}'")
    
    # Отправляем WebSocket событие entry_deleted с полными данными недели
    data = get_entries_data(db)
    broadcast_entry_event_with_data(
        event_type="entry_deleted",
        change_data={"entry": entry_snapshot.dict()},
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


