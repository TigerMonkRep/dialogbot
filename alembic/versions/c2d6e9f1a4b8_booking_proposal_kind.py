"""chat message kind booking_proposal

Revision ID: c2d6e9f1a4b8
Revises: b7c1d4e8f2a3
Create Date: 2026-11-04 22:00:00

A booking on a business's own website that waits for the user's yes (Godkend/Afvis) is its own chat message kind, not a
«draft» (a task saved as a draft, whose card opens the paywall). Telling them apart by their options would break the day
somebody adds buttons to a payment draft.
"""
from alembic import op

revision = 'c2d6e9f1a4b8'
down_revision = 'b7c1d4e8f2a3'
branch_labels = None
depends_on = None

OLD = "kind in ('text','task','move','clarify','call_proposal','draft','waiting','addon','share_proposal')"
NEW = "kind in ('text','task','move','clarify','call_proposal','draft','waiting','addon','share_proposal','booking_proposal')"


def upgrade() -> None:
    op.drop_constraint('ck_private_messages_kind', 'private_messages', type_='check')
    op.create_check_constraint('ck_private_messages_kind', 'private_messages', NEW)


def downgrade() -> None:
    op.execute("update private_messages set kind = 'clarify' where kind = 'booking_proposal'")
    op.drop_constraint('ck_private_messages_kind', 'private_messages', type_='check')
    op.create_check_constraint('ck_private_messages_kind', 'private_messages', OLD)
