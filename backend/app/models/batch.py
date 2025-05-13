# app/models/batch.py

import uuid
from pydantic import BaseModel, Field, ConfigDict # Added ConfigDict
from datetime import datetime, timezone
from typing import Optional, List

from app.models.enums import BatchStatus, BatchPriority

class BatchBase(BaseModel):
    # Renamed user_id to teacher_id for consistency
    teacher_id: str = Field(..., description="Kinde User ID of the teacher who created the batch") # MODIFIED
    total_files: int = Field(..., description="Total number of files in the batch")
    completed_files: int = Field(default=0, description="Number of files that completed processing")
    failed_files: int = Field(default=0, description="Number of files that failed processing")
    status: BatchStatus = Field(default=BatchStatus.CREATED, description="Current status of the batch")
    priority: BatchPriority = Field(default=BatchPriority.NORMAL, description="Processing priority of the batch")
    error_message: Optional[str] = Field(default=None, description="Error message if batch failed")

    # Pydantic V2 model config
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        use_enum_values = True # Ensure enums are handled correctly
    )

class BatchCreate(BatchBase):
    # teacher_id is inherited, but will be set by backend logic based on authenticated user
    # is_deleted is not needed here
    pass

class BatchUpdate(BaseModel):
    # Only fields that can be updated after creation
    completed_files: Optional[int] = None
    failed_files: Optional[int] = None
    status: Optional[BatchStatus] = None
    error_message: Optional[str] = None
    # teacher_id and is_deleted are not updatable via this model

class BatchInDBBase(BatchBase):
    id: uuid.UUID = Field(..., alias="_id", description="Internal unique identifier") # Use '...' if ID is always required
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # --- RBAC Changes Below ---
    # Replace deleted_at with is_deleted
    # deleted_at: Optional[datetime] = Field(default=None) # REMOVED
    is_deleted: bool = Field(default=False, description="Flag for soft delete status") # ADDED
    # --- RBAC Changes Above ---

    # Inherit model_config from Base, add specifics if needed
    model_config = ConfigDict(
        # from_attributes = True # Inherited
        # populate_by_name = True # Inherited
        arbitrary_types_allowed = True # Allow UUID etc.
        # use_enum_values = True # Inherited
    )

class Batch(BatchInDBBase):
    # Inherits all fields including RBAC changes
    pass

# Optional: If you need a response model that includes document IDs
class BatchWithDocuments(Batch):
     document_ids: List[uuid.UUID] = Field(default_factory=list, description="List of document IDs in this batch")
