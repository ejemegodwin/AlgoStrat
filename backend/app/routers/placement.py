"""Placement checks — skill assessments (Phase 5).

A placement check is tied to a skill. Workers attempt a check to earn a
`verified` tag on that skill (the only way the platform verifies a tag
without a work receipt). Attempts are bounded (initial max 5), with a
7-day cooldown after exhaustion, and variants are served round-robin so
the same variant is never served back-to-back.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, StringConstraints
from sqlalchemy.orm import Session

from app.core.security import get_current_admin_id, get_current_user_id
from app.db_session import get_db
from app.models import (
    PlacementAttempt,
    PlacementCheck,
    PlacementVariant,
    ProfileTag,
    User,
)
from app.schemas import (
    PlacementAttemptResponse,
    PlacementAttemptStart,
    PlacementAttemptSubmit,
    PlacementCheckResponse,
    PlacementVariantResponse,
)

router = APIRouter(tags=["placement"])

MAX_ATTEMPTS = 5
COOLDOWN_DAYS = 7


class PlacementReviewPayload(BaseModel):
    feedback: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=10, max_length=5000),
    ] = None


# --- Public endpoints ---

@router.get("/placement-checks", response_model=list[PlacementCheckResponse])
def list_placement_checks(
    skill: str | None = None,
    db: Session = Depends(get_db),
):
    """List available placement checks. Optionally filter by skill.

    Public — no account needed. Sensitive fields (reviewer_guidance,
    reviewer_notes) are never included in any response.
    """
    query = db.query(PlacementCheck)
    if skill and skill.strip():
        query = query.filter(
            PlacementCheck.skill.ilike(f"%{skill.strip().lower()}%")
        )
    checks = query.order_by(PlacementCheck.skill).all()
    return [_check_to_response(check, db) for check in checks]


@router.get("/placement-checks/{skill}", response_model=PlacementCheckResponse)
def get_placement_check(skill: str, db: Session = Depends(get_db)):
    """Get full details for one placement check by skill name.

    Public — no account needed. Only returns variant prompts and criteria;
    reviewer guidance/notes are never exposed.
    """
    check = (
        db.query(PlacementCheck)
        .filter(PlacementCheck.skill == skill.lower())
        .first()
    )
    if check is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Placement check not found.",
        )
    return _check_to_response(check, db)


# --- Worker endpoints ---

@router.post(
    "/placement-checks/{skill}/attempts",
    response_model=PlacementAttemptResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_placement_attempt(
    skill: str,
    attempt_data: PlacementAttemptStart | None = None,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Start a new placement-check attempt.

    Enforces:
    - Account must be worker or both (cannot take assessments as client-only).
    - Max 5 attempts per check; after that, a 7-day cooldown from the last
      submitted attempt.
    - If no variant_id given, pick one that differs from the worker's most
      recent attempt's variant (never back-to-back same variant).
    - Only one 'started' attempt per user per check (in-progress attempt).
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user.account_type not in ("worker", "both"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only worker accounts can take placement checks.",
        )

    check = (
        db.query(PlacementCheck)
        .filter(PlacementCheck.skill == skill.lower())
        .first()
    )
    if check is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Placement check not found.",
        )

    past_attempts = _past_attempts_for(db, user_id, check.id)

    in_progress = (
        db.query(PlacementAttempt)
        .filter(
            PlacementAttempt.user_id == user_id,
            PlacementAttempt.check_id == check.id,
            PlacementAttempt.status == "started",
        )
        .first()
    )
    if in_progress is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "You already have an in-progress attempt for this check. "
                "Submit or discard it before starting a new one."
            ),
        )

    if len(past_attempts) >= MAX_ATTEMPTS:
        last = past_attempts[0]
        if last.submitted_at is not None:
            submitted = last.submitted_at
            if submitted.tzinfo is None:
                submitted = submitted.replace(tzinfo=timezone.utc)
            elapsed = datetime.now(timezone.utc) - submitted
            if elapsed < timedelta(days=COOLDOWN_DAYS):
                remaining = timedelta(days=COOLDOWN_DAYS) - elapsed
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        f"You have used all {MAX_ATTEMPTS} attempts for this "
                        f"check. You can retry after {COOLDOWN_DAYS} days "
                        f"from your last attempt."
                    ),
                    headers={
                        "Retry-After": str(int(remaining.total_seconds()))
                    },
                )

    last_variant_id = past_attempts[0].variant_id if past_attempts else None

    if attempt_data and attempt_data.variant_id is not None:
        variant = (
            db.query(PlacementVariant)
            .filter(
                PlacementVariant.id == attempt_data.variant_id,
                PlacementVariant.check_id == check.id,
            )
            .first()
        )
        if variant is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="That variant does not belong to this check.",
            )
        if last_variant_id is not None and variant.id == last_variant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please attempt a different variant than your last.",
            )
    else:
        variant = _select_variant(db, check.id, last_variant_id)

    attempt = PlacementAttempt(
        user_id=user_id,
        check_id=check.id,
        variant_id=variant.id,
        status="started",
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    return _attempt_to_response(attempt, check, db)


@router.post(
    "/placement-attempts/{attempt_id}/submit",
    response_model=PlacementAttemptResponse,
)
def submit_placement_attempt(
    attempt_id: int,
    submit_data: PlacementAttemptSubmit,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Submit a started attempt for review."""
    attempt = (
        db.query(PlacementAttempt)
        .filter(PlacementAttempt.id == attempt_id)
        .first()
    )
    if attempt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attempt not found.",
        )

    if attempt.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only submit your own attempts.",
        )

    if attempt.status != "started":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only an in-progress attempt can be submitted.",
        )

    attempt.submission = submit_data.submission
    attempt.submitted_at = datetime.now(timezone.utc)
    attempt.status = "submitted"
    db.commit()
    db.refresh(attempt)

    check = db.get(PlacementCheck, attempt.check_id)
    return _attempt_to_response(attempt, check, db)


@router.get("/placement-attempts/me", response_model=list[PlacementAttemptResponse])
def list_my_placement_attempts(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """The current worker's attempt history, newest first."""
    attempts = (
        db.query(PlacementAttempt)
        .filter(PlacementAttempt.user_id == user_id)
        .order_by(
            PlacementAttempt.created_at.desc(), PlacementAttempt.id.desc()
        )
        .all()
    )
    return [
        _attempt_to_response(attempt, _check_for_attempt(db, attempt.check_id), db)
        for attempt in attempts
    ]


# --- Admin endpoints ---

@router.get(
    "/admin/placement-attempts",
    response_model=list[PlacementAttemptResponse],
)
def list_submitted_attempts(
    status: str | None = None,
    admin_id: int = Depends(get_current_admin_id),
    db: Session = Depends(get_db),
):
    """Admin: list submitted attempts awaiting review (or by status)."""
    allowed_statuses = {"submitted", "passed", "not_yet"}
    if status is not None and status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Use one of: {', '.join(sorted(allowed_statuses))}.",
        )

    query = db.query(PlacementAttempt)
    if status:
        query = query.filter(PlacementAttempt.status == status)
    else:
        query = query.filter(PlacementAttempt.status == "submitted")

    attempts = query.order_by(
        PlacementAttempt.submitted_at.asc(), PlacementAttempt.id.asc()
    ).all()
    return [
        _attempt_to_response(attempt, _check_for_attempt(db, attempt.check_id), db)
        for attempt in attempts
    ]


@router.post(
    "/admin/placement-attempts/{attempt_id}/review/pass",
    response_model=PlacementAttemptResponse,
)
def pass_placement_attempt(
    attempt_id: int,
    payload: PlacementReviewPayload | None = None,
    admin_id: int = Depends(get_current_admin_id),
    db: Session = Depends(get_db),
):
    """Admin: mark an attempt as passed, verifying the skill for the worker."""
    attempt = _load_reviewable_attempt(attempt_id, db)
    attempt.status = "passed"
    attempt.feedback = payload.feedback if payload else None
    attempt.reviewed_by = admin_id
    attempt.reviewed_at = datetime.now(timezone.utc)

    check = db.get(PlacementCheck, attempt.check_id)

    tag = (
        db.query(ProfileTag)
        .filter(
            ProfileTag.user_id == attempt.user_id,
            ProfileTag.kind == "skill",
            ProfileTag.value == check.skill,
        )
        .first()
    )
    if tag is None:
        tag = ProfileTag(
            user_id=attempt.user_id,
            kind="skill",
            value=check.skill,
            verified=True,
        )
        db.add(tag)
    else:
        tag.verified = True

    db.commit()
    db.refresh(attempt)
    return _attempt_to_response(attempt, check, db)


@router.post(
    "/admin/placement-attempts/{attempt_id}/review/not-yet",
    response_model=PlacementAttemptResponse,
)
def not_yet_placement_attempt(
    attempt_id: int,
    payload: PlacementReviewPayload | None = None,
    admin_id: int = Depends(get_current_admin_id),
    db: Session = Depends(get_db),
):
    """Admin: mark an attempt as 'not_yet' with feedback."""
    attempt = _load_reviewable_attempt(attempt_id, db)
    attempt.status = "not_yet"
    attempt.feedback = payload.feedback if payload else None
    if not attempt.feedback:
        attempt.feedback = (
            "Not yet — review the learning resources and try again. "
            "You can retry after a cooldown."
        )
    attempt.reviewed_by = admin_id
    attempt.reviewed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(attempt)
    check = db.get(PlacementCheck, attempt.check_id)
    return _attempt_to_response(attempt, check, db)


# --- Internal helpers ---

def _past_attempts_for(db: Session, user_id: int, check_id: int) -> list[PlacementAttempt]:
    return (
        db.query(PlacementAttempt)
        .filter(
            PlacementAttempt.user_id == user_id,
            PlacementAttempt.check_id == check_id,
            PlacementAttempt.status.in_(("submitted", "passed", "not_yet")),
        )
        .order_by(
            PlacementAttempt.submitted_at.desc(), PlacementAttempt.id.desc()
        )
        .all()
    )


def _select_variant(
    db: Session, check_id: int, last_variant_id: int | None
) -> PlacementVariant | None:
    query = db.query(PlacementVariant).filter(
        PlacementVariant.check_id == check_id
    )
    if last_variant_id is not None:
        query = query.filter(PlacementVariant.id != last_variant_id)
    variant = query.order_by(PlacementVariant.position).first()
    if variant is None and last_variant_id is not None:
        # Only one variant exists; fall back to it (no choice to make).
        variant = (
            db.query(PlacementVariant)
            .filter(PlacementVariant.check_id == check_id)
            .order_by(PlacementVariant.position)
            .first()
        )
    return variant


def _check_for_attempt(db: Session, check_id: int) -> PlacementCheck:
    check = db.get(PlacementCheck, check_id)
    if check is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Placement check not found.",
        )
    return check


def _check_to_response(
    check: PlacementCheck, db: Session
) -> PlacementCheckResponse:
    variants = (
        db.query(PlacementVariant)
        .filter(PlacementVariant.check_id == check.id)
        .order_by(PlacementVariant.position)
        .all()
    )
    return PlacementCheckResponse(
        id=check.id,
        skill=check.skill,
        title=check.title,
        description=check.description,
        learning_resources=check.learning_resources,
        variants=[
            PlacementVariantResponse(
                id=v.id,
                position=v.position,
                prompt=v.prompt,
                criteria=json.loads(v.criteria) if v.criteria else [],
            )
            for v in variants
        ],
    )


def _attempt_to_response(
    attempt: PlacementAttempt,
    check: PlacementCheck,
    db: Session,
) -> PlacementAttemptResponse:
    if check is None:
        check = _check_for_attempt(db, attempt.check_id)
    return PlacementAttemptResponse(
        id=attempt.id,
        check=_check_to_response(check, db),
        variant_id=attempt.variant_id,
        status=attempt.status,
        submission=attempt.submission,
        feedback=attempt.feedback,
        reviewed_at=attempt.reviewed_at,
        submitted_at=attempt.submitted_at,
        created_at=attempt.created_at,
    )


def _load_reviewable_attempt(attempt_id: int, db: Session) -> PlacementAttempt:
    attempt = db.query(PlacementAttempt).filter(
        PlacementAttempt.id == attempt_id
    ).first()
    if attempt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attempt not found.",
        )
    if attempt.status != "submitted":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only submitted attempts can be reviewed.",
        )
    return attempt
