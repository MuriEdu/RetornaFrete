from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.deps import get_db
from app.routers.proposals import push_proposal_update
from app.services.payments import sync_payment_from_webhook

router = APIRouter(prefix="/api/payments", tags=["payments"])


@router.post("/mercado-pago/webhook")
async def mercado_pago_webhook(
    request: Request,
    db: Session = Depends(get_db),
    topic: str | None = Query(default=None),
    type: str | None = Query(default=None),
    data_id: str | None = Query(default=None, alias="data.id"),
    payment_id: str | None = Query(default=None, alias="id"),
) -> dict[str, str]:
    event = {}
    try:
        event = await request.json()
    except Exception:
        event = {}

    event_type = (type or topic or event.get("type") or event.get("topic") or "").lower()
    candidate_payment_id = (
        data_id
        or payment_id
        or str((event.get("data") or {}).get("id") or "")
    )

    if event_type and event_type != "payment":
        return {"status": "ignored"}
    if not candidate_payment_id:
        return {"status": "ignored"}

    payment = await sync_payment_from_webhook(db, candidate_payment_id)
    if not payment:
        return {"status": "ignored"}

    db.commit()
    db.refresh(payment.proposal)
    await push_proposal_update(payment.proposal)
    return {"status": "ok"}
