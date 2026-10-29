"""Worker levels 0-3 (§14): computed from verified receipts, never
stored, never self-reported.

The receipts table is the only source of truth — a level is a derived,
explainable summary of verified work, so it can never drift from the
history it claims to summarize. Thresholds are deliberately simple
counts anyone can recompute by hand:

- Level 1: 1 verified completion
- Level 2: 3 verified completions across 2 distinct clients
- Level 3: 5 verified completions across 3 distinct clients

Distinct clients matter so that one friendly repeat client cannot
single-handedly carry a worker to the top; revision cycles are NOT
counted against anyone — asking for changes is a normal part of work.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Contract, WorkReceipt

# (level, verified_completions, distinct_clients), ascending.
THRESHOLDS = (
    (1, 1, 1),
    (2, 3, 2),
    (3, 5, 3),
)
MAX_LEVEL = THRESHOLDS[-1][0]


def level_inputs(db: Session, worker_id: int) -> tuple[int, int]:
    """The recorded inputs: receipts issued to this worker, and how
    many distinct clients those receipts came from."""
    receipts, clients = (
        db.query(
            func.count(WorkReceipt.id),
            func.count(func.distinct(Contract.client_id)),
        )
        .join(Contract, WorkReceipt.contract_id == Contract.id)
        .filter(WorkReceipt.worker_id == worker_id)
        .one()
    )
    return receipts, clients


def compute_level(verified_completions: int, distinct_clients: int) -> int:
    level = 0
    for lvl, need_receipts, need_clients in THRESHOLDS:
        if verified_completions >= need_receipts and distinct_clients >= need_clients:
            level = lvl
    return level


def next_level_gap(
    level: int, verified_completions: int, distinct_clients: int
) -> dict | None:
    """What stands between the worker and the next level, in plain
    language — the explainability requirement (None at the top)."""
    if level >= MAX_LEVEL:
        return None
    next_level, need_receipts, need_clients = THRESHOLDS[level]
    missing = []
    if verified_completions < need_receipts:
        count = need_receipts - verified_completions
        missing.append(
            f"{count} more verified completion{'s' if count > 1 else ''}"
        )
    if distinct_clients < need_clients:
        count = need_clients - distinct_clients
        missing.append(
            f"verified work for {count} more client{'s' if count > 1 else ''}"
        )
    return {
        "level": next_level,
        "required": {
            "verified_completions": need_receipts,
            "distinct_clients": need_clients,
        },
        "missing": missing,
    }


def worker_level(db: Session, worker_id: int) -> int:
    receipts, clients = level_inputs(db, worker_id)
    return compute_level(receipts, clients)
