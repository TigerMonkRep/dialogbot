"""demo call verifications: SMS code before Peter rings (F-AUD26-02-P06)

Revision ID: a7d3e9c2b5f1
Revises: 0c1d5e7a9b3f
Create Date: 2026-11-12 21:30:00
"""
from alembic import op
import sqlalchemy as sa

revision = 'a7d3e9c2b5f1'
down_revision = '0c1d5e7a9b3f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'demo_call_verifications',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('language', sa.String(length=5), nullable=False),
        sa.Column('ip_hash', sa.String(length=64), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('token_hash', sa.String(length=64), nullable=True),
        sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('call_ip_hash', sa.String(length=64), nullable=True),
        sa.Column('demo_call_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['demo_call_id'], ['demo_calls.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_demo_call_verifications_phone_sent', 'demo_call_verifications', ['phone', 'sent_at'])
    op.create_index('ix_demo_call_verifications_ip_sent', 'demo_call_verifications', ['ip_hash', 'sent_at'])
    op.create_index('ix_demo_call_verifications_call_ip', 'demo_call_verifications', ['call_ip_hash', 'consumed_at'])
    op.create_index('ix_demo_call_verifications_token', 'demo_call_verifications', ['token_hash'])


def downgrade() -> None:
    op.drop_index('ix_demo_call_verifications_token', table_name='demo_call_verifications')
    op.drop_index('ix_demo_call_verifications_call_ip', table_name='demo_call_verifications')
    op.drop_index('ix_demo_call_verifications_ip_sent', table_name='demo_call_verifications')
    op.drop_index('ix_demo_call_verifications_phone_sent', table_name='demo_call_verifications')
    op.drop_table('demo_call_verifications')
