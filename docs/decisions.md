# AlgoStrat — Engineering Decision Record

Concise records of significant decisions, so future sessions build on
them instead of re-litigating them. Newest first.

## ADR-011: Disputes and ledger reversals (2026-10-28)

Product decisions (owner-approved):

- Either contract party may raise ONE open dispute per contract while
  it is active, with a required reason and an optional milestone
  reference. Raising moves the contract to `disputed`, which freezes
  all mutations for free: every mutation path already requires
  `active` (ADR-008).
- Admin model: `users.is_admin` boolean, seeded manually via SQL.
  Admin-only endpoints list and resolve disputes; every admin action
  is recorded in `contract_events` with the admin as actor.
- Exactly three resolution outcomes:
  - `worker_favored`: a referenced submitted/changes-requested
    milestone is force-approved (posting its accrual, actor = admin);
    the contract resumes `active`.
  - `client_favored`: the contract is cancelled, open milestones
    cancel with it, and if the referenced milestone was approved, its
    accrual is REVERSED automatically in the same transaction.
  - `dismissed`: nothing changes; the contract resumes `active`.
- Reversals (ADR-009 mechanism): a `reversal` transaction whose
  entries mirror the original accrual's with negated amounts, keyed
  `reversal:{original_transaction_id}`. The milestone stays `approved`
  — history is not rewritten — but the financial obligation is wiped.
- A dispute force-approval emits `review_approved` (actor = admin), so
  it counts in the worker's reliability share — deliberately: the work
  was adjudicated as acceptable.
- One-open-dispute-per-contract is enforced by a partial unique index
  (`status = 'open'`), defense in depth behind the status check.
- The contracts status CHECK widens to include `disputed`; downgrading
  requires no disputed rows to exist (documented in the migration).

## ADR-010: Explainable matching (2026-10-28)

Product decisions (owner-approved):

- Both matching directions exist: `GET /jobs/recommended` ranks open
  jobs for the calling worker; `GET /jobs/{id}/applicants/ranked`
  ranks a job's **applicants** for its owner. The client side ranks
  only people who applied (never a platform-wide worker search) — the
  privacy exposure is bounded by the application itself.
- Transparency rule: both directions use the SAME factor definitions
  and weights. Anything a client can see about a worker is computed
  the same way the worker sees it; there are no hidden scores.
- Worker profiles live in `worker_profiles` (availability, min_budget)
  + `profile_tags` (kind skill/category, values trimmed + lowercased,
  ≤10 skills, ≤5 categories). Normalized free-form tags, not a curated
  taxonomy — one can be layered on later without migration.
- Budget compatibility = worker's declared minimum budget vs the
  job's total budget. No rate conversion until jobs carry durations.
- Score = 0.40·category + 0.20·budget + 0.25·track_record
  + 0.15·reliability. Track record caps at 3 completed contracts;
  reliability = approval share of review events, defaulting to 0.5
  (neutral, "not enough data") with no history. Newcomers are
  structurally protected: history is worth at most 40% and never
  scores below neutral.
- Anti-discrimination guardrails: scoring uses only self-declared
  professional data and platform-verified behavior — never name,
  location, account age, or email domain. Job location is displayed,
  never scored.
- Recommendations exclude the worker's own jobs (they cannot apply to
  them by rule); jobs they already applied to remain (their pipeline
  is their own business; hiding data is not our job).
- No machine learning: transparent rules with per-factor explanations
  first; ML only with lawfully obtained data and a clear evaluation
  method (master brief).

## ADR-009: Payment ledger — accrual only, double-entry (2026-10-28)

Product decisions (owner-approved):

- The ledger is an internal financial model only: it records who owes
  what to whom. No real money moves, no provider integration, no card
  storage, and the word "escrow" is never claimed.
- Double-entry bookkeeping: every transaction's entries sum to zero;
  balances are always derived (SUM of entries), never stored.
  Accounts: `client_payable`, `worker_receivable` (per user+currency),
  `platform_revenue`, `platform_cash` (platform-wide; cash is dormant
  until a provider exists).
- Accrual posts when a milestone is approved (work accepted = value
  earned), inside the same DB transaction and contract row lock as the
  approval, so a review can never half-post. Amountless milestones
  accrue nothing.
- Platform fee is configurable via `PLATFORM_FEE_PERCENT` (default 0):
  the client is debited the full amount; the worker is credited the
  amount minus fee; the fee is credited to platform revenue. Fee
  rounds HALF_UP to 2dp; the worker receives the remainder, so
  entries always balance exactly. Zero-fee accruals omit the fee
  entry (CHECK forbids amount = 0).
- Scope of this increment: accrual + read-only balances. No manual
  "mark as paid" — unverifiable payment claims are the scam vector
  the ledger exists to prevent. Settlement arrives with a provider.
- Reversals: corrections only ever happen via mirror-image reversal
  transactions (never edits or deletes). Mechanism specified here,
  implemented with the disputes increment, which owns the policy.
- Idempotency: every ledger transaction carries a unique
  `idempotency_key` (`accrual:milestone:{id}` for approvals), so
  retries — API or future provider webhooks — cannot double-post.
- API presentation: each account is reported by its natural balance
  (debit-normal accounts as SUM, credit-normal as −SUM), so users see
  non-negative "owed"/"earned" figures under normal operation.

## ADR-008: Contracts and milestones (2026-10-28)

Product decisions (owner-approved):

- A Contract is created automatically in the same transaction that
  accepts an application (accept = hire, ADR-001). No hire can exist
  without a contract. One contract per job (`contracts.job_id` unique),
  mirroring the single-hire invariant.
- Contracts snapshot the parties and terms at hire time: `client_id`,
  `worker_id`, `agreed_amount` (from the job budget), `currency`.
- Milestones are client-defined while the contract is active; the
  worker submits work; the client approves or requests changes (note
  required) and the worker may resubmit. `approved` is terminal.
- Money rule: when the contract has an agreed amount, the sum of
  milestone amounts may not exceed it, checked under the contract row
  lock. Amounts are records only — no money moves until the payment
  ledger increment.
- Completion is an explicit client action allowed only with no open
  milestones; cancellation is client-only for now (worker recourse
  arrives with the disputes increment).
- `contract_events` is an append-only audit log (no update/delete
  endpoints) carrying submission/review notes as payload, so the full
  history survives resubmission. Foundation for verifiable work
  history (differentiator 1). `milestone_id` goes NULL on milestone
  deletion (`ON DELETE SET NULL`) so the audit trail survives.
- Concurrency: all contract/milestone mutations hold
  `SELECT ... FOR UPDATE` on the contract row — the same pattern as
  the job row in ADR-001.

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
