from decimal import Decimal
from pydantic import BaseModel, ConfigDict, EmailStr, Field

class UserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: EmailStr
    account_type: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class JobCreate(BaseModel):
    title: str = Field(min_length=3, max_length=150)
    description: str = Field(min_length=10)
    budget: Decimal | None = Field(default=None, gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    title: str
    description: str
    budget: Decimal | None
    currency: str
    status: str
