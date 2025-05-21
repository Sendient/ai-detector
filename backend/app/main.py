import logging
import psutil # For system metrics in health check
import time    # For uptime calculation
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any
from datetime import datetime, timedelta, timezone # For uptime calculation
import asyncio
from fastapi import status
from pymongo.errors import OperationFailure
import os
import pymongo
from pymongo import IndexModel

# Import config and database lifecycle functions
from .core.config import PROJECT_NAME, API_V1_PREFIX, VERSION
from .db.database import connect_to_mongo, close_mongo_connection, check_database_health, get_database

# Import all endpoint routers
from .api.v1.endpoints.schools import router as schools_router
from .api.v1.endpoints.teachers import router as teachers_router
from .api.v1.endpoints.class_groups import router as class_groups_router
from .api.v1.endpoints.students import router as students_router
# from app.api.v1.endpoints.assignments import router as assignments_router # COMMENTED OUT
from .api.v1.endpoints.documents import router as documents_router
from .api.v1.endpoints.results import router as results_router
from .api.v1.endpoints.dashboard import router as dashboard_router
from .api.v1.endpoints.analytics import router as analytics_router

# Import batch processor and assessment worker
# RESOLVED CONFLICT 1
from .tasks import batch_processor, assessment_worker

# Setup logging
logger = logging.getLogger(__name__)
# logging.basicConfig(level=logging.INFO) # Ensure logging is configured appropriately

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
    version=VERSION,
    description="API for detecting AI-generated content in educational settings",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
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
    Connects to the database, ensures necessary indexes are created,
    and starts background tasks.
    """
    # FORCEFUL LOGGING START
    print("[STARTUP_EVENT_DEBUG] >>> startup_event function ENTERED")
    logger.critical("############################################################")
    logger.critical("[STARTUP_EVENT_CRITICAL] >>> FastAPI startup_event function ENTERED.")
    logger.critical("############################################################")
    # FORCEFUL LOGGING END

    logger.info("Executing startup event: Connecting to database...")
    try:
        await connect_to_mongo() # Ensure this is awaited
        logger.info("Startup event: Database connection successful.")
    except Exception as e:
        # FORCEFUL LOGGING START
        logger.critical(f"[STARTUP_EVENT_CRITICAL] connect_to_mongo() FAILED: {e}", exc_info=True)
        # FORCEFUL LOGGING END
        logger.error(f"Startup event: Failed to connect to database: {e}", exc_info=True)
        raise

    logger.info("Ensuring database indexes...")
    db = get_database() # Get database instance
    if db is None:
        # FORCEFUL LOGGING START
        logger.critical("[STARTUP_EVENT_CRITICAL] get_database() returned None. Cannot ensure collections/indexes.")
        # FORCEFUL LOGGING END
        logger.error("Cannot ensure collections/indexes: Database connection not available (db is None).")
        return

    try:
        # Ensure indexes for Teachers collection
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
                    f"or by updating the application's index definition in app/main.py to match the existing one."
                )
            else:
                # For other operation failures, log and re-raise
                logger.error(f"Database OperationFailure while creating index 'idx_teacher_kinde_id': {e.details.get('errmsg', str(e))}", exc_info=True)
                raise
        except Exception as e:
            # Catch any other unexpected errors during index creation for teachers
            logger.error(f"Unexpected error creating index 'idx_teacher_kinde_id' on teachers: {e}", exc_info=True)
            # Depending on policy, you might want to raise this too

        # --- Ensure indexes for Assessment Tasks collection ---
        ASSESSMENT_TASKS_COLLECTION_NAME = "assessment_tasks"
        assessment_tasks_collection = db.get_collection(ASSESSMENT_TASKS_COLLECTION_NAME)
        if assessment_tasks_collection is not None:
            idx_assessment_tasks_dequeue = IndexModel(
                [("priority_level", pymongo.DESCENDING), ("created_at", pymongo.ASCENDING)],
                name="idx_assessment_tasks_dequeue_order"
            )
            try:
                await assessment_tasks_collection.create_indexes([idx_assessment_tasks_dequeue])
                logger.critical(f"[STARTUP_EVENT_CRITICAL] Successfully created/verified index 'idx_assessment_tasks_dequeue_order' on {ASSESSMENT_TASKS_COLLECTION_NAME}.")
                logger.info(f"Successfully created/verified index 'idx_assessment_tasks_dequeue_order' on {ASSESSMENT_TASKS_COLLECTION_NAME}")
            except OperationFailure as e:
                if e.code == 85: # IndexOptionsConflict
                    logger.critical(f"[STARTUP_EVENT_CRITICAL] Index conflict for 'idx_assessment_tasks_dequeue_order' on {ASSESSMENT_TASKS_COLLECTION_NAME}: {e.details.get('errmsg', str(e))}")
                    logger.warning(
                        f"Index conflict for 'idx_assessment_tasks_dequeue_order' on {ASSESSMENT_TASKS_COLLECTION_NAME}. "
                        f"Code: {e.code}, Error: {e.details.get('errmsg', str(e))}. "
                        f"This means an index with the same name exists but has different options. "
                        f"The application will continue, but please resolve this manually in Azure Portal/Cosmos DB "
                        f"by deleting the existing index and allowing the application to recreate it, "
                        f"or by updating the application's index definition to match."
                    )
                elif "The order by query does not have a corresponding composite index that it can be served from." in e.details.get('errmsg', ''):
                    logger.critical(f"[STARTUP_EVENT_CRITICAL] Cosmos DB specific error for 'idx_assessment_tasks_dequeue_order' on {ASSESSMENT_TASKS_COLLECTION_NAME}: {e.details.get('errmsg', str(e))}. This indicates the composite index is still missing or not usable by Cosmos DB despite creation attempt.")
                    logger.error(f"Cosmos DB indexing issue for 'idx_assessment_tasks_dequeue_order': {e.details.get('errmsg', str(e))}", exc_info=True)
                    # Potentially raise here if this index is absolutely critical for startup
                else:
                    logger.critical(f"[STARTUP_EVENT_CRITICAL] Database OperationFailure while creating index 'idx_assessment_tasks_dequeue_order' on {ASSESSMENT_TASKS_COLLECTION_NAME}: {e.details.get('errmsg', str(e))}")
                    logger.error(f"Database OperationFailure while creating index 'idx_assessment_tasks_dequeue_order' on {ASSESSMENT_TASKS_COLLECTION_NAME}: {e.details.get('errmsg', str(e))}", exc_info=True)
                    raise
            except Exception as e:
                logger.critical(f"[STARTUP_EVENT_CRITICAL] Unexpected error creating index 'idx_assessment_tasks_dequeue_order' on {ASSESSMENT_TASKS_COLLECTION_NAME}: {e}")
                logger.error(f"Unexpected error creating index 'idx_assessment_tasks_dequeue_order' on {ASSESSMENT_TASKS_COLLECTION_NAME}: {e}", exc_info=True)
                # Potentially raise here
        else:
            logger.critical(f"[STARTUP_EVENT_CRITICAL] Could not get collection '{ASSESSMENT_TASKS_COLLECTION_NAME}' to create indexes.")
            logger.error(f"Could not get collection '{ASSESSMENT_TASKS_COLLECTION_NAME}' to create indexes.")

        # Ensure indexes for Documents collection (example, adjust as needed)
        # documents_collection = db[DOCUMENT_COLLECTION]
        # await documents_collection.create_index([("teacher_id", 1), ("upload_timestamp", -1)], name="idx_doc_teacher_upload")
        # logger.info("Successfully created/verified index 'idx_doc_teacher_upload' on documents")

        logger.info("Database indexes ensured.")

    except Exception as e:
        logger.error(f"An error occurred during index creation: {e}", exc_info=True)
        # Decide if app should proceed if index creation fails for non-critical indexes

    # Start BatchProcessor
    try:
        # Assuming BatchProcessor is designed to be started and run in the background
        from .tasks.batch_processor import BatchProcessor # Local import to avoid circular dependency issues
        processor = BatchProcessor()
        asyncio.create_task(processor.process_batches()) # Changed from processor.run() to processor.process_batches()
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

    # Start AssessmentWorker (Integrated from Codex branch)
    try:
        from .tasks.assessment_worker import AssessmentWorker # Consistent relative import
        worker = AssessmentWorker()
        asyncio.create_task(worker.run())
        logger.info("Assessment worker started")
    except Exception as e:
        logger.error(f"Failed to start assessment worker: {e}", exc_info=True)

# RESOLVED CONFLICT 2 - Using _original_fastapi_app decorator
@_original_fastapi_app.on_event("shutdown")
async def shutdown_event():
    """Stop batch processor, assessment worker, and disconnect from MongoDB on application shutdown."""
    logger.info("Executing shutdown event...")
    
    # Stop batch processor
    # Ensure batch_processor module (imported at top) has a stop() method or adjust accordingly
    if hasattr(batch_processor, 'stop') and callable(batch_processor.stop): # Defensive check
        batch_processor.stop() 
        logger.info("Batch processor stop requested")
    else:
        logger.warning("batch_processor module does not have a callable stop() method as expected.")


    # Stop assessment worker
    # Ensure assessment_worker module (imported at top) has a stop() method or adjust accordingly
    if hasattr(assessment_worker, 'stop') and callable(assessment_worker.stop): # Defensive check
        assessment_worker.stop()
        logger.info("Assessment worker stop requested")
    else:
        logger.warning("assessment_worker module does not have a callable stop() method as expected.")
        
    logger.info("Disconnecting from database...")
    await close_mongo_connection()

# --- API Endpoints ---
@_original_fastapi_app.get("/", tags=["Root"], include_in_schema=False)
async def read_root():
    """Root endpoint welcome message."""
    return {"message": f"Welcome to {PROJECT_NAME}"}

@_original_fastapi_app.get("/health", status_code=200, tags=["Health Check"])
async def health_check() -> Dict[str, Any]:
    """
    Comprehensive health check endpoint that verifies:
    - Application status and metrics (uptime, memory)
    - Database connectivity and collections
    """
    db_health = await check_database_health()
    process = psutil.Process()
    memory_info = process.memory_info()
    uptime_seconds = time.time() - APP_START_TIME
    uptime = str(timedelta(seconds=int(uptime_seconds)))

    health_info = {
        "status": "OK",
        "application": {
            "name": PROJECT_NAME,
            "version": VERSION,
            "status": "OK",
            "uptime": uptime,
            "memory_usage": {
                "rss_bytes": memory_info.rss,
                "vms_bytes": memory_info.vms,
                "percent": f"{process.memory_percent():.2f}%"
            }
        },
        "database": db_health,
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
    }

    if db_health.get("status") == "ERROR":
        health_info["status"] = "ERROR"
    elif db_health.get("status") == "WARNING":
        health_info["status"] = "WARNING"

    return health_info

# --- Liveness and Readiness Probes ---
@_original_fastapi_app.get("/healthz", tags=["Probes"], status_code=status.HTTP_200_OK)
async def liveness_probe():
    """Liveness probe: Checks if the application process is running and responsive."""
    return {"status": "live"}

@_original_fastapi_app.get("/readyz", tags=["Probes"])
async def readiness_probe(response: Response):
    """Readiness probe: Checks if the application is ready to serve traffic (e.g., DB connected)."""
    db_health = await check_database_health()
    if db_health.get("status") == "OK":
        response.status_code = status.HTTP_200_OK
        return {"status": "ready", "database": db_health}
    else:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "database": db_health}

# --- Include API Routers ---
_original_fastapi_app.include_router(schools_router, prefix=API_V1_PREFIX)
_original_fastapi_app.include_router(teachers_router, prefix=API_V1_PREFIX)
_original_fastapi_app.include_router(class_groups_router, prefix=API_V1_PREFIX)
_original_fastapi_app.include_router(students_router, prefix=API_V1_PREFIX)
# _original_fastapi_app.include_router(assignments_router, prefix=API_V1_PREFIX) # COMMENTED OUT
_original_fastapi_app.include_router(documents_router, prefix=API_V1_PREFIX)
_original_fastapi_app.include_router(results_router, prefix=API_V1_PREFIX)
_original_fastapi_app.include_router(dashboard_router, prefix=API_V1_PREFIX)
_original_fastapi_app.include_router(analytics_router, prefix=API_V1_PREFIX)

@_original_fastapi_app.get("/api/v1/test-health")
def read_root_test_health():
    return {"Status": "OK"}

app = _original_fastapi_app