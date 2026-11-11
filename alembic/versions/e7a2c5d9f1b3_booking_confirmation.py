"""bookings: «afventer bekræftelse» when the connected calendar's busy time could not be read

Revision ID: e7a2c5d9f1b3
Revises: d6f1a4b8c3e5
Create Date: 2026-11-10 18:00:00

Additive: `bookings.confirmation` (NULL = booked against readable busy time, as before; 'pending' = made while the
connected Google/Microsoft calendar could not be read – awaits a staff member; 'confirmed' = confirmed by staff).
Decision 2026-11-10 (Fürster) on F-EB-05-BK15: fail-open with «afventer bekræftelse».
"""
import sqlalchemy as sa

from alembic import op

revision = 'e7a2c5d9f1b3'
down_revision = 'd6f1a4b8c3e5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('bookings', sa.Column('confirmation', sa.String(length=16), nullable=True))
    op.create_check_constraint('ck_bookings_confirmation', 'bookings',
                               "confirmation is null or confirmation in ('pending','confirmed')")


def downgrade() -> None:
    op.drop_constraint('ck_bookings_confirmation', 'bookings', type_='check')
    op.drop_column('bookings', 'confirmation')
