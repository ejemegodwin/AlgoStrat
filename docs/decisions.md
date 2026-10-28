# AlgoStrat — Engineering Decision Record

Concise records of significant decisions, so future sessions build on
them instead of re-litigating them. Newest first.

## ADR-017: Dispute raising UI + admin resolution surface (2026-10-28)

Product decisions (owner-approved):

- The admin queue (`GET /admin/disputes`) now returns
  `AdminDisputeResponse`: the dispute plus job title, contract
  status/amount/currency, milestone summary, and all three names.
  The admin decides without being a party — the party endpoints would
  403 for them — so this endpoint deliberately crosses the party
  boundary. Admin-only keeps that contained; party endpoints keep the
  lean `DisputeResponse`.
- `UserResponse` carries `is_admin` so the SPA can surface the admin
  nav/page. This is presentation only; `get_current_admin_id` remains
  the enforcement on every admin endpoint. Granting admin stays
  manual SQL — right-sized for a solo-operated product.
- The contract page gains the dispute UI ADR-015 deferred: either
  party can raise (reason ≥ 20 chars, optional milestone reference),
  confirm-gated with the freeze spelled out, since raising makes
  every other action on the page vanish. A disputed contract shows a
  banner explaining the pause, and both parties see the resolution
  and its note once resolved.
- The resolution form states each outcome's consequences inline
  (worker_favored force-approves and accrues; client_favored cancels,
  reverses, and refunds a charged milestone; dismissed resumes
  unchanged) and the confirm restates them — resolving moves money,
  so nobody clicks it on a guess.
- Verified: 189 unit + 2 Postgres integration tests (run against the
  Neon dev branch), plus a live smoke of all three outcomes including
  the refund math (charged 60 → client_favored → receivable and
  payable both back to 0.00).

## ADR-016: Frontend — payouts (2026-10-28)

Product decisions (owner-approved roadmap, frontend slice 5):

- `/payouts` is the worker's view of the books: `worker_receivable`
  per currency as "available to withdraw", plus any `client_payable`
  still owed shown for transparency (a worker_favored dispute
  resolution posts an accrual without a charge, so a client can owe —
  hiding that would make the ledger feel wrong). Users only ever see
  their own accounts; there is no endpoint for anyone else's.
- Blank amount means "full settled balance" (the API's ADR-012
  default), so the amount field is optional with the balance as its
  placeholder. The form only offers currencies that actually hold a
  positive receivable.
- Requesting a payout is confirm-gated (it moves money, even with the
  simulated provider) and the success state shows the provider
  reference — the reference is the receipt. Payout history lists
  below; balances and history reload after every payout.
- Verified live against the Neon dev branch: full-loop funding
  (approve → charge), over-balance 400, full payout zeroes the
  balance, second payout 400s, client_payable settles to zero.

## ADR-015: Frontend — contract detail and the milestone loop (2026-10-28)

Product decisions (owner-approved roadmap, frontend slice 4):

- One contract detail page, role-aware: both parties see the same
  milestones and audit log; the actions offered depend on role and
  status (client edits pending / reviews submitted / completes or
  cancels, worker submits and resubmits). As with the apply form, the
  API enforces every rule — the UI only declines to offer what
  doesn't apply.
- Approving a priced milestone asks for a payment token (ADR-012).
  The label says "token", never "card": with the simulated provider
  any value succeeds and `tok_fail` exercises the 402 path, which the
  UI surfaces as "declined, try another" — the milestone stays
  submitted and the retry is safe (the provider reference is the
  idempotency key).
- Complete and cancel are confirm-gated (terminal actions). Complete
  is additionally disabled while open milestones exist, mirroring the
  API's OPEN_MILESTONE_STATUSES with a client-side copy that only
  drives the button state; the API remains the enforcement.
- The add-milestone form shows "allocated so far / agreed amount" so
  the budget cap (ADR-008) fails in the form instead of as a 400.
  Summing is display-only; Decimal math stays server-side.
- Disputes are deliberately NOT in this UI: raising one freezes the
  contract and resolution is admin-only (ADR-011), so a "dispute"
  button today would be a freeze with no visible way out. It lands
  together with an admin/resolution surface.
- The audit log (`GET /contracts/{id}/events`) renders verbatim with
  a label map and a fallback for unknown event types, so a new
  backend event never renders blank. Actors show as "You" / "The
  other party" — events embed actor_id, not names, and a contract
  has exactly two parties.

## ADR-014: Frontend — client reviews applicants, contracts list (2026-10-28)

Product decisions (owner-approved roadmap, frontend slice 3):

- Application review lives on the job detail page, not a separate
  screen: the owner reading their own job sees an applicants section
  where an applicant would see the apply form. Same URL, role decides
  the section (the API enforces ownership either way).
- The owner sees the ranked view (`GET /jobs/{id}/applicants/ranked`)
  with the score factors spelled out — ADR-010's transparency rule
  applies in the UI too, not just the API. Decided applications show
  as history below, without names (the application response embeds no
  worker name; the pending-ranked view is where evaluation happens).
- Accept is confirm-gated in the UI because it is the one
  consequential click: it hires, closes the job, rejects the other
  pending applications, and creates the contract (ADR-001/008). The
  confirm text says exactly that. Reject needs no confirm — it is a
  single reversible-in-spirit decision the API already records.
- Contracts list (`/contracts`) is read-only: both parties see their
  contracts with role label ("You are the client/worker") and status.
  Milestones, submit/review, and payouts UI are the next slices; the
  list links back to the job for context until a contract detail page
  exists.
- The client-side job-title join (responses embed `job_id`, not the
  title) is now shared (`src/jobs.js`) between applications and
  contracts lists. Still the accepted tradeoff from slice 2 — an
  API-side embed is the fix if these lists grow.

## ADR-013: Frontend foundation — Vite + React SPA (2026-10-28)

Product decisions (owner-approved):

- Vite + React single-page app in `frontend/`, plain JavaScript (not
  TypeScript): this is a first frontend for a backend learner, so the
  fewest new concepts at once. Migrating to TS early is cheap if
  wanted. FastAPI remains the only server; the SPA talks to it
  cross-origin (`VITE_API_URL`), which is why CORS exists
  (`CORS_ORIGINS`, explicit allowlist, never `*`).
- `react-router-dom` for routing. No state library, no data-fetching
  library, no component library: one fetch wrapper (`src/api.js`)
  owns the base URL, the Bearer header, and FastAPI's `{detail}`
  error shape; auth state lives in one context (`src/auth.jsx`).
  Adding libraries later is easier than removing them.
- The JWT is stored in localStorage and sent as a Bearer token.
  Accepted tradeoff (recorded in `docs/security.md`): any XSS hole
  exfiltrates the token, so expiry stays short and origins stay
  narrow. httpOnly cookie auth is the known hardening path and
  requires no API change beyond CORS credentials.
- Registration collects name/email/password only (the API sets
  `account_type` by default); role/profile setup is a later slice.
  Register-then-login is one flow from the user's perspective.
- First slice is read-mostly on purpose: job list and detail are
  public (matching the API), auth pages prove the token flow.
  Applying, posting jobs, contracts, and payouts UI are later slices.
- No frontend test runner yet (Vitest when interactions get
  stateful); verification for this slice was `npm run build` plus a
  live smoke (vite dev + uvicorn + preflight curl).

## ADR-012: Payments — simulated provider, charge-at-approval (2026-10-28)

Product decisions (owner-approved):

- All provider contact goes behind a port (`charge` / `transfer` /
  `refund`) in `app/services/payments.py`, selected by
  `PAYMENT_PROVIDER` (default `simulated`). This increment ships
  `SimulatedProvider`: deterministic, dedupes by idempotency
  reference, token `tok_fail` declines charges. A real adapter
  (Stripe/Paystack) is the only new code once a registered business
  exists — every money path is tested before real funds move.
- Funding model: the client is charged AT MILESTONE APPROVAL, never
  before. The platform never holds client funds — "escrow" is neither
  claimed nor implemented. Approval calls the provider FIRST; a
  decline returns 402 and posts nothing (the milestone stays
  `submitted`). On success the accrual AND the charge settlement post
  in the same DB transaction: `platform_cash +A`, `client_payable −A`
  (debt cleared). The worker's receivable stays outstanding until
  payout — it is cash-backed by definition. A priced approval needs a
  payment token from the reviewing client (request-supplied); an
  amountless milestone approves without one, as before.
- Dual-write safety: the provider idempotency reference IS the
  accrual's key (`accrual:milestone:{id}`), so a retried approval
  cannot double-charge; the charge settlement transaction is keyed
  `settlement:milestone:{id}`.
- Payouts: any user may withdraw their settled (cash-backed)
  `worker_receivable` balance via `POST /payouts` (amount optional,
  defaults to the full balance; `GET /payouts` lists history).
  Requests serialize with `SELECT ... FOR UPDATE` on the worker's
  ledger account row, so concurrent payouts cannot double-spend the
  balance. Settlement: `worker_receivable +P`, `platform_cash −P`,
  keyed `payout:{id}`. Payout destinations are free-text strings — a
  real provider tokenizes destinations; card storage remains
  forbidden.
- Refunds complete the money loop: a `client_favored` resolution on a
  CHARGED milestone additionally calls `provider.refund` and posts a
  reversal of the charge settlement in the same transaction, clearing
  the refund claim the accrual reversal created (all balances return
  to zero). Milestones approved before this increment have no charge
  settlement; their reversal stands alone (no money moved originally).
- Dispute force-approval (`worker_favored`) posts the accrual ONLY:
  the client never approved, so there is no payment token to charge.
  `client_payable` stays outstanding — adjudicated, owed, uncollected.
  Collecting it arrives with stored payment methods (provider customer
  ids — never PANs) in the real-adapter increment.
- Provider processing fees are NOT modeled yet (the simulated provider
  charges none); a real adapter will add a `platform_cost` account
  type.
- Webhooks/async: designed, not built. Charges are synchronous with
  the simulated provider; a real adapter introduces pending states
  (approval → payment pending → webhook success/failure → settlement
  posts) and a `webhook_events` table for verified, idempotent
  processing. The ledger's idempotency keys are already shaped for it.

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
