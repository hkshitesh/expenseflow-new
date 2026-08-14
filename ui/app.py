"""Streamlit front-end for the ExpenseFlow API."""

from __future__ import annotations

import os
from typing import Any

import httpx
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000")

STATUS_LABELS = {
    "SUBMITTED": "Pending",
    "APPROVED": "Approved",
    "REJECTED": "Rejected",
}

STATUS_COLORS = {
    "Pending": "#fff3cd",
    "Approved": "#d4edda",
    "Rejected": "#f8d7da",
}


def _call_api(method: str, path: str, **kwargs: Any) -> Any | None:
    """Call the API and return the parsed JSON body, or None after showing a friendly error."""
    try:
        response = httpx.request(method, f"{API_BASE}{path}", timeout=30, **kwargs)
        response.raise_for_status()
        return response.json()
    except httpx.RequestError:
        st.error(f"Could not connect to the ExpenseFlow API at {API_BASE}. Is it running?")
    except httpx.HTTPStatusError as exc:
        detail = exc.response.json().get("detail", exc.response.text)
        st.error(f"API error ({exc.response.status_code}): {detail}")
    return None


def _format_amount(amount_minor: int, currency: str) -> str:
    """Format integer minor units as a decimal amount with its currency code, for display only."""
    return f"{amount_minor / 100:,.2f} {currency}"


def _format_rupees(amount_minor: int) -> str:
    """Format integer minor units as a rupee amount with two decimals, for display only."""
    return f"₹{amount_minor / 100:,.2f}"


def _style_status(value: str) -> str:
    """Return a background-color style for a Styler cell, based on its status label."""
    color = STATUS_COLORS.get(value)
    return f"background-color: {color}" if color else ""


st.set_page_config(page_title="ExpenseFlow")
st.title("ExpenseFlow")
st.caption("Submit expenses, track their status, and generate spending insights.")

if "submitting" not in st.session_state:
    st.session_state.submitting = False

st.header("Submit an expense")
with st.form("submit_expense"):
    description = st.text_input("Description")
    amount = st.number_input("Amount", min_value=0.01, step=0.01, format="%.2f")
    currency = st.text_input("Currency", value="INR", max_chars=3)
    category = st.text_input("Category")
    submitted_by = st.text_input("Submitted by")
    submit_clicked = st.form_submit_button(
        "Submit expense", disabled=st.session_state.submitting
    )

if submit_clicked:
    st.session_state.submitting = True
    st.rerun()

if st.session_state.submitting:
    payload = {
        "description": description,
        "amount_minor": round(amount * 100),
        "currency": currency,
        "category": category,
        "submitted_by": submitted_by,
    }
    with st.spinner("Submitting expense..."):
        result = _call_api("POST", "/expenses", json=payload)
    st.session_state.submitting = False
    if result is not None:
        st.success("Expense submitted.")
    st.rerun()

st.header("Existing expenses")
st.button("Refresh table")
expenses = _call_api("GET", "/expenses")
if expenses is not None:
    if expenses:
        rows = [
            {
                "ID": expense["id"],
                "Description": expense["description"],
                "Category": expense["category"],
                "Submitted By": expense["submitted_by"],
                "Amount": _format_amount(expense["amount_minor"], expense["currency"]),
                "Amount (INR)": _format_rupees(expense["amount_base_minor"]),
                "Status": STATUS_LABELS.get(expense["status"], expense["status"]),
            }
            for expense in expenses
        ]
        styled = pd.DataFrame(rows).style.map(_style_status, subset=["Status"])
        st.dataframe(styled, width="stretch")
    else:
        st.info("No expenses yet.")

st.header("Approve or reject an expense")
expense_id = st.number_input("Expense ID", min_value=1, step=1, format="%d")
approve_col, reject_col = st.columns(2)
with approve_col:
    if st.button("Approve"):
        updated = _call_api("POST", f"/expenses/{int(expense_id)}/approve")
        if updated is not None:
            st.success(f"Expense {updated['id']} approved.")
with reject_col:
    if st.button("Reject"):
        updated = _call_api("POST", f"/expenses/{int(expense_id)}/reject")
        if updated is not None:
            st.success(f"Expense {updated['id']} rejected.")

st.header("Spending insights")
if st.button("Generate insights"):
    insights = _call_api("GET", "/reports/insights")
    if insights is not None:
        st.markdown(insights["insight"])
