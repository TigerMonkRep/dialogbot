"""bookings: honest calendar sync state for bookings mirrored to a connected Google/Microsoft calendar

Revision ID: b4d8e2f6a1c3
Revises: a7c3e9f1b2d4
Create Date: 2026-11-10 12:00:00

Additive: `calendar_sync` (NULL = no connected calendar, 'synced', 'failed') and the last sync error on bookings.
QA F-EB-04-W12 / F-EB-05-BK15.
"""
import sqlalchemy as sa

from alembic import op

revision = 'b4d8e2f6a1c3'
down_revision = 'a7c3e9f1b2d4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('bookings', sa.Column('calendar_sync', sa.String(length=16), nullable=True))
    op.add_column('bookings', sa.Column('calendar_sync_error', sa.String(length=300), nullable=True))
    op.create_check_constraint('ck_bookings_calendar_sync', 'bookings',
                               "calendar_sync is null or calendar_sync in ('synced','failed')")


def downgrade() -> None:
    op.drop_constraint('ck_bookings_calendar_sync', 'bookings', type_='check')
    op.drop_column('bookings', 'calendar_sync_error')
    op.drop_column('bookings', 'calendar_sync')
