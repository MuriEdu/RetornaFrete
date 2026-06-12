"""proposal payouts

Revision ID: 0003_proposal_payouts
Revises: 0002_payout_accounts_and_fees
Create Date: 2026-05-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM


revision = "0003_proposal_payouts"
down_revision = "0002_payout_accounts_and_fees"
branch_labels = None
depends_on = None


payout_settlement_status_enum = ENUM(
    "READY_FOR_PAYOUT",
    "PAID",
    "FAILED",
    name="payoutsettlementstatus",
    create_type=False,
)
payout_provider_enum = ENUM("MERCADO_PAGO", "PIX", "BANK", name="payoutprovider", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    payout_settlement_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "proposal_payouts",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("proposal_id", sa.Uuid(as_uuid=True), sa.ForeignKey("proposals.id"), nullable=False, unique=True),
        sa.Column("provider", payout_provider_enum, nullable=False),
        sa.Column("status", payout_settlement_status_enum, nullable=False),
        sa.Column("gross_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("platform_fee_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("net_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("destination_snapshot", sa.JSON(), nullable=False),
        sa.Column("released_at", sa.DateTime(), nullable=False),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_proposal_payouts_proposal_id"), "proposal_payouts", ["proposal_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_proposal_payouts_proposal_id"), table_name="proposal_payouts")
    op.drop_table("proposal_payouts")

    bind = op.get_bind()
    payout_settlement_status_enum.drop(bind, checkfirst=True)
