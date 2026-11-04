"""quiz-funnel drafts

Revision ID: f1a2b3c4d5e6
Revises: e5a7c9d1b3f6
Create Date: 2026-11-04 21:00:00

The quiz-funnels on /start (Erhverv) and /privat/start (Privat): funnel_drafts holds a visitor's answers and what was
built for them before they have an account; users.phone_verified_at records the SMS proof the funnel sign-up rests
on; demo_calls.context carries the company facts the receptionist may use in the demo call it places at verify.
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = 'f1a2b3c4d5e6'
down_revision = 'e5a7c9d1b3f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('funnel_drafts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('hook', sa.String(length=80), nullable=True),
    sa.Column('industry', sa.String(length=40), nullable=True),
    sa.Column('utm', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('step', sa.Integer(), nullable=False),
    sa.Column('answers', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('company', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('estimate', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('build', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('place_id', sa.String(length=320), nullable=True),
    sa.Column('website', sa.String(length=500), nullable=True),
    sa.Column('gate', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('code_hash', sa.String(length=64), nullable=True),
    sa.Column('code_attempts', sa.Integer(), server_default='0', nullable=False),
    sa.Column('code_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('code_sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('workspace_id', sa.UUID(), nullable=True),
    sa.Column('demo_call_id', sa.UUID(), nullable=True),
    sa.Column('crawl_job_ref', sa.String(length=80), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("kind in ('erhverv','privat')", name='ck_funnel_drafts_kind'),
    sa.ForeignKeyConstraint(['demo_call_id'], ['demo_calls.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_funnel_drafts_expires', 'funnel_drafts', ['expires_at'], unique=False)
    op.add_column('users', sa.Column('phone_verified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('demo_calls', sa.Column('context', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('demo_calls', 'context')
    op.drop_column('users', 'phone_verified_at')
    op.drop_index('ix_funnel_drafts_expires', table_name='funnel_drafts')
    op.drop_table('funnel_drafts')
