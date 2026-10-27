
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, Job, JobApplication, User


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine)

    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def create_user(db_session, email):
    user = User(
        full_name="Test User",
        email=email,
        password_hash="test-hash",
    )
    db_session.add(user)
    db_session.flush()
    return user


def test_job_rejects_invalid_status(db_session):
    user = create_user(db_session, "job-owner@example.com")

    job = Job(
        customer_id=user.id,
        title="Test job",
        description="A test job description",
        currency="USD",
        status="invalid",
    )
    db_session.add(job)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_application_rejects_invalid_status(db_session):
    owner = create_user(db_session, "owner@example.com")
    applicant = create_user(db_session, "applicant@example.com")

    job = Job(
        customer_id=owner.id,
        title="Test job",
        description="A test job description",
        currency="USD",
        status="open",
    )
    db_session.add(job)
    db_session.flush()

    application = JobApplication(
        job_id=job.id,
        applicant_id=applicant.id,
        cover_letter="I am interested in this job.",
        status="invalid",
    )
    db_session.add(application)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_job_cannot_have_two_accepted_applications(db_session):
    owner = create_user(db_session, "single-hire-owner@example.com")
    first = create_user(db_session, "single-hire-first@example.com")
    second = create_user(db_session, "single-hire-second@example.com")

    job = Job(
        customer_id=owner.id,
        title="Test job",
        description="A test job description",
        currency="USD",
        status="open",
    )
    db_session.add(job)
    db_session.flush()

    db_session.add_all([
        JobApplication(
            job_id=job.id,
            applicant_id=first.id,
            cover_letter="I am interested in this job.",
            status="accepted",
        ),
        JobApplication(
            job_id=job.id,
            applicant_id=second.id,
            cover_letter="I am also interested in this job.",
            status="accepted",
        ),
    ])

    with pytest.raises(IntegrityError):
        db_session.commit()
