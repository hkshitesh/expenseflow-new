# ExpenseFlow — Production Gap Audit

Audited against the actual code in `app/` (and `ui/app.py`) as of this writing — see `docs/HANDOFF.md` for the operational overview this audit assumes. `CLAUDE.md` states this is explicitly a PoC; this document exists to make that status concrete before anyone proposes moving it toward production.

Effort estimates are rough, single-engineer, and assume no other gap here is fixed first (some overlap — e.g. observability work touches error handling).

## 1. Authentication and key rotation

**Gap**: There is no authentication or authorization anywhere. Every endpoint in `app/routes.py` — submit, list, get, approve, reject, insights — is open to anyone who can reach the process, with no notion of identity beyond the free-text `submitted_by` string the client itself supplies (unverified, not tied to any account). There's also no key-rotation story for the one secret that exists, `ANTHROPIC_API_KEY` — it's a static value in `.env` with no rotation mechanism, expiry, or scoping.

**Blocking.**

**Effort**: 3–5 days for a minimal scheme (e.g. API-key or JWT bearer auth on every route, `submitted_by` derived from the authenticated identity instead of client input, plus an approver/submitter role distinction so approve/reject isn't open to submitters). Add ~1 day for key-rotation process/documentation if using a secrets manager (see §7).

## 2. Input validation

**Gap**: Field-level validation exists and is reasonable for what it covers (`app/schemas.py`: length bounds on strings, `amount_minor > 0`, currency upper-cased and checked for 3 alphabetic characters). But it stops short of production-grade: `currency` accepts any 3-letter alphabetic string with no ISO-4217 allow-list (`"ZZZ"` passes), `category` is unconstrained free text with no allow-list or normalization (so reporting/insights will fragment across near-duplicate categories), and there's no upper bound on `amount_minor` (a client can submit an absurdly large integer). Query params on `GET /expenses` (`status`, `category`) aren't sanitized beyond pydantic's own type coercion, which is fine today but there's no length cap on `category` as a query param either.

**Deferrable** — current validation is not unsafe (no injection risk; SQLAlchemy's `select().where()` is parameterized), just permissive enough to let bad/garbage data accumulate.

**Effort**: 1–2 days to add a currency allow-list, a category allow-list or normalization step, and an upper bound on amounts.

## 3. Rate limiting

**Gap**: None exists. No middleware, no per-IP/per-key throttling, on any endpoint. `GET /reports/insights` is the sharpest edge here: it makes a live, uncached call to the Anthropic API on every single request with no cost or concurrency ceiling — a handful of clients hammering that endpoint directly translates to Anthropic API spend and latency, with no circuit breaker beyond the try/except that catches API errors.

**Blocking** for the insights endpoint specifically (unbounded external-API cost exposure); **deferrable** for the CRUD endpoints (SQLite-local, cheap) if there's a trusted-network assumption in the interim.

**Effort**: 1–2 days for basic rate limiting (e.g. `slowapi` or a reverse-proxy-level limiter) across all routes, tighter limits on `/reports/insights`. Add response caching on insights (even a short TTL) as a cheaper complementary fix, +0.5 day.

## 4. Observability and logging

**Gap**: Logging is almost entirely absent. There's exactly one `logger.error(...)` call, in `app/insights.py`, for Anthropic API failures — no logging on request handling, no structured logs, no request IDs, no access logs beyond whatever Uvicorn prints by default, and `logging.basicConfig` is never called, so log level/format/destination are unconfigured. There are no metrics (request counts, latency, error rates), no tracing, and no health/readiness endpoint for a load balancer or orchestrator to probe (see §9).

**Blocking** — without this, diagnosing a production incident means reading Uvicorn's default stdout output and guessing.

**Effort**: 2–4 days for structured logging (request/response middleware logging method, path, status, latency, request id), basic metrics (even Prometheus-style counters via a middleware), and wiring log level from config/env instead of defaults.

## 5. Error handling

**Gap**: The three explicit error paths (`404` on missing expense, `409` on invalid state transition, `422` on pydantic validation) are correctly modeled and use FastAPI's `HTTPException` properly. But there's no handling for the failure modes that matter most in production: a DB connection error or constraint violation on write isn't caught anywhere and will surface as an unhandled `500` with a raw traceback (FastAPI's default), and there's no global exception handler to turn that into a safe, consistent error body. The FX-provider `TODO` in `app/routes.py` means the one place the spec calls for explicit `502`/`503` handling (`docs/ARCHITECTURE.md` §4.1) doesn't exist yet because the call it would guard isn't implemented either.

**Blocking** — an unhandled exception currently means an unstructured 500 and (depending on debug settings) a leaked traceback to the client.

**Effort**: 1–2 days for a global exception handler + consistent error envelope, plus explicit handling once the real FX call lands (bundled with that work, not separately estimated here).

## 6. Database migrations and pooling

**Gap**: Schema management is `Base.metadata.create_all(bind=engine)` on startup (`app/db.py`) — this creates missing tables but never alters existing ones, so there is no way to evolve the schema (add a column, change a constraint) without manual intervention or downtime. No Alembic (or equivalent) is present. Connection pooling is whatever SQLAlchemy's default `create_engine` gives a SQLite URL — no pool size, timeout, or overflow configuration, and SQLite itself has no real concurrent-writer story (`check_same_thread=False` disables the sanity check, but doesn't add real concurrency). The whole persistence layer is one file, `expenseflow.db`, with no backup/replication.

**Blocking** for any real deployment: no migration path means the first schema change after go-live is already a manual, risky operation, and SQLite is a single point of failure with no backup.

**Effort**: 3–5 days — introduce Alembic and an initial baseline migration (1–2 days), migrate to a server-based DB (Postgres) with real pool configuration (2–3 days, bundled with a backup/restore story).

## 7. Secrets management

**Gap**: The only secret, `ANTHROPIC_API_KEY`, is read from a `.env` file via `python-dotenv` (`app/db.py`, `app/insights.py`). `.env` is correctly gitignored, but there's no secrets-manager integration (Vault, AWS Secrets Manager, etc.), no encryption at rest for the file itself, and no rotation mechanism (§1). This is a reasonable pattern for local dev, not for a deployed service where `.env` files on disk are themselves a liability.

**Blocking** for any multi-environment or team-shared deployment.

**Effort**: 1–2 days to move secret loading to the target platform's secrets manager (env-injection from a vault/secrets-manager at deploy time), keeping `.env` only for local dev.

## 8. Tests and coverage

**Gap**: There are zero tests in the repository. `CLAUDE.md` documents `python -m pytest -q` as the test command and `docs/ARCHITECTURE.md` describes an intended `tests/` directory using FastAPI's test client with the FX call mocked, but no such directory exists yet. Coverage is 0% by definition — none of the state-machine guards (`409` on double-approve), validation rules, or the insights fallback path are verified by anything beyond manual testing.

**Blocking** — shipping any change with zero regression coverage on a state machine (approve/reject) that guards against double-writes is a direct risk.

**Effort**: 3–5 days for a first real suite: FastAPI `TestClient` + a test DB (SQLite in-memory or a temp file), covering the five endpoints' happy paths, the `404`/`409`/`422` error paths, and the insights fallback with the Anthropic call mocked. Ongoing effort to keep coverage current on top of that.

## 9. Deployment and health checks

**Gap**: There is no deployment artifact at all — no `Dockerfile`, no CI config (no `.github/workflows` or equivalent), no `requirements.txt`/`pyproject.toml` to pin what gets installed (see `README.md`). There's no health or readiness endpoint (`/healthz`-style), so a load balancer or orchestrator has nothing to probe beyond hitting a real data endpoint. The app is currently started with `uvicorn --reload`, which is a dev-mode flag (auto-reload, single process) with no process manager, no graceful shutdown handling beyond what Uvicorn/FastAPI's `lifespan` gives for free, and no worker count configured for concurrency.

**Blocking** — there is currently no way to deploy this anywhere except "run the dev command on a box."

**Effort**: 3–5 days — dependency lockfile (0.5 day), Dockerfile + non-`--reload` Uvicorn/Gunicorn config (1 day), a `/healthz` endpoint that checks DB connectivity (0.5 day), and a basic CI pipeline running lint/tests on push (1–2 days).

## 10. Data privacy for expense data

**Gap**: Expense records contain `description` (free text, potentially sensitive — e.g. "taxi to [clinic name]"), `submitted_by` (an identifier, effectively PII), and amounts. None of this is encrypted at rest (plain SQLite file on disk), there's no data-retention or deletion policy (no soft-delete, no purge job — records live forever per `docs/ARCHITECTURE.md`'s explicit scope decision), and — tied directly to §3 — every stored expense's category/amount/status is sent to a third-party API (Anthropic) on every call to `/reports/insights` with no redaction, consent flag, or data-processing agreement referenced anywhere in the repo. There's also no audit log of who viewed/approved/rejected what beyond the bare `status`/`updated_at` columns (no `approved_by`, explicitly deferred per `docs/ARCHITECTURE.md`).

**Blocking** if this handles real employee expense data (the description field alone is enough to trigger most companies' data-handling policies) and especially if the insights feature stays wired to an external LLM API without a reviewed data-processing agreement; **deferrable** only for a scoped internal pilot with synthetic or non-sensitive data and explicit sign-off that the third-party API call is acceptable.

**Effort**: 2–3 days for retention/deletion tooling and an audit trail (`approved_by`, decision history) at minimum; encryption-at-rest and a reviewed third-party data-sharing decision are organizational/legal work, not purely engineering effort, and aren't estimated here.

## Summary

| # | Area | Verdict | Rough effort |
|---|---|---|---|
| 1 | Auth & key rotation | Blocking | 3–5 days (+1 day rotation) |
| 2 | Input validation | Deferrable | 1–2 days |
| 3 | Rate limiting | Blocking (insights), deferrable (CRUD) | 1.5–2.5 days |
| 4 | Observability & logging | Blocking | 2–4 days |
| 5 | Error handling | Blocking | 1–2 days |
| 6 | Migrations & pooling | Blocking | 3–5 days |
| 7 | Secrets management | Blocking | 1–2 days |
| 8 | Tests & coverage | Blocking | 3–5 days |
| 9 | Deployment & health checks | Blocking | 3–5 days |
| 10 | Data privacy | Blocking (real data), deferrable (pilot only) | 2–3 days + legal review |

Total, if tackled serially: roughly 4–6 engineer-weeks to clear the blocking items, before any legal/compliance review on data privacy. Most items are independent enough to parallelize across more than one engineer.
