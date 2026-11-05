"""assistant pronoun

Revision ID: e2a7c4d9f1b3
Revises: d1f6b3a8e4c9
Create Date: 2026-11-06 10:00:00

How the Privat texts refer to the assistant the user named: han, hun or den (private_profiles.assistant_pronoun).
"""
from alembic import op
import sqlalchemy as sa


revision = 'e2a7c4d9f1b3'
down_revision = 'd1f6b3a8e4c9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('private_profiles', sa.Column('assistant_pronoun', sa.String(length=4), nullable=True))


def downgrade() -> None:
    op.drop_column('private_profiles', 'assistant_pronoun')
