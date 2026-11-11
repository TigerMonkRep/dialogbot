"""privat: credits → «Opkaldssaldo» in kroner (Fürster's decision 2026-11-11, F-PDEC-01)

credit_ledger.amount becomes øre (minor units of the row's currency) instead of a number of credits: every existing
row is converted at 1 credit = 2,90 kr. (29 kr. for 10) = 290 øre, in DKK (the credits were bought and granted as
Danish credits). A new `currency` column says whose minor units a row holds (an account's balance is in its Privat
currency – app/modules/privat/ledger.py). New kind 'convert' (a balance moved to the customer's currency at its first
foreign checkout). The payment markers lose the word too: private_calls.paid_via 'credits' → 'balance',
private_tasks.paid_by 'credit' → 'balance'.

Downgrade: back to whole credits (amount / 290, rounded); rows in another currency than DKK and 'convert' rows are
deleted first. Exact for the converted rows, rounded for movements made after the upgrade.

Revision ID: f3a8c6d2b5e9
Revises: d7f2b9c4e1a8
Create Date: 2026-11-11
"""
import sqlalchemy as sa

from alembic import op

revision = 'f3a8c6d2b5e9'
down_revision = 'd7f2b9c4e1a8'
branch_labels = None
depends_on = None

CREDIT_MINOR = 290  # 1 credit = 2,90 kr. (29 kr. / 10) – Fürster's conversion rate
KINDS_OLD = "kind in ('grant','purchase','reserve','capture','release','spend','sponsor','referral')"
KINDS_NEW = "kind in ('grant','purchase','reserve','capture','release','spend','sponsor','referral','convert')"


def upgrade() -> None:
    op.add_column('credit_ledger', sa.Column('currency', sa.String(length=3), server_default='DKK', nullable=False))
    op.execute(f"update credit_ledger set amount = amount * {CREDIT_MINOR}")
    op.drop_constraint('ck_credit_ledger_kind', 'credit_ledger', type_='check')
    op.create_check_constraint('ck_credit_ledger_kind', 'credit_ledger', KINDS_NEW)
    op.create_check_constraint('ck_credit_ledger_currency', 'credit_ledger', "currency in ('DKK','SEK','NOK','EUR')")

    op.drop_constraint('ck_private_calls_paid_via', 'private_calls', type_='check')
    op.execute("update private_calls set paid_via = 'balance' where paid_via = 'credits'")
    op.create_check_constraint('ck_private_calls_paid_via', 'private_calls',
                               "paid_via is null or paid_via in ('balance','plan')")
    op.drop_constraint('ck_private_tasks_paid_by', 'private_tasks', type_='check')
    op.execute("update private_tasks set paid_by = 'balance' where paid_by = 'credit'")
    op.create_check_constraint('ck_private_tasks_paid_by', 'private_tasks',
                               "paid_by in ('free','balance','sponsor','none','call','plan')")


def downgrade() -> None:
    op.drop_constraint('ck_private_tasks_paid_by', 'private_tasks', type_='check')
    op.execute("update private_tasks set paid_by = 'credit' where paid_by = 'balance'")
    op.create_check_constraint('ck_private_tasks_paid_by', 'private_tasks',
                               "paid_by in ('free','credit','sponsor','none','call','plan')")
    op.drop_constraint('ck_private_calls_paid_via', 'private_calls', type_='check')
    op.execute("update private_calls set paid_via = 'credits' where paid_via = 'balance'")
    op.create_check_constraint('ck_private_calls_paid_via', 'private_calls',
                               "paid_via is null or paid_via in ('credits','plan')")

    op.execute("delete from credit_ledger where kind = 'convert' or currency <> 'DKK'")
    op.drop_constraint('ck_credit_ledger_currency', 'credit_ledger', type_='check')
    op.drop_constraint('ck_credit_ledger_kind', 'credit_ledger', type_='check')
    op.create_check_constraint('ck_credit_ledger_kind', 'credit_ledger', KINDS_OLD)
    op.execute(f"update credit_ledger set amount = round(amount::numeric / {CREDIT_MINOR})::integer")
    op.drop_column('credit_ledger', 'currency')
