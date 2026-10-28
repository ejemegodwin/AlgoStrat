"""Explainable worker-job matching (ADR-010).

Rules-based scoring only — no machine learning. Every score ships with
per-factor explanations, and both matching directions (jobs for a
worker, applicants for a job) use the SAME factors and weights, so a
score a client sees about a worker is computed exactly the way the
worker sees it themselves.

Factors use only self-declared professional data (categories, minimum
budget) and platform-verified behavior (completed contracts, review
outcomes) — never name, location, account age, or email domain.
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Contract,
    ContractEvent,
    Job,
    Milestone,
    ProfileTag,
    WorkerProfile,
)

WEIGHTS = {
    "category": 0.40,
    "budget": 0.20,
    "track_record": 0.25,
    "reliability": 0.15,
}

# Track record maxes out at this many completed contracts, capping the
# advantage tenure can buy (differentiator: newcomer on-ramp).
TRACK_RECORD_FULL_CREDIT_CONTRACTS = 3


@dataclass
class FactorScore:
    score: float  # 0.0 - 1.0
    reason: str


@dataclass
class WorkerContext:
    """Everything the factors need about one worker, fetched once."""

    user_id: int
    categories: set[str]
    min_budget: Decimal | None
    completed_contracts: int
    approved_reviews: int
    total_reviews: int

    @property
    def approval_share(self) -> float | None:
        """Share of review events that were approvals; None means the
        worker has no review history at all."""
        if self.total_reviews == 0:
            return None
        return self.approved_reviews / self.total_reviews


def build_worker_context(db: Session, user_id: int) -> WorkerContext:
    categories = {
        tag.value
        for tag in db.query(ProfileTag).filter(
            ProfileTag.user_id == user_id,
            ProfileTag.kind == "category",
        )
    }

    profile = db.query(WorkerProfile).filter(WorkerProfile.user_id == user_id).first()
    min_budget = profile.min_budget if profile is not None else None

    completed_contracts = db.query(func.count(Contract.id)).filter(
        Contract.worker_id == user_id,
        Contract.status == "completed",
    ).scalar()

    # Review outcomes across every milestone this worker has had
    # reviewed, from the append-only event log.
    review_rows = (
        db.query(ContractEvent.event_type, func.count(ContractEvent.id))
        .join(Milestone, ContractEvent.milestone_id == Milestone.id)
        .join(Contract, Milestone.contract_id == Contract.id)
        .filter(
            Contract.worker_id == user_id,
            ContractEvent.event_type.in_(("review_approved", "changes_requested")),
        )
        .group_by(ContractEvent.event_type)
        .all()
    )
    counts = dict(review_rows)
    approved = counts.get("review_approved", 0)
    total = approved + counts.get("changes_requested", 0)

    return WorkerContext(
        user_id=user_id,
        categories=categories,
        min_budget=min_budget,
        completed_contracts=completed_contracts,
        approved_reviews=approved,
        total_reviews=total,
    )


def category_factor(job: Job, ctx: WorkerContext, whose: str) -> FactorScore:
    if not ctx.categories:
        return FactorScore(0.0, f"No categories declared in {whose} profile.")
    if job.category is None:
        return FactorScore(0.0, "The job has no category.")

    job_category = job.category.strip().lower()
    if job_category in ctx.categories:
        return FactorScore(
            1.0, f"Category '{job.category}' matches {whose} declared categories."
        )
    return FactorScore(
        0.0, f"Category '{job.category}' is outside {whose} declared categories."
    )


def budget_factor(job: Job, ctx: WorkerContext, whose: str) -> FactorScore:
    if ctx.min_budget is None:
        return FactorScore(1.0, f"No minimum budget set on {whose} profile.")
    if job.budget is None:
        return FactorScore(
            0.5, "The job lists no budget, so compatibility is unknown."
        )
    if job.budget >= ctx.min_budget:
        return FactorScore(
            1.0,
            f"Budget {job.budget} {job.currency} meets the "
            f"{ctx.min_budget} minimum.",
        )
    return FactorScore(
        0.0,
        f"Budget {job.budget} {job.currency} is below the "
        f"{ctx.min_budget} minimum.",
    )


def track_record_factor(ctx: WorkerContext, whose: str) -> FactorScore:
    score = min(ctx.completed_contracts, TRACK_RECORD_FULL_CREDIT_CONTRACTS) / (
        TRACK_RECORD_FULL_CREDIT_CONTRACTS
    )
    if ctx.completed_contracts == 0:
        return FactorScore(score, f"No completed contracts on {whose} record.")
    return FactorScore(
        score,
        f"{ctx.completed_contracts} completed contract(s) on {whose} record "
        f"({TRACK_RECORD_FULL_CREDIT_CONTRACTS}+ earns full credit).",
    )


def reliability_factor(ctx: WorkerContext, whose: str) -> FactorScore:
    share = ctx.approval_share
    if share is None:
        # Newcomers start neutral, never at zero: no history is not
        # evidence of unreliability (differentiator: newcomer on-ramp).
        return FactorScore(0.5, "No review history yet — counted as neutral.")
    return FactorScore(
        share,
        f"{ctx.approved_reviews} of {ctx.total_reviews} milestone reviews "
        f"were approvals.",
    )


def score_job_for_worker(
    job: Job, ctx: WorkerContext, whose: str = "the worker"
) -> tuple[float, dict[str, FactorScore]]:
    """Score one job against one worker. `whose` phrasing lets both
    audiences read the same factors in natural language."""
    factors = {
        "category": category_factor(job, ctx, whose),
        "budget": budget_factor(job, ctx, whose),
        "track_record": track_record_factor(ctx, whose),
        "reliability": reliability_factor(ctx, whose),
    }
    total = round(
        sum(WEIGHTS[name] * factor.score for name, factor in factors.items()),
        3,
    )
    return total, factors
