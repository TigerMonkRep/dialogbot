"""browser runs and booking profiles

Revision ID: b7c1d4e8f2a3
Revises: b4e8f2a6c1d3
Create Date: 2026-11-04 21:00:00

browser_runs: one tethered browser run per Privat task attempt (status, steps, before->after, evidence keys).
business_booking_profiles: which booking engine a business uses (public information, found once from its website).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'b7c1d4e8f2a3'
down_revision = 'b4e8f2a6c1d3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('business_booking_profiles',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('website_host', sa.String(length=253), nullable=False),
    sa.Column('website', sa.String(length=500), nullable=False),
    sa.Column('cvr', sa.String(length=8), nullable=True),
    sa.Column('phone_e164', sa.String(length=20), nullable=True),
    sa.Column('engine', sa.String(length=32), nullable=False),
    sa.Column('booking_url', sa.String(length=1000), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('detected_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('website_host')
    )
    op.create_index('ix_business_booking_profiles_cvr', 'business_booking_profiles', ['cvr'], unique=False)
    op.create_index('ix_business_booking_profiles_phone', 'business_booking_profiles', ['phone_e164'], unique=False)
    op.create_table('browser_runs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('task_id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('engine', sa.String(length=32), nullable=False),
    sa.Column('mode', sa.String(length=12), nullable=True),
    sa.Column('allowed_domains', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('goal', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('steps', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('before_after', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('evidence_urls', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('max_steps', sa.Integer(), server_default='25', nullable=False),
    sa.Column('max_seconds', sa.Integer(), server_default='180', nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('awaiting_since', sa.DateTime(timezone=True), nullable=True),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error_code', sa.String(length=40), nullable=True),
    sa.Column('cost_cents', sa.Integer(), server_default='0', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("mode is null or mode in ('playbook','llm')", name='ck_browser_runs_mode'),
    sa.CheckConstraint("status in ('planned','running','awaiting_approval','approved','done','failed','fallback_phone')", name='ck_browser_runs_status'),
    sa.ForeignKeyConstraint(['task_id'], ['private_tasks.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_browser_runs_task', 'browser_runs', ['task_id'], unique=False)
    op.create_index('ix_browser_runs_ws_status', 'browser_runs', ['workspace_id', 'status'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_browser_runs_ws_status', table_name='browser_runs')
    op.drop_index('ix_browser_runs_task', table_name='browser_runs')
    op.drop_table('browser_runs')
    op.drop_index('ix_business_booking_profiles_phone', table_name='business_booking_profiles')
    op.drop_index('ix_business_booking_profiles_cvr', table_name='business_booking_profiles')
    op.drop_table('business_booking_profiles')
