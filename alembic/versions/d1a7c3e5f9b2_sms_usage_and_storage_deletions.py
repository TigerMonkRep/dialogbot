"""sms usage (code SMS the business pays for) and storage deletions (support files follow their rows)

Revision ID: d1a7c3e5f9b2
Revises: c5e1f7a3d9b2
Create Date: 2026-11-13 12:00:00

- sms_usage: one row per code SMS sent from the worker (W04/W13 for the business, the demo-call code for Dialogbot's
  sales workspace). No price: SMS are not priced yet (net_minor NULL).
- storage_deletions + trigger: every deleted support_attachments row (a ticket deleted, a workspace deleted and the
  delete cascading) queues its storage key; the worker removes the object (GDPR, Fürster 13/11).
"""
from alembic import op
import sqlalchemy as sa

revision = 'd1a7c3e5f9b2'
down_revision = 'c5e1f7a3d9b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'sms_usage',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('purpose', sa.String(length=24), nullable=False),
        sa.Column('segments', sa.Integer(), nullable=False),
        sa.Column('simulated', sa.Boolean(), nullable=False),
        sa.Column('provider_ref', sa.String(length=64), nullable=True),
        sa.Column('net_minor', sa.Integer(), nullable=True),
        sa.Column('outbox_event_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("purpose in ('webchat_phone','booking_manage','demo_call_code')", name='ck_sms_usage_purpose'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['outbox_event_id'], ['outbox_events.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('outbox_event_id', name='uq_sms_usage_outbox_event'),
    )
    op.create_index('ix_sms_usage_workspace_created', 'sms_usage', ['workspace_id', 'created_at'])
    op.create_table(
        'storage_deletions',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('storage_key', sa.String(length=250), nullable=False),
        sa.Column('reason', sa.String(length=40), nullable=False),
        sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_error', sa.String(length=200), nullable=True),
        sa.Column('done_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_storage_deletions_pending', 'storage_deletions', ['done_at', 'created_at'])
    # SET search_path FROM CURRENT: the function finds storage_deletions in the schema it was created in (dialogbot in
    # production), whatever the deleting session's search_path is.
    op.execute("""
        CREATE FUNCTION support_attachment_deleted() RETURNS trigger
        LANGUAGE plpgsql SET search_path FROM CURRENT AS $$
        BEGIN
            INSERT INTO storage_deletions (storage_key, reason) VALUES (OLD.storage_key, 'support_attachment');
            RETURN OLD;
        END $$
    """)
    op.execute("""
        CREATE TRIGGER trg_support_attachments_deleted AFTER DELETE ON support_attachments
        FOR EACH ROW EXECUTE FUNCTION support_attachment_deleted()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_support_attachments_deleted ON support_attachments")
    op.execute("DROP FUNCTION IF EXISTS support_attachment_deleted()")
    op.drop_index('ix_storage_deletions_pending', table_name='storage_deletions')
    op.drop_table('storage_deletions')
    op.drop_index('ix_sms_usage_workspace_created', table_name='sms_usage')
    op.drop_table('sms_usage')
