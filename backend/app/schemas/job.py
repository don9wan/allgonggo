from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from uuid import UUID


class JobSourceOut(BaseModel):
    id: UUID
    source: str
    url: str

    model_config = {"from_attributes": True}


class JobOut(BaseModel):
    id: UUID
    title: str
    company: str
    location: Optional[str] = None
    experience: Optional[str] = None
    employment_type: Optional[str] = None
    is_active: bool
    crawled_at: datetime
    sources: List[JobSourceOut] = []

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    jobs: List[JobOut]
    total: int
    page: int
    size: int
    has_next: bool
