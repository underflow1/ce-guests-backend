from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.meeting_result import MeetingResult
from app.models.meeting_result_reason import MeetingResultReason
from app.models.user import User
from app.api.deps import get_current_user, get_current_active_admin
from app.schemas.meeting_result import (
    MeetingResultCreate,
    MeetingResultUpdate,
    MeetingResultResponse,
    MeetingResultsResponse,
    MeetingResultReasonCreate,
    MeetingResultReasonUpdate,
    MeetingResultReasonResponse,
    MeetingResultReasonsResponse,
)
from app.services.auth import get_current_timestamp

router = APIRouter()


@router.get("/meeting-results", response_model=MeetingResultsResponse)
def get_active_meeting_results(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    results = (
        db.query(MeetingResult)
        .filter(MeetingResult.is_active == 1)
        .order_by(MeetingResult.name.asc())
        .all()
    )
    return {"results": [MeetingResultResponse.from_orm(result) for result in results]}


@router.get("/meeting-results/all", response_model=MeetingResultsResponse)
def get_all_meeting_results(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    results = db.query(MeetingResult).order_by(MeetingResult.name.asc()).all()
    return {"results": [MeetingResultResponse.from_orm(result) for result in results]}


@router.post("/meeting-results", response_model=MeetingResultResponse, status_code=status.HTTP_201_CREATED)
def create_meeting_result(
    payload: MeetingResultCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Название результата встречи не может быть пустым",
        )

    existing = db.query(MeetingResult).filter(func.lower(MeetingResult.name) == func.lower(name)).first()
    timestamp = get_current_timestamp()

    if existing:
        if existing.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Результат встречи уже существует",
            )
        existing.is_active = 1
        existing.updated_at = timestamp
        existing.updated_by = current_user.id
        db.commit()
        db.refresh(existing)
        return MeetingResultResponse.from_orm(existing)

    result = MeetingResult(
        name=name,
        is_active=1,
        created_at=timestamp,
        updated_at=None,
        updated_by=None,
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return MeetingResultResponse.from_orm(result)


@router.patch("/meeting-results/{result_id}", response_model=MeetingResultResponse)
def update_meeting_result(
    result_id: str,
    payload: MeetingResultUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    result = db.query(MeetingResult).filter(MeetingResult.id == result_id).first()
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Результат встречи не найден",
        )

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Название результата встречи не может быть пустым",
            )
        existing = (
            db.query(MeetingResult)
            .filter(func.lower(MeetingResult.name) == func.lower(name), MeetingResult.id != result.id)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Результат встречи с таким названием уже существует",
            )
        result.name = name

    if payload.is_active is not None:
        result.is_active = 1 if payload.is_active else 0

    result.updated_at = get_current_timestamp()
    result.updated_by = current_user.id

    db.commit()
    db.refresh(result)
    return MeetingResultResponse.from_orm(result)


@router.get("/meeting-results/{result_id}/reasons", response_model=MeetingResultReasonsResponse)
def get_active_meeting_result_reasons(
    result_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reasons = (
        db.query(MeetingResultReason)
        .filter(MeetingResultReason.meeting_result_id == result_id, MeetingResultReason.is_active == 1)
        .order_by(MeetingResultReason.name.asc())
        .all()
    )
    return {"reasons": [MeetingResultReasonResponse.from_orm(reason) for reason in reasons]}


@router.get("/meeting-results/{result_id}/reasons/all", response_model=MeetingResultReasonsResponse)
def get_all_meeting_result_reasons(
    result_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    reasons = (
        db.query(MeetingResultReason)
        .filter(MeetingResultReason.meeting_result_id == result_id)
        .order_by(MeetingResultReason.name.asc())
        .all()
    )
    return {"reasons": [MeetingResultReasonResponse.from_orm(reason) for reason in reasons]}


@router.post("/meeting-results/{result_id}/reasons", response_model=MeetingResultReasonResponse, status_code=status.HTTP_201_CREATED)
def create_meeting_result_reason(
    result_id: str,
    payload: MeetingResultReasonCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    result = db.query(MeetingResult).filter(MeetingResult.id == result_id).first()
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Результат встречи не найден",
        )

    name = payload.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Название причины не может быть пустым",
        )

    existing = (
        db.query(MeetingResultReason)
        .filter(
            MeetingResultReason.meeting_result_id == result_id,
            func.lower(MeetingResultReason.name) == func.lower(name),
        )
        .first()
    )
    timestamp = get_current_timestamp()

    if existing:
        if existing.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Причина для результата уже существует",
            )
        existing.is_active = 1
        existing.updated_at = timestamp
        existing.updated_by = current_user.id
        db.commit()
        db.refresh(existing)
        return MeetingResultReasonResponse.from_orm(existing)

    reason = MeetingResultReason(
        meeting_result_id=result_id,
        name=name,
        is_active=1,
        created_at=timestamp,
        updated_at=None,
        updated_by=None,
    )
    db.add(reason)
    db.commit()
    db.refresh(reason)
    return MeetingResultReasonResponse.from_orm(reason)


@router.patch("/meeting-result-reasons/{reason_id}", response_model=MeetingResultReasonResponse)
def update_meeting_result_reason(
    reason_id: str,
    payload: MeetingResultReasonUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    reason = db.query(MeetingResultReason).filter(MeetingResultReason.id == reason_id).first()
    if not reason:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Причина результата не найдена",
        )

    target_result_id = payload.meeting_result_id or reason.meeting_result_id
    target_result = db.query(MeetingResult).filter(MeetingResult.id == target_result_id).first()
    if not target_result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Результат встречи не найден",
        )

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Название причины не может быть пустым",
            )
        existing = (
            db.query(MeetingResultReason)
            .filter(
                MeetingResultReason.meeting_result_id == target_result_id,
                func.lower(MeetingResultReason.name) == func.lower(name),
                MeetingResultReason.id != reason.id,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Причина с таким названием уже существует",
            )
        reason.name = name

    if payload.meeting_result_id is not None:
        reason.meeting_result_id = payload.meeting_result_id

    if payload.is_active is not None:
        reason.is_active = 1 if payload.is_active else 0

    reason.updated_at = get_current_timestamp()
    reason.updated_by = current_user.id

    db.commit()
    db.refresh(reason)
    return MeetingResultReasonResponse.from_orm(reason)
