"""USD: the Opkaldssaldo's ledger accepts dollars (the US site, /us)

Revision ID: 2e3f7a9c1d5b
Revises: 1d2e6f8b0c4a, a7d3e9c1b5f2 (joins the two heads main got from #217 and #218)
Create Date: 2026-11-13 12:00:00
"""
from alembic import op

revision = '2e3f7a9c1d5b'
down_revision = ('1d2e6f8b0c4a', 'a7d3e9c1b5f2')
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint('ck_credit_ledger_currency', 'credit_ledger', type_='check')
    op.create_check_constraint('ck_credit_ledger_currency', 'credit_ledger', "currency in ('DKK','SEK','NOK','EUR','USD')")


def downgrade() -> None:
    op.drop_constraint('ck_credit_ledger_currency', 'credit_ledger', type_='check')
    op.create_check_constraint('ck_credit_ledger_currency', 'credit_ledger', "currency in ('DKK','SEK','NOK','EUR')")
