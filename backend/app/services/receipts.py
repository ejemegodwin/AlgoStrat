"""Work receipts: tamper-evident proof of verified completion (§12.3).

A receipt binds a canonical JSON payload to two things:

- content_hash = SHA-256 over the canonical payload — editing one word
  of the payload changes the hash, so history cannot be rewritten.
- signature = HMAC-SHA256 over the content hash with the server-side
  RECEIPT_SIGNING_KEY — only the platform can produce a valid signature,
  so receipts cannot be forged.

Verification distinguishes valid / invalid-or-altered / unknown, and
never needs private data: evidence appears in the payload only as
hashes, the client is identified by nothing at all, and amounts are
excluded. Stdlib only (hashlib, hmac, json) — no new dependencies.
"""

import hashlib
import hmac
import json
import os
import uuid
from datetime import timezone

from sqlalchemy.orm import Session

from app.models import Contract, ContractEvent, Job, User, WorkReceipt


class ReceiptSigningUnavailableError(RuntimeError):
    """RECEIPT_SIGNING_KEY is not configured on this environment."""


def canonicalize(payload: dict) -> str:
    """Deterministic JSON: sorted keys, tight separators. Two payloads
    with the same content MUST produce byte-identical strings, or hash
    comparison is meaningless."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )


def hash_canonical(canonical: str) -> str:
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def evidence_hash(reference: str) -> str:
    """Proves an evidence reference existed at receipt time without
    exposing the reference itself (it may be a private link)."""
    return hashlib.sha256(reference.encode("utf-8")).hexdigest()


def _signing_key() -> bytes:
    key = os.getenv("RECEIPT_SIGNING_KEY")
    if not key:
        raise ReceiptSigningUnavailableError(
            "RECEIPT_SIGNING_KEY is not configured."
        )
    return key.encode("utf-8")


def sign(content_hash: str, key: bytes) -> str:
    return hmac.new(
        key, content_hash.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def verify_receipt(receipt: WorkReceipt, key: bytes) -> bool:
    """True only if the stored payload still matches its hash AND the
    signature matches this environment's key. Constant-time compares."""
    actual_hash = hash_canonical(receipt.payload)
    if not hmac.compare_digest(actual_hash, receipt.content_hash):
        return False
    expected_signature = sign(actual_hash, key)
    return hmac.compare_digest(expected_signature, receipt.signature)


def issue_receipt(db: Session, *, contract: Contract, actor_id: int) -> WorkReceipt:
    """Issue the one receipt for a completed contract. Called inside the
    completion transaction: completion and receipt commit or roll back
    together, so a verified completion ALWAYS has its receipt.

    One receipt per contract is enforced by a unique constraint on
    contract_id — corrections would be a superseding record, never an
    edit.
    """
    job = db.query(Job).filter(Job.id == contract.job_id).first()
    worker = db.query(User).filter(User.id == contract.worker_id).first()

    approved = [m for m in contract.milestones if m.status == "approved"]
    revision_cycles = sum(
        1
        for m in contract.milestones
        for s in m.submissions
        if s.review_decision == "changes_requested"
    )

    receipt_uuid = str(uuid.uuid4())
    payload = {
        "version": 1,
        "platform": "AlgoStrat",
        "receipt_uuid": receipt_uuid,
        "worker": {"id": worker.id, "name": worker.full_name},
        "job": {
            "id": job.id,
            "title": job.title,
            "category": job.category,
            "job_type": job.job_type,
        },
        "contract_id": contract.id,
        # completed_at was set moments ago by the completion path.
        "completed_at": contract.completed_at.astimezone(
            timezone.utc
        ).isoformat(),
        # The criteria the worker agreed to (frozen at hire time).
        "criteria": json.loads(contract.criteria_snapshot),
        "milestones": [
            {
                "title": m.title,
                "evidence_hashes": [
                    evidence_hash(ref) for ref in m.latest_evidence
                ],
            }
            for m in approved
        ],
        "outcome": {
            "approved_milestones": len(approved),
            "revision_cycles": revision_cycles,
        },
    }

    canonical = canonicalize(payload)
    digest = hash_canonical(canonical)
    receipt = WorkReceipt(
        receipt_uuid=receipt_uuid,
        worker_id=worker.id,
        contract_id=contract.id,
        payload=canonical,
        content_hash=digest,
        signature=sign(digest, _signing_key()),
    )
    db.add(receipt)
    db.add(
        ContractEvent(
            contract_id=contract.id,
            actor_id=actor_id,
            event_type="receipt_issued",
            note=receipt_uuid,
        )
    )
    return receipt
