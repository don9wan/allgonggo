"""init_jobs_and_job_sources

Revision ID: 001
Revises:
Create Date: 2026-05-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("company", sa.Text(), nullable=False),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("experience", sa.Text(), nullable=True),
        sa.Column("employment_type", sa.Text(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("crawled_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_jobs_company", "jobs", ["company"])
    op.create_index("ix_jobs_is_active", "jobs", ["is_active"])
    op.create_index("ix_jobs_crawled_at", "jobs", ["crawled_at"])

    op.execute(
        "CREATE INDEX ix_jobs_raw_text_trgm ON jobs USING gin (raw_text gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_jobs_title_trgm ON jobs USING gin (title gin_trgm_ops)"
    )

    op.create_table(
        "job_sources",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("crawled_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_job_sources_job_id", "job_sources", ["job_id"])
    op.create_index("ix_job_sources_source", "job_sources", ["source"])
    op.create_index("ix_job_sources_url", "job_sources", ["url"], unique=True)


def downgrade() -> None:
    op.drop_table("job_sources")
    op.drop_table("jobs")
