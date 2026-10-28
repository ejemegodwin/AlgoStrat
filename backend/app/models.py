
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


class LedgerAccount(Base):
    """One account per owner + type + currency (ADR-009). Balances are
    derived from entries, never stored."""

    __tablename__ = "ledger_accounts"

    __table_args__ = (
        UniqueConstraint(
            "owner_type",
            "owner_id",
            "account_type",
            "currency",
            name="uq_ledger_account",
        ),
        CheckConstraint(
            "owner_type IN ('user', 'platform')",
            name="ck_ledger_accounts_owner_type",
        ),
        CheckConstraint(
            "account_type IN ('client_payable', 'worker_receivable', "
            "'platform_revenue', 'platform_cash')",
            name="ck_ledger_accounts_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # NULL owner means the account belongs to the platform itself.
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    account_type: Mapped[str] = mapped_column(String(30), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class LedgerTransaction(Base):
    """A balanced financial fact (ADR-009). Append-only: corrections are
    reversal transactions, never edits."""

    __tablename__ = "ledger_transactions"

    __table_args__ = (
        CheckConstraint(
            "type IN ('accrual', 'settlement', 'reversal', 'adjustment')",
            name="ck_ledger_transactions_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("contracts.id"), nullable=False, index=True
    )
    milestone_id: Mapped[int | None] = mapped_column(
        ForeignKey("milestones.id"), nullable=True
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Retries (API or future provider webhooks) must never double-post.
    idempotency_key: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    entries: Mapped[list["LedgerEntry"]] = relationship(
        back_populates="transaction"
    )


class LedgerEntry(Base):
    """One signed movement into one account. Entries within a
    transaction always sum to zero; the sign encodes direction."""

    __tablename__ = "ledger_entries"

    __table_args__ = (
        CheckConstraint("amount <> 0", name="ck_ledger_entries_amount_nonzero"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("ledger_transactions.id"), nullable=False, index=True
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("ledger_accounts.id"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    transaction: Mapped["LedgerTransaction"] = relationship(
        back_populates="entries"
    )