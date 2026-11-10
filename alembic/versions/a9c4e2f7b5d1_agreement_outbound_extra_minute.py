"""reception_agreements: outbound overage price in the package snapshot (shared package, no per-call fee)

Revision ID: a9c4e2f7b5d1
Revises: f3b8d1e6a4c2
Create Date: 2026-11-10 20:00:00

Decision 2026-11-10 (Fürster): one package of 300 minutes a month that inbound and outbound (campaign) minutes draw on
together; above it 1,50 kr. inbound / 2 kr. outbound per started minute; no 4 kr. fee per outbound call.
`inbound_included_minutes` now holds the shared package (name kept). Backfill of the new column: the market's
equivalent of 2 kr. (200 øre / 2,95 SEK / 3,15 NOK / 0,27 EUR) – the campaign minute price these agreements had.
"""
import sqlalchemy as sa

from alembic import op

revision = 'a9c4e2f7b5d1'
down_revision = 'f3b8d1e6a4c2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('reception_agreements', sa.Column('outbound_extra_minute_net_minor', sa.Integer(), nullable=True))
    op.execute("update reception_agreements set outbound_extra_minute_net_minor = "
               "case currency when 'SEK' then 295 when 'NOK' then 315 when 'EUR' then 27 else 200 end")
    op.alter_column('reception_agreements', 'outbound_extra_minute_net_minor', nullable=False)


def downgrade() -> None:
    op.drop_column('reception_agreements', 'outbound_extra_minute_net_minor')
