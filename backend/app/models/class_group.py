# app/models/class_group.py
from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Optional, List
from datetime import datetime, timezone
import uuid

# Core schema for class_name and academic_year with validation
class ClassGroupCoreSchema(BaseModel):
    class_name: Optional[str] = Field(None, description="Name of the class (e.g., 'Math 101', '9th Grade English'). Must be provided if academic_year is present and must be more than just the academic year.")
    academic_year: Optional[str] = Field(None, description="Academic year (e.g., '2024-2025'). Can be omitted if class_name is also omitted.")

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )

    @model_validator(mode='before') # mode='before' applies to input data before model creation
    @classmethod
    def validate_class_name_and_academic_year(cls, values):
        # Ensure values is a dict, which it should be in 'before' mode for model_dump or direct dict input
        if not isinstance(values, dict):
            # If it's already a model instance (e.g. during model_validate), access fields via getattr
            # This case should ideally not be hit if used purely for input validation.
            class_name = getattr(values, 'class_name', None)
            academic_year = getattr(values, 'academic_year', None)
        else:
            class_name, academic_year = values.get('class_name'), values.get('academic_year')

        if academic_year is not None:
            if class_name is None:
                raise ValueError('class_name is required if academic_year is provided.')
            if not isinstance(class_name, str) or not class_name.strip(): # Ensure class_name is a non-empty string
                 raise ValueError('class_name must be a non-empty string if academic_year is provided.')
            if class_name.strip() == academic_year.strip():
                raise ValueError('class_name cannot consist only of the academic_year.')
        # Allow both to be None or class_name to be provided without academic_year
        return values

# Model for the request payload from the client (only core fields)
class ClassGroupCreateRequest(ClassGroupCoreSchema):
    pass

# Model used internally for creating the DB record, includes teacher_id
class ClassGroupCreate(ClassGroupCoreSchema):
    teacher_id: uuid.UUID = Field(..., description="Internal Database ID of the Teacher who owns this class")
    # student_ids are typically managed after the class is created, so not included here by default.
    # school_id is not used.

# Shared base properties including teacher_id, used by DB and response models
class ClassGroupBase(ClassGroupCoreSchema):
    teacher_id: uuid.UUID = Field(..., description="Internal Database ID of the Teacher who owns this class")
    # No model_config here, will be inherited or overridden

# Properties stored in DB
class ClassGroupInDBBase(ClassGroupBase):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, alias="_id", description="Unique identifier for the class group")
    is_deleted: bool = Field(default=False, description="Flag for soft delete status")
    student_ids: List[uuid.UUID] = Field(default_factory=list, description="List of student IDs enrolled in the class")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When the class group was created")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When the class group was last updated")

    model_config = ConfigDict(
        populate_by_name=True, # Allows using alias _id for id
        from_attributes=True,  # Allows ORM mode (though Beanie uses Pydantic models directly)
        arbitrary_types_allowed=True # For uuid and datetime
    )

# Final model representing a ClassGroup read from DB (for responses)
class ClassGroup(ClassGroupInDBBase):
    # Inherits all fields. This is the primary model for API responses.
    pass

# Model for updating an existing ClassGroup
class ClassGroupUpdate(ClassGroupCoreSchema): # Inherits class_name and academic_year
    # teacher_id should not be updatable directly via this model by a general update endpoint.
    # student_ids are typically managed by dedicated endpoints.
    # is_deleted is usually handled by a delete endpoint.
    class_name: Optional[str] = None # Make fields optional for updates
    academic_year: Optional[str] = None

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        from_attributes=True # If updating from an ORM model instance
    )

# Model for responses that include student details (if needed in future)
class ClassGroupWithStudents(ClassGroup):
    # This is a placeholder; actual student objects would be defined elsewhere
    # and potentially fetched/resolved separately.
    # For now, student_ids are in ClassGroupInDBBase.
    # students: Optional[List[Any]] = Field(None, description="Full student objects, if populated")
    pass
