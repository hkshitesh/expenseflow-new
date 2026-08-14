"""API routes for ExpenseFlow."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.insights import generate_insight
from app.models import STATUS_APPROVED, STATUS_REJECTED, STATUS_SUBMITTED, Expense
from app.schemas import ExpenseCreate, ExpenseOut, ExpenseStatus

router = APIRouter()

BASE_CURRENCY = "INR"


@router.post("/expenses", response_model=ExpenseOut, status_code=201)
def create_expense(payload: ExpenseCreate, db: Session = Depends(get_db)) -> Expense:
    """Submit a new expense, normalised to the base currency (INR), with status SUBMITTED."""
    # TODO: call the external FX provider (httpx) to get a real rate for
    # payload.currency -> INR. Until then, amount_base_minor mirrors amount_minor 1:1.
    expense = Expense(
        description=payload.description,
        amount_minor=payload.amount_minor,
        currency=payload.currency,
        category=payload.category,
        submitted_by=payload.submitted_by,
        amount_base_minor=payload.amount_minor,
        base_currency=BASE_CURRENCY,
        fx_rate=Decimal(1),
        status=STATUS_SUBMITTED,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


@router.get("/expenses", response_model=list[ExpenseOut])
def list_expenses(
    status: ExpenseStatus | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
) -> list[Expense]:
    """List expenses, optionally filtered by status and/or category."""
    stmt = select(Expense)
    if status is not None:
        stmt = stmt.where(Expense.status == status)
    if category is not None:
        stmt = stmt.where(Expense.category == category)
    return list(db.scalars(stmt))


@router.get("/expenses/{expense_id}", response_model=ExpenseOut)
def get_expense(expense_id: int, db: Session = Depends(get_db)) -> Expense:
    """Retrieve a single expense by id, or 404 if it does not exist."""
    expense = db.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="Expense not found")
    return expense


@router.post("/expenses/{expense_id}/approve", response_model=ExpenseOut)
def approve_expense(expense_id: int, db: Session = Depends(get_db)) -> Expense:
    """Approve a SUBMITTED expense. 404 if missing, 409 if not currently SUBMITTED."""
    expense = db.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="Expense not found")
    if expense.status != STATUS_SUBMITTED:
        raise HTTPException(
            status_code=409, detail=f"Expense is {expense.status}, not SUBMITTED"
        )
    expense.status = STATUS_APPROVED
    db.commit()
    db.refresh(expense)
    return expense


@router.post("/expenses/{expense_id}/reject", response_model=ExpenseOut)
def reject_expense(expense_id: int, db: Session = Depends(get_db)) -> Expense:
    """Reject a SUBMITTED expense. 404 if missing, 409 if not currently SUBMITTED."""
    expense = db.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="Expense not found")
    if expense.status != STATUS_SUBMITTED:
        raise HTTPException(
            status_code=409, detail=f"Expense is {expense.status}, not SUBMITTED"
        )
    expense.status = STATUS_REJECTED
    db.commit()
    db.refresh(expense)
    return expense


@router.get("/reports/insights")
def get_insights(db: Session = Depends(get_db)) -> dict[str, str]:
    """Generate a short spending insight summary across all expenses."""
    expenses = list(db.scalars(select(Expense)))
    expense_dicts = [
        {
            "amount_base_minor": expense.amount_base_minor,
            "category": expense.category,
            "status": expense.status,
        }
        for expense in expenses
    ]
    return {"insight": generate_insight(expense_dicts)}
