# app/models/document.py

import uuid
from pydantic import BaseModel, Field, field_validator, ConfigDict # Added ConfigDict for V2
from datetime import datetime, timezone
from typing import Optional, Any # Added Any for validator

# Import Enums with correct names
from .enums import FileType, DocumentStatus # Corrected: DocumentStatus

# --- Base Model ---
class DocumentBase(BaseModel):
    original_filename: str = Field(..., description="Original name of the uploaded file")
    storage_blob_path: str = Field(..., description="Path or name of the file in blob storage")
    file_type: FileType = Field(..., description="Detected type of the file (PDF, DOCX, etc.)")
    upload_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: DocumentStatus = Field(default=DocumentStatus.UPLOADED, description="Processing status of the document")
    student_id: uuid.UUID = Field(..., description="ID of the student associated with this document")
    assignment_id: uuid.UUID = Field(..., description="ID of the assignment associated with this document")
    teacher_id: str = Field(..., description="Kinde User ID of the Teacher who owns this document")

    # Batch processing fields
    batch_id: Optional[uuid.UUID] = Field(default=None, description="ID of the batch this document belongs to")
    queue_position: Optional[int] = Field(default=None, description="Position in the processing queue")
    processing_priority: Optional[int] = Field(default=0, description="Processing priority (higher = more priority)")
    processing_attempts: Optional[int] = Field(default=0, description="Number of processing attempts")
    error_message: Optional[str] = Field(default=None, description="Error message if processing failed")

    # Analytics fields
    character_count: Optional[int] = Field(default=None, description="Number of characters in the extracted text")
    word_count: Optional[int] = Field(default=None, description="Number of words in the extracted text")

    @field_validator('file_type', mode='before')
    @classmethod
    def map_short_extension_to_filetype(cls, value: Any) -> Any:
        if isinstance(value, str):
            # Ensure mapping keys are lowercase to match potential input variations
            value_lower = value.lower()
            mapping = {
                "pdf": FileType.PDF,
                "docx": FileType.DOCX,
                "txt": FileType.TXT,
                "text": FileType.TEXT, # TEXT is an alias for TXT in FileType enum
                "png": FileType.PNG,
                "jpg": FileType.JPG,
                "jpeg": FileType.JPEG, # JPEG is an alias for JPG in FileType enum
            }
            # Return the enum member if found, otherwise return the original value
            # for Pydantic's default validation to handle (which might raise an error if it's still invalid)
            return mapping.get(value_lower, value)
        return value

    # Pydantic V2 model config (can be defined here or in inheriting classes)
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        use_enum_values = True # Ensure enums are handled correctly
    )

# --- Model for Creation (received via API) ---
class DocumentCreate(DocumentBase):
    # All fields from Base are needed for creation
    # teacher_id and is_deleted are set by the backend
    pass

# --- Model for Update (received via API) ---
# Typically only status might be updated via API, or maybe other fields later
class DocumentUpdate(BaseModel):
    status: Optional[DocumentStatus] = Field(None, description="New processing status")
    queue_position: Optional[int] = None
    processing_priority: Optional[int] = None
    processing_attempts: Optional[int] = None
    error_message: Optional[str] = None
    # teacher_id and is_deleted are not updatable via this model

# --- Model for Database (includes internal fields) ---
class DocumentInDBBase(DocumentBase):
    id: uuid.UUID = Field(..., alias="_id", description="Internal unique identifier") # Use '_id' alias for MongoDB
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # --- RBAC Changes Below ---
    # teacher_id: str = Field(..., description="Kinde User ID of the Teacher who owns this document") # MOVED to Base
    # Replaced deleted_at with is_deleted for consistency
    # deleted_at: Optional[datetime] = Field(default=None) # REMOVED
    is_deleted: bool = Field(default=False, description="Flag for soft delete status") # ADDED
    # --- RBAC Changes Above ---

    # Inherit model_config from Base, can add specifics here if needed
    model_config = ConfigDict(
        # from_attributes = True # Inherited
        # populate_by_name = True # Inherited
        arbitrary_types_allowed = True # If using complex types like ObjectId directly
        # use_enum_values = True # Inherited
    )


# --- Model for API Response ---
class Document(DocumentInDBBase):
    # This model represents the data returned by the API
    # Inherits all fields including RBAC changes
    pass

# --- Model for Batch Response ---
class DocumentBatchResponse(BaseModel):
    id: uuid.UUID
    original_filename: str
    status: DocumentStatus
    queue_position: Optional[int]
    error_message: Optional[str]
