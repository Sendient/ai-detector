# app/models/teacher.py
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional, List
from datetime import datetime, timezone
import uuid
# Assuming enums.py is in the same directory or accessible via path
from .enums import TeacherRole, MarketingSource, SubscriptionPlan, StripeSubscriptionStatus # IMPORT NEW ENUMS

# Shared base properties
class TeacherBase(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100, description="Teacher's first name")
    last_name: str = Field(..., min_length=1, max_length=100, description="Teacher's last name")
    email: EmailStr = Field(..., description="Teacher's email address")
    school_name: Optional[str] = Field(None, min_length=1, max_length=200, description="Name of the school the teacher belongs to")
    role: TeacherRole = Field(default=TeacherRole.TEACHER, description="The primary role of the teacher/user")
    is_administrator: bool = Field(default=False, description="Flag indicating if the user has administrative privileges")
    how_did_you_hear: Optional[MarketingSource] = None
    description: Optional[str] = Field(None, description="Optional bio or description")
    country: Optional[str] = Field(None, description="Country of the teacher/school")
    state_county: Optional[str] = Field(None, description="State or County of the teacher/school")
    is_active: bool = Field(default=True, description="Whether the teacher account is active")

    model_config = ConfigDict(
        use_enum_values=True,
        from_attributes=True,
        populate_by_name=True,
    )

# Properties required on creation - Inherits from TeacherBase
class TeacherCreate(TeacherBase):
    school_name: str = Field(..., min_length=1, max_length=200)
    country: str = Field(...)
    state_county: str = Field(...)

    model_config = ConfigDict(
        use_enum_values=True,
        json_schema_extra={
            "example": {
                "first_name": "John",
                "last_name": "Doe",
                "email": "john.doe@example.com",
                "school_name": "Example School",
                "role": "teacher",
                "country": "United Kingdom",
                "state_county": "London",
            }
        }
    )

# Properties stored in DB
class TeacherInDBBase(TeacherBase):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, alias="_id", description="Internal unique identifier for the teacher record")
    kinde_id: str = Field(..., description="Kinde User ID, obtained from authentication token", index=True) # Suggest adding index=True for querying

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_deleted: bool = Field(default=False, description="Flag for soft delete status")

    # --- Kinde specific fields from token ---
    kinde_permissions: Optional[List[str]] = Field(default_factory=list, description="Permissions from Kinde token")
    kinde_org_code: Optional[str] = Field(None, description="Organization code from Kinde token")
    kinde_picture: Optional[str] = Field(None, description="User picture URL from Kinde token")
    kinde_given_name: Optional[str] = Field(None, description="User given name from Kinde token")
    kinde_family_name: Optional[str] = Field(None, description="User family name from Kinde token")

    # --- STRIPE SUBSCRIPTION FIELDS START ---
    current_plan: SubscriptionPlan = Field(
        default=SubscriptionPlan.FREE,
        description="Current subscription plan of the teacher"
    )
    stripe_customer_id: Optional[str] = Field(
        default=None,
        description="Stripe Customer ID, links to Stripe's customer object",
        index=True # Suggest adding index=True for querying (especially by webhooks)
    )
    stripe_subscription_id: Optional[str] = Field(
        default=None,
        description="Stripe Subscription ID, if on a paid plan (e.g., Pro)",
        index=True # Suggest adding index=True for querying
    )
    subscription_status: Optional[StripeSubscriptionStatus] = Field(
        default=None,
        description="Status of the Stripe subscription (e.g., active, canceled, past_due)"
    )
    current_period_end: Optional[datetime] = Field(
        default=None,
        description="End date of the current billing period for an active subscription"
    )
    # --- STRIPE SUBSCRIPTION FIELDS END ---

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        arbitrary_types_allowed=True, # Important for UUID and datetime
        use_enum_values=True,
    )

# Final model representing a Teacher read from DB (API Response)
class Teacher(TeacherInDBBase):
    # Inherits all fields including Stripe subscription fields
    pass

# Model for updating (Profile Page uses this, or admin updates)
class TeacherUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    school_name: Optional[str] = Field(None, min_length=1, max_length=200)
    role: Optional[TeacherRole] = None
    is_administrator: Optional[bool] = Field(None, description="Set administrative privileges")
    description: Optional[str] = Field(None)
    country: Optional[str] = Field(None)
    state_county: Optional[str] = Field(None)
    is_active: Optional[bool] = Field(None)

    # --- Fields for Stripe Integration ---
    # Typically, stripe_customer_id is set once and not changed.
    # Other Stripe fields (current_plan, subscription_status, stripe_subscription_id, current_period_end)
    # are usually managed by webhooks. They are included here for completeness if admin override is needed.
    stripe_customer_id: Optional[str] = Field(None, description="Stripe Customer ID")
    current_plan: Optional[SubscriptionPlan] = None
    subscription_status: Optional[StripeSubscriptionStatus] = None
    # stripe_subscription_id: Optional[str] = None # Usually set by webhooks, not direct update
    # current_period_end: Optional[datetime] = None # Usually set by webhooks, not direct update
    # --- End Stripe Integration Fields ---

    model_config = ConfigDict(
        use_enum_values=True,
    )