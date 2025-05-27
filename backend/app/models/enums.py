# app/models/enums.py
from enum import Enum

class TeacherRole(str, Enum):
    TEACHER = "teacher"
    SCHOOL_ADMIN = "school_admin"  # Assuming you might have roles like this
    # Add any other roles your system uses or might use
    # Example: IT_COORDINATOR = "it_coordinator"
    # Example: DISTRICT_ADMIN = "district_admin"

class MarketingSource(str, Enum):
    GOOGLE = "Google"
    FACEBOOK = "Facebook"
    LINKEDIN = "LinkedIn"
    WORD_OF_MOUTH = "Word of Mouth"
    CONFERENCE = "Conference"
    EMAIL_MARKETING = "Email Marketing" # Example addition
    EDUCATIONAL_FORUM = "Educational Forum" # Example addition
    OTHER = "Other"
    # Add other sources as relevant to your marketing efforts

class FileType(str, Enum):
    PDF = "application/pdf"
    DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    TXT = "text/plain"
    TEXT = "text/plain"  # Alias for TXT
    PNG = "image/png"
    JPG = "image/jpeg"
    JPEG = "image/jpeg" # Alias for JPG

class DocumentStatus(str, Enum):
    UPLOADED = "UPLOADED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED" # Assessment finished, results available
    FAILED = "FAILED"       # As seen in tests and common usage
    RETRYING = "RETRYING"   # System is retrying a failed step
    ERROR = "ERROR"         # An error occurred during processing
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED" # User has exceeded their usage limit
    DELETED = "DELETED"     # ADDED: For soft-deleted documents
    # Add other statuses as needed

# --- NEW ENUMS FOR STRIPE INTEGRATION ---
class SubscriptionPlan(str, Enum):
    FREE = "Free"
    PRO = "Pro"
    SCHOOLS = "Schools"  # Added Schools plan
    # If you had a 'Schools' plan that was NOT going through Stripe checkout
    # but you still wanted to represent its status internally, you might add it here:
    # SCHOOLS_CONTACT_US = "Schools (Contact Us)"
    # For now, focusing on plans that interact with Stripe or define access levels.

class StripeSubscriptionStatus(str, Enum):
    ACTIVE = "active"  # Subscription is active and payments are up to date.
    CANCELED = "canceled"  # Subscription has been canceled by the user or admin, will end at period end.
    INCOMPLETE = "incomplete"  # Initial payment attempt failed, needs action from the customer.
    INCOMPLETE_EXPIRED = "incomplete_expired"  # Incomplete payment not resolved, subscription expired.
    PAST_DUE = "past_due"  # Payment failed, Stripe is retrying (dunning). Access might be restricted.
    TRIALING = "trialing"  # User is in a trial period.
    UNPAID = "unpaid" # All payment attempts have failed, subscription is effectively void.
    # These are common Stripe statuses. You can expand or refine based on Stripe's documentation
    # and how you want to handle each case in your application.
# --- END NEW ENUMS ---

class ResultStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"  # Added as a common intermediate state
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING" # As seen in tests
    DELETED = "DELETED"     # ADDED: For soft-deleted results
    # Add other statuses as needed, e.g., CANCELED if applicable to results

class BatchStatus(str, Enum):
    CREATED = "CREATED"               # Batch record created, files may not be uploaded yet
    UPLOADING = "UPLOADING"           # Files are being uploaded
    VALIDATING = "VALIDATING"         # Basic validation of files in progress
    QUEUED = "QUEUED"                 # All files uploaded and validated, batch is queued for processing
    PROCESSING = "PROCESSING"           # Batch is actively being processed (documents are being assessed)
    COMPLETED = "COMPLETED"             # All documents in the batch processed successfully
    PARTIAL_FAILURE = "PARTIAL_FAILURE" # Some documents processed, some failed
    ERROR = "ERROR"                   # A critical error occurred processing the batch itself, or all files failed
    # Add other statuses as needed, e.g., CANCELLED

class BatchPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"