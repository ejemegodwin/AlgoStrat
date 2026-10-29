# AlgoStrat — Roadmap

Priority follows the master brief's rule: user value, feasibility,
security, cost, and evidence of demand — not novelty. Completed work is
not listed here; it is recorded as ADRs in `docs/decisions.md`
(ADR-001 through ADR-018).

## Now — Deployment: make the product reachable

Everything works; nobody can reach it. "Production" is currently just
the Neon database — there is no running server and no hosted frontend.

- [ ] Choose a backend host (Render/Fly/Railway class) and a static host
      for the SPA (or serve same-origin)
- [ ] Run `alembic upgrade head` on deploy, not by hand
- [ ] Configure host env vars/secrets; set `CORS_ORIGINS` to the real
      frontend origin
- [ ] Post-deploy smoke checklist (reuse the preflight pattern from the
      2026-10-28 dev-branch smoke: register → post → apply → accept →
      milestone loop → payout)
- [ ] Update README with the live URLs

**Why first:** every increment after this is verified live instead of in
a big-bang deploy later; it also forces the documented security
limitations (below) to become real decisions. Low code risk, some
hosting cost.

## Next — Differentiator 5: reporting & moderation

The trust story (differentiators 1–4) needs a defense mechanism. The
admin dispute queue is a proven pattern to extend.

- [ ] `reports` model: reporter, target (job / user / contract), reason
      category, free text, status
- [ ] `POST` report endpoint for users
- [ ] Admin triage queue page, reusing the dispute-queue UI pattern
      (decision context embedded, consequences inline)
- [ ] Simple, explainable flag rules (duplicate listings, repeated
      abusive reports) feeding the queue — human decides, no automatic
      bans, appeals path exists (per the master brief)

## Then — Differentiator 6: newcomer on-ramp

Matching is already newcomer-neutral; this makes it newcomer-positive.

- [ ] Beginner-friendly flag on jobs (client opt-in) + discovery filter
- [ ] Design questions first: what qualifies a job, how to avoid a
      low-pay ghetto, whether skill assessments have a place
- [ ] Surface completed-work feedback prominently for workers with thin
      histories (the contract/milestone record already exists)

## Security hardening queue

Accepted limitations from `docs/security.md`, pulled forward as
deployment and real usage demand:

- [ ] Password reset / account recovery flow (does not exist at all)
- [ ] Email verification
- [ ] Refresh tokens + revocation (a stolen token currently works until
      expiry; expiry is short as mitigation)
- [ ] Cookie-based auth to replace localStorage JWT (XSS exfiltration
      path)
- [ ] Shared rate-limit store (Redis) — only when running more than one
      instance

## Blocked — real payment provider (Stripe or Paystack)

Waiting on a registered business; the provider port (ADR-012) makes this
additive rather than invasive when unblocked.

Designed-not-built: pending states + `webhook_events` table with
signature verification, a `platform_cost` account modeling provider
fees, stored payment methods via provider customer ids. Until then:
**never claim escrow** — the current ledger is accurate internal
accounting, not regulated client-money handling.

## API evolution (non-urgent, needs a migration plan)

- [ ] Paginated envelope for list endpoints (current lists are bounded
      but unenveloped; changing shape breaks the SPA without a plan)
- [ ] Embed job titles in application responses API-side (the SPA
      currently joins titles client-side; revisit if lists grow)
