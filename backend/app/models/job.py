import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.database import Base


class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(Text, nullable=False)
    company = Column(Text, nullable=False)
    location = Column(Text, nullable=True)
    experience = Column(Text, nullable=True)
    employment_type = Column(Text, nullable=True)
    raw_text = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    crawled_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    sources = relationship("JobSource", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_jobs_company", "company"),
        Index("ix_jobs_is_active", "is_active"),
        Index("ix_jobs_crawled_at", "crawled_at"),
    )


class JobSource(Base):
    __tablename__ = "job_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    source = Column(String(50), nullable=False)
    url = Column(Text, nullable=False)
    crawled_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    job = relationship("Job", back_populates="sources")

    __table_args__ = (
        Index("ix_job_sources_job_id", "job_id"),
        Index("ix_job_sources_source", "source"),
        Index("ix_job_sources_url", "url", unique=True),
    )
