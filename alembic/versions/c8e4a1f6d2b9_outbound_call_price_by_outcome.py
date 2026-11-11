"""outbound call price by outcome after the package (Fürster 2026-11-10 20:28)

Revision ID: c8e4a1f6d2b9
Revises: b6d2f8a3c7e9
Create Date: 2026-11-10 22:00:00

- reception_agreements: outbound_call_answered/voicemail/no_answer_net_minor – the price of an outbound call that
  starts after the package is used up (4 kr. / 1 kr. / 0,25 kr. and the markets' equivalents). Backfill by currency.
- campaign_calls.outcome_class: 'answered' | 'voicemail' | 'no_answer' (NULL = no report yet, billed as no_answer).
  Backfill from what is stored: connected_seconds > 0 → answered, a report without a conversation → no_answer.
"""
import sqlalchemy as sa

from alembic import op

revision = 'c8e4a1f6d2b9'
down_revision = 'b6d2f8a3c7e9'
branch_labels = None
depends_on = None

PRICES = {"answered": (400, 590, 630, 55), "voicemail": (100, 150, 160, 14), "no_answer": (25, 35, 40, 3)}


def upgrade() -> None:
    for k, (dkk, sek, nok, eur) in PRICES.items():
        col = f"outbound_call_{k}_net_minor"
        op.add_column('reception_agreements', sa.Column(col, sa.Integer(), nullable=True))
        op.execute(f"update reception_agreements set {col} = case currency when 'SEK' then {sek} when 'NOK' then {nok} "
                   f"when 'EUR' then {eur} else {dkk} end")
        op.alter_column('reception_agreements', col, nullable=False)
    op.add_column('campaign_calls', sa.Column('outcome_class', sa.String(length=12), nullable=True))
    op.execute("update campaign_calls set outcome_class = case when connected_seconds > 0 then 'answered' "
               "when connected_seconds is not null then 'no_answer' end")
    op.create_check_constraint('ck_campaign_calls_outcome_class', 'campaign_calls',
                               "outcome_class is null or outcome_class in ('answered','voicemail','no_answer')")


def downgrade() -> None:
    op.drop_constraint('ck_campaign_calls_outcome_class', 'campaign_calls', type_='check')
    op.drop_column('campaign_calls', 'outcome_class')
    for k in PRICES:
        op.drop_column('reception_agreements', f"outbound_call_{k}_net_minor")
