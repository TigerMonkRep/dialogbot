"""voice designed and origin, own voice recordings

Revision ID: 527c5e36aced
Revises: a8a4f6f5ffaf
Create Date: 2026-09-27 21:10:06.498831
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = '527c5e36aced'
down_revision = 'a8a4f6f5ffaf'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('voice_profiles', sa.Column('origin', sa.String(length=24), nullable=False,
                                              server_default='dataset_speaker'))
    op.add_column('voice_profiles', sa.Column('description', sa.Text(), nullable=False, server_default=''))
    op.add_column('voice_versions', sa.Column('provenance', postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                                              server_default=sa.text("'{}'::jsonb")))
    op.create_check_constraint('ck_voice_profiles_origin', 'voice_profiles',
                               "origin in ('dataset_speaker','designed','customer_recorded','hired_speaker')")
    op.drop_constraint('ck_voice_versions_method', 'voice_versions', type_='check')
    op.create_check_constraint('ck_voice_versions_method', 'voice_versions',
                               "method in ('reference_conditioning','designed_blend','finetuned_checkpoint',"
                               "'trained_from_scratch')")
    op.create_table('own_voice_projects',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('speaker_name', sa.String(length=120), nullable=False),
    sa.Column('manuscript', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('consent', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('rights_record_id', sa.UUID(), nullable=True),
    sa.Column('profile_id', sa.UUID(), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('withdrawn_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("manuscript in ('kort','standard')", name='ck_own_voice_projects_manuscript'),
    sa.CheckConstraint("status in ('recording','submitted','withdrawn')", name='ck_own_voice_projects_status'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['profile_id'], ['voice_profiles.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['rights_record_id'], ['voice_rights_records.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('own_voice_recordings',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('sentence_id', sa.String(length=40), nullable=False),
    sa.Column('key', sa.String(length=300), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('seconds', sa.Float(), nullable=False),
    sa.Column('qc', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['own_voice_projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', 'sentence_id', name='uq_own_voice_recordings_sentence')
    )


def downgrade() -> None:
    op.drop_table('own_voice_recordings')
    op.drop_table('own_voice_projects')
    op.execute("DELETE FROM voice_versions WHERE method = 'designed_blend'")
    op.drop_constraint('ck_voice_versions_method', 'voice_versions', type_='check')
    op.create_check_constraint('ck_voice_versions_method', 'voice_versions',
                               "method in ('reference_conditioning','finetuned_checkpoint','trained_from_scratch')")
    op.drop_constraint('ck_voice_profiles_origin', 'voice_profiles', type_='check')
    op.drop_column('voice_versions', 'provenance')
    op.drop_column('voice_profiles', 'description')
    op.drop_column('voice_profiles', 'origin')
