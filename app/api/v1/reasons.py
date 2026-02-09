from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.reason import Reason
from app.models.state_reason_option import StateReasonOption
from app.models.user import User
from app.api.deps import get_current_user, get_current_active_admin
from app.schemas.reason import (
    ReasonCreate,
    ReasonUpdate,
    ReasonResponse,
    ReasonsResponse,
    StateReasonsUpdate,
)
from app.services.auth import get_current_timestamp

router = APIRouter()


def _validate_state_for_reasons(state_value: int) -> int:
    s = int(state_value)
    if s not in (40, 50):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Причины поддерживаются только для state=40 (Отказ) и state=50 (Не оформлен)",
        )
    return s


@router.get("/reasons", response_model=ReasonsResponse)
def get_active_reasons(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reasons = db.query(Reason).filter(Reason.is_active == 1).order_by(Reason.name.asc()).all()
    return {"reasons": [ReasonResponse.from_orm(r) for r in reasons]}


@router.get("/reasons/all", response_model=ReasonsResponse)
def get_all_reasons(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    reasons = db.query(Reason).order_by(Reason.name.asc()).all()
    return {"reasons": [ReasonResponse.from_orm(r) for r in reasons]}


@router.post("/reasons", response_model=ReasonResponse, status_code=status.HTTP_201_CREATED)
def create_reason(
    payload: ReasonCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Название не может быть пустым")

    existing = db.query(Reason).filter(func.lower(Reason.name) == func.lower(name)).first()
    if existing:
        if existing.is_active != 1:
            existing.is_active = 1
            existing.updated_at = get_current_timestamp()
            existing.updated_by = current_user.id
            db.commit()
            db.refresh(existing)
        return ReasonResponse.from_orm(existing)

    now = get_current_timestamp()
    reason = Reason(
        name=name,
        is_active=1,
        created_at=now,
        updated_at=None,
        updated_by=None,
    )
    db.add(reason)
    db.commit()
    db.refresh(reason)
    return ReasonResponse.from_orm(reason)


@router.patch("/reasons/{reason_id}", response_model=ReasonResponse)
def update_reason(
    reason_id: str,
    payload: ReasonUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    reason = db.query(Reason).filter(Reason.id == reason_id).first()
    if not reason:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Причина не найдена")

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Название не может быть пустым")
        reason.name = name
    if payload.is_active is not None:
        reason.is_active = 1 if payload.is_active else 0

    reason.updated_at = get_current_timestamp()
    reason.updated_by = current_user.id
    db.commit()
    db.refresh(reason)
    return ReasonResponse.from_orm(reason)


@router.get("/states/{state}/reasons", response_model=ReasonsResponse)
def get_allowed_active_state_reasons(
    state: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = _validate_state_for_reasons(state)
    reasons = (
        db.query(Reason)
        .join(StateReasonOption, StateReasonOption.reason_id == Reason.id)
        .filter(StateReasonOption.state == s, Reason.is_active == 1)
        .order_by(Reason.name.asc())
        .all()
    )
    return {"reasons": [ReasonResponse.from_orm(r) for r in reasons]}


@router.get("/states/{state}/reasons/all", response_model=ReasonsResponse)
def get_allowed_state_reasons_all(
    state: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    s = _validate_state_for_reasons(state)
    reasons = (
        db.query(Reason)
        .join(StateReasonOption, StateReasonOption.reason_id == Reason.id)
        .filter(StateReasonOption.state == s)
        .order_by(Reason.name.asc())
        .all()
    )
    return {"reasons": [ReasonResponse.from_orm(r) for r in reasons]}


@router.put("/states/{state}/reasons", response_model=ReasonsResponse)
def set_state_reasons(
    state: int,
    payload: StateReasonsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    s = _validate_state_for_reasons(state)
    incoming_ids = list(dict.fromkeys(payload.reason_ids or []))

    # validate all ids exist
    if incoming_ids:
        found = db.query(Reason).filter(Reason.id.in_(incoming_ids)).all()
        found_ids = {r.id for r in found}
        missing = [rid for rid in incoming_ids if rid not in found_ids]
        if missing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некоторые причины не найдены")

    # delete old
    db.query(StateReasonOption).filter(StateReasonOption.state == s).delete(synchronize_session=False)
    # insert new
    for rid in incoming_ids:
        db.add(StateReasonOption(state=s, reason_id=rid))
    db.commit()

    reasons = (
        db.query(Reason)
        .join(StateReasonOption, StateReasonOption.reason_id == Reason.id)
        .filter(StateReasonOption.state == s)
        .order_by(Reason.name.asc())
        .all()
    )
    return {"reasons": [ReasonResponse.from_orm(r) for r in reasons]}

