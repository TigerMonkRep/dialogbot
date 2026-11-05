"""private appointments

Revision ID: f5a9c2d7e3b1
Revises: e4f8b1c6d2a9
Create Date: 2026-11-05 10:00:00

The Kalender app: `private_appointments` holds the times the user approved (a call the business confirmed, a confirmed
browser booking, or a time the user told the assistant), and `private_profiles` gets the hash of the secret calendar
subscription link.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'f5a9c2d7e3b1'
down_revision = 'e4f8b1c6d2a9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'private_appointments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('task_id', sa.UUID(), nullable=True),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column('source_ref', sa.String(length=80), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('location', sa.String(length=300), server_default='', nullable=False),
        sa.Column('notes', sa.Text(), server_default='', nullable=False),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=16), server_default='confirmed', nullable=False),
        sa.Column('sequence', sa.Integer(), server_default='0', nullable=False),
        sa.Column('external', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("source in ('call','browser','manual')", name='ck_private_appointments_source'),
        sa.CheckConstraint("status in ('confirmed','cancelled')", name='ck_private_appointments_status'),
        sa.CheckConstraint('ends_at > starts_at', name='ck_private_appointments_range'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name='fk_private_appointments_workspace_id',
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['private_tasks.id'], name='fk_private_appointments_task_id',
                                ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name='pk_private_appointments'),
        sa.UniqueConstraint('source_ref', name='uq_private_appointments_source_ref'),
    )
    op.create_index('ix_private_appointments_ws_starts', 'private_appointments', ['workspace_id', 'starts_at'])
    op.add_column('private_profiles', sa.Column('calendar_feed_token_hash', sa.String(length=64), nullable=True))
    op.add_column('private_profiles', sa.Column('calendar_feed_created_at', sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint('uq_private_profiles_calendar_feed_token_hash', 'private_profiles',
                                ['calendar_feed_token_hash'])


def downgrade() -> None:
    op.drop_constraint('uq_private_profiles_calendar_feed_token_hash', 'private_profiles', type_='unique')
    op.drop_column('private_profiles', 'calendar_feed_created_at')
    op.drop_column('private_profiles', 'calendar_feed_token_hash')
    op.drop_index('ix_private_appointments_ws_starts', table_name='private_appointments')
    op.drop_table('private_appointments')
