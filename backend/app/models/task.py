from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class AssessmentTask(BaseModel):
    """Model representing a queued assessment task."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, alias="_id")
    document_id: uuid.UUID
    user_id: str  # This is the Kinde user ID (teacher_id)
    priority_level: int = 0
    attempts: int = 0
    status: str = "PENDING"  # PENDING, IN_PROGRESS, COMPLETED (by worker), DEAD_LETTER
    available_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    retry_count: int = Field(default=0)
    last_error: Optional[str] = Field(default=None)

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat(),
            uuid.UUID: lambda u: str(u),
        } 