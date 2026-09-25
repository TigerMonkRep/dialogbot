"""leads tasks agreements

Revision ID: 477adf47202c
Revises: 501a6eb0eaeb
Create Date: 2026-09-25 21:14:26.958781
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '477adf47202c'
down_revision = '501a6eb0eaeb'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('reception_agreements',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('model', sa.String(length=1), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('monthly_net_minor', sa.Integer(), nullable=False),
    sa.Column('lead_fee_net_minor', sa.Integer(), nullable=False),
    sa.Column('tax_basis_points', sa.Integer(), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("model in ('A','B')", name='ck_reception_agreements_model'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workspace_id', 'version', name='uq_reception_agreements_ws_version')
    )
    op.create_table('leads',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('conversation_id', sa.UUID(), nullable=True),
    sa.Column('contact_name', sa.String(length=200), nullable=False),
    sa.Column('contact_email', sa.String(length=320), nullable=True),
    sa.Column('contact_phone', sa.String(length=40), nullable=True),
    sa.Column('need_summary', sa.Text(), nullable=False),
    sa.Column('qualification_status', sa.String(length=16), nullable=False),
    sa.Column('qualification_reason', sa.String(length=500), nullable=True),
    sa.Column('pipeline_status', sa.String(length=16), nullable=False),
    sa.Column('billing_status', sa.String(length=16), nullable=False),
    sa.Column('billing_decided_by', sa.UUID(), nullable=True),
    sa.Column('billing_decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('billing_reason', sa.String(length=500), nullable=True),
    sa.Column('agreement_id', sa.UUID(), nullable=True),
    sa.Column('fee_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("billing_status in ('pending','approved','rejected')", name='ck_leads_billing'),
    sa.CheckConstraint("pipeline_status in ('new','contacted','won','lost')", name='ck_leads_pipeline'),
    sa.CheckConstraint("qualification_status in ('unqualified','qualified','disqualified')", name='ck_leads_qualification'),
    sa.ForeignKeyConstraint(['agreement_id'], ['reception_agreements.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['billing_decided_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('conversation_id', name='uq_leads_conversation')
    )
    op.create_index('ix_leads_workspace_created', 'leads', ['workspace_id', 'created_at'], unique=False)
    op.create_table('tasks',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('lead_id', sa.UUID(), nullable=True),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('status', sa.String(length=8), nullable=False),
    sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('assignee_user_id', sa.UUID(), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_by', sa.UUID(), nullable=True),
    sa.CheckConstraint("status in ('open','done')", name='ck_tasks_status'),
    sa.ForeignKeyConstraint(['assignee_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['completed_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_tasks_workspace_status_due', 'tasks', ['workspace_id', 'status', 'due_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_tasks_workspace_status_due', table_name='tasks')
    op.drop_table('tasks')
    op.drop_index('ix_leads_workspace_created', table_name='leads')
    op.drop_table('leads')
    op.drop_table('reception_agreements')
