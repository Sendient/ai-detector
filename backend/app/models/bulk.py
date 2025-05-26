from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import Optional, List
import uuid

class StudentBulkCreateItem(BaseModel):
    FirstName: str = Field(..., description="Student's first name from CSV")
    LastName: str = Field(..., description="Student's last name from CSV")
    EmailAddress: Optional[EmailStr] = Field(default=None, description="Student's email address from CSV (Optional)")
    ExternalID: Optional[str] = Field(default=None, max_length=16, description="Student's external ID from CSV (Optional, max 16 chars)")
    Descriptor: Optional[str] = Field(default=None, description="Student's descriptor from CSV (Optional)")
    AssignToClass: Optional[str] = Field(default=None, description="Class name to assign student to (Optional)")

    # Pydantic V2 model_config for potential future use if needed (e.g. orm_mode / from_attributes)
    # For simple request bodies, explicit aliasing is often handled by frontend or a custom alias_generator.
    # If the frontend sends keys matching these field names, no special config is needed here for aliases.
    # model_config = ConfigDict(populate_by_name=True) # This is more for ORM attributes.

class StudentBulkCreateRequest(BaseModel):
    students: List[StudentBulkCreateItem]

class StudentBulkResponseItem(BaseModel):
    row_number: int # To help frontend map back to original CSV row
    status: str # e.g., "CREATED", "FAILED", "CREATED_WITH_NEW_CLASS", "CREATED_WITH_EXISTING_CLASS"
    student_id: Optional[uuid.UUID] = None
    student_name: Optional[str] = None # For easier display of which student
    class_group_id: Optional[uuid.UUID] = None
    class_name_processed: Optional[str] = None # The class name that was processed
    message: str # Detailed message, especially for errors

class StudentBulkCreateResponse(BaseModel):
    results: List[StudentBulkResponseItem]
    summary: dict # e.g., total_processed, total_succeeded, total_failed 