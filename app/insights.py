"""Spending insight generation via the Anthropic Messages API."""

from __future__ import annotations

import logging

import anthropic
from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 300
_FALLBACK_INSIGHT = "Insights are temporarily unavailable. Please try again later."


def _build_summary(expenses: list[dict]) -> str:
    """Render expenses as a compact text summary for the model prompt."""
    lines = [
        f"- {expense['amount_base_minor']} minor units, "
        f"category={expense['category']}, status={expense['status']}"
        for expense in expenses
    ]
    return "\n".join(lines)


def generate_insight(expenses: list[dict]) -> str:
    """Summarize spending patterns into three short bullet insights.

    Args:
        expenses: Each dict must have amount_base_minor, category, and status.

    Returns:
        A short bullet-point summary of spending insights, or a safe
        fallback string if the Anthropic API call fails.
    """
    summary = _build_summary(expenses)
    prompt = (
        "Here is a list of expenses (amounts in minor units of the base "
        f"currency):\n\n{summary}\n\n"
        "Give exactly three short bullet insights about this spending."
    )

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return next(
            (block.text for block in response.content if block.type == "text"),
            _FALLBACK_INSIGHT,
        )
    except (anthropic.APIError, anthropic.APIConnectionError) as exc:
        logger.error("Anthropic API call failed: %s", exc)
        return _FALLBACK_INSIGHT
