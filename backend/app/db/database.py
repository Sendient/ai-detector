# app/db/database.py
import motor.motor_asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone # Added timezone import

# Import configuration from your core config module
# Adjust path if needed
from app.core.config import MONGODB_URL, DB_NAME, PROJECT_NAME

# Setup logging using your project name
# Ensure logging is configured elsewhere (e.g., main.py)
# logging.basicConfig(level=logging.INFO) # Avoid configuring here if done elsewhere
logger = logging.getLogger(f"{PROJECT_NAME}.db") # Using f-string for logger name

# Global variables to hold the client and database instances with type hints
# Using underscore prefix convention for module-level globals
_client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None
_db: Optional[motor.motor_asyncio.AsyncIOMotorDatabase] = None

async def connect_to_mongo() -> bool:
    """
    Establishes connection to the MongoDB/Cosmos DB database.
    Reads configuration from app.core.config.

    Returns:
        bool: True if connection successful, False otherwise.
    """
    global _client, _db

    if _db is not None:
        logger.info("Database connection already established.")
        return True

    if not MONGODB_URL:
        logger.error("FATAL ERROR: MONGODB_URL is not configured in app.core.config.")
        return False

    logger.info(f"Attempting to connect to MongoDB database: '{DB_NAME}'...")
    try:
        _client = motor.motor_asyncio.AsyncIOMotorClient(
            MONGODB_URL,
            tls=True,           # Often required for Cosmos DB
            retryWrites=False,    # Required for Cosmos DB
            serverSelectionTimeoutMS=10000,
            maxPoolSize=10,
            uuidRepresentation='standard' # <-- ADDED THIS LINE
            # appname=PROJECT_NAME # Optional: helps identify app in logs/metrics
        )
        # Ping the server to verify connection before proceeding
        await _client.admin.command('ping')
        logger.info("MongoDB server ping successful.")

        _db = _client[DB_NAME]
        logger.info(f"Successfully connected to MongoDB/Cosmos DB database: '{DB_NAME}'")
        return True

    except Exception as e:
        logger.error(f"ERROR: Could not connect to MongoDB: {e}", exc_info=True)
        _client = None
        _db = None
        return False

async def close_mongo_connection():
    """Closes the MongoDB connection and resets state."""
    global _client, _db
    if _client:
        logger.info("Closing MongoDB connection...")
        _client.close()
        logger.info("MongoDB connection closed.")
        _client = None
        _db = None
    else:
        logger.info("No active MongoDB connection to close.")

def get_database() -> Optional[motor.motor_asyncio.AsyncIOMotorDatabase]:
    """
    Returns the database instance.
    Relies on connect_to_mongo() being called successfully at app startup.
    """
    if _db is None:
        logger.warning("Warning: Database instance is not initialized! Check connection.")
    return _db

def get_mongo_client() -> Optional[motor.motor_asyncio.AsyncIOMotorClient]:
    """
    Returns the MongoDB client instance.
    Relies on connect_to_mongo() being called successfully at app startup.
    """
    if _client is None:
        logger.warning("Warning: MongoDB client is not initialized! Check connection.")
    return _client

async def check_database_health() -> Dict[str, Any]:
    """
    Performs a health check on the database connection and returns detailed status information.

    Returns:
        Dict containing status, connection details, collection info, errors, timestamp.
    """
    # Define expected collections based on crud.py constants (assuming crud.py is accessible or names are hardcoded/configured)
    # If importing crud causes circular dependencies, list names directly
    try:
        from ..db import crud # Try importing crud to get constants
        EXPECTED_COLLECTIONS = [
            crud.SCHOOL_COLLECTION,
            crud.TEACHER_COLLECTION,
            crud.CLASSGROUP_COLLECTION,
            crud.STUDENT_COLLECTION,
            crud.DOCUMENT_COLLECTION,
            crud.RESULT_COLLECTION,
            crud.BATCH_COLLECTION
        ]
    except ImportError:
         # Fallback if crud cannot be imported here
         EXPECTED_COLLECTIONS = [
            "schools", "teachers", "classgroups", "students",
            "documents", "results", "batches"
         ]


    health_info = {
        "status": "OK",
        "connected": False,
        "collections": [],
        "expected_collections": EXPECTED_COLLECTIONS,
        "missing_collections": [],
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z" # Use UTC timestamp
    }

    try:
        db_instance = get_database() # Renamed variable to avoid conflict
        # Use 'is None' check
        if db_instance is None:
            health_info.update({
                "status": "ERROR",
                "error": "Database instance not initialized (connection likely failed on startup)"
            })
            return health_info

        # Verify connection with ping using the client from the db instance
        if db_instance.client:
             await db_instance.client.admin.command('ping')
             health_info["connected"] = True
        else:
             raise RuntimeError("Database client not available for ping")


        # List actual collections
        collections = await db_instance.list_collection_names()
        health_info["collections"] = collections

        # Check for missing expected collections
        missing = [col for col in EXPECTED_COLLECTIONS if col not in collections]
        if missing:
            health_info["missing_collections"] = missing
            health_info["status"] = "WARNING" # Downgrade status if collections missing
            logger.warning(f"Database health check WARNING: Missing expected collections: {missing}")

        return health_info

    except Exception as e:
        logger.error(f"Database health check failed: {e}", exc_info=True)
        health_info.update({
            "status": "ERROR",
            "connected": False, # Explicitly set connected to false on error
            "error": str(e)
        })
        return health_info

# Helper function (kept for reference, but crud.py has its own _get_collection)
# def _get_collection(collection_name: str) -> Optional[AsyncIOMotorCollection]: ...

