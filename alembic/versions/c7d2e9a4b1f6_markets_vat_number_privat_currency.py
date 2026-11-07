"""markets: the company's VAT number and the Privat subscription's currency

Revision ID: c7d2e9a4b1f6
Revises: f3a9c1d5e7b2
Create Date: 2026-11-07 18:00:00

Additive, both nullable (app/modules/billing/markets.py, docs/markets.md):
- billing_accounts.vat_number: an EU company outside Denmark is invoiced without VAT (reverse charge) only with one.
- private_subscriptions.currency: set at the first Checkout from the visitor's language; existing rows stay null and
  are read as DKK (every existing Privat customer paid in DKK).
"""
import sqlalchemy as sa

from alembic import op

revision = 'c7d2e9a4b1f6'
down_revision = 'f3a9c1d5e7b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('billing_accounts', sa.Column('vat_number', sa.String(length=32), nullable=True))
    op.add_column('private_subscriptions', sa.Column('currency', sa.String(length=3), nullable=True))


def downgrade() -> None:
    op.drop_column('private_subscriptions', 'currency')
    op.drop_column('billing_accounts', 'vat_number')
