# app/models/class_group.py
from pydantic import BaseModel, Field, ConfigDict # Use ConfigDict from Pydantic V2
from typing import Optional, List
from datetime import datetime, timezone # Import timezone for default factory
import uuid

# Shared base properties - REMOVED school_id
class ClassGroupBase(BaseModel):
    """Base class for ClassGroup with common attributes."""
    class_name: str = Field(..., description="Name of the class (e.g., 'Math 101', '9th Grade English')")
    academic_year: str = Field(..., description="Academic year (e.g., '2024-2025')")
    teacher_id: str = Field(..., description="Kinde User ID of the Teacher who owns this class")
    # school_id: uuid.UUID = Field(..., description="Reference to the School this class belongs to") # REMOVED
    # # teacher_id is handled in DB model # REMOVED COMMENT

    # Pydantic V2 model config (can be defined here or in inheriting classes)
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )

# Properties required on creation - teacher_id and is_deleted are set by backend
class ClassGroupCreate(ClassGroupBase):
    """Model for creating a new ClassGroup."""
    # Student IDs are typically managed after the class is created.
    student_ids: Optional[List[uuid.UUID]] = Field(default_factory=list, description="List of student IDs enrolled in the class (Optional at creation)")
    # school_id is removed
    pass


# Properties stored in DB - ADDED RBAC fields, adjusted teacher_id type, removed school_id
class ClassGroupInDBBase(ClassGroupBase):
    """Base model for ClassGroup data stored in the database."""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, alias="_id", description="Unique identifier for the class group")

    # --- RBAC Changes Below ---
    # Changed teacher_id to str to store Kinde User ID
    # teacher_id: str = Field(..., description="Kinde User ID of the Teacher who owns this class") # MOVED to Base
    is_deleted: bool = Field(default=False, description="Flag for soft delete status") # ADDED
    # school_id is removed (was inherited from Base)
    # --- RBAC Changes Above ---

    student_ids: List[uuid.UUID] = Field(default_factory=list, description="List of student IDs enrolled in the class")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When the class group was created")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When the class group was last updated")

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        arbitrary_types_allowed=True
    )

# Final model representing a ClassGroup read from DB
class ClassGroup(ClassGroupInDBBase):
    """Complete ClassGroup model for data retrieved from the database."""
    # Inherits all fields including RBAC changes
    pass

# Model for updating (e.g., changing name, adding/removing students)
class ClassGroupUpdate(BaseModel):
    """Model for updating an existing ClassGroup."""
    class_name: Optional[str] = Field(None, description="Name of the class group")
    academic_year: Optional[str] = Field(None, description="Academic year (e.g., '2024-2025')")
    student_ids: Optional[List[uuid.UUID]] = Field(None, description="List of student IDs in this class")
    # teacher_id should not be updatable via this model
    # school_id is removed

    # Ensure ConfigDict is present if needed, or rely on default behavior
    model_config = ConfigDict(
        arbitrary_types_allowed=True # If needed for any complex types in future
    )
