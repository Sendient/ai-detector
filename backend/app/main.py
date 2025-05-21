import logging
import psutil # For system metrics in health check
import time   # For uptime calculation
import sys    # For sys.stdout in logging configuration
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, Optional
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

# Import worker and processor classes directly
from .tasks.batch_processor import BatchProcessor
from .tasks.assessment_worker import AssessmentWorker

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

# Initialize app.state for storing worker/processor instances and tasks
_original_fastapi_app.state.assessment_worker_instance = None
_original_fastapi_app.state.assessment_worker_task = None
_original_fastapi_app.state.batch_processor_instance = None
_original_fastapi_app.state.batch_processor_task = None

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
    # --- Configure Logging ---
    # MODIFIED: Default to DEBUG if LOG_LEVEL is not explicitly INFO, WARNING, ERROR, or CRITICAL
    log_level_name = os.getenv("LOG_LEVEL", "DEBUG").upper() # Default to DEBUG
    if log_level_name not in ["INFO", "WARNING", "ERROR", "CRITICAL"]:
        log_level_name = "DEBUG" # Force DEBUG if invalid or other value like "DEBUG"
    numeric_log_level = getattr(logging, log_level_name, logging.DEBUG)

    # Get the root logger
    root_logger = logging.getLogger()
    # Set its level. Uvicorn might also set this, but we re-affirm.
    root_logger.setLevel(numeric_log_level)

    # Check if a handler with our specific formatter already exists to avoid duplicates if reloaded
    # This is a simple check; more robust would be to name the handler or check its type/formatter more precisely.
    handler_exists = any(
        isinstance(h, logging.StreamHandler) and 
        isinstance(h.formatter, logging.Formatter) and 
        h.formatter._fmt == "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        for h in root_logger.handlers
    )
    
    if not handler_exists:
        stream_handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        stream_handler.setFormatter(formatter)
        # Set level on the handler itself too, though root_logger.setLevel is primary
        stream_handler.setLevel(numeric_log_level) 
        root_logger.addHandler(stream_handler)
        logger_to_use = logging.getLogger("startup_config_adder")
        logger_to_use.info(f"Added new StreamHandler to root logger. Root logger level: {logging.getLevelName(root_logger.level)} ({root_logger.level}). LOG_LEVEL env: {log_level_name}.")
    else:
        logger_to_use = logging.getLogger("startup_config_existing")
        logger_to_use.info(f"StreamHandler with correct formatter already exists. Root logger level: {logging.getLevelName(root_logger.level)} ({root_logger.level}). LOG_LEVEL env: {log_level_name}.")
    # --- End Logging Configuration ---

    logger.info(f"Logging configured. Root level: {logging.getLevelName(root_logger.level)}.")

    logger.info("Executing startup event: Connecting to database...")
    try:
        await connect_to_mongo()
        logger.info("Startup event: Database connection successful.")
    except Exception as e:
        logger.critical(f"[STARTUP_CRITICAL] connect_to_mongo() FAILED: {e}", exc_info=True)
        raise

    logger.info("Ensuring database indexes...")
    db = get_database()
    if db is None:
        logger.critical("[STARTUP_CRITICAL] get_database() returned None. Cannot ensure indexes.")
        return
    try:
        await db.teachers.create_index("kinde_id", name="idx_teacher_kinde_id", unique=False)
        logger.info("Index on teachers.kinde_id ensured.")
        idx_assessment_dequeue = IndexModel([("priority_level", pymongo.DESCENDING), ("created_at", pymongo.ASCENDING)], name="idx_assessment_tasks_dequeue_order")
        await db.assessment_tasks.create_indexes([idx_assessment_dequeue])
        logger.info("Index on assessment_tasks for dequeue order ensured.")
    except OperationFailure as e:
        if e.code == 85 or "The order by query does not have a corresponding composite index" in e.details.get('errmsg', ''):
            logger.warning(f"Index creation/verification conflict/issue: {e.details.get('errmsg', str(e))}. App will continue.")
        else:
            logger.error(f"Database OperationFailure during index creation: {e}", exc_info=True)
            raise
    except Exception as e:
        logger.error(f"Error during index creation: {e}", exc_info=True)

    # Start BatchProcessor
    try:
        bp_instance = BatchProcessor() # Uses imported class
        _original_fastapi_app.state.batch_processor_instance = bp_instance
        _original_fastapi_app.state.batch_processor_task = asyncio.create_task(bp_instance.process_batches())
        logger.info("BatchProcessor started and stored in app.state.")
    except Exception as e:
        logger.critical(f"[STARTUP_CRITICAL] Failed to start BatchProcessor: {e}", exc_info=True)

    # Start AssessmentWorker
    try:
        db_for_worker = get_database() # Re-fetch or ensure db is still valid if startup is long
        if db_for_worker is not None:
            aw_instance = AssessmentWorker(db=db_for_worker) # Uses imported class
            _original_fastapi_app.state.assessment_worker_instance = aw_instance
            _original_fastapi_app.state.assessment_worker_task = asyncio.create_task(aw_instance.run())
            logger.info("AssessmentWorker started and stored in app.state.")
        else:
            logger.error("Failed to get DB for AssessmentWorker post-index creation. Worker not started.")
    except Exception as e:
        logger.critical(f"[STARTUP_CRITICAL] Failed to start AssessmentWorker: {e}", exc_info=True)
    
    logger.info("[STARTUP_EVENT] >>> FastAPI startup_event function COMPLETED.")

@_original_fastapi_app.on_event("shutdown")
async def shutdown_event():
    """Stop batch processor, assessment worker, and disconnect from MongoDB on application shutdown."""
    logger.info("Executing shutdown event...")

    # Stop batch processor
    bp_instance = getattr(_original_fastapi_app.state, 'batch_processor_instance', None)
    bp_task = getattr(_original_fastapi_app.state, 'batch_processor_task', None)
    if bp_instance and hasattr(bp_instance, 'stop'):
        logger.info("Requesting BatchProcessor to stop...")
        bp_instance.stop()
        if bp_task and not bp_task.done():
            logger.info("Waiting for BatchProcessor task to complete...")
            try:
                await asyncio.wait_for(bp_task, timeout=10.0)
                logger.info("BatchProcessor task completed.")
            except asyncio.TimeoutError:
                logger.warning("BatchProcessor task timed out. Cancelling...")
                bp_task.cancel()
            except Exception as e_bp_shutdown:
                logger.error(f"Error during BatchProcessor task shutdown: {e_bp_shutdown}", exc_info=True)
    
    # Stop assessment worker
    aw_instance = getattr(_original_fastapi_app.state, 'assessment_worker_instance', None)
    aw_task = getattr(_original_fastapi_app.state, 'assessment_worker_task', None)
    if aw_instance and hasattr(aw_instance, 'stop'):
        logger.info("Requesting AssessmentWorker to stop...")
        aw_instance.stop()
        if aw_task and not aw_task.done():
            logger.info("Waiting for AssessmentWorker task to complete...")
            try:
                timeout_aw = getattr(aw_instance, 'poll_interval', 10.0) + 5.0
                await asyncio.wait_for(aw_task, timeout=timeout_aw)
                logger.info("AssessmentWorker task completed.")
            except asyncio.TimeoutError:
                logger.warning("AssessmentWorker task timed out. Cancelling...")
                aw_task.cancel()
                try: await aw_task
                except asyncio.CancelledError: logger.info("AssessmentWorker task successfully cancelled.")
                except Exception as e_aw_cancel: logger.error(f"Error awaiting cancelled AW task: {e_aw_cancel}", exc_info=True)
            except Exception as e_aw_shutdown:
                logger.error(f"Error during AssessmentWorker task shutdown: {e_aw_shutdown}", exc_info=True)

    logger.info("Disconnecting from database...")
    await close_mongo_connection()
    logger.info("Database connection closed. Shutdown event complete.")

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