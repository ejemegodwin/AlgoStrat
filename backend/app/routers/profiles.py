from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import get_current_user_id
from app.db_session import get_db
from app.models import ProfileTag, WorkerProfile
from app.schemas import WorkerProfileResponse, WorkerProfileUpsert

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


@router.put("/profiles/me/worker", response_model=WorkerProfileResponse)
def upsert_my_worker_profile(
    profile_data: WorkerProfileUpsert,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
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
