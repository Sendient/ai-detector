# app/core/config.py
import os
import logging
from dotenv import load_dotenv
from pathlib import Path
from typing import Optional, List
from pydantic_settings import BaseSettings

# --- Path Setup & .env Loading ---
# Assume .env is in the backend project root, two levels up from core
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / '.env'

# Check if .env exists and load it
if ENV_PATH.is_file():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    # Use print for early config warnings as logger might not be set up yet
    print(f"Warning: .env file not found at {ENV_PATH}. Relying on system environment variables.")

# --- Pydantic Settings Class ---
class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Detector API"
    DEBUG: bool = False
    VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    # Database Settings
    MONGODB_URL: Optional[str] = None
    DB_NAME: str = "aidetector_dev1"

    # Kinde Backend Settings
    KINDE_DOMAIN: Optional[str] = None
    KINDE_AUDIENCE: Optional[str] = None # This can be a single string
    KINDE_CLIENT_ID: Optional[str] = None # For machine-to-machine if used
    # If KINDE_AUDIENCE can be multiple, use: KINDE_AUDIENCE: Optional[List[str]] = None

    # Azure Blob Storage Settings
    AZURE_BLOB_CONNECTION_STRING: Optional[str] = None
    AZURE_BLOB_CONTAINER_NAME: str = "uploaded-documents"

    # ML API Endpoint
    ML_API_URL: Optional[str] = "https://fa-sdt-uks-aitextdet-prod.azurewebsites.net/api/ai-text-detection?code=PZrMzMk1VBBCyCminwvgUfzv_YGhVU-5E1JIs2if7zqiAzFuMhUC-g%3D%3D" # Default Production URL

    # Stripe Settings (Placeholders)
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None

    # Optional: Allowed origins for CORS (can be a list or a comma-separated string)
    ALLOWED_ORIGINS: List[str] = []

    # Add other environment variables as needed
    # e.g., ML_API_KEY: Optional[str] = None

    # Pydantic-settings can automatically load from .env if configured here
    # class Config:
    #     env_file = ENV_PATH # Use the path determined above
    #     env_file_encoding = "utf-8"
    #     extra = 'ignore' # Ignore extra fields in .env not defined in Settings

# Create an instance of the Settings class
settings = Settings()

# --- Logging Setup ---
# Set logging level based on settings.DEBUG
LOG_LEVEL_NAME: str = os.getenv("LOG_LEVEL", "WARNING").upper()
if settings.DEBUG:
    LOG_LEVEL_NAME = "DEBUG"

# Convert log level name to actual level
ACTUAL_LOG_LEVEL = getattr(logging, LOG_LEVEL_NAME, logging.WARNING)

logging.basicConfig(
    level=ACTUAL_LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s' # More detailed format
)

# Configure specific loggers (can be more granular if needed)
logging.getLogger('uvicorn').setLevel(logging.WARNING)
logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
logging.getLogger('fastapi').setLevel(logging.INFO if settings.DEBUG else logging.WARNING)
logging.getLogger('motor').setLevel(logging.WARNING)
logging.getLogger('azure').setLevel(logging.WARNING)
logging.getLogger('pymongo').setLevel(logging.WARNING)

# Get logger for this module (config.py)
logger = logging.getLogger(__name__)

# --- Validate critical settings after loading ---
if not settings.MONGODB_URL:
    logger.critical("CRITICAL: MONGODB_URL environment variable is not set and no default provided.")
# No need to check DB_NAME as it has a default

if not settings.KINDE_DOMAIN:
    logger.warning("KINDE_DOMAIN environment variable is not set. Authentication will likely fail.")
if not settings.KINDE_AUDIENCE:
    logger.warning("KINDE_AUDIENCE environment variable is not set. Token validation might fail.")

if not settings.AZURE_BLOB_CONNECTION_STRING:
    logger.warning("AZURE_BLOB_CONNECTION_STRING environment variable is not set. File uploads will fail.")
# No need to check AZURE_BLOB_CONTAINER_NAME as it has a default

# --- Log loaded settings (optional, careful with secrets in real logs) ---
if settings.DEBUG:
    logger.debug(f"PROJECT_NAME: {settings.PROJECT_NAME}")
    logger.debug(f"DEBUG: {settings.DEBUG}")
    logger.debug(f"API_V1_PREFIX: {settings.API_V1_PREFIX}")
    logger.debug(f"DB_NAME: {settings.DB_NAME}")
    logger.debug(f"KINDE_DOMAIN: {settings.KINDE_DOMAIN}")
    logger.debug(f"KINDE_AUDIENCE: {settings.KINDE_AUDIENCE}")
    logger.debug(f"AZURE_BLOB_CONTAINER_NAME: {settings.AZURE_BLOB_CONTAINER_NAME}")
    logger.debug(f"MONGODB_URL Set: {'Yes' if settings.MONGODB_URL else 'No - CRITICAL'}")
    logger.debug(f"AZURE_BLOB_CONNECTION_STRING Set: {'Yes' if settings.AZURE_BLOB_CONNECTION_STRING else 'No - WARNING'}")

# The individual uppercase constants previously defined (e.g., PROJECT_NAME, DEBUG directly from os.getenv)
# are now superseded by accessing them via the 'settings' object, e.g., settings.PROJECT_NAME, settings.DEBUG.
# Your application code should be updated to import and use 'settings.VARIABLE_NAME' 
# instead of 'VARIABLE_NAME' from this module if it was doing so.
# However, files like security.py that did `from .config import KINDE_DOMAIN` will continue to work
# if KINDE_DOMAIN is still present as a module-level variable (which it will be if not removed after settings definition).
# For consistency, it's better to have other modules import the `settings` object.

# To ensure modules importing specific constants still work during transition, we can alias them (optional):
PROJECT_NAME = settings.PROJECT_NAME
DEBUG = settings.DEBUG
VERSION = settings.VERSION
API_V1_PREFIX = settings.API_V1_PREFIX
MONGODB_URL = settings.MONGODB_URL
DB_NAME = settings.DB_NAME
KINDE_DOMAIN = settings.KINDE_DOMAIN
KINDE_AUDIENCE = settings.KINDE_AUDIENCE
AZURE_BLOB_CONNECTION_STRING = settings.AZURE_BLOB_CONNECTION_STRING
AZURE_BLOB_CONTAINER_NAME = settings.AZURE_BLOB_CONTAINER_NAME
STRIPE_SECRET_KEY = settings.STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET = settings.STRIPE_WEBHOOK_SECRET

