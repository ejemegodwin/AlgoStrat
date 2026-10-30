from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.rate_limit import rate_limit, waitlist_rate_limiter
from app.db_session import get_db
from app.models import WaitlistLead
from app.schemas import WaitlistCreate

router = APIRouter(prefix="/waitlist", tags=["waitlist"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit(waitlist_rate_limiter))],
)
def join_waitlist(
    lead_data: WaitlistCreate,
    db: Session = Depends(get_db),
):
    lead = WaitlistLead(
        email=str(lead_data.email),
        audience=lead_data.audience,
        region=lead_data.region,
        consent=lead_data.consent,
    )

    try:
        db.add(lead)
        db.commit()
        db.refresh(lead)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email is already on the waitlist.",
        )

    return {"id": lead.id, "status": "joined"}
