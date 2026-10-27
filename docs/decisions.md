# AlgoStrat — Engineering Decision Record

Concise records of significant decisions, so future sessions build on
them instead of re-litigating them. Newest first.

## ADR-007: Routers split by domain (2026-10-27)

`main.py` only assembles the app and wires routers: `routers/auth.py`,
`routers/jobs.py`, `routers/applications.py`. Route handlers moved
verbatim. Note: FastAPI 0.148 stores included routers lazily as
`_IncludedRouter` entries in `app.routes`; use `app.openapi()` to
enumerate resolved paths.

## ADR-006: Whitespace policy (2026-10-27)

User-controlled text (names, titles, descriptions, categories,
locations, cover letters) is stripped before length validation via
per-field `StringConstraints(strip_whitespace=True)`; whitespace-only
optional job fields become NULL. **Passwords are never stripped** —
every character is part of the secret. Model-wide
`str_strip_whitespace` was rejected precisely because it would alter
passwords.

## ADR-005: Test strategy (2026-10-27)

Default suite runs on in-memory SQLite (fast, isolated). Behavior that
only PostgreSQL provides (row locking under concurrency) is covered by
`tests/test_postgres_integration.py`, skipped unless `TEST_DATABASE_URL`
is set — it must NEVER point at a production/shared database (fixture
truncates tables). GitHub Actions runs migrations + the full suite
against a PostgreSQL 16 service container.

## ADR-004: Rate limiting (2026-10-27)

Registration (10/min) and login (5/min) are limited per client IP by an
in-memory fixed-window limiter (`app/core/rate_limit.py`). Accepted
limitations: single-process state, resets on restart, not shared across
workers. Production upgrade path: Redis-backed limiter or
gateway/proxy-level limiting. Client IP comes from
`request.client.host`; behind a proxy use `--proxy-headers` and trust
only your own proxy.

## ADR-003: Email normalization (2026-10-27)

Emails are stripped and lowercased in `UserCreate`/`UserLogin` schema
validators, making accounts case-insensitive. Migration
`7a2b3c4d5e6f` lowercases existing rows and ABORTS if case-insensitive
duplicates exist (no silent account merging). It is irreversible
(original casing lost). No DB CHECK constraint: SQLite's `lower()` is
ASCII-only and could reject valid internationalized addresses.

## ADR-002: Currency allowlist (2026-10-27)

Job currencies are validated against `SUPPORTED_CURRENCIES` in
`app/schemas.py` (curated ISO 4217 codes covering major global,
African, Middle Eastern, Latin American, and Asian markets), normalized
to trimmed uppercase. Format-only validation was rejected: it stored
junk like `XXX` and non-ASCII triples. Extend the set as markets grow.

## ADR-001: Single-hire application acceptance (2026-10-27)

Product decision (owner-approved): accepting an application means
hiring. Accept requires the job to be open and the application pending;
it atomically accepts the chosen application, closes the job, and
rejects all other pending applications. Closing a job rejects its
remaining pending applications. Invariants: at most one accepted
application per job; a closed job has no pending applications.

Enforcement: `SELECT ... FOR UPDATE` on the job row in the decide,
apply, and close endpoints serializes concurrent transactions
(PostgreSQL; SQLite ignores it, which is why the concurrency test is
PG-only), plus a partial unique index
`uq_job_applications_one_accepted_per_job` on `(job_id) WHERE
status = 'accepted'` as database-level defense in depth.
