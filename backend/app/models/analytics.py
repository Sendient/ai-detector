from pydantic import BaseModel, Field
from typing import Optional
from datetime import date

class UsageStatsResponse(BaseModel):
    period: Optional[str] = Field(default=None, description="The requested period (daily, weekly, monthly), or null for all-time")
    target_date: Optional[date] = Field(default=None, description="The target date used for calculation, or null for all-time")
    start_date: Optional[date] = Field(default=None, description="The calculated start date of the period, or null for all-time")
    end_date: Optional[date] = Field(default=None, description="The calculated end date of the period, or null for all-time")
    document_count: int = Field(..., description="Number of documents uploaded in the period")
    total_characters: int = Field(..., description="Total characters counted in documents uploaded during the period")
    total_words: int = Field(..., description="Total words counted in documents uploaded during the period")
    teacher_id: str = Field(..., description="The Kinde ID of the teacher for whom stats were calculated")

    # New fields for all-time stats breakdown
    current_documents: Optional[int] = Field(default=None, description="Number of non-deleted documents (for all-time stats)")
    deleted_documents: Optional[int] = Field(default=None, description="Number of deleted documents (for all-time stats)")
    total_processed_documents: Optional[int] = Field(default=None, description="Total documents processed (current + deleted, for all-time stats)") 