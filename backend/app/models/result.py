# app/models/result.py
from pydantic import BaseModel, Field, ConfigDict # Added ConfigDict
from typing import Optional, List, Dict, Any # Added List, Dict, Any
from datetime import datetime, timezone # Added timezone
import uuid
# Assuming enums.py is in the same directory or accessible via path
from .enums import ResultStatus # Import Enum

# --- NEW: Model for a single paragraph result from ML API ---
class ParagraphResult(BaseModel):
    """Represents the analysis result for a single paragraph."""
    paragraph: Optional[str] = Field(None, description="The text content of the paragraph")
    label: Optional[str] = Field(None, description="Classification label for the paragraph (e.g., AI-Generated, Human-Written, Undetermined)")
    probability: Optional[float] = Field(None, ge=0.0, le=1.0, description="AI detection probability score for the paragraph (0.0 to 1.0)")

    # Allow extra fields if the API returns more than we explicitly define,
    # although we only care about the ones defined above for now.
    model_config = ConfigDict(extra='allow')


# --- Updated ResultBase ---
class ResultBase(BaseModel):
    """Base model for Result data, including fields from the ML API."""
    document_id: uuid.UUID = Field(..., description="Link to the Document model this result belongs to")
    teacher_id: str = Field(..., description="Kinde User ID of the Teacher who owns the associated document")

    # Overall Score: We'll store the probability from the first paragraph result here
    # as the primary score, based on the API example.
    score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Overall AI detection score (probability, typically from the first/main result)")
    status: ResultStatus = Field(default=ResultStatus.PENDING, description="Status of the analysis result")

    # Overall flags from the API response root
    label: Optional[str] = Field(None, description="Overall classification label from the ML API (e.g., Human-Written, AI-Generated)")
    ai_generated: Optional[bool] = Field(None, description="Overall boolean flag indicating if ML API classified as AI-generated")
    human_generated: Optional[bool] = Field(None, description="Overall boolean flag indicating if ML API classified as human-generated")

    # --- NEW FIELD: Store detailed paragraph results ---
    # This field will hold the list of results for each paragraph.
    paragraph_results: Optional[List[ParagraphResult]] = Field(default=None, description="Detailed analysis results per paragraph")
    # --- END NEW FIELD ---

    # Pydantic V2 model config (can be defined here or in inheriting classes)
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        use_enum_values = True # Ensure enums are handled correctly
    )

# Properties required on creation (usually set internally when upload happens)
class ResultCreate(ResultBase):
    """Model used when initially creating a Result record (typically with PENDING status)."""
    # Set defaults for fields not known at initial creation
    score: Optional[float] = None
    label: Optional[str] = None
    ai_generated: Optional[bool] = None
    human_generated: Optional[bool] = None
    paragraph_results: Optional[List[ParagraphResult]] = None
    status: ResultStatus = ResultStatus.PENDING # Ensure status is PENDING on create
    # teacher_id and is_deleted are set by the backend

# Properties stored in DB (includes system fields)
class ResultInDBBase(ResultBase):
    """Base model representing how Result data is stored in the database."""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, alias="_id", description="Internal unique identifier for the result")
    # Use result_timestamp for consistency with spec, default to now
    result_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp when the result was generated or last updated")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp when the result record was created")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp when the result record was last updated")

    # --- RBAC Changes Below ---
    # Add teacher_id, likely derived from the associated document upon creation
    # teacher_id: str = Field(..., description="Kinde User ID of the Teacher who owns the associated document") # MOVED to Base
    # Replace deleted_at with is_deleted for consistency
    # deleted_at: Optional[datetime] = Field(default=None) # REMOVED
    is_deleted: bool = Field(default=False, description="Flag for soft delete status (likely linked to document deletion)") # ADDED
    # --- RBAC Changes Above ---

    # Pydantic V2 Config
    model_config = ConfigDict(
        populate_by_name=True,           # Allow using '_id' alias
        from_attributes=True,            # Allow creating from DB object attributes
        arbitrary_types_allowed=True,    # Allow UUID etc.
        use_enum_values=True             # Store/retrieve enums by their value
    )

# Final model representing a Result read from DB (API Response)
class Result(ResultInDBBase):
    """Complete Result model representing data retrieved from the database."""
    # Inherits all fields from ResultInDBBase including RBAC changes
    pass

# Model for updating (when ML analysis completes)
class ResultUpdate(BaseModel):
    """Model used when updating a Result record after ML analysis."""
    # All fields are optional because we only update what we receive from the ML API
    score: Optional[float] = Field(None, ge=0.0, le=1.0)
    status: Optional[ResultStatus] = None
    label: Optional[str] = None
    ai_generated: Optional[bool] = None
    human_generated: Optional[bool] = None
    # --- NEW FIELD for update ---
    paragraph_results: Optional[List[ParagraphResult]] = None
    # --- END NEW FIELD ---
    # Update result_timestamp automatically when updating the result
    result_timestamp: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))
    # teacher_id and is_deleted are not updatable via this model

    # Pydantic V2 Config
    model_config = ConfigDict(
        use_enum_values=True
    )

