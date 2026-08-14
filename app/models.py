"""SQLAlchemy ORM models for ExpenseFlow."""

from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db import Base

STATUS_SUBMITTED = "SUBMITTED"
STATUS_APPROVED = "APPROVED"
STATUS_REJECTED = "REJECTED"
VALID_STATUSES = (STATUS_SUBMITTED, STATUS_APPROVED, STATUS_REJECTED)

_status_check = "status IN ({values})".format(
    values=", ".join(f"'{status}'" for status in VALID_STATUSES)
)


class Expense(Base):
    """An expense submitted for approval, normalised to INR (base currency) on write."""

    __tablename__ = "expenses"
    __table_args__ = (CheckConstraint(_status_check, name="ck_expenses_status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    submitted_by: Mapped[str] = mapped_column(String(200), nullable=False)
    amount_base_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default=STATUS_SUBMITTED
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
