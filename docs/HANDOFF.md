# ExpenseFlow — Handoff

For a deployment/ops engineer picking this up. See `../README.md` for setup/run instructions and the full endpoint reference; this doc covers what the service does, how it works internally, and what to watch for operationally.

## What it does

ExpenseFlow is a PoC API for one journey: submit an expense, normalise it to a base currency (INR), then approve or reject it. There's also a reporting endpoint that asks Claude to summarize spending patterns.

Five endpoints, all under `app/routes.py`:

- `POST /expenses` — create, status `SUBMITTED`
- `GET /expenses` — list, optional `status`/`category` filters
- `GET /expenses/{id}` — fetch one
- `POST /expenses/{id}/approve` — `SUBMITTED` → `APPROVED`
- `POST /expenses/{id}/reject` — `SUBMITTED` → `REJECTED`
- `GET /reports/insights` — Claude-generated 3-bullet spending summary

## How it works

- **Framework**: FastAPI app (`app/main.py`) with a `lifespan` hook that calls `init_db()` on startup — this creates the `expenses` table if it doesn't exist. There's no separate migration step or tool.
- **Storage**: SQLite, single file `expenseflow.db` in the repo root (`app/db.py`, `DATABASE_URL = "sqlite:///expenseflow.db"`). One process-wide `Engine` and `sessionmaker`; each request gets its own `Session` via the `get_db()` dependency, closed after the request.
- **Data model**: one table, `expenses` (`app/models.py`). Money fields (`amount_minor`, `amount_base_minor`) are integers in minor units; `fx_rate` is a `Numeric(18,8)`. `status` has a DB-level `CheckConstraint` restricting it to `SUBMITTED`/`APPROVED`/`REJECTED` — the API never accepts a free-form status, only the `/approve` and `/reject` actions.
- **Validation**: pydantic v2 models in `app/schemas.py`. Currency codes are upper-cased and length/alpha-checked at request time; there's no ISO-4217 allow-list, so any 3-letter alphabetic string is accepted.
- **FX conversion is a placeholder, not real.** `app/routes.py` hardcodes `amount_base_minor = payload.amount_minor` and `fx_rate = Decimal(1)` — there's a `TODO` to call a real FX provider via `httpx`, but that call is not implemented. Every expense's "base" amount is currently just its original amount, unconverted, no matter what `currency` was submitted. Do not treat `amount_base_minor` as a real INR conversion in its current state.
- **State machine**: `/approve` and `/reject` both check-then-write against `status == "SUBMITTED"` inside one DB session before changing state, returning `409` otherwise. This is a single-process, single-session guard — adequate for the SQLite PoC, not safe against multi-process races (see below).
- **Insights endpoint** (`app/insights.py`) pulls every expense's `amount_base_minor`/`category`/`status` into a text summary and sends it to the Anthropic Messages API (model `claude-sonnet-4-6`, capped at 300 output tokens). On `anthropic.APIError`/`APIConnectionError` it logs and returns a fixed fallback string instead of propagating an error — so this endpoint always returns `200`, even when the model call fails.
- **Optional UI**: `ui/app.py` is a separate Streamlit front-end that calls this API over HTTP (`API_BASE` env var, default `http://127.0.0.1:8000`). It's not started by anything in `app/` and has its own process/dependencies.

## What a deployment engineer needs to know

- **Config**: the only environment variable read is `ANTHROPIC_API_KEY`, loaded from `.env` via `python-dotenv` (loaded in both `app/db.py` and `app/insights.py`). Nothing else is configurable via env — the DB path and base currency (`INR`) are hardcoded constants in `app/db.py` / `app/routes.py`.
- **No `requirements.txt`/`pyproject.toml` exists yet.** Dependencies currently live only as imports; see `README.md` for the explicit `pip install` list. If you're containerizing this, you'll want to pin and freeze these first — check with the project owner before adding a dependency file, per `CLAUDE.md`.
- **Persistence is a single SQLite file** (`expenseflow.db`) with no backup/rotation and no migration tooling (schema changes rely on `create_all`, which only adds missing tables — it will not alter existing ones). Moving to Postgres or adding a migration tool (e.g. Alembic) would both be pre-production requirements, not something currently in place.
- **Concurrency**: SQLite + `check_same_thread=False` lets multiple threads share the engine, but there's no row-level locking beyond SQLite's own file locking, and the approve/reject guard is only safe within one process's session-then-commit. Don't run multiple app processes against the same `expenseflow.db` file expecting strict double-approve protection.
- **Secrets**: only `ANTHROPIC_API_KEY` needs to be provisioned as a secret. `.env` is gitignored; don't put real keys anywhere else (no other secret-bearing config exists).
- **External dependency at request time**: `GET /reports/insights` makes a live call to the Anthropic API on every request — there's no caching. Expect that endpoint's latency and availability to track Anthropic's API, not the local DB. It degrades gracefully (fallback string) rather than failing the request.
- **No auth**: there is no authentication/authorization on any endpoint. Anyone who can reach the service can submit, list, approve, or reject any expense. This is explicitly a PoC — do not expose it outside a trusted network without adding auth first.
- **No tests currently checked in** despite `python -m pytest -q` being the documented test command in `CLAUDE.md` — there's no `tests/` directory in the repo yet.
