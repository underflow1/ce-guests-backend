import json
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.reason import Reason
from app.models.setting import Setting
from app.models.state_reason_option import StateReasonOption
from app.models.user import User
from app.models.visit_goal import VisitGoal
from app.schemas.reason import ReasonResponse
from app.schemas.reference_data import ReferenceDataResponse
from app.schemas.visit_goal import VisitGoalResponse
from app.services.settings import normalize_pass_integration
from app.services.production_calendar import get_production_calendar_status, is_production_calendar_enabled

router = APIRouter()


@router.get("/reference-data", response_model=ReferenceDataResponse)
def get_reference_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pass_ordering_enabled = False
    production_calendar_enabled = is_production_calendar_enabled(db)
    production_calendar_status = get_production_calendar_status(db, datetime.now().year)
    pass_setting = db.query(Setting).filter(Setting.key == "pass_integration").first()
    if pass_setting and pass_setting.value:
        try:
            pass_payload = normalize_pass_integration(json.loads(pass_setting.value))
            pass_ordering_enabled = bool(pass_payload.get("enabled"))
        except Exception:
            pass_ordering_enabled = False

    visit_goals = (
        db.query(VisitGoal)
        .filter(VisitGoal.is_active == 1)
        .order_by(VisitGoal.name.asc())
        .all()
    )

    active_reasons = (
        db.query(Reason)
        .filter(Reason.is_active == 1)
        .order_by(Reason.name.asc())
        .all()
    )
    active_reason_by_id = {reason.id: reason for reason in active_reasons}

    reasons_by_state_ids: dict[int, list[str]] = defaultdict(list)
    state_reason_rows = (
        db.query(StateReasonOption)
        .order_by(StateReasonOption.state.asc())
        .all()
    )
    for row in state_reason_rows:
        reason = active_reason_by_id.get(row.reason_id)
        if reason is None:
            continue
        reasons_by_state_ids[int(row.state)].append(row.reason_id)

    reasons_by_state: dict[str, list[ReasonResponse]] = {}
    for state, reason_ids in reasons_by_state_ids.items():
        resolved_reasons = [
            active_reason_by_id[rid]
            for rid in reason_ids
            if rid in active_reason_by_id
        ]
        reasons_by_state[str(state)] = [ReasonResponse.from_orm(reason) for reason in resolved_reasons]

    return ReferenceDataResponse(
        visit_goals=[VisitGoalResponse.from_orm(goal) for goal in visit_goals],
        reasons=[ReasonResponse.from_orm(reason) for reason in active_reasons],
        reasons_by_state=reasons_by_state,
        pass_ordering_enabled=pass_ordering_enabled,
        production_calendar_enabled=production_calendar_enabled,
        production_calendar_loaded_for_current_year=bool(
            production_calendar_status.get("is_complete_for_current_year")
        ),
        production_calendar_fallback_active=bool(
            production_calendar_enabled
            and not production_calendar_status.get("is_complete_for_current_year")
        ),
    )
