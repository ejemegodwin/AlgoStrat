from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    get_current_user_id,
    hash_password,
    verify_password,
)
from app.database import check_database_connection
from app.db_session import get_db
from app.models import Job, JobApplication, User
from app.schemas import (
    JobApplicationCreate,
    JobApplicationResponse,
    JobCreate,
    JobResponse,
    JobUpdate,
    UserCreate,
    UserLogin,
    UserResponse,
)

app = FastAPI(title="AlgoStrat API")


@app.get("/")
def home():
    return {
        "message": "Welcome to AlgoStrat!",
        "status": "running",
    }


@app.get("/health/database")

def database_health():
    try:
        result = check_database_connection()

        return {
            "database": "connected",
            "test_query": result,
        }
    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Database connection failed.",
        )
    
@app.post(
    "/auth/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)

def register_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
):
    existing_user = (
        db.query(User)
        .filter(User.email == str(user_data.email))
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        full_name=user_data.full_name,
        email=str(user_data.email),
        password_hash=hash_password(user_data.password),
    )

    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    return user

@app.post("/auth/login")
def login_user(
    login_data: UserLogin,
    db: Session = Depends(get_db),
):
    user = (
        db.query(User)
        .filter(User.email == str(login_data.email))
        .first()
    )

    if user is None or not verify_password(
        login_data.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(user.id)

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }

@app.get("/auth/me", response_model=UserResponse)
def get_my_profile(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists.",
        )

    return user


@app.post(
    "/jobs",
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
        currency=job_data.currency.upper(),
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


@app.get("/jobs", response_model=list[JobResponse])
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
        search_term = f"%{keyword.strip()}%"
        query = query.filter(
            Job.title.ilike(search_term)
            | Job.description.ilike(search_term)
        )

    if currency:
        query = query.filter(Job.currency == currency.strip().upper())

    if category and category.strip():
        query = query.filter(
            Job.category.ilike(f"%{category.strip()}%")
        )

    if location and location.strip():
        query = query.filter(
            Job.location.ilike(f"%{location.strip()}%")
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


@app.get("/jobs/{job_id}", response_model=JobResponse)
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


@app.patch("/jobs/{job_id}/close", response_model=JobResponse)
def close_job(
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
            detail="You can only close your own jobs.",
        )

    job.status = "closed"

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


@app.patch("/jobs/{job_id}", response_model=JobResponse)
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



@app.post(
    "/jobs/{job_id}/applications",
    response_model=JobApplicationResponse,
    status_code=status.HTTP_201_CREATED,
)
def apply_for_job(
    job_id: int,
    application_data: JobApplicationCreate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id).first()

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


@app.get(
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
