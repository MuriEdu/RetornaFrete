import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import Cargo, CargoStatus, Proposal, ProposalBid, ProposalStatus, Role, Trip, TripStatus, User
from app.routers.matches import haversine_km, is_trip_date_compatible
from app.schemas import CreateProposalRequest, NegotiateProposalRequest, ProposalActionRequest, ProposalResponse
from app.services.notifications import notification_manager

router = APIRouter(prefix="/api/proposals", tags=["proposals"])


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
        proposal.status = ProposalStatus.ACCEPTED
        proposal.trip.status = TripStatus.MATCHED
        proposal.cargo.status = CargoStatus.MATCHED

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

    proposal.status = ProposalStatus.ACCEPTED
    proposal.trip.status = TripStatus.MATCHED
    proposal.cargo.status = CargoStatus.MATCHED
    db.commit()
    db.refresh(proposal)
    await push_proposal_update(proposal)
    return serialize_proposal(proposal)


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
