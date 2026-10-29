"""Work receipts: issuance happens inside contract completion
(contracts.py); this router serves receipts and public verification."""

import json
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.rate_limit import rate_limit, verify_rate_limiter
from app.core.security import get_current_user_id
from app.db_session import get_db
from app.models import WorkReceipt
from app.routers.contracts import load_contract, require_party
from app.schemas import ReceiptResponse, ReceiptSummary, VerifyResponse
from app.services import receipts as receipts_service

router = APIRouter(tags=["receipts"])


@router.get(
    "/contracts/{contract_id}/receipt",
    response_model=ReceiptResponse,
)
def get_contract_receipt(
    contract_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """The full receipt (payload + hash + signature) for a completed
    contract. Parties only — the public view is /verify/{uuid}."""
    contract = load_contract(contract_id, db)
    require_party(contract, user_id)

    receipt = (
        db.query(WorkReceipt)
        .filter(WorkReceipt.contract_id == contract_id)
        .first()
    )
    if receipt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This contract has no receipt.",
        )
    return receipt


@router.get("/receipts/me", response_model=list[ReceiptSummary])
def list_my_receipts(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """The current user's verifiable work history, newest first."""
    receipts = (
        db.query(WorkReceipt)
        .filter(WorkReceipt.worker_id == user_id)
        .order_by(WorkReceipt.created_at.desc(), WorkReceipt.id.desc())
        .all()
    )
    summaries = []
    for receipt in receipts:
        payload = json.loads(receipt.payload)
        summaries.append(
            ReceiptSummary(
                receipt_uuid=receipt.receipt_uuid,
                contract_id=receipt.contract_id,
                job_title=payload["job"]["title"],
                job_category=payload["job"]["category"],
                completed_at=payload.get("completed_at"),
                created_at=receipt.created_at,
            )
        )
    return summaries


@router.get(
    "/verify/{receipt_uuid}",
    response_model=VerifyResponse,
    dependencies=[Depends(rate_limit(verify_rate_limiter))],
)
def verify_receipt(receipt_uuid: str, db: Session = Depends(get_db)):
    """PUBLIC verification — no account needed.

    Answers exactly one question: is this receipt genuine and untampered?
    - not_found: no such receipt was ever issued.
    - invalid: the stored payload no longer matches its hash/signature
      (altered history).
    - valid: authentic; returns only minimal display fields — never the
      client, amounts, or evidence references.
    """
    receipt = (
        db.query(WorkReceipt)
        .filter(WorkReceipt.receipt_uuid == receipt_uuid)
        .first()
    )
    if receipt is None:
        return VerifyResponse(status="not_found")

    key = os.getenv("RECEIPT_SIGNING_KEY")
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Receipt verification is not configured on this server.",
        )

    if not receipts_service.verify_receipt(receipt, key.encode("utf-8")):
        return VerifyResponse(status="invalid")

    payload = json.loads(receipt.payload)
    return VerifyResponse(
        status="valid",
        worker_name=payload["worker"]["name"],
        job_title=payload["job"]["title"],
        job_category=payload["job"]["category"],
        completed_at=datetime.fromisoformat(payload["completed_at"]),
    )
