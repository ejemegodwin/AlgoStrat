from decimal import Decimal
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

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


class UserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
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
    title: str = Field(min_length=3, max_length=150)
    description: str = Field(min_length=10)
    budget: Decimal | None = Field(default=None, gt=0)
    currency: str = Field(default="USD")
    category: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=120)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return _normalize_currency(value)


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
    title: str | None = Field(default=None, min_length=3, max_length=150)
    description: str | None = Field(default=None, min_length=10)
    budget: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None)
    category: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=120)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return _normalize_currency(value)


class JobApplicationCreate(BaseModel):
    cover_letter: str = Field(min_length=20, max_length=5000)


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
