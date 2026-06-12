"""payout accounts and marketplace fees

Revision ID: 0002_payout_accounts_and_fees
Revises: 0001_initial_schema
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM


revision = "0002_payout_accounts_and_fees"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


payout_provider_enum = ENUM("MERCADO_PAGO", "PIX", "BANK", name="payoutprovider", create_type=False)
payout_connection_status_enum = ENUM(
    "DISCONNECTED",
    "CONNECTED",
    "NEEDS_REAUTH",
    name="payoutconnectionstatus",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    payout_provider_enum.create(bind, checkfirst=True)
    payout_connection_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "user_payout_accounts",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("provider", payout_provider_enum, nullable=False),
        sa.Column("status", payout_connection_status_enum, nullable=False),
        sa.Column("account_email", sa.String(length=255), nullable=True),
        sa.Column("oauth_access_token", sa.Text(), nullable=True),
        sa.Column("oauth_refresh_token", sa.Text(), nullable=True),
        sa.Column("oauth_expires_at", sa.DateTime(), nullable=True),
        sa.Column("pix_key", sa.String(length=255), nullable=True),
        sa.Column("bank_name", sa.String(length=120), nullable=True),
        sa.Column("bank_branch", sa.String(length=40), nullable=True),
        sa.Column("bank_account", sa.String(length=40), nullable=True),
        sa.Column("bank_account_type", sa.String(length=20), nullable=True),
        sa.Column("owner_name", sa.String(length=255), nullable=True),
        sa.Column("provider_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_user_payout_accounts_user_id"), "user_payout_accounts", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_payout_accounts_user_id"), table_name="user_payout_accounts")
    op.drop_table("user_payout_accounts")

    bind = op.get_bind()
    payout_connection_status_enum.drop(bind, checkfirst=True)
    payout_provider_enum.drop(bind, checkfirst=True)
