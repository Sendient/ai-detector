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
    storage_blob_path: str = Field(..., description="Path to the file in blob storage")
    file_type: FileType = Field(..., description="Detected type of the file (PDF, DOCX, TXT)")
    upload_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of when the document was uploaded")
    student_id: Optional[uuid.UUID] = Field(None, description="Internal ID of the student associated with the document")
    assignment_id: Optional[uuid.UUID] = Field(None, description="ID of the assignment associated with the document")
    status: DocumentStatus = Field(default=DocumentStatus.UPLOADED, description="Current processing status of the document")
    
    # Optional fields based on your application's needs
    batch_id: Optional[uuid.UUID] = Field(None, description="ID of the batch this document belongs to, if any")
    queue_position: Optional[int] = Field(None, description="Position in the processing queue (if applicable)")
    processing_priority: int = Field(default=0, description="Priority for processing (e.g., 0=normal, 1=high)")
    
    # Fields to be populated after processing by the ML model or text extraction
    character_count: Optional[int] = Field(None, description="Number of characters in the document")
    word_count: Optional[int] = Field(None, description="Number of words in the document")
    # summary: Optional[str] = Field(None, description="AI-generated summary of the document") # Example
    # keywords: Optional[List[str]] = Field(default_factory=list, description="AI-extracted keywords") # Example

    # teacher_id should always be present and is derived from the authenticated user
    # It's not Optional[str] here because DocumentBase might be used where it's always expected.
    # However, for DocumentCreate, it's set by the backend. For Document, it's always there.
    # For consistency in schemas that expect it, keep it non-optional in Base, handle in Create/Update.
    teacher_id: str = Field(..., description="Kinde ID of the teacher who uploaded/owns the document")

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
        use_enum_values = True, # Ensure enums are handled correctly
        json_encoders = {
            datetime: lambda dt: dt.isoformat(),
            uuid.UUID: lambda u: str(u),
            # Handling Enums: Pydantic v2 typically handles enums well by default.
            # If you need their string values in JSON, ensure they are stored/retrieved as such
            # or add specific encoders if the default behavior isn't what you need.
            # DocumentStatus: lambda ds: ds.value, 
            # FileType: lambda ft: ft.value,
        }
        # Ensure this alias is correctly handled if you use `_id` in DB and `id` in model
        # alias_generator = to_snake_case # If you use camelCase in Python and snake_case in JSON/DB
        # Example for `id` vs `_id`:
        # fields = {'id': '_id'} # This is for Pydantic V1. V2 uses Field(alias='_id')
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
