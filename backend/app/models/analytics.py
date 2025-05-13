from pydantic import BaseModel, Field
from typing import Optional
from datetime import date

class UsageStatsResponse(BaseModel):
    period: str = Field(..., description="The requested period (daily, weekly, monthly)")
    target_date: date = Field(..., description="The target date used for calculation")
    start_date: date = Field(..., description="The calculated start date of the period")
    end_date: date = Field(..., description="The calculated end date of the period")
    document_count: int = Field(..., description="Number of documents uploaded in the period")
    total_characters: int = Field(..., description="Total characters counted in documents uploaded during the period")
    total_words: int = Field(..., description="Total words counted in documents uploaded during the period")
    teacher_id: str = Field(..., description="The Kinde ID of the teacher for whom stats were calculated") 