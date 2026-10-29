
import json
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

    __table_args__ = (
        CheckConstraint(
            "account_type IN ('client', 'worker', 'both')",
            name="ck_users_account_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    # Marketplace side (ADR-018): client posts jobs, worker applies,
    # both do both. No default on purpose — every account picks a side
    # explicitly at registration.
    account_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Platform arbiter for dispute resolution (ADR-011); seeded manually.
    is_admin: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default=text("false")
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
        CheckConstraint(
            "job_type IN ('standard', 'starter_task', 'placement_check')",
            name="ck_jobs_job_type",
        ),
        CheckConstraint(
            "work_mode IN ('remote', 'in_person')",
            name="ck_jobs_work_mode",
        ),
        CheckConstraint(
            "min_worker_level BETWEEN 0 AND 3",
            name="ck_jobs_min_worker_level",
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
    # starter_task = small evaluable task for newcomers; placement_check
    # = category assessment task (Phase 5). Standard is the default.
    job_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="standard"
    )
    work_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="remote"
    )
    deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Gates applications by the worker's computed level (Phase 4);
    # 0 = open to everyone, newcomers included.
    min_worker_level: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    customer: Mapped["User"] = relationship(back_populates="jobs")
    criteria: Mapped[list["JobCriterion"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="JobCriterion.position",
        lazy="selectin",
    )


class JobCriterion(Base):
    """One written acceptance criterion on a job.

    The backbone of the verifiable-work thesis: reviews evaluate the
    submission against these, and the completion receipt snapshots them.
    Editable only while the job is open and has no contract — criteria
    must not silently change after work has started.
    """

    __tablename__ = "job_criteria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    required: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    job: Mapped["Job"] = relationship(back_populates="criteria")


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
    # The worker's proposal: what they'd charge and how long they'd
    # take. None = "as listed in the job".
    proposed_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    proposed_currency: Mapped[str | None] = mapped_column(
        String(3), nullable=True
    )
    estimated_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
            "status IN ('active', 'completed', 'cancelled', 'disputed')",
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
    # Immutable snapshot of the job's acceptance criteria at hire time
    # (JSON list of {position, text, required}). Written once at contract
    # creation; reviews and receipts rely on THIS copy, so a later job
    # edit can never rewrite what the worker agreed to.
    criteria_snapshot: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
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

    submissions: Mapped[list["Submission"]] = relationship(
        back_populates="milestone",
        cascade="all, delete-orphan",
        order_by="Submission.id",
        lazy="selectin",
    )

    @property
    def latest_evidence(self) -> list[str]:
        """Evidence refs from the most recent submission (for responses)."""
        if not self.submissions:
            return []
        return json.loads(self.submissions[-1].evidence)

    contract: Mapped["Contract"] = relationship(back_populates="milestones")


class Submission(Base):
    """One submission of work for a milestone (full revision history).

    The milestone row carries the LATEST state; this table keeps every
    attempt — the evidence reviews, disputes, and receipts point at.
    Evidence is references only (links, repo paths, file names); no file
    uploads yet — controlled storage is a deliberate later decision.
    """

    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    milestone_id: Mapped[int] = mapped_column(
        ForeignKey("milestones.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    note: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON list of evidence reference strings.
    evidence: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    # Filled when the client reviews THIS submission; None = awaiting review.
    review_decision: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    milestone: Mapped["Milestone"] = relationship(back_populates="submissions")


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


class WorkReceipt(Base):
    """Tamper-evident proof of one verified completion (§12.3).

    Issued exactly once per completed contract, inside the completion
    transaction, and never edited: the canonical payload, its SHA-256
    content hash, and the server-side HMAC signature are stored together,
    so any later change to the payload flips verification to 'invalid'.
    Public verification needs nothing private — evidence appears only as
    hashes, the client not at all, and no amounts.
    """

    __tablename__ = "work_receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    receipt_uuid: Mapped[str] = mapped_column(
        String(36), nullable=False, unique=True, index=True
    )
    worker_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    # One receipt per contract — corrections are superseding records,
    # never edits.
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("contracts.id"), nullable=False, unique=True
    )
    # Canonical JSON (sorted keys, tight separators) exactly as hashed.
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    signature: Mapped[str] = mapped_column(String(64), nullable=False)
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
    # NULL for user-level transactions (payout settlements, ADR-012).
    contract_id: Mapped[int | None] = mapped_column(
        ForeignKey("contracts.id"), nullable=True, index=True
    )
    milestone_id: Mapped[int | None] = mapped_column(
        ForeignKey("milestones.id"), nullable=True
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Retries (API or future provider webhooks) must never double-post.
    idempotency_key: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False
    )
    # The provider's own reference for the money movement (ADR-012),
    # for reconciliation; NULL for pre-payments-era transactions.
    provider_reference: Mapped[str | None] = mapped_column(
        String(100), nullable=True
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


class Payout(Base):
    """A worker's withdrawal of settled earnings (ADR-012). The ledger
    settlement is the financial record; this row is the operational
    one (who asked, where to, what the provider called it)."""

    __tablename__ = "payouts"

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payouts_amount_positive"),
        CheckConstraint(
            "status IN ('succeeded', 'failed')", name="ck_payouts_status"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    worker_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="succeeded"
    )
    provider_reference: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class Dispute(Base):
    """A raised disagreement on a contract (ADR-011). While one is open
    the contract is frozen in `disputed` status."""

    __tablename__ = "disputes"

    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'resolved')", name="ck_disputes_status"
        ),
        CheckConstraint(
            "resolution IS NULL OR resolution IN "
            "('worker_favored', 'client_favored', 'dismissed')",
            name="ck_disputes_resolution",
        ),
        # At most one open dispute per contract (ADR-011), enforced by
        # the database even if application logic regresses.
        Index(
            "uq_disputes_one_open_per_contract",
            "contract_id",
            unique=True,
            sqlite_where=text("status = 'open'"),
            postgresql_where=text("status = 'open'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("contracts.id"), nullable=False, index=True
    )
    # SET NULL so the dispute record survives deletion of the milestone.
    milestone_id: Mapped[int | None] = mapped_column(
        ForeignKey("milestones.id", ondelete="SET NULL"), nullable=True
    )
    raised_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="open"
    )
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class WorkerProfile(Base):
    """Work-seeking data for matching (ADR-010), kept off the users row
    because every account can both hire and work."""

    __tablename__ = "worker_profiles"

    __table_args__ = (
        CheckConstraint(
            "availability IN ('available', 'busy', 'unavailable')",
            name="ck_worker_profiles_availability",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), unique=True, nullable=False
    )
    availability: Mapped[str] = mapped_column(
        String(20), nullable=False, default="available"
    )
    min_budget: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    # Presentation fields (§10): optional self-description.
    headline: Mapped[str | None] = mapped_column(String(150), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ProfileTag(Base):
    """A skill or category declared by a worker. Values are trimmed and
    lowercased so matching compares like with like (ADR-010)."""

    __tablename__ = "profile_tags"

    __table_args__ = (
        UniqueConstraint("user_id", "kind", "value", name="uq_profile_tag"),
        CheckConstraint(
            "kind IN ('skill', 'category')", name="ck_profile_tags_kind"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[str] = mapped_column(String(50), nullable=False)
    # True only when the platform verified this tag (placement checks,
    # Phase 5). Workers declare tags; they can never self-verify.
    verified: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

class PlacementCheck(Base):
    """An assessment for one skill (Phase 5). Passing it is the ONLY way
    the platform marks a skill tag as verified without a receipt.

    `reviewer_guidance` and variant `reviewer_notes` are the answer key:
    they are never included in any worker-facing response.
    """

    __tablename__ = "placement_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Shown after a "not yet" outcome: where to improve.
    learning_resources: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    reviewer_guidance: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    variants: Mapped[list["PlacementVariant"]] = relationship(
        back_populates="check",
        cascade="all, delete-orphan",
        order_by="PlacementVariant.position",
        lazy="selectin",
    )


class PlacementVariant(Base):
    """One interchangeable version of a check's task."""

    __tablename__ = "placement_variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    check_id: Mapped[int] = mapped_column(
        ForeignKey("placement_checks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON list of explicit criteria strings shown to the worker.
    criteria: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    check: Mapped["PlacementCheck"] = relationship(back_populates="variants")


class PlacementAttempt(Base):
    """One try at a check. Status flow:
    started -> submitted -> passed | not_yet (reviewed by an admin)."""

    __tablename__ = "placement_attempts"

    __table_args__ = (
        CheckConstraint(
            "status IN ('started', 'submitted', 'passed', 'not_yet')",
            name="ck_placement_attempts_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    check_id: Mapped[int] = mapped_column(
        ForeignKey("placement_checks.id"), nullable=False, index=True
    )
    variant_id: Mapped[int] = mapped_column(
        ForeignKey("placement_variants.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="started"
    )
    submission: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PlacementCheck(Base):
    """An assessment for one skill (Phase 5). Passing it is the ONLY way
    the platform marks a skill tag as verified without a receipt.

    `reviewer_guidance` and variant `reviewer_notes` are the answer key:
    they are never included in any worker-facing response.
    """

    __tablename__ = "placement_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Shown after a "not yet" outcome: where to improve.
    learning_resources: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    reviewer_guidance: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    variants: Mapped[list["PlacementVariant"]] = relationship(
        back_populates="check",
        cascade="all, delete-orphan",
        order_by="PlacementVariant.position",
        lazy="selectin",
    )


class PlacementVariant(Base):
    """One interchangeable version of a check's task."""

    __tablename__ = "placement_variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    check_id: Mapped[int] = mapped_column(
        ForeignKey("placement_checks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON list of explicit criteria strings shown to the worker.
    criteria: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    check: Mapped["PlacementCheck"] = relationship(back_populates="variants")


class PlacementAttempt(Base):
    """One try at a check. Status flow:
    started -> submitted -> passed | not_yet (reviewed by an admin)."""

    __tablename__ = "placement_attempts"

    __table_args__ = (
        CheckConstraint(
            "status IN ('started', 'submitted', 'passed', 'not_yet')",
            name="ck_placement_attempts_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    check_id: Mapped[int] = mapped_column(
        ForeignKey("placement_checks.id"), nullable=False, index=True
    )
    variant_id: Mapped[int] = mapped_column(
        ForeignKey("placement_variants.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="started"
    )
    submission: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PlacementCheck(Base):
    """An assessment for one skill (Phase 5). Passing it is the ONLY way
    the platform marks a skill tag as verified without a receipt.

    `reviewer_guidance` and variant `reviewer_notes` are the answer key:
    they are never included in any worker-facing response.
    """

    __tablename__ = "placement_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Shown after a "not yet" outcome: where to improve.
    learning_resources: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    reviewer_guidance: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    variants: Mapped[list["PlacementVariant"]] = relationship(
        back_populates="check",
        cascade="all, delete-orphan",
        order_by="PlacementVariant.position",
        lazy="selectin",
    )


class PlacementVariant(Base):
    """One interchangeable version of a check's task."""

    __tablename__ = "placement_variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    check_id: Mapped[int] = mapped_column(
        ForeignKey("placement_checks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON list of explicit criteria strings shown to the worker.
    criteria: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    check: Mapped["PlacementCheck"] = relationship(back_populates="variants")


class PlacementAttempt(Base):
    """One try at a check. Status flow:
    started -> submitted -> passed | not_yet (reviewed by an admin)."""

    __tablename__ = "placement_attempts"

    __table_args__ = (
        CheckConstraint(
            "status IN ('started', 'submitted', 'passed', 'not_yet')",
            name="ck_placement_attempts_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    check_id: Mapped[int] = mapped_column(
        ForeignKey("placement_checks.id"), nullable=False, index=True
    )
    variant_id: Mapped[int] = mapped_column(
        ForeignKey("placement_variants.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="started"
    )
    submission: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
