import json
from decimal import Decimal
from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

# Currencies AlgoStrat currently supports for job budgets.
# Deliberately a curated allowlist (not "any 3-letter code") so that
# junk values can never be stored. Extend as new markets are added.
SUPPORTED_CURRENCIES: frozenset[str] = frozenset({
    # Major global currencies
    "USD", "EUR", "GBP", "CAD", "AUD", "NZD", "CHF",
    "JPY", "CNY", "HKD", "SGD", "INR",
    # Middle East
    "AED", "SAR",
    # Africa
    "NGN", "GHS", "KES", "ZAR", "EGP",
    # Latin America
    "BRL", "MXN",
    # Nordics
    "SEK", "NOK", "DKK",
    # Southeast Asia
    "PHP", "IDR",
})


def _normalize_currency(value: str) -> str:
    normalized = value.strip().upper()

    if normalized not in SUPPORTED_CURRENCIES:
        raise ValueError(
            "Currency must be a supported ISO 4217 code (e.g. USD, EUR, NGN)."
        )

    return normalized


def _normalize_email(value: str) -> str:
    # Accounts must be case-insensitive: the same mailbox must never end
    # up as two accounts, and login must work regardless of casing.
    return value.strip().lower()


def _empty_string_to_none(value: str | None) -> str | None:
    # Optional text fields: a whitespace-only value means "absent",
    # so store NULL rather than an empty string.
    if value is None:
        return None
    return value or None


class UserCreate(BaseModel):
    full_name: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=2, max_length=120),
    ]
    email: EmailStr
    # Passwords must never be whitespace-stripped: every character is
    # part of the secret and is hashed exactly as entered.
    password: str = Field(min_length=8, max_length=128)
    # The marketplace side (ADR-018). Required — no silent default,
    # because the default used to grant everything.
    account_type: str = Field(pattern="^(client|worker|both)$")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _normalize_email(value)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: EmailStr
    account_type: str
    # Lets the SPA decide whether to surface the admin UI; the API
    # still enforces admin-only on every admin endpoint.
    is_admin: bool


class UserLogin(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _normalize_email(value)


class JobCriterionInput(BaseModel):
    # strip_whitespace + min_length=1 rejects whitespace-only text.
    text: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
    ]
    required: bool = True


class JobCriterionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    text: str
    required: bool


# Bounds a job's criteria list so payloads stay sane.
CRITERIA_MAX_COUNT = 20


class JobCreate(BaseModel):
    title: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=3, max_length=150),
    ]
    description: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=10),
    ]
    budget: Decimal | None = Field(default=None, gt=0)
    currency: str = Field(default="USD")
    category: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=50),
    ] | None = None
    location: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=120),
    ] | None = None
    # Written acceptance criteria (the verifiable-work thesis). Optional
    # for standard jobs; starter tasks and placement checks MUST have at
    # least one (enforced in the router, which knows the final state).
    criteria: list[JobCriterionInput] = Field(
        default_factory=list, max_length=CRITERIA_MAX_COUNT
    )
    job_type: str = Field(
        default="standard", pattern="^(standard|starter_task|placement_check)$"
    )
    work_mode: str = Field(default="remote", pattern="^(remote|in_person)$")
    deadline: datetime | None = None
    min_worker_level: int = Field(default=0, ge=0, le=3)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return _normalize_currency(value)

    @field_validator("category", "location")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _empty_string_to_none(value)


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    title: str
    description: str
    budget: Decimal | None
    currency: str
    status: str
    category: str | None
    location: str | None
    criteria: list[JobCriterionResponse] = []
    job_type: str
    work_mode: str
    deadline: datetime | None
    min_worker_level: int


class JobUpdate(BaseModel):
    title: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=3, max_length=150),
    ] | None = None
    description: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=10),
    ] | None = None
    budget: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None)
    category: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=50),
    ] | None = None
    location: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=120),
    ] | None = None
    # None = unchanged; a provided list REPLACES all criteria (router
    # rejects the change once a contract exists for the job).
    criteria: list[JobCriterionInput] | None = Field(
        default=None, max_length=CRITERIA_MAX_COUNT
    )
    job_type: str | None = Field(
        default=None, pattern="^(standard|starter_task|placement_check)$"
    )
    work_mode: str | None = Field(
        default=None, pattern="^(remote|in_person)$"
    )
    # Null clears the deadline (same convention as budget).
    deadline: datetime | None = None
    min_worker_level: int | None = Field(default=None, ge=0, le=3)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return _normalize_currency(value)

    @field_validator("category", "location")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _empty_string_to_none(value)


class JobApplicationCreate(BaseModel):
    cover_letter: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=20, max_length=5000
        ),
    ]
    # Optional proposal: price/currency/pace. None = "as the job lists".
    proposed_price: Decimal | None = Field(default=None, gt=0)
    proposed_currency: str | None = None
    estimated_days: int | None = Field(default=None, ge=1, le=365)

    @field_validator("proposed_currency")
    @classmethod
    def normalize_proposed_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_currency(value)


class JobApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    applicant_id: int
    cover_letter: str
    status: str
    proposed_price: Decimal | None
    proposed_currency: str | None
    estimated_days: int | None
    created_at: datetime


class JobApplicationUpdate(BaseModel):
    status: str = Field(pattern="^(accepted|rejected)$")


class CriterionSnapshotItem(BaseModel):
    position: int
    text: str
    required: bool


class ContractResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    application_id: int
    client_id: int
    worker_id: int
    agreed_amount: Decimal | None
    currency: str
    status: str
    # The criteria the worker agreed to, frozen at hire time.
    criteria_snapshot: list[CriterionSnapshotItem] = []
    created_at: datetime
    completed_at: datetime | None

    @field_validator("criteria_snapshot", mode="before")
    @classmethod
    def parse_snapshot(cls, value):
        if isinstance(value, str):
            return json.loads(value)
        return value


class MilestoneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contract_id: int
    title: str
    description: str | None
    amount: Decimal | None
    due_date: datetime | None
    position: int
    status: str
    submission_note: str | None
    submitted_at: datetime | None
    reviewed_at: datetime | None
    # Evidence refs from the latest submission (model property).
    latest_evidence: list[str] = []


class ContractDetailResponse(ContractResponse):
    milestones: list[MilestoneResponse]


class ContractEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contract_id: int
    milestone_id: int | None
    actor_id: int
    event_type: str
    note: str | None
    created_at: datetime


class MilestoneCreate(BaseModel):
    title: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=3, max_length=150),
    ]
    description: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=5000),
    ] | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    due_date: datetime | None = None
    # Explicit position is optional; omitted means "append at the end".
    position: int | None = Field(default=None, ge=1)

    @field_validator("description")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _empty_string_to_none(value)


class MilestoneUpdate(BaseModel):
    # All optional: only the fields actually sent are changed. Sending an
    # explicit null clears nullable fields (amount, due_date, description).
    title: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=3, max_length=150),
    ] | None = None
    description: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=5000),
    ] | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    due_date: datetime | None = None
    position: int | None = Field(default=None, ge=1)

    @field_validator("description")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _empty_string_to_none(value)


class MilestoneSubmit(BaseModel):
    note: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=10, max_length=5000),
    ]
    # Evidence references: links, repo paths, file names. References only
    # — no file uploads yet. Each ref is trimmed; blanks are rejected.
    evidence: list[
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
        ]
    ] = Field(default_factory=list, max_length=10)


class SubmissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    note: str
    evidence: list[str]
    submitted_at: datetime
    review_decision: str | None
    review_note: str | None
    reviewed_at: datetime | None

    @field_validator("evidence", mode="before")
    @classmethod
    def parse_evidence(cls, value):
        # Stored as JSON text; the API serves it as a real list.
        if isinstance(value, str):
            return json.loads(value)
        return value


class ReceiptResponse(BaseModel):
    """Full receipt, visible to the contract parties only."""

    model_config = ConfigDict(from_attributes=True)

    receipt_uuid: str
    contract_id: int
    worker_id: int
    # The canonical payload exactly as hashed (served parsed).
    payload: dict
    content_hash: str
    signature: str
    created_at: datetime

    @field_validator("payload", mode="before")
    @classmethod
    def parse_payload(cls, value):
        if isinstance(value, str):
            return json.loads(value)
        return value


class ReceiptSummary(BaseModel):
    """One line of a worker's receipt history (their own view)."""

    receipt_uuid: str
    contract_id: int
    job_title: str
    # Jobs may have no category; receipts must still summarize.
    job_category: str | None
    completed_at: datetime | None
    created_at: datetime


class VerifyResponse(BaseModel):
    """Public verification: valid / invalid / not_found, with minimal
    fields on success — no client identity, no amounts, no evidence refs."""

    status: str
    worker_name: str | None = None
    job_title: str | None = None
    job_category: str | None = None
    completed_at: datetime | None = None


class MilestoneReview(BaseModel):
    decision: str = Field(pattern="^(approve|request_changes)$")
    note: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=10, max_length=5000),
    ] | None = None
    # Required to approve a PRICED milestone (ADR-012): the client's
    # payment-method token for the charge. A provider token, never
    # card data; a real adapter receives provider-issued tokens.
    payment_token: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=3, max_length=100),
    ] | None = None

    @model_validator(mode="after")
    def note_required_when_requesting_changes(self) -> "MilestoneReview":
        # "Request changes" without an explanation is a dead end for the
        # worker; approval may stay silent.
        if self.decision == "request_changes" and self.note is None:
            raise ValueError("A note is required when requesting changes.")
        return self


class LedgerAccountBalance(BaseModel):
    account_type: str
    currency: str
    balance: Decimal


class LedgerEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    amount: Decimal


class LedgerTransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contract_id: int
    milestone_id: int | None
    type: str
    note: str | None
    created_at: datetime
    entries: list[LedgerEntryResponse]


class WorkerProfileUpsert(BaseModel):
    availability: str = Field(
        default="available", pattern="^(available|busy|unavailable)$"
    )
    min_budget: Decimal | None = Field(default=None, gt=0)
    # Presentation fields: how the worker introduces themselves. All
    # optional — a profile is useful long before it is polished.
    headline: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)
    ] | None = None
    bio: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)
    ] | None = None
    country: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ] | None = None
    timezone: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
    ] | None = None
    skills: list[
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
        ]
    ] = Field(default_factory=list, max_length=10)
    categories: list[
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
        ]
    ] = Field(default_factory=list, max_length=5)

    @field_validator("skills", "categories")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        # Lowercased and deduplicated so matching compares like with
        # like; order of first appearance is preserved.
        normalized: list[str] = []
        for value in values:
            value = value.lower()
            if value not in normalized:
                normalized.append(value)
        return normalized


class WorkerProfileResponse(BaseModel):
    availability: str
    min_budget: Decimal | None
    headline: str | None = None
    bio: str | None = None
    country: str | None = None
    timezone: str | None = None
    # Self-reported by the worker — presented as claims, never as proof.
    skills: list[str]
    categories: list[str]
    # Verified by the platform (placement checks, Phase 5). The API
    # never lets a worker set these; the split is structural so the UI
    # can always show which is which.
    verified_skills: list[str] = []


class LevelRequirement(BaseModel):
    verified_completions: int
    distinct_clients: int


class NextLevelGap(BaseModel):
    """What the next level requires and what is still missing, in plain
    language — a worker should never have to guess how levels work."""

    level: int
    required: LevelRequirement
    missing: list[str]


class WorkerLevelResponse(BaseModel):
    """A worker's level with the recorded inputs it was computed from —
    levels are explainable, never a black box (§14)."""

    level: int
    verified_completions: int
    distinct_clients: int
    next_level: NextLevelGap | None


class RecommendationFactor(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    score: float
    reason: str


class JobRecommendation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job: JobResponse
    score: float
    factors: dict[str, RecommendationFactor]


class RankedApplicant(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    application: JobApplicationResponse
    worker_name: str
    score: float
    factors: dict[str, RecommendationFactor]


class DisputeRaise(BaseModel):
    reason: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=20, max_length=5000),
    ]
    milestone_id: int | None = None


class DisputeResolve(BaseModel):
    resolution: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            pattern="^(worker_favored|client_favored|dismissed)$",
        ),
    ]
    note: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=10, max_length=5000),
    ]


class DisputeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contract_id: int
    milestone_id: int | None
    raised_by: int
    reason: str
    status: str
    resolution: str | None
    resolution_note: str | None
    resolved_by: int | None
    created_at: datetime
    resolved_at: datetime | None


class AdminDisputeResponse(DisputeResponse):
    """The dispute plus everything an admin needs to decide it without
    being a party to the contract (party endpoints stay lean). Admin
    endpoints only — this deliberately crosses the party boundary."""

    job_title: str
    contract_status: str
    agreed_amount: Decimal | None
    currency: str
    milestone_title: str | None
    milestone_status: str | None
    milestone_amount: Decimal | None
    raised_by_name: str
    client_name: str
    worker_name: str


class PayoutCreate(BaseModel):
    currency: str = Field(min_length=3, max_length=3)
    # Absent means "pay out the full settled balance" (ADR-012).
    amount: Decimal | None = Field(
        default=None, gt=0, max_digits=14, decimal_places=2
    )
    destination: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=3, max_length=255),
    ]

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return _normalize_currency(value)


class PayoutResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount: Decimal
    currency: str
    destination: str
    status: str
    provider_reference: str | None
    created_at: datetime
