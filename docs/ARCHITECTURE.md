# ExpenseFlow Architecture

PoC scope only. One journey: submit an expense, convert it to INR (base currency), approve or reject it.

## 1. Schema — `expenses` table

| Column | Type | Nullable | Why |
|---|---|---|---|
| `id` | `Integer`, PK, autoincrement | No | Resource identifier, used in `/expenses/{id}` and as the approve/reject target. |
| `description` | `String(500)` | No | Human-readable reason for the expense; needed for a reviewer to make a decision. |
| `amount_minor` | `Integer` | No | Amount as submitted, in minor units, in the submitter's original currency. Kept separate from the base amount so the original submission is never lost. |
| `currency` | `String(3)` | No | ISO 4217 code (upper-cased) of `amount_minor`. |
| `category` | `String(100)` | No | Free-text expense category as submitted, for reviewer context and future reporting. |
| `submitted_by` | `String(200)` | No | Identifier of the person who submitted the expense. |
| `amount_base_minor` | `Integer` | No | Amount normalized to INR, in minor units. Computed once at submit time and frozen (never recomputed) so approve/reject and any future reporting have a stable number to work with. |
| `base_currency` | `String(3)` | No | Denormalized copy of the base currency ("INR") at time of write — records what base was actually used, protecting the audit trail if the base policy ever changes. |
| `fx_rate` | `Numeric(18,8)` | No (use `1` when `currency == base_currency`) | Exact rate used for the conversion, captured at submission. Given `amount_minor` and `fx_rate`, `amount_base_minor` must be re-derivable — this is the audit/reproducibility field. `Numeric`, not `Float`, avoids binary floating-point drift. |
| `status` | `String` with `CheckConstraint`/`Enum`: `SUBMITTED`, `APPROVED`, `REJECTED` | No, default `SUBMITTED` | Three explicit states (not a boolean) because "pending" is distinct from either terminal state, and the approve/reject guard needs a named state to check against. |
| `created_at` | `DateTime` (UTC), server default now | No | When the expense was submitted. |
| `updated_at` | `DateTime` (UTC), updated on every write | No | When the expense was last decided — separated from `created_at` so "submitted at X, decided at Y" doesn't need a history table. |

Deliberately excluded (out of scope for this journey): `approved_by`/`rejected_by`, `rejection_reason`, soft-delete flag, a separate FX-rate-history table.

## 2. Endpoints

| Method | Path | Request body | Response | Notes |
|---|---|---|---|---|
| `POST` | `/expenses` | `description: str`, `amount_minor: int` (> 0), `currency: str` (3-letter ISO code), `category: str`, `submitted_by: str` | `201` → full `Expense` (see below), status `SUBMITTED` | Calls the external FX provider via `httpx` synchronously to populate `amount_base_minor`/`fx_rate`. `422` on bad input; `502`/`503` if the FX call fails — the row is never written without a base amount. |
| `GET` | `/expenses` | — (optional query `status`) | `200` → `list[Expense]` | Lets a reviewer find pending items. No pagination — out of scope. |
| `GET` | `/expenses/{expense_id}` | — | `200` → `Expense`, `404` if missing | Lets a reviewer inspect one expense before deciding. |
| `POST` | `/expenses/{expense_id}/approve` | — | `200` → updated `Expense` | `404` if missing, `409` if not currently `SUBMITTED`. |
| `POST` | `/expenses/{expense_id}/reject` | — | `200` → updated `Expense` | `404` if missing, `409` if not currently `SUBMITTED`. |

`Expense` response shape: `id, description, amount_minor, currency, category, submitted_by, amount_base_minor, base_currency, fx_rate, status, created_at, updated_at`.

Approve/reject are action-style sub-resources (`POST .../approve`, not `PATCH` with a `status` field) so the endpoint shape itself encodes the state machine — a client can never set `status` to an arbitrary value.

## 3. File Layout

- **`app/db.py`** — SQLAlchemy `engine` (`sqlite:///expenseflow.db`), `SessionLocal`, `Base`, the `get_db()` dependency, `init_db()`/`create_all`, and `.env` loading via `python-dotenv` for any FX-provider config (API key/URL).
- **`app/models.py`** — the `Expense` ORM model mapping to the schema in Section 1, including the `status` check constraint.
- **`app/schemas.py`** — pydantic v2 models `ExpenseCreate` (request) and `ExpenseOut` (response), plus a shared `ExpenseStatus` literal/enum. Field validation (currency code format, positive amount) lives here.
- **`app/routes.py`** — the five endpoints from Section 2, each with type hints and a docstring. Houses the FX-call helper (httpx, with timeout and error handling) and the approve/reject state-transition guard.
- **`app/main.py`** — creates the `FastAPI()` app, includes the router, runs `init_db()` on startup. This is what `uvicorn app.main:app --reload` targets.

No files beyond these five — the FX-call helper and env loading stay folded into `routes.py`/`db.py` rather than introducing new modules. Tests live in `tests/` alongside `app/`, using FastAPI's test client with the external FX call mocked.

## 4. Edge Cases

**1. External FX provider down, slow, or returns malformed data.**
The submit endpoint's happy path requires a synchronous `httpx` call before the row can be written, since `amount_base_minor`/`fx_rate` are `NOT NULL`. Use a short explicit timeout, catch `httpx.TimeoutException`/`RequestError`/parse errors, and on any failure write nothing — return `502`/`503` and let the client retry. No expense is ever persisted with a missing or fabricated base amount, and no in-request retry loop is added (that's the client's job).

**2. Rounding/precision converting to integer minor units.**
`amount_minor * fx_rate` almost never lands on a whole paisa. Do the arithmetic in `Decimal` (never `float`, per the money rule), with `fx_rate` stored as `Numeric(18,8)`, and apply one fixed, documented rounding rule (round-half-up to the nearest paisa) at the single call site where conversion happens. Because `fx_rate` is persisted exactly as used, `amount_base_minor` is always reproducible from the stored row.

**3. Invalid state transitions (double approve/reject, reject-after-approve).**
Both `/approve` and `/reject` must check `status == "SUBMITTED"` before writing, returning `409` naming the current status otherwise — never a silent no-op or overwrite. The check-then-write happens within one DB session to avoid a race between concurrent calls on the same row (sufficient for a SQLite PoC; no optimistic-locking column needed). The `status` check constraint also forecloses arbitrary/typo'd status values, since no endpoint accepts a free-form `status` field.

Currency-code validity was considered but ranked below these three — it's a one-time input check (regex/length/fixed list) with no ongoing state-machine or external-dependency risk.
