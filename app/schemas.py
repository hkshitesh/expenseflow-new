"""Pydantic v2 request/response models for ExpenseFlow."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ExpenseStatus = Literal["SUBMITTED", "APPROVED", "REJECTED"]


class ExpenseCreate(BaseModel):
    """Request body for submitting a new expense."""

    description: str = Field(min_length=1, max_length=500)
    amount_minor: int = Field(gt=0)
    currency: str
    category: str = Field(min_length=1, max_length=100)
    submitted_by: str = Field(min_length=1, max_length=200)

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, value: str) -> str:
        """Uppercase and enforce a 3-letter ISO 4217-style currency code."""
        value = value.upper()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("currency must be a 3-letter ISO code")
        return value


class ExpenseOut(BaseModel):
    """Response body representing a stored expense."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    description: str
    amount_minor: int
    currency: str
    category: str
    submitted_by: str
    amount_base_minor: int
    base_currency: str
    fx_rate: Decimal
    status: ExpenseStatus
    created_at: datetime.datetime
    updated_at: datetime.datetime
