# app/models/class_group.py
from typing import List, Optional, Union
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

# Model for the request payload from the client (API input for POST)
# This model does NOT include teacher_id, student_ids, is_deleted as these
# will be derived/set by the backend or have defaults.
class ClassGroupClientCreate(BaseModel): 
    class_name: str = Field(..., min_length=1, max_length=200, description="Name of the class group")
    academic_year: Optional[str] = Field(None, max_length=50, description="Academic year, e.g., '2024-2025'")

    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={UUID: str, datetime: lambda dt: dt.isoformat()}
    )

# Base model for ClassGroup attributes - teacher_id is required here as it's fundamental to the object
class ClassGroupBase(BaseModel):
    class_name: str = Field(..., min_length=1, max_length=200, description="Name of the class group")
    academic_year: Optional[str] = Field(None, max_length=50, description="Academic year, e.g., '2024-2025'")
    teacher_id: Union[UUID, str] = Field(..., description="UUID of the teacher associated with the class") # Keep as UUID for internal consistency
    student_ids: List[UUID] = Field(default_factory=list, description="List of student UUIDs in the class")
    is_deleted: bool = Field(default=False, description="Flag to mark class group as deleted")

    model_config = ConfigDict(
        populate_by_name=True, # Allows using field name or alias
        from_attributes=True,  # Allows ORM mode (reading data from ORM objects)
        json_encoders={UUID: str, datetime: lambda dt: dt.isoformat()},
        arbitrary_types_allowed=True # Allow custom types like UUID
    )

# Model for creating a new class group - This is what's used internally and passed to CRUD.
# It includes all necessary fields for DB storage.
class ClassGroupCreate(ClassGroupBase):
    # Inherits all fields from ClassGroupBase including required teacher_id
    pass

# Model for updating an existing class group (API input)
# All fields are optional for partial updates
class ClassGroupUpdate(BaseModel):
    class_name: Optional[str] = Field(None, min_length=1, max_length=200)
    academic_year: Optional[str] = Field(None, max_length=50)
    # teacher_id should generally not be updatable directly by client here,
    # class ownership changes might be a separate, more controlled process.
    # student_ids can be updated via dedicated add/remove student endpoints.
    # is_deleted is handled by the DELETE endpoint.
    # For now, keeping them as optional if direct update is intended.
    student_ids: Optional[List[UUID]] = None 
    is_deleted: Optional[bool] = None

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        json_encoders={UUID: str, datetime: lambda dt: dt.isoformat()},
        arbitrary_types_allowed=True
    )

# Model for representing a class group stored in the DB, inherits from Base
# Includes fields that are auto-generated or managed by the DB
class ClassGroupInDBBase(ClassGroupBase):
    id: UUID = Field(..., alias='_id', description="MongoDB document ID")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Timestamp of creation")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Timestamp of last update")
    
    model_config = ConfigDict(
        populate_by_name=True, 
        from_attributes=True,
        json_encoders={UUID: str, datetime: lambda dt: dt.isoformat()},
        arbitrary_types_allowed=True
    )

# Final model representing a ClassGroup read from DB (returned by API)
class ClassGroup(ClassGroupInDBBase):
    pass

# Model for a list of ClassGroups (e.g., for /admin/classgroups GET endpoint)
class ClassGroupList(BaseModel):
    items: List[ClassGroup]
    total: int

    model_config = ConfigDict(
        json_encoders={UUID: str, datetime: lambda dt: dt.isoformat()}
    )
