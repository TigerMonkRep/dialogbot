"""sales channel phase 4

Revision ID: e6f8a0b2c4d7
Revises: d5e7f9a1b3c6
Create Date: 2026-10-30 15:26:02.546301
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'e6f8a0b2c4d7'
down_revision = 'd5e7f9a1b3c6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('sales_data_requests',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('subject', sa.String(length=8), nullable=False),
    sa.Column('value', sa.String(length=320), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('handled_by', sa.UUID(), nullable=True),
    sa.Column('handled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind in ('access','erasure','objection')", name='ck_sales_data_requests_kind'),
    sa.CheckConstraint("status in ('open','done','rejected')", name='ck_sales_data_requests_status'),
    sa.CheckConstraint("subject in ('phone','email','cvr')", name='ck_sales_data_requests_subject'),
    sa.ForeignKeyConstraint(['handled_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('call_recordings',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('call_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.String(length=14), nullable=False),
    sa.Column('storage_key', sa.String(length=300), nullable=True),
    sa.Column('bytes', sa.Integer(), nullable=True),
    sa.Column('duration_seconds', sa.Integer(), nullable=True),
    sa.Column('content_type', sa.String(length=60), nullable=True),
    sa.Column('provider_ref', sa.String(length=100), nullable=True),
    sa.Column('available_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('delete_reason', sa.String(length=200), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status in ('PENDING','AVAILABLE','FAILED','NOT_RECORDED','DELETED')", name='ck_call_recordings_status'),
    sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('call_id')
    )
    op.create_table('sales_media_access_log',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('call_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('kind', sa.String(length=8), nullable=False),
    sa.Column('at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind in ('play','export')", name='ck_sales_media_access_log_kind'),
    sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_sales_media_access_log_call', 'sales_media_access_log', ['call_id', 'at'], unique=False)
    op.add_column('campaigns', sa.Column('recording_enabled', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('users', sa.Column('can_export_media', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('users', 'can_export_media')
    op.drop_column('campaigns', 'recording_enabled')
    op.drop_index('ix_sales_media_access_log_call', table_name='sales_media_access_log')
    op.drop_table('sales_media_access_log')
    op.drop_table('call_recordings')
    op.drop_table('sales_data_requests')
