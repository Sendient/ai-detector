# app/models/class_group.py
from typing import List, Optional, Union
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

# Base model for ClassGroup attributes
class ClassGroupBase(BaseModel):
    class_name: str = Field(..., min_length=1, max_length=200, description="Name of the class group")
    academic_year: Optional[str] = Field(None, max_length=50, description="Academic year, e.g., '2024-2025'")
    teacher_id: Union[UUID, str] = Field(..., description="UUID or Kinde ID of the teacher associated with the class")
    student_ids: List[UUID] = Field(default_factory=list, description="List of student UUIDs in the class")
    is_deleted: bool = Field(default=False, description="Flag to mark class group as deleted")

    model_config = ConfigDict(
        populate_by_name=True, # Allows using field name or alias
        from_attributes=True,  # Allows ORM mode (reading data from ORM objects)
        json_encoders={UUID: str, datetime: lambda dt: dt.isoformat()},
        arbitrary_types_allowed=True # Allow custom types like UUID
    )

# Model for creating a new class group (API input)
class ClassGroupCreate(ClassGroupBase):
    pass

# Model for updating an existing class group (API input)
# All fields are optional for partial updates
class ClassGroupUpdate(BaseModel):
    class_name: Optional[str] = Field(None, min_length=1, max_length=200)
    academic_year: Optional[str] = Field(None, max_length=50)
    teacher_id: Optional[Union[UUID, str]] = None
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
        populate_by_name=True, # Allows using field name or alias, e.g. 'id' for '_id'
        from_attributes=True,  # Allows ORM mode (reading data from ORM objects)
        json_encoders={UUID: str, datetime: lambda dt: dt.isoformat()},
        arbitrary_types_allowed=True # Allow custom types like UUID
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
