from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.visit_goal import VisitGoal
from app.models.user import User
from app.api.deps import get_current_user, get_current_active_admin
from app.schemas.visit_goal import (
    VisitGoalCreate,
    VisitGoalUpdate,
    VisitGoalResponse,
    VisitGoalsResponse,
)
from app.services.auth import get_current_timestamp

router = APIRouter()


@router.get("/visit-goals", response_model=VisitGoalsResponse)
def get_active_visit_goals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    goals = (
        db.query(VisitGoal)
        .filter(VisitGoal.is_active == 1)
        .order_by(VisitGoal.name.asc())
        .all()
    )
    return {"goals": [VisitGoalResponse.from_orm(goal) for goal in goals]}


@router.get("/visit-goals/all", response_model=VisitGoalsResponse)
def get_all_visit_goals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    goals = db.query(VisitGoal).order_by(VisitGoal.name.asc()).all()
    return {"goals": [VisitGoalResponse.from_orm(goal) for goal in goals]}


@router.post("/visit-goals", response_model=VisitGoalResponse, status_code=status.HTTP_201_CREATED)
def create_visit_goal(
    payload: VisitGoalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Название цели визита не может быть пустым",
        )

    existing = db.query(VisitGoal).filter(func.lower(VisitGoal.name) == func.lower(name)).first()
    timestamp = get_current_timestamp()

    if existing:
        if existing.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Цель визита уже существует",
            )
        existing.is_active = 1
        existing.updated_at = timestamp
        existing.updated_by = current_user.id
        db.commit()
        db.refresh(existing)
        return VisitGoalResponse.from_orm(existing)

    goal = VisitGoal(
        name=name,
        is_active=1,
        created_at=timestamp,
        updated_at=None,
        updated_by=None,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return VisitGoalResponse.from_orm(goal)


@router.patch("/visit-goals/{goal_id}", response_model=VisitGoalResponse)
def update_visit_goal(
    goal_id: str,
    payload: VisitGoalUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    goal = db.query(VisitGoal).filter(VisitGoal.id == goal_id).first()
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Цель визита не найдена",
        )

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Название цели визита не может быть пустым",
            )
        existing = (
            db.query(VisitGoal)
            .filter(func.lower(VisitGoal.name) == func.lower(name), VisitGoal.id != goal.id)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Цель визита с таким названием уже существует",
            )
        goal.name = name

    if payload.is_active is not None:
        goal.is_active = 1 if payload.is_active else 0

    goal.updated_at = get_current_timestamp()
    goal.updated_by = current_user.id

    db.commit()
    db.refresh(goal)
    return VisitGoalResponse.from_orm(goal)
