"""billing: remember the refunds and credit notes seen per invoice, so commission is reduced by the delta once

Revision ID: c5e9f3a7b2d4
Revises: b4d8e2f6a1c3
Create Date: 2026-11-10 13:00:00

Additive: `invoices.refunds` JSONB {"charges": {charge_id: cumulative amount_refunded}, "credit_notes": {id: total},
"applied_minor": refunded amount already taken off the commission}. QA F-BQ-008-B06.
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = 'c5e9f3a7b2d4'
down_revision = 'b4d8e2f6a1c3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('invoices', sa.Column('refunds', postgresql.JSONB(astext_type=sa.Text()), server_default='{}',
                                        nullable=False))


def downgrade() -> None:
    op.drop_column('invoices', 'refunds')
