
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    account_type: Mapped[str] = mapped_column(
        String(20), default="individual", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    jobs: Mapped[list["Job"]] = relationship(back_populates="customer")


class Job(Base):
    __tablename__ = "jobs"

    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'closed')",
            name="ck_jobs_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    budget: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="open"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    customer: Mapped["User"] = relationship(back_populates="jobs")


class JobApplication(Base):
    __tablename__ = "job_applications"

    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "applicant_id",
            name="uq_job_application_applicant",
        ),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'withdrawn')",
            name="ck_job_applications_status",
        ),
        # Single-hire invariant: at most one accepted application per job,
        # enforced by the database even if application logic regresses.
        Index(
            "uq_job_applications_one_accepted_per_job",
            "job_id",
            unique=True,
            sqlite_where=text("status = 'accepted'"),
            postgresql_where=text("status = 'accepted'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id"), nullable=False, index=True
    )
    applicant_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    cover_letter: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class Contract(Base):
    """The receipt of a hire: created atomically when an application is
    accepted (ADR-008). Snapshots parties and terms at hire time."""

    __tablename__ = "contracts"

    __table_args__ = (
        UniqueConstraint("job_id", name="uq_contracts_job"),
        UniqueConstraint("application_id", name="uq_contracts_application"),
        CheckConstraint(
            "status IN ('active', 'completed', 'cancelled')",
            name="ck_contracts_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), nullable=False)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("job_applications.id"), nullable=False
    )
    client_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    worker_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    agreed_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    milestones: Mapped[list["Milestone"]] = relationship(
        back_populates="contract",
        order_by=lambda: (Milestone.position, Milestone.id),
    )


class Milestone(Base):
    __tablename__ = "milestones"

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'submitted', 'changes_requested', "
            "'approved', 'cancelled')",
            name="ck_milestones_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("contracts.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    # Latest submission only, denormalized for cheap reads; the full
    # history (including earlier submissions) lives in contract_events.
    submission_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    contract: Mapped["Contract"] = relationship(back_populates="milestones")


class ContractEvent(Base):
    """Append-only audit log for a contract (ADR-008). Never updated or
    deleted through the API; this is the evidence trail that verifiable
    work history will be built on."""

    __tablename__ = "contract_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("contracts.id"), nullable=False, index=True
    )
    # SET NULL so the audit trail survives deletion of a pending milestone.
    milestone_id: Mapped[int | None] = mapped_column(
        ForeignKey("milestones.id", ondelete="SET NULL"), nullable=True
    )
    actor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )