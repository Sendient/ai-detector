# app/models/enums.py

from enum import Enum

# --- User/Teacher Related Enums ---

class TeacherRole(str, Enum):
    """Enumeration for different roles a teacher/user might have."""
    TEACHER = "teacher"
    TUTOR = "tutor"
    LECTURER = "lecturer"
    ADMIN = "admin"
    OTHER = "other"

class MarketingSource(str, Enum):
    """Enumeration for how a user heard about the service."""
    GOOGLE = "Google"
    FACEBOOK = "Facebook"
    LINKEDIN = "Linkedin"
    CONFERENCE = "Conference"
    REFERRAL = "Referral"
    OTHER = "Other"

# --- Document/File Related Enums ---

class FileType(str, Enum):
    """Enumeration for supported document/file types."""
    PDF = "pdf"
    DOCX = "docx"
    PNG = "png"
    JPG = "jpg"
    JPEG = "jpeg" # Added common alias
    TXT = "txt"
    TEXT = "text" # Added for potential copy-paste input type

class DocumentStatus(str, Enum):
    """Enumeration for the processing status of a document."""
    UPLOADED = "UPLOADED"     # File received and stored (Changed to uppercase)
    QUEUED = "QUEUED"         # Queued for AI analysis (Changed to uppercase)
    PROCESSING = "PROCESSING" # Actively being analyzed by ML model (Changed to uppercase)
    RETRYING = "RETRYING"     # Retry attempt in progress
    COMPLETED = "COMPLETED"   # Analysis finished, result available (Changed to uppercase)
    ERROR = "ERROR"           # An error occurred during processing (Changed to uppercase)
    FAILED = "FAILED"         # Processing failed permanently

# --- Result Related Enums ---

class ResultStatus(str, Enum):
    """Enumeration for the status of an AI detection result."""
    PENDING = "PENDING"       # Analysis requested but not yet started/completed (Changed to uppercase)
    ASSESSING = "ASSESSING"   # Analysis in progress (Changed to uppercase)
    COMPLETED = "COMPLETED"   # Analysis complete, score available (Changed to uppercase)
    RETRYING = "RETRYING"     # Retry attempt in progress
    ERROR = "ERROR"           # Error during analysis, score may be unavailable (Changed to uppercase)
    FAILED = "FAILED"         # Analysis failed permanently

class BatchStatus(str, Enum):
    """Enumeration for the status of a document batch upload."""
    CREATED = "CREATED"       # Batch created, files not yet uploaded
    QUEUED = "QUEUED"         # Batch queued for processing
    UPLOADING = "UPLOADING"   # Files are being uploaded
    VALIDATING = "VALIDATING" # Validating uploaded files
    PROCESSING = "PROCESSING" # Processing individual documents
    COMPLETED = "COMPLETED"   # All documents in batch processed
    PARTIAL = "PARTIAL"       # Some documents processed, some failed
    ERROR = "ERROR"           # Batch processing failed

class BatchPriority(str, Enum):
    """Enumeration for batch processing priority."""
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"