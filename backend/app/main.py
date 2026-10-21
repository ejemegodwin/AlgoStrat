
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
from app.models import Job, User
from app.schemas import JobCreate, JobResponse, UserCreate, UserLogin, UserResponse

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
        budget=job_data.budget,
        currency=job_data.currency.upper(),
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    return job


@app.get("/jobs", response_model=list[JobResponse])
def list_jobs(db: Session = Depends(get_db)):
    jobs = (
        db.query(Job)
        .filter(Job.status == "open")
        .order_by(Job.created_at.desc())
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
    db.commit()
    db.refresh(job)

    return job
