# backend/app/core/config.py
import os
import logging
from dotenv import load_dotenv
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic_settings import BaseSettings
from pydantic import model_validator
from pydantic import EmailStr

# --- Path Setup & .env Loading ---
# Assume .env is in the backend project root, two levels up from core
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / '.env'
# print(f"CONFIG.PY: ENV_PATH determined as: {ENV_PATH}") # REMOVED DEBUG PRINT
# print(f"CONFIG.PY: Does ENV_PATH exist? {ENV_PATH.is_file()}") # REMOVED DEBUG PRINT

# Check if .env exists and load it
# if ENV_PATH.is_file(): # MODIFIED: Commented out
#     load_dotenv(dotenv_path=ENV_PATH) # MODIFIED: Commented out
# else: # MODIFIED: Commented out
#     # Use print for early config warnings as logger might not be set up yet # MODIFIED: Commented out
#     print(f"Warning: .env file not found at {ENV_PATH}. Relying on system environment variables.") # MODIFIED: Commented out

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

    ADMIN_EMAIL_DOMAIN: str = "@sendient.ai" # ADDED: Admin email domain

    # Azure Blob Storage Settings
    AZURE_BLOB_CONNECTION_STRING: Optional[str] = None
    AZURE_BLOB_CONTAINER_NAME: str = "uploaded-documents"

    # ML API Endpoint
    ML_AIDETECTOR_URL: Optional[str] = None # For the AI Detector service
    ML_API_TIMEOUT_SECONDS: int = 60 # Timeout for ML API calls in seconds

    # --- Stripe Settings ---
    STRIPE_SECRET_KEY: Optional[str] = None # e.g., sk_test_YOURKEY or sk_live_YOURKEY
    STRIPE_PUBLISHABLE_KEY: Optional[str] = None # e.g., pk_test_YOURKEY or pk_live_YOURKEY (primarily for frontend)
    STRIPE_WEBHOOK_SECRET: Optional[str] = None # e.g., whsec_YOURKEY (for verifying webhook events)
    STRIPE_PRO_PLAN_PRICE_ID: Optional[str] = None # e.g., price_YOURPRICEID (the ID of your £8/month Pro plan)
    # --- End Stripe Settings ---

    # --- Frontend URL for redirects ---
    FRONTEND_URL: Optional[str] = "http://localhost:5173" # Default for local dev, overridden by .env
    # --- End Frontend URL ---

    # Optional: Allowed origins for CORS (can be a list or a comma-separated string)
    ALLOWED_ORIGINS: str = ""

    # Pydantic-settings can automatically load from .env if configured here
    # For Pydantic V2, model_config is used. For V1, it's class Config.
    # Assuming Pydantic V2 or later, which uses pydantic-settings
    # print(f"CONFIG.PY: About to define Settings.model_config with ENV_PATH: {ENV_PATH}") # REMOVED DEBUG PRINT
    model_config = {
        "env_file": ENV_PATH,
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }
    # If using older Pydantic (V1.x), this would be:
    # class Config:
    #     env_file = ENV_PATH
    #     env_file_encoding = "utf-8"
    #     extra = 'ignore'

    @model_validator(mode='before')
    @classmethod
    def load_deprecated_db_env_vars(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """
        Load database connection details from deprecated environment variables
        if the new ones (MONGODB_URL, DB_NAME) are not already set.
        """
        # Using print here because logger might not be configured when this validator runs
        print("DEBUG [Config Validator]: Entered load_deprecated_db_env_vars.")

        initial_mongodb_url = values.get('MONGODB_URL')
        initial_db_name = values.get('DB_NAME')

        print(f"DEBUG [Config Validator]: Initial MONGODB_URL from values: {'SET' if initial_mongodb_url else 'NOT SET'}")
        if initial_mongodb_url:
            print(f"DEBUG [Config Validator]: Initial MONGODB_URL value (truncated): {str(initial_mongodb_url)[:30]}...")
        
        print(f"DEBUG [Config Validator]: Initial DB_NAME from values: {initial_db_name if initial_db_name else 'NOT SET'}")


        # Fallback for MONGODB_URL
        if not initial_mongodb_url:
            print("DEBUG [Config Validator]: MONGODB_URL not in initial values. Attempting fallback from MONGO_DETAILS.")
            mongodb_url_from_deprecated = os.getenv('MONGO_DETAILS')
            if mongodb_url_from_deprecated:
                values['MONGODB_URL'] = mongodb_url_from_deprecated
                print(f"INFO [Config Validator]: Using MONGO_DETAILS for MONGODB_URL: {mongodb_url_from_deprecated[:30]}...")
            else:
                print("DEBUG [Config Validator]: MONGO_DETAILS not found in os.getenv(). MONGODB_URL remains unset by fallback.")
        else:
            print("DEBUG [Config Validator]: MONGODB_URL found in initial values. No fallback needed from MONGO_DETAILS.")

        # Fallback for DB_NAME
        # Pydantic applies the default for DB_NAME if it's not in .env or system env *after* this validator.
        if 'DB_NAME' not in values: # If DB_NAME wasn't explicitly set (e.g., by an env var DB_NAME=value)
            print("DEBUG [Config Validator]: DB_NAME not in initial values. Attempting fallbacks.")
            mongo_database_name_env = os.getenv('MONGO_DATABASE_NAME') # Check Azure-provided var first
            mongo_initdb_database_env = os.getenv('MONGO_INITDB_DATABASE') # Check original fallback second

            if mongo_database_name_env:
                values['DB_NAME'] = mongo_database_name_env
                print(f"INFO [Config Validator]: Using MONGO_DATABASE_NAME ('{mongo_database_name_env}') for DB_NAME field.")
            elif mongo_initdb_database_env:
                values['DB_NAME'] = mongo_initdb_database_env
                print(f"INFO [Config Validator]: Using MONGO_INITDB_DATABASE ('{mongo_initdb_database_env}') for DB_NAME field.")
            else:
                print("DEBUG [Config Validator]: Neither MONGO_DATABASE_NAME nor MONGO_INITDB_DATABASE found in os.getenv(). DB_NAME field will rely on Pydantic default or remain unset by fallback.")
        else:
            # If DB_NAME was in values, it means it was explicitly set by an env var named DB_NAME.
            print(f"DEBUG [Config Validator]: DB_NAME ('{initial_db_name}') found in initial values (e.g., from .env or system env DB_NAME). No fallback needed.")
        
        final_mongodb_url = values.get('MONGODB_URL')
        final_db_name = values.get('DB_NAME') # This could be the default if not set by .env or fallback

        print(f"DEBUG [Config Validator]: Final MONGODB_URL to be used: {'SET' if final_mongodb_url else 'NOT SET'}")
        if final_mongodb_url:
            print(f"DEBUG [Config Validator]: Final MONGODB_URL value (truncated): {str(final_mongodb_url)[:30]}...")
        print(f"DEBUG [Config Validator]: Final DB_NAME to be used: {final_db_name if final_db_name else 'Pydantic Default will apply'}")
        print("DEBUG [Config Validator]: Exiting load_deprecated_db_env_vars.")
        return values

    SENDGRID_API_KEY: str = "default_sendgrid_api_key"
    SENDGRID_FROM_EMAIL: EmailStr = "noreply@example.com"

    # Free Plan: Both Word and Character-based limits
    FREE_PLAN_MONTHLY_WORD_LIMIT: int = 5000
    FREE_PLAN_MONTHLY_CHAR_LIMIT: int = 25000

    # Pro Plan: Both Word and Character-based limits
    PRO_PLAN_MONTHLY_WORD_LIMIT: int = 100000
    PRO_PLAN_MONTHLY_CHAR_LIMIT: int = 500000

    # Sentry
    SENTRY_DSN: str | None = None

# Create an instance of the Settings class
# print("CONFIG.PY: About to create Settings() instance.") # REMOVED DEBUG PRINT
settings = Settings()
# print(f"CONFIG.PY: Settings() instance created. settings.STRIPE_WEBHOOK_SECRET: {settings.STRIPE_WEBHOOK_SECRET}") # REMOVED DEBUG PRINT

# --- Logging Setup ---
# Set logging level based on settings.DEBUG
LOG_LEVEL_NAME: str = os.getenv("LOG_LEVEL", "WARNING").upper()
if settings.DEBUG:
    LOG_LEVEL_NAME = "DEBUG"

ACTUAL_LOG_LEVEL = getattr(logging, LOG_LEVEL_NAME, logging.WARNING)

logging.basicConfig(
    level=ACTUAL_LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logging.getLogger('uvicorn').setLevel(logging.WARNING)
logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
logging.getLogger('fastapi').setLevel(logging.INFO if settings.DEBUG else logging.WARNING)
logging.getLogger('motor').setLevel(logging.WARNING)
logging.getLogger('azure').setLevel(logging.WARNING)
logging.getLogger('pymongo').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# --- Validate critical settings after loading ---
if not settings.MONGODB_URL:
    logger.critical("CRITICAL: MONGODB_URL environment variable is not set.")
if not settings.KINDE_DOMAIN:
    logger.warning("KINDE_DOMAIN environment variable is not set. Authentication will likely fail.")
if not settings.KINDE_AUDIENCE:
    logger.warning("KINDE_AUDIENCE environment variable is not set. Token validation might fail.")
if not settings.AZURE_BLOB_CONNECTION_STRING:
    logger.warning("AZURE_BLOB_CONNECTION_STRING environment variable is not set. File uploads will fail.")

# --- Validate Stripe settings ---
if not settings.STRIPE_SECRET_KEY:
    logger.critical("CRITICAL: STRIPE_SECRET_KEY environment variable is not set. Stripe integration will fail.")
if not settings.STRIPE_PUBLISHABLE_KEY:
    logger.warning("STRIPE_PUBLISHABLE_KEY environment variable is not set. Frontend Stripe integration might be affected.")
if not settings.STRIPE_WEBHOOK_SECRET:
    logger.critical("CRITICAL: STRIPE_WEBHOOK_SECRET environment variable is not set. Stripe webhook verification will fail.")
if not settings.STRIPE_PRO_PLAN_PRICE_ID:
    logger.critical("CRITICAL: STRIPE_PRO_PLAN_PRICE_ID environment variable is not set. Subscribing to Pro plan will fail.")
# --- End Stripe settings validation ---

# --- Validate Frontend URL ---
if not settings.FRONTEND_URL:
    logger.critical("CRITICAL: FRONTEND_URL environment variable is not set. Stripe redirects will likely fail.")
# --- End Frontend URL validation ---

# --- Log loaded settings (optional, careful with secrets in real logs) ---
if settings.DEBUG:
    logger.debug(f"PROJECT_NAME: {settings.PROJECT_NAME}")
    logger.debug(f"DEBUG: {settings.DEBUG}")
    # ... (log other non-sensitive settings as you see fit) ...
    logger.debug(f"MONGODB_URL Set: {'Yes' if settings.MONGODB_URL else 'No - CRITICAL'}")
    logger.debug(f"STRIPE_SECRET_KEY Set: {'Yes' if settings.STRIPE_SECRET_KEY else 'No - CRITICAL'}")
    logger.debug(f"STRIPE_PUBLISHABLE_KEY Set: {'Yes' if settings.STRIPE_PUBLISHABLE_KEY else 'No - WARNING'}")
    logger.debug(f"STRIPE_WEBHOOK_SECRET Set: {'Yes' if settings.STRIPE_WEBHOOK_SECRET else 'No - CRITICAL'}")
    logger.debug(f"STRIPE_PRO_PLAN_PRICE_ID Set: {'Yes' if settings.STRIPE_PRO_PLAN_PRICE_ID else 'No - CRITICAL'}")
    logger.debug(f"FRONTEND_URL Set: {'Yes' if settings.FRONTEND_URL else 'No - CRITICAL'}")
    logger.debug(f"ADMIN_EMAIL_DOMAIN: {settings.ADMIN_EMAIL_DOMAIN}") # ADDED: Log the loaded admin email domain


# --- Aliases for backward compatibility or direct import (optional, but good for transition) ---
# It's generally better for other modules to import the `settings` object directly.
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
ADMIN_EMAIL_DOMAIN = settings.ADMIN_EMAIL_DOMAIN # ADDED: Alias for direct import if needed

# Stripe settings aliases
STRIPE_SECRET_KEY = settings.STRIPE_SECRET_KEY
STRIPE_PUBLISHABLE_KEY = settings.STRIPE_PUBLISHABLE_KEY
STRIPE_WEBHOOK_SECRET = settings.STRIPE_WEBHOOK_SECRET
STRIPE_PRO_PLAN_PRICE_ID = settings.STRIPE_PRO_PLAN_PRICE_ID

# Frontend URL alias
FRONTEND_URL = settings.FRONTEND_URL

