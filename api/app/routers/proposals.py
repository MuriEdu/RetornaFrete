import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import Cargo, CargoStatus, FreightPaymentStatus, Proposal, ProposalBid, ProposalStatus, Role, Trip, TripStatus, User
from app.routers.matches import haversine_km, is_trip_date_compatible
from app.schemas import ConfirmDeliveryCodeRequest, CreateProposalRequest, NegotiateProposalRequest, ProposalActionRequest, ProposalPaymentDetailsResponse, ProposalPaymentSummaryResponse, ProposalResponse
from app.services.notifications import notification_manager
from app.services.payments import create_checkout_preference, ensure_proposal_payment, mercado_pago_configured, sync_payment_from_search, validate_payment_release

router = APIRouter(prefix="/api/proposals", tags=["proposals"])


def serialize_payment(payment) -> ProposalPaymentSummaryResponse | None:
    if not payment:
        return None
    return ProposalPaymentSummaryResponse(
        amount=float(payment.amount),
        status=payment.status,
        provider="MERCADO_PAGO",
        providerStatus=payment.mercado_pago_payment_status,
        paidAt=payment.paid_at,
        releasedAt=payment.released_at,
        deliveryCodeHint=f"***{payment.delivery_code[-3:]}",
    )


def serialize_payment_details(payment, *, include_delivery_code: bool) -> ProposalPaymentDetailsResponse:
    return ProposalPaymentDetailsResponse(
        amount=float(payment.amount),
        status=payment.status,
        provider="MERCADO_PAGO",
        providerStatus=payment.mercado_pago_payment_status,
        paidAt=payment.paid_at,
        releasedAt=payment.released_at,
        deliveryCodeHint=f"***{payment.delivery_code[-3:]}",
        checkoutUrl=payment.mercado_pago_checkout_url,
        sandboxCheckoutUrl=payment.mercado_pago_sandbox_checkout_url,
        deliveryCode=payment.delivery_code if include_delivery_code else None,
        lastError=payment.last_error,
    )


def serialize_proposal(proposal: Proposal) -> ProposalResponse:
    cargo = proposal.cargo
    trip = proposal.trip
    distance = haversine_km(cargo.origin_lat, cargo.origin_lon, cargo.dest_lat, cargo.dest_lon)
    return ProposalResponse(
        id=proposal.id,
        cargoId=proposal.cargo_id,
        tripId=proposal.trip_id,
        initialValue=float(proposal.initial_value),
        currentBid=float(proposal.current_bid),
        currentBidderId=proposal.current_bidder_id,
        createdAt=proposal.created_at,
        status=proposal.status,
        freightDate=cargo.trip_date,
        originCity=cargo.origin_name,
        destCity=cargo.destination_name,
        distanceKm=f"{distance:.2f}",
        productName=cargo.product_name,
        weightKg=cargo.weight_kg,
        tripDate=trip.trip_date,
        payment=serialize_payment(proposal.payment),
        bidHistory=[
            {
                "id": bid.id,
                "value": float(bid.value),
                "bidderId": bid.bidder_id,
                "bidderName": bid.bidder.fullname,
                "createdAt": bid.created_at,
            }
            for bid in proposal.bids
        ],
    )


async def push_proposal_update(proposal: Proposal) -> None:
    payload = serialize_proposal(proposal).model_dump(mode="json")
    await notification_manager.publish_proposal_update([proposal.cargo.user_id, proposal.trip.user_id], payload)


def get_proposal_or_404(db: Session, proposal_id: uuid.UUID) -> Proposal:
    proposal = db.scalar(select(Proposal).where(Proposal.id == proposal_id))
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return proposal


def finalize_acceptance(db: Session, proposal: Proposal) -> None:
    proposal.status = ProposalStatus.ACCEPTED
    proposal.trip.status = TripStatus.MATCHED
    proposal.cargo.status = CargoStatus.MATCHED
    ensure_proposal_payment(db, proposal)


@router.get("/my-offers")
def my_offers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProposalResponse]:
    proposals = db.scalars(select(Proposal).join(Cargo).where(Cargo.user_id == current_user.id)).all()
    return [serialize_proposal(proposal) for proposal in proposals]


@router.get("/recived")
def received_offers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProposalResponse]:
    proposals = db.scalars(select(Proposal).join(Trip).where(Trip.user_id == current_user.id)).all()
    return [serialize_proposal(proposal) for proposal in proposals]


@router.post("", response_model=ProposalResponse)
async def create_proposal(
    payload: CreateProposalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProposalResponse:
    if current_user.role != Role.SHIPPER:
        raise HTTPException(status_code=403, detail="Only shippers can create proposals")

    cargo = db.scalar(select(Cargo).where(Cargo.id == payload.cargoId, Cargo.user_id == current_user.id))
    trip = db.scalar(select(Trip).where(Trip.id == payload.tripId))
    if not cargo or not trip:
        raise HTTPException(status_code=404, detail="Trip or cargo not found")
    if cargo.status != CargoStatus.ACTIVE or trip.status != TripStatus.AVAILABLE:
        raise HTTPException(status_code=400, detail="Trip or cargo is not available")
    if not is_trip_date_compatible(cargo.trip_date, trip.trip_date, cargo.is_date_flexible):
        raise HTTPException(status_code=400, detail="Trip date is incompatible with cargo date")

    proposal = Proposal(
        cargo_id=cargo.id,
        trip_id=trip.id,
        created_by_id=current_user.id,
        current_bidder_id=current_user.id,
        initial_value=payload.initialPrice,
        current_bid=payload.initialPrice,
        status=ProposalStatus.PENDING,
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    await push_proposal_update(proposal)
    return serialize_proposal(proposal)


@router.patch("/{proposal_id}/respond", response_model=ProposalResponse)
async def respond_proposal(
    proposal_id: uuid.UUID,
    payload: ProposalActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProposalResponse:
    proposal = get_proposal_or_404(db, proposal_id)
    if current_user.id not in {proposal.cargo.user_id, proposal.trip.user_id}:
        raise HTTPException(status_code=403, detail="Forbidden")

    if payload.action == "REJECT":
        proposal.status = ProposalStatus.REJECTED
    else:
        finalize_acceptance(db, proposal)

    db.commit()
    db.refresh(proposal)
    await push_proposal_update(proposal)
    return serialize_proposal(proposal)


@router.patch("/{proposal_id}/negotiate", response_model=ProposalResponse)
async def negotiate_proposal(
    proposal_id: uuid.UUID,
    payload: NegotiateProposalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProposalResponse:
    proposal = get_proposal_or_404(db, proposal_id)
    participants = {proposal.cargo.user_id, proposal.trip.user_id}
    if current_user.id not in participants:
        raise HTTPException(status_code=403, detail="Forbidden")
    if proposal.status in {ProposalStatus.ACCEPTED, ProposalStatus.REJECTED, ProposalStatus.CANCELED}:
        raise HTTPException(status_code=400, detail="Proposal already finalized")

    db.add(ProposalBid(proposal_id=proposal.id, bidder_id=current_user.id, value=payload.newBid))
    proposal.current_bid = payload.newBid
    proposal.current_bidder_id = current_user.id
    proposal.status = ProposalStatus.UNDER_NEGOTIATION
    db.commit()
    db.refresh(proposal)
    await push_proposal_update(proposal)
    return serialize_proposal(proposal)


@router.patch("/{proposal_id}/accept", response_model=ProposalResponse)
async def accept_proposal(
    proposal_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProposalResponse:
    proposal = get_proposal_or_404(db, proposal_id)
    if current_user.id not in {proposal.cargo.user_id, proposal.trip.user_id}:
        raise HTTPException(status_code=403, detail="Forbidden")

    finalize_acceptance(db, proposal)
    db.commit()
    db.refresh(proposal)
    await push_proposal_update(proposal)
    return serialize_proposal(proposal)


@router.get("/{proposal_id}/payment", response_model=ProposalPaymentDetailsResponse)
def get_proposal_payment(
    proposal_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProposalPaymentDetailsResponse:
    proposal = get_proposal_or_404(db, proposal_id)
    if current_user.id not in {proposal.cargo.user_id, proposal.trip.user_id}:
        raise HTTPException(status_code=403, detail="Forbidden")
    if proposal.status != ProposalStatus.ACCEPTED:
        raise HTTPException(status_code=400, detail="Proposal payment is available only after acceptance")

    payment = ensure_proposal_payment(db, proposal)
    db.commit()
    db.refresh(proposal)
    return serialize_payment_details(payment, include_delivery_code=current_user.id == proposal.cargo.user_id)


@router.post("/{proposal_id}/payment/preference", response_model=ProposalPaymentDetailsResponse)
async def create_proposal_payment_preference(
    proposal_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProposalPaymentDetailsResponse:
    proposal = get_proposal_or_404(db, proposal_id)
    if current_user.id != proposal.cargo.user_id:
        raise HTTPException(status_code=403, detail="Only the shipper can start freight payment")
    if proposal.status != ProposalStatus.ACCEPTED:
        raise HTTPException(status_code=400, detail="Proposal must be accepted before payment")
    if not mercado_pago_configured():
        raise HTTPException(status_code=503, detail="Mercado Pago is not configured")

    payment = ensure_proposal_payment(db, proposal)
    await create_checkout_preference(payment, proposal, current_user.email)
    db.commit()
    db.refresh(proposal)
    await push_proposal_update(proposal)
    return serialize_payment_details(payment, include_delivery_code=True)


@router.post("/{proposal_id}/payment/sync", response_model=ProposalPaymentDetailsResponse)
async def sync_proposal_payment(
    proposal_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProposalPaymentDetailsResponse:
    proposal = get_proposal_or_404(db, proposal_id)
    if current_user.id not in {proposal.cargo.user_id, proposal.trip.user_id}:
        raise HTTPException(status_code=403, detail="Forbidden")
    if proposal.status != ProposalStatus.ACCEPTED:
        raise HTTPException(status_code=400, detail="Proposal must be accepted before payment sync")

    payment = ensure_proposal_payment(db, proposal)
    if mercado_pago_configured():
        await sync_payment_from_search(payment)
    db.commit()
    db.refresh(proposal)
    await push_proposal_update(proposal)
    return serialize_payment_details(payment, include_delivery_code=current_user.id == proposal.cargo.user_id)


@router.post("/{proposal_id}/payment/release", response_model=ProposalPaymentDetailsResponse)
async def confirm_delivery_and_release_payment(
    proposal_id: uuid.UUID,
    payload: ConfirmDeliveryCodeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProposalPaymentDetailsResponse:
    proposal = get_proposal_or_404(db, proposal_id)
    if current_user.id != proposal.trip.user_id:
        raise HTTPException(status_code=403, detail="Only the trucker can confirm delivery release")

    payment = ensure_proposal_payment(db, proposal)
    validate_payment_release(payment, proposal)
    if payload.deliveryCode.strip() != payment.delivery_code:
        raise HTTPException(status_code=400, detail="Invalid delivery code")

    payment.status = FreightPaymentStatus.RELEASED
    payment.released_at = datetime.utcnow()
    proposal.cargo.status = CargoStatus.DELIVERED
    proposal.trip.status = TripStatus.COMPLETED
    db.commit()
    db.refresh(proposal)
    await push_proposal_update(proposal)
    return serialize_payment_details(payment, include_delivery_code=False)


@router.delete("/{proposal_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_proposal(
    proposal_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    proposal = get_proposal_or_404(db, proposal_id)
    if current_user.id not in {proposal.cargo.user_id, proposal.trip.user_id}:
        raise HTTPException(status_code=403, detail="Forbidden")
    proposal.status = ProposalStatus.CANCELED
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
