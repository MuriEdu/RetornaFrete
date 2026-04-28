"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


role_enum = ENUM("SHIPPER", "TRUCKER", name="role", create_type=False)
account_status_enum = ENUM("ACTIVE", name="accountstatus", create_type=False)
proposal_status_enum = ENUM(
    "PENDING",
    "UNDER_NEGOTIATION",
    "ACCEPTED",
    "REJECTED",
    "CANCELED",
    name="proposalstatus",
    create_type=False,
)
trip_status_enum = ENUM("AVAILABLE", "MATCHED", "CANCELED", "COMPLETED", name="tripstatus", create_type=False)
cargo_status_enum = ENUM("ACTIVE", "MATCHED", "DELIVERED", "CANCELED", name="cargostatus", create_type=False)
freight_payment_status_enum = ENUM(
    "AWAITING_PAYMENT",
    "PENDING",
    "APPROVED",
    "RELEASED",
    "FAILED",
    "CANCELED",
    name="freightpaymentstatus",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    role_enum.create(bind, checkfirst=True)
    account_status_enum.create(bind, checkfirst=True)
    proposal_status_enum.create(bind, checkfirst=True)
    trip_status_enum.create(bind, checkfirst=True)
    cargo_status_enum.create(bind, checkfirst=True)
    freight_payment_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("fullname", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", role_enum, nullable=False),
        sa.Column("account_status", account_status_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "vehicle_types",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
    )
    op.create_index(op.f("ix_vehicle_types_name"), "vehicle_types", ["name"], unique=True)

    op.create_table(
        "municipios",
        sa.Column("ibge_code", sa.Integer(), primary_key=True, autoincrement=False, nullable=False),
        sa.Column("nm_mun", sa.String(length=120), nullable=False),
        sa.Column("sigla_uf", sa.String(length=2), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
    )
    op.create_index(op.f("ix_municipios_nm_mun"), "municipios", ["nm_mun"], unique=False)
    op.create_index(op.f("ix_municipios_sigla_uf"), "municipios", ["sigla_uf"], unique=False)

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("token"),
    )
    op.create_index(op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], unique=False)

    op.create_table(
        "vehicles",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type_id", sa.Integer(), sa.ForeignKey("vehicle_types.id"), nullable=False),
        sa.Column("brand", sa.String(length=120), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("license_plate", sa.String(length=16), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_vehicles_user_id"), "vehicles", ["user_id"], unique=False)

    op.create_table(
        "trips",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(as_uuid=True), sa.ForeignKey("vehicles.id"), nullable=False),
        sa.Column("origin_name", sa.String(length=255), nullable=False),
        sa.Column("destination_name", sa.String(length=255), nullable=False),
        sa.Column("origin_lat", sa.Float(), nullable=False),
        sa.Column("origin_lon", sa.Float(), nullable=False),
        sa.Column("dest_lat", sa.Float(), nullable=False),
        sa.Column("dest_lon", sa.Float(), nullable=False),
        sa.Column("trip_date", sa.Date(), nullable=False),
        sa.Column("price_per_km", sa.Numeric(10, 2), nullable=False),
        sa.Column("status", trip_status_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_trips_user_id"), "trips", ["user_id"], unique=False)

    op.create_table(
        "cargos",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("required_vehicle_type_id", sa.Integer(), sa.ForeignKey("vehicle_types.id"), nullable=False),
        sa.Column("origin_name", sa.String(length=255), nullable=False),
        sa.Column("destination_name", sa.String(length=255), nullable=False),
        sa.Column("origin_lat", sa.Float(), nullable=False),
        sa.Column("origin_lon", sa.Float(), nullable=False),
        sa.Column("dest_lat", sa.Float(), nullable=False),
        sa.Column("dest_lon", sa.Float(), nullable=False),
        sa.Column("trip_date", sa.Date(), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("weight_kg", sa.Float(), nullable=False),
        sa.Column("is_date_flexible", sa.Boolean(), nullable=False),
        sa.Column("status", cargo_status_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_cargos_user_id"), "cargos", ["user_id"], unique=False)

    op.create_table(
        "proposals",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("cargo_id", sa.Uuid(as_uuid=True), sa.ForeignKey("cargos.id"), nullable=False),
        sa.Column("trip_id", sa.Uuid(as_uuid=True), sa.ForeignKey("trips.id"), nullable=False),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("current_bidder_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("initial_value", sa.Numeric(10, 2), nullable=False),
        sa.Column("current_bid", sa.Numeric(10, 2), nullable=False),
        sa.Column("status", proposal_status_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_proposals_cargo_id"), "proposals", ["cargo_id"], unique=False)
    op.create_index(op.f("ix_proposals_trip_id"), "proposals", ["trip_id"], unique=False)

    op.create_table(
        "proposal_bids",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("proposal_id", sa.Uuid(as_uuid=True), sa.ForeignKey("proposals.id"), nullable=False),
        sa.Column("bidder_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("value", sa.Numeric(10, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_proposal_bids_proposal_id"), "proposal_bids", ["proposal_id"], unique=False)

    op.create_table(
        "proposal_payments",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("proposal_id", sa.Uuid(as_uuid=True), sa.ForeignKey("proposals.id"), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("status", freight_payment_status_enum, nullable=False),
        sa.Column("delivery_code", sa.String(length=8), nullable=False),
        sa.Column("mercado_pago_external_reference", sa.String(length=120), nullable=False),
        sa.Column("mercado_pago_preference_id", sa.String(length=120), nullable=True),
        sa.Column("mercado_pago_checkout_url", sa.Text(), nullable=True),
        sa.Column("mercado_pago_sandbox_checkout_url", sa.Text(), nullable=True),
        sa.Column("mercado_pago_payment_id", sa.String(length=120), nullable=True),
        sa.Column("mercado_pago_payment_status", sa.String(length=60), nullable=True),
        sa.Column("mercado_pago_status_detail", sa.String(length=120), nullable=True),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("released_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("proposal_id"),
        sa.UniqueConstraint("mercado_pago_external_reference"),
    )
    op.create_index(op.f("ix_proposal_payments_mercado_pago_payment_id"), "proposal_payments", ["mercado_pago_payment_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_proposal_payments_mercado_pago_payment_id"), table_name="proposal_payments")
    op.drop_table("proposal_payments")

    op.drop_index(op.f("ix_proposal_bids_proposal_id"), table_name="proposal_bids")
    op.drop_table("proposal_bids")

    op.drop_index(op.f("ix_proposals_trip_id"), table_name="proposals")
    op.drop_index(op.f("ix_proposals_cargo_id"), table_name="proposals")
    op.drop_table("proposals")

    op.drop_index(op.f("ix_cargos_user_id"), table_name="cargos")
    op.drop_table("cargos")

    op.drop_index(op.f("ix_trips_user_id"), table_name="trips")
    op.drop_table("trips")

    op.drop_index(op.f("ix_vehicles_user_id"), table_name="vehicles")
    op.drop_table("vehicles")

    op.drop_index(op.f("ix_refresh_tokens_user_id"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.drop_index(op.f("ix_municipios_sigla_uf"), table_name="municipios")
    op.drop_index(op.f("ix_municipios_nm_mun"), table_name="municipios")
    op.drop_table("municipios")

    op.drop_index(op.f("ix_vehicle_types_name"), table_name="vehicle_types")
    op.drop_table("vehicle_types")

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    freight_payment_status_enum.drop(bind, checkfirst=True)
    cargo_status_enum.drop(bind, checkfirst=True)
    trip_status_enum.drop(bind, checkfirst=True)
    proposal_status_enum.drop(bind, checkfirst=True)
    account_status_enum.drop(bind, checkfirst=True)
    role_enum.drop(bind, checkfirst=True)
