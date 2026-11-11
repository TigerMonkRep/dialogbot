"""reception_agreements: snapshot of the package (included inbound minutes + inbound overage price)

Revision ID: f3b8d1e6a4c2
Revises: e7a2c5d9f1b3
Create Date: 2026-11-10 19:00:00

QA F-BQ-011-B05: the agreement snapshotted only the monthly price; the statement read the package and the overage
price from the list at the time the statement was made, so a list change rewrote every not-yet-invoiced month.
Backfill: existing agreements get the list prices in force today (300 minutes; 1,50 kr. / 2,20 SEK / 2,35 NOK /
0,20 EUR per started minute) – the prices they have been billed at so far.
"""
import sqlalchemy as sa

from alembic import op

revision = 'f3b8d1e6a4c2'
down_revision = 'e7a2c5d9f1b3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('reception_agreements', sa.Column('inbound_included_minutes', sa.Integer(), nullable=True))
    op.add_column('reception_agreements', sa.Column('inbound_extra_minute_net_minor', sa.Integer(), nullable=True))
    op.execute("update reception_agreements set inbound_included_minutes = 300, inbound_extra_minute_net_minor = "
               "case currency when 'SEK' then 220 when 'NOK' then 235 when 'EUR' then 20 else 150 end")
    op.alter_column('reception_agreements', 'inbound_included_minutes', nullable=False)
    op.alter_column('reception_agreements', 'inbound_extra_minute_net_minor', nullable=False)


def downgrade() -> None:
    op.drop_column('reception_agreements', 'inbound_extra_minute_net_minor')
    op.drop_column('reception_agreements', 'inbound_included_minutes')
