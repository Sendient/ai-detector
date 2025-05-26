# app/models/student.py
from pydantic import BaseModel, Field, EmailStr, constr, ConfigDict # Import ConfigDict for Pydantic V2, EmailStr
from typing import Optional, List
from datetime import datetime, timezone
import uuid
# No need to import bool, it's a built-in type

# Shared base properties
class StudentBase(BaseModel):
    first_name: str = Field(..., min_length=1, description="Student's first name")
    last_name: str = Field(..., min_length=1, description="Student's last name")
    teacher_id: str = Field(..., description="Kinde User ID of the owning teacher")
    class_group_ids: Optional[List[uuid.UUID]] = Field(default_factory=list, description="List of class group IDs the student is assigned to")

    # --- ADDED email field ---
    email: Optional[EmailStr] = Field(default=None, description="Student's email address (Optional)")
    # -------------------------

    # Optional external ID provided by the institution/user
    external_student_id: Optional[constr(strip_whitespace=True, max_length=16)] = Field( # type: ignore
        default=None,
        description="Optional external student ID (max 16 chars, unique if provided)"
    )
    descriptor: Optional[str] = Field(default=None, description="Optional descriptor or note about the student")
    year_group: Optional[str] = Field(default=None, description="Optional year group or grade level")

    # Pydantic V2 model config
    model_config = ConfigDict(
        from_attributes=True,      # Allow creating schema from DB model object
        populate_by_name=True,     # Allow population by alias (e.g., '_id' for 'id')
    )


# Properties required on creation
class StudentCreate(StudentBase):
    # Inherits fields from StudentBase, including the new optional email
    # teacher_id and is_deleted are NOT needed here - they are set by the backend
    # MODIFIED COMMENT: teacher_id is now inherited. The logic for how it's set (backend vs. payload)
    # will be handled by the endpoint and CRUD function.
    pass

# Properties stored in DB - Intermediate Base including system fields
class StudentInDBBase(StudentBase):
    # Use 'id' in Python, map to '_id' in MongoDB via alias.
    id: uuid.UUID = Field(default_factory=uuid.uuid4, alias="_id", description="Internal unique identifier")

    # Timestamps will now use default_factory for automatic generation
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp when the student record was created")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp when the student record was last updated")

    # --- RBAC Changes Below ---
    # teacher_id: str = Field(..., description="Kinde User ID of the owning teacher") # MOVED to Base
    is_deleted: bool = Field(default=False, description="Flag for soft delete status") # Added (with default=False)
    # --- RBAC Changes Above ---

    # Pydantic V2 configuration inherited includes from_attributes=True, populate_by_name=True
    # arbitrary_types_allowed=True is often needed for MongoDB UUIDs etc.
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        # Inherit others by default, but can re-declare if needed
        # populate_by_name=True,
        # from_attributes=True,
    )


# Final model representing a Student read from DB (returned by API)
class Student(StudentInDBBase):
    # Inherits all fields from StudentInDBBase: id, created_at, updated_at,
    # teacher_id, is_deleted, and all fields from StudentBase
    class_group_ids: Optional[List[uuid.UUID]] = Field(default_factory=list, description="List of class group IDs the student is assigned to")
    pass

# Model for updating - All fields are optional for partial updates
class StudentUpdate(BaseModel):
    first_name: Optional[str] = Field(default=None, min_length=1, description="Student's first name")
    last_name: Optional[str] = Field(default=None, min_length=1, description="Student's last name")
    # --- ADDED email field ---
    email: Optional[EmailStr] = Field(default=None, description="Student's email address")
    # -------------------------
    external_student_id: Optional[constr(strip_whitespace=True, max_length=16)] = Field( # type: ignore
        default=None,
        description="Optional external student ID (max 16 chars, unique if provided)"
    )
    descriptor: Optional[str] = Field(default=None, description="Optional descriptor or note about the student")
    year_group: Optional[str] = Field(default=None, description="Optional year group or grade level")

    # Note: teacher_id and is_deleted are NOT included here.
    # Ownership shouldn't change, and soft delete is a separate action.

# Basic student info for embedding in other models
class StudentBasicInfo(BaseModel):
    id: uuid.UUID = Field(..., alias="_id")
    first_name: str
    last_name: str

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        arbitrary_types_allowed=True
    )