# AlgoStrat — Security Notes

## Authentication

- Passwords hashed with Argon2 via pwdlib (`PasswordHash.recommended()`).
- Login issues JWT access tokens (HS256, configurable expiry, default 30
  minutes). `sub` claim is validated strictly (digit string → int).
- Unknown-email logins verify against a precomputed dummy hash so
  response timing matches wrong-password logins (no enumeration via
  timing); both return the same 401 message.
- Registration (10/min/IP) and login (5/min/IP) are rate limited
  in-memory; see ADR-004 in `docs/decisions.md` for limitations and the
  production upgrade path.

## Authorization

- Every protected endpoint resolves the user from the JWT and checks
  ownership explicitly (jobs by `customer_id`, applications by
  `applicant_id`); application decisions are restricted to the job
  owner. No indirect object reference grants access by id alone.

## Input handling

- Pydantic v2 schemas validate and normalize all request bodies
  (trim-before-length-check, currency allowlist, email normalization,
  status pattern). Passwords are never trimmed.
- Search filters use parameterized SQLAlchemy queries with LIKE
  wildcards escaped; no string-built SQL anywhere.
- Database errors return generic 503s; internal details never reach the
  response body (regression-tested).

## Data integrity

- Check constraints bound job and application statuses; unique
  constraint prevents duplicate applications; partial unique index
  enforces one accepted application per job.
- Multi-step state changes (accept/close) run in one transaction with
  `SELECT ... FOR UPDATE` on the job row.

## Secrets and configuration

- `DATABASE_URL`, `JWT_SECRET_KEY`, etc. come from the environment;
  `.env` is git-ignored; `.env.example` documents variables without
  values. The app refuses to start without them.
- CI uses throwaway credentials scoped to the workflow run.

## Known limitations (honest list)

- Rate limiter is per-process; multi-instance deployments need a shared
  store (Redis) or proxy-level limiting.
- No refresh tokens, token revocation list, or email verification yet;
  a stolen valid token works until expiry (keep expiry short).
- CORS is not configured; add explicit origins when the frontend
  deployment exists — do not use `allow_origins=["*"]` with credentials.
- Password reset / account recovery flow does not exist yet.
