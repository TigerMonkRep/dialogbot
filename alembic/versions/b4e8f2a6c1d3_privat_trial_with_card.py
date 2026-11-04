"""privat: the trial starts at Stripe with a card; accounts begin without rights

Revision ID: b4e8f2a6c1d3
Revises: a3d7e1f9c2b4
Create Date: 2026-11-04 20:00:00

private_subscriptions.status gains 'none': a new account has a row without rights (the free tier sees lists shared
with it and nothing else) until the 14-day trial starts at Stripe Checkout, with a card. Existing card-less trial rows
keep running until they expire.
"""
from alembic import op

revision = 'b4e8f2a6c1d3'
down_revision = 'a3d7e1f9c2b4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint('ck_private_subscriptions_status', 'private_subscriptions', type_='check')
    op.create_check_constraint('ck_private_subscriptions_status', 'private_subscriptions',
                               "status in ('none','trial','active','past_due','canceled')")


def downgrade() -> None:
    op.execute("update private_subscriptions set status = 'trial' where status = 'none'")
    op.drop_constraint('ck_private_subscriptions_status', 'private_subscriptions', type_='check')
    op.create_check_constraint('ck_private_subscriptions_status', 'private_subscriptions',
                               "status in ('trial','active','past_due','canceled')")
