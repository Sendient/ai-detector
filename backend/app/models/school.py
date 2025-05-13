# app/models/school.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime, timezone
import uuid

# Shared base properties
class SchoolBase(BaseModel):
    school_name: str = Field(..., min_length=1)
    school_state_region: Optional[str] = None
    school_country: str = Field(..., min_length=2) # e.g., ISO country code or name

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )

# Properties required on creation
class SchoolCreate(SchoolBase):
    pass # Inherits model_config

# Properties stored in DB
class SchoolInDBBase(SchoolBase):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, alias="_id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # model_config is inherited from SchoolBase.
    # If specific settings were needed, they'd be here, e.g.:
    # model_config = ConfigDict(
    #     populate_by_name=True, # from SchoolBase
    #     from_attributes=True,  # from SchoolBase
    #     arbitrary_types_allowed=True 
    # )

# Final model representing a School read from DB
class School(SchoolInDBBase):
    pass # Inherits model_config

# Model for updating
class SchoolUpdate(BaseModel):
    school_name: Optional[str] = None
    school_state_region: Optional[str] = None
    school_country: Optional[str] = None

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )