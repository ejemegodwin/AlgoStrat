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


class UserLogin(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _normalize_email(value)


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


class JobApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    applicant_id: int
    cover_letter: str
    status: str
    created_at: datetime


class JobApplicationUpdate(BaseModel):
    status: str = Field(pattern="^(accepted|rejected)$")


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
    created_at: datetime
    completed_at: datetime | None


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


class MilestoneReview(BaseModel):
    decision: str = Field(pattern="^(approve|request_changes)$")
    note: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=10, max_length=5000),
    ] | None = None

    @model_validator(mode="after")
    def note_required_when_requesting_changes(self) -> "MilestoneReview":
        # "Request changes" without an explanation is a dead end for the
        # worker; approval may stay silent.
        if self.decision == "request_changes" and self.note is None:
            raise ValueError("A note is required when requesting changes.")
        return self
