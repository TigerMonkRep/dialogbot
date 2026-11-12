"""billing: 7 days' grace when an Erhverv subscription stops being paid (Fürster 12/11)

When a paid subscription stops being paid – the card expired or was removed, or a payment failed – the chat and the
phone keep running for 7 days while the owner is mailed (at the start, after about 3 days and the day before the stop).
A subscription that was never paid gets no grace.

- first_paid_at      the first time the subscription was seen paid (never paid = null = no grace)
- unpaid_since       when it stopped being paid (the grace runs from here); null while paid
- payment_failed_at  the last failed payment (Stripe invoice.payment_failed); cleared by a paid invoice or a new card
- grace_mails        how many of the three grace mails have been queued

Existing customers with a saved card and a confirmed subscription count as paid from now on.

Revision ID: d2b7e4a9c1f6
Revises: c4e7a2d91f38
Create Date: 2026-11-12
"""
import sqlalchemy as sa

from alembic import op

revision = 'd2b7e4a9c1f6'
down_revision = 'c4e7a2d91f38'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("billing_accounts", sa.Column("first_paid_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("billing_accounts", sa.Column("unpaid_since", sa.DateTime(timezone=True), nullable=True))
    op.add_column("billing_accounts", sa.Column("payment_failed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("billing_accounts", sa.Column("grace_mails", sa.SmallInteger(), nullable=False, server_default="0"))
    op.create_check_constraint("ck_billing_accounts_grace_mails", "billing_accounts", "grace_mails between 0 and 3")
    op.execute("""
        update billing_accounts b set first_paid_at = now()
        where b.payment_method_id is not null
          and exists (select 1 from reception_agreements a where a.workspace_id = b.workspace_id
                      and a.version = (select max(a2.version) from reception_agreements a2 where a2.workspace_id = b.workspace_id)
                      and a.model <> 'B')
    """)


def downgrade() -> None:
    op.drop_constraint("ck_billing_accounts_grace_mails", "billing_accounts", type_="check")
    op.drop_column("billing_accounts", "grace_mails")
    op.drop_column("billing_accounts", "payment_failed_at")
    op.drop_column("billing_accounts", "unpaid_since")
    op.drop_column("billing_accounts", "first_paid_at")
