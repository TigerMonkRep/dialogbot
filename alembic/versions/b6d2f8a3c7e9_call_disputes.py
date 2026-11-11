"""call_disputes: complaints about a billed call, the only way minutes are credited

Revision ID: b6d2f8a3c7e9
Revises: a9c4e2f7b5d1
Create Date: 2026-11-10 21:00:00

Decision 2026-11-10 (Fürster): minutes are credited only when the customer complains about a call. One complaint per
call; the operator approves (open month: the minutes go back into the package; invoiced month: a credit line on the
next invoice) or rejects (nothing changes).
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = 'b6d2f8a3c7e9'
down_revision = 'a9c4e2f7b5d1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'call_disputes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=False),
        sa.Column('call_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('calls.id', ondelete='CASCADE'), nullable=True),
        sa.Column('campaign_call_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('campaign_calls.id', ondelete='CASCADE'), nullable=True),
        sa.Column('period', sa.Date(), nullable=False),
        sa.Column('call_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('minutes', sa.Integer(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('decided_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('decision_note', sa.Text(), nullable=False),
        sa.Column('credit_mode', sa.String(length=8), nullable=True),
        sa.Column('credit_net_minor', sa.Integer(), server_default='0', nullable=False),
        sa.CheckConstraint('(call_id is null) <> (campaign_call_id is null)', name='ck_call_disputes_one_call'),
        sa.CheckConstraint("status in ('open','approved','rejected')", name='ck_call_disputes_status'),
        sa.CheckConstraint("credit_mode is null or credit_mode in ('pool','invoice')", name='ck_call_disputes_credit_mode'),
        sa.UniqueConstraint('call_id', name='uq_call_disputes_call'),
        sa.UniqueConstraint('campaign_call_id', name='uq_call_disputes_campaign_call'),
    )
    op.create_index('ix_call_disputes_workspace_status', 'call_disputes', ['workspace_id', 'status'])


def downgrade() -> None:
    op.drop_index('ix_call_disputes_workspace_status', table_name='call_disputes')
    op.drop_table('call_disputes')
