"""discount codes

Revision ID: a3d7e1f9c2b4
Revises: f1a2b3c4d5e6
Create Date: 2026-11-04 18:10:00

Operators make discount codes in the admin for Erhverv, Privat or both. discount_codes holds the code and its terms
(percent or amount, once / N months / forever, a cap, a window) plus the Stripe coupon and promotion code that
carry it on Privat's Checkout; discount_redemptions records which workspace used which code (once per workspace).
"""
import sqlalchemy as sa

from alembic import op

revision = 'a3d7e1f9c2b4'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('discount_codes',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('code', sa.String(length=40), nullable=False),
    sa.Column('audience', sa.String(length=10), nullable=False),
    sa.Column('percent_off', sa.Integer(), nullable=True),
    sa.Column('amount_off_minor', sa.Integer(), nullable=True),
    sa.Column('duration', sa.String(length=10), nullable=False),
    sa.Column('duration_months', sa.Integer(), nullable=True),
    sa.Column('max_redemptions', sa.Integer(), nullable=True),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('note', sa.String(length=300), nullable=False),
    sa.Column('stripe_coupon_id', sa.String(length=64), nullable=True),
    sa.Column('stripe_promotion_code_id', sa.String(length=64), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("audience in ('erhverv','privat','begge')", name='ck_discount_codes_audience'),
    sa.CheckConstraint("duration in ('once','repeating','forever')", name='ck_discount_codes_duration'),
    sa.CheckConstraint('(percent_off is null) <> (amount_off_minor is null)', name='ck_discount_codes_one_value'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_table('discount_redemptions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('code_id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('audience', sa.String(length=10), nullable=False),
    sa.Column('source', sa.String(length=30), nullable=False),
    sa.Column('stripe_ref', sa.String(length=80), nullable=True),
    sa.Column('redeemed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['code_id'], ['discount_codes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code_id', 'workspace_id', name='uq_discount_redemptions_ws')
    )
    op.create_index('ix_discount_redemptions_code_id', 'discount_redemptions', ['code_id'], unique=False)
    op.create_index('ix_discount_redemptions_workspace_id', 'discount_redemptions', ['workspace_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_discount_redemptions_workspace_id', table_name='discount_redemptions')
    op.drop_index('ix_discount_redemptions_code_id', table_name='discount_redemptions')
    op.drop_table('discount_redemptions')
    op.drop_table('discount_codes')
