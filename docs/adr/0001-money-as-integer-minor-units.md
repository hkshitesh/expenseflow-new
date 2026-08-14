# 1. Money as integer minor units

## Status

Accepted

## Context

ExpenseFlow stores and manipulates monetary amounts: the amount an employee submits (`amount_minor`), and the amount normalised to the base currency (`amount_base_minor`), converted using a stored `fx_rate`. These values are persisted in SQLite (`app/models.py`), validated at the API boundary (`app/schemas.py`), and will be summed/compared/reported on (approvals, insights) as the system grows.

We need a representation that:

- Never silently loses or drifts precision across writes, reads, and arithmetic (submit → convert → approve/reject → report).
- Round-trips exactly through JSON, the DB, and Python without format-specific rounding surprises.
- Is simple to validate (`amount_minor: int = Field(gt=0)`) and simple to reason about across the whole codebase, given this is a small PoC maintained by one team.

## Decision

Store every monetary amount as an **integer in minor units** (paise for INR, cents for USD, etc.) — `amount_minor` and `amount_base_minor` are both `Integer` columns, never `Float`. The one place amounts are not plain integers is the conversion rate itself, `fx_rate`, which is a `Numeric(18,8)` so a fractional rate can still be stored exactly.

This is stated as a project-wide rule in `CLAUDE.md`: "Money is stored as integer minor units (paise / cents), never float."

## Alternatives considered

- **`float`/`double` major-unit amounts** (e.g. `142.50`). Rejected: binary floating-point cannot represent most decimal fractions exactly (`0.1 + 0.2 != 0.3`), so repeated arithmetic (FX conversion, future sums/aggregates) accumulates silent rounding error. This is the failure mode the project rule exists specifically to avoid.
- **`Decimal`/`Numeric` major-unit amounts** (e.g. `Numeric(12,2)` storing `142.50`). Avoids float drift and is arguably more "natural" to read, but reintroduces a rounding *policy* question at every arithmetic step (how many decimal places, when to round) and needs a fixed-point library or careful `Decimal` handling on both the Python side and at the DB/driver boundary. Integer minor units get the same exactness with plain integer arithmetic and no rounding decisions until the one explicit conversion step.
- **Arbitrary-precision string amounts.** Rejected: pushes parsing/validation and arithmetic entirely into application code with no DB-level type safety (no `gt=0` at the column level, no numeric comparison/sort support from SQLite), for no precision benefit over integers here.

## Consequences

- **Positive**: all monetary arithmetic in the codebase is exact integer arithmetic; there is no float-drift class of bug to guard against. `ExpenseCreate.amount_minor: int = Field(gt=0)` (`app/schemas.py`) is a trivial, exact validation. Every amount round-trips exactly through pydantic, SQLAlchemy, and JSON.
- **Positive**: the FX rate is isolated as the single place fractional precision is needed (`Numeric(18,8)`), and per `docs/ARCHITECTURE.md`, `amount_base_minor` is meant to be re-derivable from `amount_minor * fx_rate` given one fixed, documented rounding rule — that rounding is confined to one call site instead of scattered across every read/write of an amount.
- **Negative / cost**: every layer that displays or accepts money must know the currency's minor-unit factor (100 for INR/USD, 0 for JPY, etc.) to convert to/from a human-readable major-unit string; this project does not currently encode that factor anywhere, so any future formatting code (e.g. the Streamlit UI) has to hardcode or hand-wave it.
- **Negative / cost**: `amount_minor` is a plain `Integer`, which is bounded (SQLite affinity aside, application-level overflow isn't validated) — fine for expense-sized amounts, but not future-proofed for arbitrarily large values without revisiting the column type.
- **Note**: this decision covers *storage and arithmetic*, not FX conversion correctness — see `app/routes.py`, where the actual FX lookup is currently a `TODO` and `fx_rate` is hardcoded to `1`. The integer-minor-units decision holds regardless of whether the FX call behind it is real or a placeholder.
