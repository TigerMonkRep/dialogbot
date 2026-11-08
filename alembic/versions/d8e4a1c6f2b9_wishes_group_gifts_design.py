"""wishes: product details on wishlist items, group gifts («Deles om en gave») and a design per wishlist

Revision ID: d8e4a1c6f2b9
Revises: c7d2e9a4b1f6
Create Date: 2026-11-08 12:00:00

Additive and backward compatible (docs/privat-api.md «Ønsker, fællesgaver og design»):
- private_task_items: optional product fields (price in minor units + currency, price source and fetch time, shop,
  size/colour/variant, quantity default 1, stored image, product details as data), the owner's «Tillad fællesgave»
  setting with its proposed target, and archived_at (a wish deleted while givers had an agreement on it).
  Existing items keep working unchanged: quantity 1, everything else null/false.
- private_tasks.design: the wishlist's theme and overrides (null = the default theme).
- private_group_gifts / private_gift_pledges: the givers' agreement (target frozen at the first pledge) and one
  pledge row per giver. No money moves anywhere.
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = 'd8e4a1c6f2b9'
down_revision = 'c7d2e9a4b1f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    add = lambda c: op.add_column('private_task_items', c)  # noqa: E731
    add(sa.Column('quantity', sa.Integer(), server_default='1', nullable=False))
    add(sa.Column('price_minor', sa.BigInteger(), nullable=True))
    add(sa.Column('currency', sa.String(length=3), nullable=True))
    add(sa.Column('price_source', sa.String(length=8), nullable=True))
    add(sa.Column('price_fetched_at', sa.DateTime(timezone=True), nullable=True))
    add(sa.Column('shop', sa.String(length=120), nullable=True))
    add(sa.Column('size', sa.String(length=80), nullable=True))
    add(sa.Column('color', sa.String(length=80), nullable=True))
    add(sa.Column('variant', sa.String(length=120), nullable=True))
    add(sa.Column('image_key', sa.String(length=200), nullable=True))
    add(sa.Column('image_origin', sa.String(length=8), nullable=True))
    add(sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    add(sa.Column('group_gift_enabled', sa.Boolean(), server_default='false', nullable=False))
    add(sa.Column('group_gift_target_minor', sa.BigInteger(), nullable=True))
    add(sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('private_tasks', sa.Column('design', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.create_table(
        'private_group_gifts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('item_id', sa.Uuid(), nullable=False),
        sa.Column('task_id', sa.Uuid(), nullable=False),
        sa.Column('target_minor', sa.BigInteger(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('cancel_reason', sa.String(length=32), nullable=True),
        sa.Column('coordinator_user_id', sa.Uuid(), nullable=True),
        sa.Column('pending_coordinator_user_id', sa.Uuid(), nullable=True),
        sa.Column('bought_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("status in ('open','bought','cancelled')", name='ck_private_group_gifts_status'),
        sa.CheckConstraint('target_minor > 0', name='ck_private_group_gifts_target'),
        sa.ForeignKeyConstraint(['item_id'], ['private_task_items.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['private_tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['coordinator_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['pending_coordinator_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_private_group_gifts_task', 'private_group_gifts', ['task_id'])
    op.create_index('uq_private_group_gifts_live_item', 'private_group_gifts', ['item_id'], unique=True,
                    postgresql_where=sa.text("status <> 'cancelled'"))
    op.create_table(
        'private_gift_pledges',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('gift_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('amount_minor', sa.BigInteger(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('amount_minor > 0', name='ck_private_gift_pledges_amount'),
        sa.CheckConstraint("status in ('active','cancelled')", name='ck_private_gift_pledges_status'),
        sa.ForeignKeyConstraint(['gift_id'], ['private_group_gifts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('gift_id', 'user_id', name='uq_private_gift_pledges_gift_user'),
    )
    op.create_index('ix_private_gift_pledges_user', 'private_gift_pledges', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_private_gift_pledges_user', table_name='private_gift_pledges')
    op.drop_table('private_gift_pledges')
    op.drop_index('uq_private_group_gifts_live_item', table_name='private_group_gifts')
    op.drop_index('ix_private_group_gifts_task', table_name='private_group_gifts')
    op.drop_table('private_group_gifts')
    op.drop_column('private_tasks', 'design')
    for c in ('archived_at', 'group_gift_target_minor', 'group_gift_enabled', 'details', 'image_origin', 'image_key',
              'variant', 'color', 'size', 'shop', 'price_fetched_at', 'price_source', 'currency', 'price_minor',
              'quantity'):
        op.drop_column('private_task_items', c)
