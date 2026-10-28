from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import get_current_admin_id
from app.db_session import get_db
from app.models import Dispute, LedgerTransaction, Milestone
from app.routers.contracts import (
    OPEN_MILESTONE_STATUSES,
    commit_or_503,
    load_contract,
    record_event,
)
from app.schemas import DisputeResolve, DisputeResponse
from app.services import ledger as ledger_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/disputes", response_model=list[DisputeResponse])
def list_disputes(
    dispute_status: str = Query(default="open", pattern="^(open|resolved)$"),
    admin_id: int = Depends(get_current_admin_id),
    db: Session = Depends(get_db),
):
    return (
        db.query(Dispute)
        .filter(Dispute.status == dispute_status)
        .order_by(Dispute.created_at.asc(), Dispute.id.asc())
        .all()
    )


@router.post("/disputes/{dispute_id}/resolve", response_model=DisputeResponse)
def resolve_dispute(
    dispute_id: int,
    resolve_data: DisputeResolve,
    admin_id: int = Depends(get_current_admin_id),
    db: Session = Depends(get_db),
):
    dispute = db.query(Dispute).filter(Dispute.id == dispute_id).first()
    if dispute is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dispute not found."
        )

    # Serialize with any in-flight contract mutations (ADR-008 pattern).
    contract = load_contract(dispute.contract_id, db, for_update=True)

    if dispute.status == "resolved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This dispute has already been resolved.",
        )

    now = datetime.now(timezone.utc)
    resolution = resolve_data.resolution

    if resolution == "worker_favored":
        # Force-approve the referenced milestone if work was submitted;
        # the accrual posts in this same transaction, actor = admin.
        if dispute.milestone_id is not None:
            milestone = (
                db.query(Milestone)
                .filter(Milestone.id == dispute.milestone_id)
                .first()
            )
            if milestone is not None and milestone.status in (
                "submitted",
                "changes_requested",
            ):
                milestone.status = "approved"
                milestone.reviewed_at = now
                ledger_service.post_accrual(
                    db, milestone=milestone, contract=contract, actor_id=admin_id
                )
                record_event(
                    db,
                    contract.id,
                    admin_id,
                    "review_approved",
                    milestone_id=milestone.id,
                    note="Approved by admin dispute resolution.",
                )
        contract.status = "active"

    elif resolution == "client_favored":
        # Cancel the contract; if the referenced milestone was approved,
        # reverse its accrual in the same transaction (ADR-009/011).
        if dispute.milestone_id is not None:
            milestone = (
                db.query(Milestone)
                .filter(Milestone.id == dispute.milestone_id)
                .first()
            )
            if milestone is not None and milestone.status == "approved":
                accrual = (
                    db.query(LedgerTransaction)
                    .filter(
                        LedgerTransaction.milestone_id == milestone.id,
                        LedgerTransaction.type == "accrual",
                    )
                    .first()
                )
                if accrual is not None:
                    ledger_service.post_reversal(
                        db,
                        original=accrual,
                        actor_id=admin_id,
                        note=f"Reversed by dispute #{dispute.id} resolution.",
                    )
        contract.status = "cancelled"
        db.query(Milestone).filter(
            Milestone.contract_id == contract.id,
            Milestone.status.in_(OPEN_MILESTONE_STATUSES),
        ).update({"status": "cancelled"}, synchronize_session=False)

    else:  # dismissed — nothing changes, the contract resumes.
        contract.status = "active"

    dispute.status = "resolved"
    dispute.resolution = resolution
    dispute.resolution_note = resolve_data.note
    dispute.resolved_by = admin_id
    dispute.resolved_at = now
    record_event(
        db,
        contract.id,
        admin_id,
        "dispute_resolved",
        milestone_id=dispute.milestone_id,
        note=f"{resolution}: {resolve_data.note}",
    )

    commit_or_503(db)
    db.refresh(dispute)
    return dispute
