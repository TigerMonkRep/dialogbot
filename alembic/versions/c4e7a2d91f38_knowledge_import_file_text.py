"""knowledge import from a file or pasted text: source type/name and summary on source_imports, review note on versions

Fürster's wish (Rebotti): besides the website, an owner can upload a document (PDF, DOCX, XLSX, CSV, TXT) or paste
text; the AI sorts it into knowledge drafts. The file itself is never stored – only the drafts and these counts.

Revision ID: c4e7a2d91f38
Revises: a16e24b7c9d1
Create Date: 2026-11-11
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = 'c4e7a2d91f38'
down_revision = 'a16e24b7c9d1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("source_imports", sa.Column("source_type", sa.String(16), nullable=False, server_default="website"))
    op.add_column("source_imports", sa.Column("source_name", sa.String(200), nullable=True))
    op.add_column("source_imports", sa.Column("summary", postgresql.JSONB(), nullable=False, server_default="{}"))
    op.alter_column("source_imports", "url", existing_type=sa.String(500), nullable=True)
    op.create_check_constraint("ck_source_imports_source_type", "source_imports",
                               "source_type in ('website','file','text')")
    op.add_column("knowledge_versions", sa.Column("review_note", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("knowledge_versions", "review_note")
    op.drop_constraint("ck_source_imports_source_type", "source_imports", type_="check")
    # A file/text import has no URL; the old schema requires one – keep the row, labelled with what it was.
    op.execute("update source_imports set url = left(coalesce(source_type || ':' || source_name, source_type), 500) "
               "where url is null")
    op.alter_column("source_imports", "url", existing_type=sa.String(500), nullable=False)
    op.drop_column("source_imports", "summary")
    op.drop_column("source_imports", "source_name")
    op.drop_column("source_imports", "source_type")
