"""dedup duplicate job sources (same job_id + source)

Revision ID: 002
Revises: 001
Create Date: 2026-05-23
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    # (job_id, source) 중복 중 crawled_at이 가장 오래된 것만 남기고 나머지 삭제
    op.execute("""
        DELETE FROM job_sources
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY job_id, source
                           ORDER BY crawled_at
                       ) AS rn
                FROM job_sources
            ) ranked
            WHERE rn > 1
        )
    """)


def downgrade():
    pass
