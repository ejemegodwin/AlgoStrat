import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import (
    WORKER_SIDE,
    get_current_user,
    get_current_user_id,
    require_side,
)
from app.db_session import get_db
from app.models import Contract, ContractEvent, Job, JobApplication, User
from app.schemas import (
    JobApplicationCreate,
    JobApplicationResponse,
    JobApplicationUpdate,
    RankedApplicant,
)
from app.services import matching as matching_service

router = APIRouter(tags=["applications"])


@router.post(
    "/jobs/{job_id}/applications",
    response_model=JobApplicationResponse,
    status_code=status.HTTP_201_CREATED,
)
def apply_for_job(
    job_id: int,
    application_data: JobApplicationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_side(user, WORKER_SIDE, "apply to jobs")
    user_id = user.id
    # Lock the job row so an accept/close cannot commit between the
    # open-status check and the insert of this application.
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

    if job.status != "open":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You can only apply for open jobs.",
        )

    if job.customer_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot apply for your own job.",
        )

    application = JobApplication(
        job_id=job_id,
        applicant_id=user_id,
        cover_letter=application_data.cover_letter,
        proposed_price=application_data.proposed_price,
        proposed_currency=application_data.proposed_currency,
        estimated_days=application_data.estimated_days,
    )

    try:
        db.add(application)
        db.commit()
        db.refresh(application)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already applied for this job.",
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to submit application right now. Please try again later.",
        ) from exc

    return application


@router.get(
    "/applications/me",
    response_model=list[JobApplicationResponse],
)
def list_my_applications(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    applications = (
        db.query(JobApplication)
        .filter(JobApplication.applicant_id == user_id)
        .order_by(
            JobApplication.created_at.desc(),
            JobApplication.id.desc(),
        )
        .all()
    )

    return applications


@router.get(
    "/jobs/{job_id}/applications",
    response_model=list[JobApplicationResponse],
)
def list_job_applications(
    job_id: int,
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
            detail="You can only view applications for your own jobs.",
        )

    applications = (
        db.query(JobApplication)
        .filter(JobApplication.job_id == job_id)
        .order_by(
            JobApplication.created_at.desc(),
            JobApplication.id.desc(),
        )
        .all()
    )

    return applications


@router.get(
    "/jobs/{job_id}/applicants/ranked",
    response_model=list[RankedApplicant],
)
def rank_applicants(
    job_id: int,
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
            detail="You can only view applicants for your own jobs.",
        )

    # The ranked pool is the pending applications — the decision still
    # at hand. Withdrawn and decided applications are already resolved.
    applications = (
        db.query(JobApplication)
        .filter(
            JobApplication.job_id == job_id,
            JobApplication.status == "pending",
        )
        .order_by(
            JobApplication.created_at.desc(),
            JobApplication.id.desc(),
        )
        .all()
    )

    ranked = []
    for application in applications:
        context = matching_service.build_worker_context(
            db, application.applicant_id
        )
        # Same factors, same weights as the worker-facing side
        # (ADR-010 transparency rule).
        total, factors = matching_service.score_job_for_worker(
            job, context, whose="the worker's"
        )
        worker = db.query(User).filter(User.id == application.applicant_id).first()
        ranked.append(
            RankedApplicant(
                application=application,
                worker_name=worker.full_name,
                score=total,
                factors=factors,
            )
        )

    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked


@router.patch(
    "/jobs/{job_id}/applications/{application_id}",
    response_model=JobApplicationResponse,
)
def update_job_application(
    job_id: int,
    application_id: int,
    application_data: JobApplicationUpdate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    # Lock the job row for the whole decision: two concurrent accepts for
    # the same single-hire job are serialized, and the second one sees the
    # job as closed instead of hiring a second applicant.
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
            detail="You can only manage applications for your own jobs.",
        )

    application = (
        db.query(JobApplication)
        .filter(
            JobApplication.id == application_id,
            JobApplication.job_id == job_id,
        )
        .first()
    )

    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found.",
        )

    if application.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pending applications can be updated.",
        )

    if application_data.status == "accepted":
        # Accepting means hiring for a single-hire job: the job must still
        # be open, and accepting atomically closes the job and rejects all
        # other pending applications in the same transaction.
        if job.status != "open":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You can only accept applications for open jobs.",
            )

        application.status = "accepted"
        job.status = "closed"

        db.query(JobApplication).filter(
            JobApplication.job_id == job_id,
            JobApplication.id != application_id,
            JobApplication.status == "pending",
        ).update({"status": "rejected"}, synchronize_session=False)

        # Accepting means hiring (ADR-001), and a hire must always have
        # its contract (ADR-008): create it in the same transaction so a
        # failure rolls the whole hire back together.
        contract = Contract(
            job_id=job.id,
            application_id=application.id,
            client_id=job.customer_id,
            worker_id=application.applicant_id,
            agreed_amount=job.budget,
            currency=job.currency,
            # Freeze the agreed acceptance criteria into the contract:
            # reviews and receipts point at this copy, not the job's.
            criteria_snapshot=json.dumps(
                [
                    {
                        "position": criterion.position,
                        "text": criterion.text,
                        "required": criterion.required,
                    }
                    for criterion in job.criteria
                ]
            ),
        )
        db.add(contract)
        db.flush()  # assign contract.id before writing its first event
        db.add(
            ContractEvent(
                contract_id=contract.id,
                actor_id=user_id,
                event_type="contract_created",
            )
        )
    else:
        application.status = "rejected"

    try:
        db.commit()
        db.refresh(application)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to update application right now. Please try again later.",
        ) from exc

    return application


@router.patch(
    "/applications/{application_id}/withdraw",
    response_model=JobApplicationResponse,
)
def withdraw_application(
    application_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    application = (
        db.query(JobApplication)
        .filter(JobApplication.id == application_id)
        .first()
    )

    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found.",
        )

    if application.applicant_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only withdraw your own applications.",
        )

    if application.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pending applications can be withdrawn.",
        )

    application.status = "withdrawn"

    try:
        db.commit()
        db.refresh(application)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to withdraw application right now. Please try again later.",
        ) from exc

    return application
