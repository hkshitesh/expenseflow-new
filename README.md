# ExpenseFlow

A small expense submission and approval API. This is a proof of concept, not a production service.

One user journey: submit an expense, have it normalised to a base currency, then approve or reject it.

Money is always stored as integer minor units (paise/cents), never as a float.

## What it does

- **Submit an expense** — `POST /expenses` records a description, amount, currency, category, and submitter, and stores it with status `SUBMITTED`.
- **List / inspect expenses** — filter by status and/or category, or fetch a single expense by id.
- **Approve or reject** — move a `SUBMITTED` expense to `APPROVED` or `REJECTED`. Only `SUBMITTED` expenses can be decided; deciding twice is rejected.
- **Spending insights** — `GET /reports/insights` asks Claude to summarize spending patterns across all stored expenses into three bullet points.

### Current FX behaviour

Every expense is normalised to a base currency of **INR**. Right now the conversion is a placeholder: `amount_base_minor` is a straight 1:1 copy of `amount_minor` and `fx_rate` is always `1`, regardless of the submitted `currency`. There's a `TODO` in `app/routes.py` to call a real FX provider via `httpx` — that call isn't wired up yet, so don't rely on real currency conversion from this PoC.

## Stack

- Python 3.10+, FastAPI, Uvicorn
- SQLAlchemy ORM on SQLite (`expenseflow.db`)
- pydantic v2 for request/response models
- `anthropic` (Claude Messages API) to generate the `/reports/insights` summary
- python-dotenv for loading `.env`
- pytest for tests

## Project layout

```
app/
  main.py     - FastAPI app, lifespan hook that creates tables on startup
  db.py       - engine, session factory, Base, get_db() dependency, init_db()
  models.py   - Expense ORM model
  schemas.py  - ExpenseCreate / ExpenseOut pydantic models
  routes.py   - the five HTTP endpoints
  insights.py - builds the /reports/insights summary via the Anthropic API
ui/
  app.py      - optional Streamlit front-end that calls this API over HTTP
```

## Setup on Windows

These steps use PowerShell. Adjust `python` to `py -3.12` if you have multiple Python versions installed.

1. Clone the repo and open it in a terminal:

   ```powershell
   cd expenseflow-b6
   ```

2. Create and activate a virtual environment:

   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

   If PowerShell blocks the activation script, run this once (in an elevated prompt is not required):

   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
   ```

3. Install dependencies:

   ```powershell
   python -m pip install --upgrade pip
   pip install fastapi uvicorn[standard] sqlalchemy pydantic python-dotenv anthropic httpx pytest
   ```

   > There's no `requirements.txt` in this repo yet. Do not add new third-party dependencies beyond what's above without checking with the project owner first (see `CLAUDE.md`).

## Configure `.env`

The app loads environment variables from a `.env` file in the repo root via `python-dotenv`. Create one with:

```
ANTHROPIC_API_KEY=sk-ant-...
```

- `ANTHROPIC_API_KEY` is required for `GET /reports/insights` to call Claude. If it's missing or the API call fails, that endpoint still returns `200` with a fallback insight string instead of erroring.
- Never commit `.env` — it's already listed in `.gitignore`.

## Run the server

```powershell
python -m uvicorn app.main:app --reload
```

The app creates the SQLite database and the `expenses` table automatically on startup (in `expenseflow.db`) if they don't already exist. By default Uvicorn serves on `http://127.0.0.1:8000`.

## Run the tests

```powershell
python -m pytest -q
```

## Endpoint reference

Base currency is fixed to `INR` for every expense.

### `POST /expenses`

Submit a new expense. Status code `201` on success.

Request body:

| Field | Type | Constraints |
|---|---|---|
| `description` | string | length 1–500 |
| `amount_minor` | integer | must be `> 0` |
| `currency` | string | 3-letter alphabetic code, upper-cased automatically (e.g. `usd` → `USD`) |
| `category` | string | length 1–100 |
| `submitted_by` | string | length 1–200 |

Response (`ExpenseOut`, also returned by every other endpoint below):

| Field | Type | Notes |
|---|---|---|
| `id` | integer | |
| `description` | string | |
| `amount_minor` | integer | as submitted |
| `currency` | string | as submitted |
| `category` | string | |
| `submitted_by` | string | |
| `amount_base_minor` | integer | normalised to `base_currency`; currently mirrors `amount_minor` (see FX note above) |
| `base_currency` | string | always `INR` |
| `fx_rate` | decimal | currently always `1` |
| `status` | string | `SUBMITTED`, `APPROVED`, or `REJECTED` |
| `created_at` | datetime | |
| `updated_at` | datetime | |

Errors: `422` if the request body fails validation.

### `GET /expenses`

List expenses, optionally filtered.

Query parameters (both optional, can be combined):

- `status` — one of `SUBMITTED`, `APPROVED`, `REJECTED`
- `category` — exact match on the stored category string

Returns `200` with a JSON array of `ExpenseOut`. No pagination.

### `GET /expenses/{expense_id}`

Fetch a single expense by id.

- `200` with `ExpenseOut` if found.
- `404` if no expense with that id exists.

### `POST /expenses/{expense_id}/approve`

Approve an expense.

- `200` with the updated `ExpenseOut` (status `APPROVED`).
- `404` if the expense doesn't exist.
- `409` if the expense is not currently `SUBMITTED` (e.g. already approved or rejected).

### `POST /expenses/{expense_id}/reject`

Reject an expense.

- `200` with the updated `ExpenseOut` (status `REJECTED`).
- `404` if the expense doesn't exist.
- `409` if the expense is not currently `SUBMITTED`.

### `GET /reports/insights`

Generate a short spending insight summary across every stored expense (all statuses).

Returns `200` with:

```json
{ "insight": "..." }
```

`insight` is three bullet points generated by Claude from each expense's `amount_base_minor`, `category`, and `status`. If the Anthropic API call fails, `insight` falls back to a fixed unavailability message rather than erroring.
