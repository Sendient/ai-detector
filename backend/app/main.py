# app/main.py
import logging
import psutil # For system metrics in health check
import time   # For uptime calculation
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any
from datetime import datetime, timedelta, timezone # For uptime calculation
import asyncio
from fastapi import status
from pymongo.errors import OperationFailure
import os

# Import config and database lifecycle functions
# Adjust path '.' based on where main.py is relative to 'core' and 'db'
from .core.config import PROJECT_NAME, API_V1_PREFIX, VERSION
from .db.database import connect_to_mongo, close_mongo_connection, check_database_health, get_database

# Import all endpoint routers
# Adjust path '.' based on where main.py is relative to 'api'
# Includes routers for all entities: schools, teachers, class_groups, students, assignments, documents, results
from .api.v1.endpoints.schools import router as schools_router
from .api.v1.endpoints.teachers import router as teachers_router
from .api.v1.endpoints.class_groups import router as class_groups_router
from .api.v1.endpoints.students import router as students_router
# from app.api.v1.endpoints.assignments import router as assignments_router # COMMENTED OUT
from .api.v1.endpoints.documents import router as documents_router
from .api.v1.endpoints.results import router as results_router
from .api.v1.endpoints.dashboard import router as dashboard_router
from .api.v1.endpoints.analytics import router as analytics_router

# Import batch processor
from .tasks import batch_processor

# Setup logging
logger = logging.getLogger(__name__) # Use main module logger or project-specific
# Ensure logging is configured appropriately elsewhere if not using basicConfig
# logging.basicConfig(level=logging.INFO)

# Track application start time for uptime calculation
APP_START_TIME = time.time()

frontend_origin = os.getenv("FRONTEND_URL")
origins = [
    "http://localhost:5173",  # Vite frontend
    "http://localhost:3000",  # Alternative frontend port
    "http://127.0.0.1:5173",  # Alternative localhost
    "http://127.0.0.1:3000",  # Alternative localhost
    "https://gray-mud-0fe5b3703.6.azurestaticapps.net", # Production frontend origin
    frontend_origin  # Add frontend URL from environment variable
]

# Remove any None values in case the env var is not set
origins = [o for o in origins if o]

# Create FastAPI app instance with detailed configuration
_original_fastapi_app = FastAPI(
    title=f"{PROJECT_NAME} - Sentient AI Detector App",
    version=VERSION, # Use version from config
    description="API for detecting AI-generated content in educational settings",
    # Customize API docs/schema URLs
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
    # Using on_event decorators below for DB lifecycle
)

# Add CORS middleware
_original_fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

# --- Event Handlers for DB Connection and Batch Processor ---
@_original_fastapi_app.on_event("startup")
async def startup_event():
    """
    Event handler for application startup.
    Connects to the database and ensures necessary indexes are created.
    """
    # FORCEFUL LOGGING START
    print("[STARTUP_EVENT_DEBUG] >>> startup_event function ENTERED")
    logger.critical("############################################################")
    logger.critical("[STARTUP_EVENT_CRITICAL] >>> FastAPI startup_event function ENTERED.")
    logger.critical("############################################################")
    # FORCEFUL LOGGING END

    logger.info("Executing startup event: Connecting to database...")
    try:
        # FORCEFUL LOGGING START
        logger.critical("[STARTUP_EVENT_CRITICAL] Attempting connect_to_mongo()")
        # FORCEFUL LOGGING END
        await connect_to_mongo() # Ensure this is awaited
        # FORCEFUL LOGGING START
        logger.critical("[STARTUP_EVENT_CRITICAL] connect_to_mongo() SUCCEEDED")
        # FORCEFUL LOGGING END
        logger.info("Startup event: Database connection successful.")
    except Exception as e:
        # FORCEFUL LOGGING START
        logger.critical(f"[STARTUP_EVENT_CRITICAL] connect_to_mongo() FAILED: {e}", exc_info=True)
        # FORCEFUL LOGGING END
        logger.error(f"Startup event: Failed to connect to database: {e}", exc_info=True)
        raise

    # FORCEFUL LOGGING START
    logger.critical("[STARTUP_EVENT_CRITICAL] Attempting to get_database()")
    # FORCEFUL LOGGING END
    db = get_database() # Get database instance
    if db is None:
        # FORCEFUL LOGGING START
        logger.critical("[STARTUP_EVENT_CRITICAL] get_database() returned None. Cannot ensure collections/indexes.")
        # FORCEFUL LOGGING END
        logger.error("Cannot ensure collections/indexes: Database connection not available (db is None).")
        return
    
    # FORCEFUL LOGGING START
    logger.critical(f"[STARTUP_EVENT_CRITICAL] get_database() SUCCEEDED. DB object: {db}")
    logger.critical("[STARTUP_EVENT_CRITICAL] Ensuring database collections and indexes...")
    # FORCEFUL LOGGING END
    logger.info("Ensuring database collections and indexes...")

    try:
        # --- Ensure Collections Exist ---
        # Updated to include all known collections from crud.py constants
        collection_names_to_ensure = [
            "schools", "teachers", "classgroups", "students", 
            "documents", "results", "batches" # Added "batches" as it's in crud.py too
        ]
        # FORCEFUL LOGGING START
        logger.critical(f"[STARTUP_EVENT_CRITICAL] Collections to ensure: {collection_names_to_ensure}")
        logger.critical("[STARTUP_EVENT_CRITICAL] Attempting db.list_collection_names()")
        # FORCEFUL LOGGING END
        existing_collections = await db.list_collection_names()
        # FORCEFUL LOGGING START
        logger.critical(f"[STARTUP_EVENT_CRITICAL] Existing collections from DB: {existing_collections}")
        # FORCEFUL LOGGING END

        for coll_name in collection_names_to_ensure:
            # FORCEFUL LOGGING START
            logger.critical(f"[STARTUP_EVENT_CRITICAL] Checking collection: '{coll_name}'")
            # FORCEFUL LOGGING END
            if coll_name not in existing_collections:
                # FORCEFUL LOGGING START
                logger.critical(f"[STARTUP_EVENT_CRITICAL] Collection '{coll_name}' NOT FOUND. Attempting to create.")
                # FORCEFUL LOGGING END
                try:
                    await db.create_collection(coll_name)
                    # FORCEFUL LOGGING START
                    logger.critical(f"[STARTUP_EVENT_CRITICAL] Successfully CREATED collection '{coll_name}'.")
                    # FORCEFUL LOGGING END
                    logger.info(f"Successfully created collection '{coll_name}'.")
                except OperationFailure as e:
                    # FORCEFUL LOGGING START
                    logger.critical(f"[STARTUP_EVENT_CRITICAL] OperationFailure CREATING collection '{coll_name}': {e.details.get('errmsg', str(e))}", exc_info=True)
                    # FORCEFUL LOGGING END
                    logger.error(f"OperationFailure creating collection '{coll_name}': {e.details.get('errmsg', str(e))}", exc_info=True)
                    # Depending on policy, you might want to raise this
                except Exception as e:
                    # FORCEFUL LOGGING START
                    logger.critical(f"[STARTUP_EVENT_CRITICAL] Unexpected error CREATING collection '{coll_name}': {e}", exc_info=True)
                    # FORCEFUL LOGGING END
                    logger.error(f"Unexpected error creating collection '{coll_name}': {e}", exc_info=True)
                    # Depending on policy, you might want to raise this
            else:
                # FORCEFUL LOGGING START
                logger.critical(f"[STARTUP_EVENT_CRITICAL] Collection '{coll_name}' ALREADY EXISTS.")
                # FORCEFUL LOGGING END
                logger.info(f"Collection '{coll_name}' already exists.")

        # --- Ensure Indexes ---
        # Ensure indexes for Teachers collection
        # FORCEFUL LOGGING START
        logger.critical("[STARTUP_EVENT_CRITICAL] Ensuring indexes for 'teachers' collection.")
        # FORCEFUL LOGGING END
        teachers_collection = db.get_collection("teachers")
        try:
            await teachers_collection.create_index("kinde_id", name="idx_teacher_kinde_id", unique=False)
            # FORCEFUL LOGGING START
            logger.critical("[STARTUP_EVENT_CRITICAL] Successfully created/verified index 'idx_teacher_kinde_id' on teachers.kinde_id.")
            # FORCEFUL LOGGING END
            logger.info("Successfully created/verified non-unique index 'idx_teacher_kinde_id' on teachers.kinde_id")
        except OperationFailure as e:
            if e.code == 85: # IndexOptionsConflict
                # FORCEFUL LOGGING START
                logger.critical(f"[STARTUP_EVENT_CRITICAL] Index conflict for 'idx_teacher_kinde_id' on teachers.kinde_id: {e.details.get('errmsg', str(e))}")
                # FORCEFUL LOGGING END
                logger.warning(
                    f"Index conflict for 'idx_teacher_kinde_id' on teachers.kinde_id. "
                    f"Code: {e.code}, Error: {e.details.get('errmsg', str(e))}. "
                    f"This means an index with the same name exists but has different options (e.g., unique, sparse). "
                    f"The application will continue, but please resolve this manually in Azure Portal/Cosmos DB "
                    f"by deleting the existing 'idx_teacher_kinde_id' and allowing the application to recreate it, "
                    f"or by updating the application\'s index definition in app/main.py to match the existing one."
                )
            else:
                # FORCEFUL LOGGING START
                logger.critical(f"[STARTUP_EVENT_CRITICAL] Database OperationFailure while creating index 'idx_teacher_kinde_id' on teachers: {e.details.get('errmsg', str(e))}", exc_info=True)
                # FORCEFUL LOGGING END
                logger.error(f"Database OperationFailure while creating index 'idx_teacher_kinde_id': {e.details.get('errmsg', str(e))}", exc_info=True)
                raise # Re-raise other OperationFailures
        except Exception as e:
            # FORCEFUL LOGGING START
            logger.critical(f"[STARTUP_EVENT_CRITICAL] Unexpected error creating index 'idx_teacher_kinde_id' on teachers: {e}", exc_info=True)
            # FORCEFUL LOGGING END
            logger.error(f"Unexpected error creating index 'idx_teacher_kinde_id' on teachers: {e}", exc_info=True)
            # Depending on policy, you might want to raise this too

        # Example for ensuring indexes on 'results' collection if needed
        # FORCEFUL LOGGING START
        logger.critical("[STARTUP_EVENT_CRITICAL] Ensuring indexes for 'results' collection (example shown). Adjust as needed.")
        # FORCEFUL LOGGING END
        # results_collection = db.get_collection("results")
        # await results_collection.create_index("document_id", name="idx_result_document_id", unique=True) # Example: if result is unique per document
        # logger.info("Successfully created/verified index 'idx_result_document_id' on results.document_id")

        # FORCEFUL LOGGING START
        logger.critical("[STARTUP_EVENT_CRITICAL] Database collections and indexes ensured.")
        # FORCEFUL LOGGING END
        logger.info("Database collections and indexes ensured.")

    except Exception as e:
        # FORCEFUL LOGGING START
        logger.critical(f"[STARTUP_EVENT_CRITICAL] An error occurred during collection or index creation: {e}", exc_info=True)
        # FORCEFUL LOGGING END
        logger.error(f"An error occurred during collection or index creation: {e}", exc_info=True)
        # Decide if app should proceed if creation fails

    # Start background tasks if any (like BatchProcessor)
    try:
        # FORCEFUL LOGGING START
        logger.critical("[STARTUP_EVENT_CRITICAL] Attempting to start BatchProcessor.")
        # FORCEFUL LOGGING END
        # Assuming BatchProcessor is designed to be started and run in the background
        from .tasks.batch_processor import BatchProcessor # Local import to avoid circular dependency issues
        processor = BatchProcessor()
        asyncio.create_task(processor.process_batches()) # Changed from processor.run() to processor.process_batches()
        # FORCEFUL LOGGING START
        logger.critical("[STARTUP_EVENT_CRITICAL] Batch processor task created.")
        # FORCEFUL LOGGING END
        logger.info("Batch processor started")
    except Exception as e:
        # FORCEFUL LOGGING START
        logger.critical(f"[STARTUP_EVENT_CRITICAL] Failed to start batch processor: {e}", exc_info=True)
        # FORCEFUL LOGGING END
        logger.error(f"Failed to start batch processor: {e}", exc_info=True)
    
    # FORCEFUL LOGGING START
    logger.critical("############################################################")
    logger.critical("[STARTUP_EVENT_CRITICAL] >>> FastAPI startup_event function COMPLETED.")
    logger.critical("############################################################")
    # FORCEFUL LOGGING END

@_original_fastapi_app.on_event("shutdown")
async def shutdown_event():
    """Stop batch processor and disconnect from MongoDB on application shutdown."""
    logger.info("Executing shutdown event...")
    
    # Stop batch processor
    batch_processor.stop()
    logger.info("Batch processor stopped")
    
    # Disconnect from database
    logger.info("Disconnecting from database...")
    await close_mongo_connection()

# --- API Endpoints ---
@_original_fastapi_app.get("/", tags=["Root"], include_in_schema=False) # Decorate _original_fastapi_app
async def read_root():
    """Root endpoint welcome message."""
    return {"message": f"Welcome to {PROJECT_NAME}"}

@_original_fastapi_app.get("/health", status_code=200, tags=["Health Check"]) # Decorate _original_fastapi_app
async def health_check() -> Dict[str, Any]:
    """
    Comprehensive health check endpoint that verifies:
    - Application status and metrics (uptime, memory)
    - Database connectivity and collections
    """
    # Get database health information
    db_health = await check_database_health()

    # Get system metrics using psutil
    process = psutil.Process()
    memory_info = process.memory_info()

    # Calculate uptime
    uptime_seconds = time.time() - APP_START_TIME
    uptime = str(timedelta(seconds=int(uptime_seconds)))

    # Prepare response dictionary
    health_info = {
        "status": "OK", # Start with OK, potentially downgrade based on checks
        "application": {
            "name": PROJECT_NAME,
            "version": VERSION,
            "status": "OK", # Application itself is running if it responds
            "uptime": uptime,
            "memory_usage": {
                "rss_bytes": memory_info.rss,  # Resident Set Size (bytes)
                "vms_bytes": memory_info.vms,  # Virtual Memory Size (bytes)
                "percent": f"{process.memory_percent():.2f}%" # Memory usage percentage
            }
        },
        "database": db_health, # Include detailed DB health dictionary
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z" # Use UTC timestamp
    }

    # Determine overall status based on database health
    if db_health.get("status") == "ERROR":
        health_info["status"] = "ERROR"
    elif db_health.get("status") == "WARNING": # If check_database_health can return WARNING
        health_info["status"] = "WARNING"

    return health_info

# --- Liveness and Readiness Probes ---
@_original_fastapi_app.get("/healthz", tags=["Probes"], status_code=status.HTTP_200_OK) # Decorate _original_fastapi_app
async def liveness_probe():
    """Liveness probe: Checks if the application process is running and responsive."""
    return {"status": "live"}

@_original_fastapi_app.get("/readyz", tags=["Probes"]) # Decorate _original_fastapi_app
async def readiness_probe(response: Response):
    """Readiness probe: Checks if the application is ready to serve traffic (e.g., DB connected)."""
    db_health = await check_database_health()
    if db_health.get("status") == "OK":
        response.status_code = status.HTTP_200_OK
        return {"status": "ready", "database": db_health}
    else:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "database": db_health}
# --- End Probes ---

# --- Include API Routers ---
# Apply the configured prefix (e.g., /api/v1) to all included routers
_original_fastapi_app.include_router(schools_router, prefix=API_V1_PREFIX) # Apply to _original_fastapi_app
_original_fastapi_app.include_router(teachers_router, prefix=API_V1_PREFIX) # Apply to _original_fastapi_app
_original_fastapi_app.include_router(class_groups_router, prefix=API_V1_PREFIX) # Apply to _original_fastapi_app
_original_fastapi_app.include_router(students_router, prefix=API_V1_PREFIX) # Apply to _original_fastapi_app
# _original_fastapi_app.include_router(assignments_router, prefix=API_V1_PREFIX) # COMMENTED OUT
_original_fastapi_app.include_router(documents_router, prefix=API_V1_PREFIX) # Apply to _original_fastapi_app
_original_fastapi_app.include_router(results_router, prefix=API_V1_PREFIX)   # Apply to _original_fastapi_app
_original_fastapi_app.include_router(dashboard_router, prefix=API_V1_PREFIX) # Apply to _original_fastapi_app
_original_fastapi_app.include_router(analytics_router, prefix=API_V1_PREFIX) # Apply to _original_fastapi_app

# Add a simple health check endpoint directly to the app
@_original_fastapi_app.get("/api/v1/test-health") # Decorate _original_fastapi_app
def read_root_test_health(): # Renamed function to avoid conflict if 'read_root' is used elsewhere
    return {"Status": "OK"}

# This 'app' will be used by the ASGI server (e.g., uvicorn).
# If state_middleware.app_with_state exists and is used, it would wrap _original_fastapi_app here.
# For now, assuming direct usage or middleware is added via .add_middleware.
app = _original_fastapi_app # The app served by uvicorn is the original, unless wrapped.

# Example if you had an app_with_state wrapper:
# from backend.app.utils.state_middleware import app_with_state # Hypothetical import
# app = app_with_state(_original_fastapi_app)
# Tests would import _original_fastapi_app, uvicorn would run 'app'.

# --- TODOs & Future Enhancements ---
# TODO: Add middleware, CORS configuration, and global exception handlers

