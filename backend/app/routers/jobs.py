from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import get_current_user_id
from app.db_session import get_db
from app.models import Job, JobApplication
from app.schemas import JobCreate, JobRecommendation, JobResponse, JobUpdate
from app.services import matching as matching_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _escape_like(term: str) -> str:
    """Escape LIKE wildcards so user input is matched literally."""
    return (
        term.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


@router.post(
    "",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_job(
    job_data: JobCreate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    job = Job(
        customer_id=user_id,
        title=job_data.title,
        description=job_data.description,
        category=job_data.category,
        location=job_data.location,
        budget=job_data.budget,
        currency=job_data.currency,
    )

    try:
        db.add(job)
        db.commit()
        db.refresh(job)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to create job right now. Please try again later.",
        ) from exc

    return job


@router.get("", response_model=list[JobResponse])
def list_jobs(
    keyword: str | None = None,
    currency: str | None = None,
    category: str | None = None,
    location: str | None = None,
    min_budget: Decimal | None = None,
    max_budget: Decimal | None = None,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Limit must be between 1 and 100.",
        )

    if offset < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Offset cannot be negative.",
        )

    if min_budget is not None and min_budget < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Minimum budget cannot be negative.",
        )

    if max_budget is not None and max_budget < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Maximum budget cannot be negative.",
        )

    if (
        min_budget is not None
        and max_budget is not None
        and min_budget > max_budget
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Minimum budget cannot exceed maximum budget.",
        )

    query = db.query(Job).filter(Job.status == "open")

    if keyword and keyword.strip():
        search_term = f"%{_escape_like(keyword.strip())}%"
        query = query.filter(
            Job.title.ilike(search_term, escape="\\")
            | Job.description.ilike(search_term, escape="\\")
        )

    if currency:
        query = query.filter(Job.currency == currency.strip().upper())

    if category and category.strip():
        query = query.filter(
            Job.category.ilike(
                f"%{_escape_like(category.strip())}%", escape="\\"
            )
        )

    if location and location.strip():
        query = query.filter(
            Job.location.ilike(
                f"%{_escape_like(location.strip())}%", escape="\\"
            )
        )

    if min_budget is not None:
        query = query.filter(Job.budget >= min_budget)

    if max_budget is not None:
        query = query.filter(Job.budget <= max_budget)

    jobs = (
        query
        .order_by(Job.created_at.desc(), Job.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return jobs


# Registered BEFORE /{job_id} so the literal path wins over the
# path-parameter route.
@router.get("/recommended", response_model=list[JobRecommendation])
def recommended_jobs(
    limit: int = 20,
    offset: int = 0,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Limit must be between 1 and 100.",
        )

    if offset < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Offset cannot be negative.",
        )

    context = matching_service.build_worker_context(db, user_id)

    # The worker's own jobs are excluded: they cannot apply to them.
    jobs = (
        db.query(Job)
        .filter(Job.status == "open", Job.customer_id != user_id)
        .order_by(Job.created_at.desc(), Job.id.desc())
        .all()
    )

    recommendations = []
    for job in jobs:
        total, factors = matching_service.score_job_for_worker(
            job, context, whose="your"
        )
        recommendations.append(
            JobRecommendation(job=job, score=total, factors=factors)
        )

    # Python's sort is stable, so equal scores keep the newest-first
    # order the query established.
    recommendations.sort(key=lambda item: item.score, reverse=True)

    return recommendations[offset : offset + limit]


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id).first()

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found.",
        )

    return job


@router.patch("/{job_id}/close", response_model=JobResponse)
def close_job(
    job_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    # Lock the job row so a concurrent accept cannot race the closure.
    job = (
        db.query(Job)
        .filter(Job.id == job_id)
        .with_for_update()
        .first()
    )

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found.",
        )

    if job.customer_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only close your own jobs.",
        )

    job.status = "closed"

    # A closed job must not keep pending applications: they can no longer
    # be accepted, so resolve them as rejected in the same transaction.
    db.query(JobApplication).filter(
        JobApplication.job_id == job_id,
        JobApplication.status == "pending",
    ).update({"status": "rejected"}, synchronize_session=False)

    try:
        db.commit()
        db.refresh(job)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to close job right now. Please try again later.",
        ) from exc

    return job


@router.patch("/{job_id}", response_model=JobResponse)
def update_job(
    job_id: int,
    job_data: JobUpdate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id).first()

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found.",
        )

    if job.customer_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own jobs.",
        )

    if job.status != "open":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You can only edit open jobs.",
        )

    update_data = job_data.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least one field to update.",
        )

    for field, value in update_data.items():
        if value is None and field != "budget":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"{field} cannot be null.",
            )

    for field, value in update_data.items():
        setattr(job, field, value)

    try:
        db.commit()
        db.refresh(job)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to update job right now. Please try again later.",
        ) from exc

    return job
