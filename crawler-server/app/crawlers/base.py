import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RawJob:
    title: str
    company: str
    url: str
    source: str
    location: Optional[str] = None
    experience: Optional[str] = None
    employment_type: Optional[str] = None
    raw_text: str = ""
