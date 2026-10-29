from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import (
    WORKER_SIDE,
    get_current_user,
    get_current_user_id,
    require_side,
)
from app.db_session import get_db
from app.models import ProfileTag, User, WorkerProfile
from app.schemas import (
    WorkerLevelResponse,
    WorkerProfileResponse,
    WorkerProfileUpsert,
)
from app.services import levels as levels_service

router = APIRouter(tags=["profiles"])


def _profile_response(db: Session, user_id: int) -> WorkerProfileResponse:
    profile = db.query(WorkerProfile).filter(WorkerProfile.user_id == user_id).first()
    tags = (
        db.query(ProfileTag)
        .filter(ProfileTag.user_id == user_id)
        .order_by(ProfileTag.id)
        .all()
    )

    return WorkerProfileResponse(
        availability=profile.availability if profile else "available",
        min_budget=profile.min_budget if profile else None,
        skills=[tag.value for tag in tags if tag.kind == "skill"],
        categories=[tag.value for tag in tags if tag.kind == "category"],
    )


@router.get("/profiles/me/worker", response_model=WorkerProfileResponse)
def get_my_worker_profile(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    return _profile_response(db, user_id)


@router.get("/workers/me/level", response_model=WorkerLevelResponse)
def get_my_worker_level(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """The caller's worker level (0-3) with the exact inputs it was
    computed from and what is missing for the next one (§14). Levels
    are derived from signed receipts — never stored, never self-reported."""
    receipts, clients = levels_service.level_inputs(db, user_id)
    level = levels_service.compute_level(receipts, clients)
    return WorkerLevelResponse(
        level=level,
        verified_completions=receipts,
        distinct_clients=clients,
        next_level=levels_service.next_level_gap(level, receipts, clients),
    )


@router.put("/profiles/me/worker", response_model=WorkerProfileResponse)
def upsert_my_worker_profile(
    profile_data: WorkerProfileUpsert,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_side(user, WORKER_SIDE, "maintain a worker profile")
    user_id = user.id
    profile = db.query(WorkerProfile).filter(WorkerProfile.user_id == user_id).first()

    if profile is None:
        profile = WorkerProfile(user_id=user_id)
        db.add(profile)

    profile.availability = profile_data.availability
    profile.min_budget = profile_data.min_budget
    profile.updated_at = datetime.now(timezone.utc)

    # PUT is a full replace: the submitted tag lists become the profile.
    db.query(ProfileTag).filter(ProfileTag.user_id == user_id).delete(
        synchronize_session=False
    )
    for kind, values in (
        ("skill", profile_data.skills),
        ("category", profile_data.categories),
    ):
        for value in values:
            db.add(ProfileTag(user_id=user_id, kind=kind, value=value))

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to save your profile right now. Please try again later.",
        ) from exc

    return _profile_response(db, user_id)
