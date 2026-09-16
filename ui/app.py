"""Streamlit front-end for the ExpenseFlow API."""

from __future__ import annotations

import os
import re
from typing import Any

import httpx
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000")

_BULLET_RE = re.compile(r"^[-*•]\s+|^\d+[.)]\s+")

_STATUS_COLORS = {
    "SUBMITTED": "#fff3cd",
    "APPROVED": "#d4edda",
    "REJECTED": "#f8d7da",
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
        try:
            detail = exc.response.json().get("detail", exc.response.text)
        except ValueError:
            detail = exc.response.text
        st.error(f"API error ({exc.response.status_code}): {detail}")
    return None


def _parse_insight(text: str) -> tuple[str, list[str]]:
    """Split an insight response into its summary text and bullet points."""
    summary_lines: list[str] = []
    bullets: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _BULLET_RE.match(line)
        if match:
            bullets.append(line[match.end() :].strip())
        else:
            summary_lines.append(line)
    return " ".join(summary_lines), bullets


def _style_status(value: str) -> str:
    """Return a background-color style for a Styler cell, based on its status."""
    color = _STATUS_COLORS.get(value)
    return f"background-color: {color}" if color else ""


st.set_page_config(page_title="ExpenseFlow")
st.title("ExpenseFlow")
st.caption("Submit expenses, review them, and generate spending insights.")

st.header("Submit an expense")
with st.form("submit_expense"):
    description = st.text_input("Description")
    amount = st.number_input("Amount", min_value=0.01, step=0.01, format="%.2f")
    currency = st.text_input("Currency", value="INR", max_chars=3)
    category = st.text_input("Category")
    submitted_by = st.text_input("Submitted by")
    submit_clicked = st.form_submit_button("Submit expense")

if submit_clicked:
    payload = {
        "description": description,
        "amount_minor": round(amount * 100),
        "currency": currency,
        "category": category,
        "submitted_by": submitted_by,
    }
    result = _call_api("POST", "/expenses", json=payload)
    if result is not None:
        st.success("Expense submitted.")

st.header("Existing expenses")
expenses = _call_api("GET", "/expenses")
if expenses is not None:
    if expenses:
        rows = [
            {
                "ID": expense["id"],
                "Description": expense["description"],
                "Category": expense["category"],
                "Submitted By": expense["submitted_by"],
                "Amount": f"{expense['amount_minor'] / 100:,.2f} {expense['currency']}",
                "Amount (Base)": f"{expense['amount_base_minor'] / 100:,.2f} {expense['base_currency']}",
                "Status": expense["status"],
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
        summary, bullets = _parse_insight(insights["insight"])
        if summary:
            st.write(summary)
        for bullet in bullets:
            st.markdown(f"- {bullet}")
