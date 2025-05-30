# backend/app/main.py
import logging
import psutil # For system metrics in health check
import time   # For uptime calculation
import sys    # For sys.stdout in logging configuration
from fastapi import FastAPI, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone # For uptime calculation
import asyncio
from fastapi import status
from pymongo.errors import OperationFailure
import os
import pymongo
from pymongo import IndexModel
import stripe # Import the stripe library

# Import config and database lifecycle functions
# Assuming your config.py provides 'settings' object and other constants
from .core.config import settings, PROJECT_NAME, API_V1_PREFIX, VERSION
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
from .api.v1.endpoints.admin import router as admin_router
# --- NEW: Import Stripe subscription and webhook routers ---
from .api.v1.endpoints.subscriptions import router as subscriptions_router
from .api.v1.webhooks.stripe import router as stripe_webhook_router
# --- END NEW IMPORTS ---


# Import worker and processor classes directly
from .tasks.batch_processor import BatchProcessor
from .tasks.assessment_worker import AssessmentWorker

# Setup logging (initial basic config, refined in startup)
logger = logging.getLogger(__name__)
# Basic config to ensure logger works before startup_event refines it.
# The startup_event will set more detailed formatting and levels.
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())


# --- INITIALIZE STRIPE ---
# This should be done once when the application starts.
# It configures the Stripe library with your secret key.
if settings.STRIPE_SECRET_KEY:
    stripe.api_key = settings.STRIPE_SECRET_KEY
    # You can also set a specific Stripe API version if needed for compatibility
    # stripe.api_version = "2022-11-15" # Example, check Stripe docs for latest or recommended
    logger.info("Stripe client initialized successfully with configured API key.")
else:
    logger.critical("CRITICAL: STRIPE_SECRET_KEY is not set in settings. Stripe client cannot be initialized.")
    # Depending on your app's needs, you might want to prevent startup or run in a degraded mode.
# --- END INITIALIZE STRIPE ---


# Track application start time for uptime calculation
APP_START_TIME = time.time()

# --- CORS Setup ---
# Use ALLOWED_ORIGINS from settings if available, otherwise use the hardcoded list + env var
if settings.ALLOWED_ORIGINS:
    # Split the comma-separated string into a list of origins
    origins_to_use = [origin.strip() for origin in settings.ALLOWED_ORIGINS.split(',') if origin.strip()]
    logger.info(f"Using ALLOWED_ORIGINS from settings for CORS: {origins_to_use}")
else:
    logger.warning("ALLOWED_ORIGINS not set in config. Falling back to default list and FRONTEND_URL env var for CORS.")
    frontend_origin_env = os.getenv("FRONTEND_URL")
    default_origins = [
        "http://localhost:5173",  # Vite frontend
        "http://localhost:3000",  # Alternative frontend port
        "http://127.0.0.1:5173",  # Alternative localhost
        "http://127.0.0.1:3000",  # Alternative localhost
        "https://gray-mud-0fe5b3703.6.azurestaticapps.net",
        "https://app.smartdetector.ai",
        "https://dev-app.smartdetector.ai",
        "https://staging-app.smartdetector.ai",
        "https://nice-stone-0864d4c03.6.azurestaticapps.net",
        "https://calm-sand-0d8c25a03.6.azurestaticapps.net"
    ]
    if frontend_origin_env:
        default_origins.append(frontend_origin_env)
    origins_to_use = [o for o in default_origins if o] # Remove any None values

if not origins_to_use:
    logger.error("CRITICAL: No CORS origins configured. Frontend communication will likely fail.")
# --- End CORS Setup ---


# Create FastAPI app instance with detailed configuration
_original_fastapi_app = FastAPI(
    title=f"{settings.PROJECT_NAME} - Sentient AI Detector App", # Use settings.PROJECT_NAME
    version=settings.VERSION, # Use settings.VERSION
    description="API for detecting AI-generated content in educational settings",
    docs_url="/api/docs", # Consider making this conditional on settings.DEBUG
    redoc_url="/api/redoc", # Consider making this conditional on settings.DEBUG
    openapi_url="/api/openapi.json" # Consider f"{settings.API_V1_PREFIX}/openapi.json"
)

# Initialize app.state for storing worker/processor instances and tasks
_original_fastapi_app.state.assessment_worker_instance = None
_original_fastapi_app.state.assessment_worker_task = None
_original_fastapi_app.state.batch_processor_instance = None
_original_fastapi_app.state.batch_processor_task = None

# +++ TEMPORARY DEBUG ROUTE +++
# @_original_fastapi_app.put("/api/v1/put-test")
# async def temp_put_test_route(request: Request):
#     logger.info("!!!! TEMPORARY DEBUG: /api/v1/put-test endpoint was reached via PUT !!!!")
#     body = await request.json()
#     logger.info(f"!!!! TEMPORARY DEBUG: /api/v1/put-test PAYLOAD: {body} !!!!")
#     return {"message": "PUT request to /api/v1/put-test received successfully", "payload": body}
# +++ END TEMPORARY DEBUG ROUTE +++

# +++ NEW TEMPORARY PING ROUTE for /api/v1/teachers/ping +++
@_original_fastapi_app.get("/api/v1/teachers/ping")
async def temp_teachers_ping():
    logger.info("!!!! TEMPORARY DEBUG: /api/v1/teachers/ping endpoint was reached via GET !!!!")
    return {"message": "pong from /api/v1/teachers/ping"}
# +++ END NEW TEMPORARY PING ROUTE +++

# Add CORS middleware
if origins_to_use:
    _original_fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=origins_to_use,
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
    and starts background tasks. Refines logging configuration.
    """
    # --- Configure Logging (Refined) ---
    log_level_env_val = os.getenv("LOG_LEVEL", "INFO" if not settings.DEBUG else "DEBUG").upper()
    numeric_log_level = getattr(logging, log_level_env_val, logging.INFO if not settings.DEBUG else logging.DEBUG)
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_log_level)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()
    stream_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(numeric_log_level)
    root_logger.addHandler(stream_handler)
    logger.info(f"Logging re-configured in startup. Root level: {logging.getLevelName(root_logger.level)}. LOG_LEVEL env: {log_level_env_val}.")
    # --- End Logging Configuration ---

    logger.info("Executing startup event: Connecting to database...")
    connected_successfully = False # Flag to track connection status

    try:
        # connect_to_mongo returns True on success, False on failure
        connected_successfully = await connect_to_mongo()
        if connected_successfully:
            logger.info("Startup event: Database connection successful.")
        else:
            # connect_to_mongo internally logs the specific error and sets _db to None
            logger.critical("[STARTUP_CRITICAL] connect_to_mongo() returned False. Database connection failed. Halting startup.")
            raise RuntimeError("Failed to connect to MongoDB during startup.") # This will halt FastAPI startup

    except Exception as e: # Catches exceptions from connect_to_mongo OR the RuntimeError raised above
        logger.critical(f"[STARTUP_CRITICAL] Database connection process FAILED: {e}", exc_info=True)
        raise # Re-raise to ensure FastAPI app startup is halted

    # The rest of the startup_event proceeds ONLY if the connection was successful.
    # If we reach here, connected_successfully must have been True.

    logger.info("Ensuring database indexes...")
    db = get_database() # This should now always return a valid DB instance.

    if db is None:
        # This check acts as an additional safeguard.
        # If connect_to_mongo succeeded but get_database() still returns None,
        # it indicates a deeper issue in database.py state management.
        logger.critical("[STARTUP_CRITICAL] get_database() returned None even after supposedly successful connection. Halting startup.")
        raise RuntimeError("Database not available after supposedly successful connection during startup.")

    # --- Database Index Creation ---
    try:
        # (Keep your existing index creation logic here)
        # Example:
        await db.teachers.create_index("kinde_id", name="idx_teacher_kinde_id", unique=False)
        logger.info("Index on teachers.kinde_id ensured (unique=False).")
        # Ensure Stripe related indexes on teachers collection
        await db.teachers.create_index("stripe_customer_id", name="idx_teacher_stripe_customer_id", unique=False, sparse=True) # TEMPORARILY NON-UNIQUE
        logger.info("Index on teachers.stripe_customer_id ensured (unique=False, sparse=True) - TEMPORARILY NON-UNIQUE.")
        await db.teachers.create_index("stripe_subscription_id", name="idx_teacher_stripe_subscription_id", unique=False, sparse=True) # TEMPORARILY NON-UNIQUE
        logger.info("Index on teachers.stripe_subscription_id ensured (unique=False, sparse=True) - TEMPORARILY NON-UNIQUE.")
        
        idx_assessment_dequeue = IndexModel(
            [("priority_level", pymongo.DESCENDING), ("created_at", pymongo.ASCENDING)],
            name="idx_assessment_tasks_dequeue_order"
        )
        await db.assessment_tasks.create_indexes([idx_assessment_dequeue])
        logger.info("Index on assessment_tasks for dequeue order ensured.")

    except OperationFailure as e:
        # (Keep your existing OperationFailure handling logic)
        if e.code in [85, 86] or "already exists with different options" in e.details.get('errmsg', ''):
            logger.warning(f"Index creation conflict for an existing index: {e.details.get('errmsg', str(e))}. App will continue.")
        # ... (other specific error handling for OperationFailure)
        elif "The order by query does not have a corresponding composite index" in e.details.get('errmsg', ''): # For CosmosDB specific messages if applicable
            logger.warning(f"CosmosDB index hint: {e.details.get('errmsg', str(e))}. App will continue.")
        else:
            logger.error(f"Database OperationFailure during index creation: {e}", exc_info=True)
            # Consider if certain OperationFailures should also halt startup
    except Exception as e:
        logger.error(f"Error during index creation: {e}", exc_info=True)
        # Consider if generic errors during index creation should halt startup
    # --- End Database Index Creation ---

    # --- Start Background Workers ---
    # (Keep your existing worker startup logic here)
    # Example: Start BatchProcessor
    try:
        bp_instance = BatchProcessor() # Ensure BatchProcessor is correctly imported
        _original_fastapi_app.state.batch_processor_instance = bp_instance
        _original_fastapi_app.state.batch_processor_task = asyncio.create_task(bp_instance.process_batches())
        logger.info("BatchProcessor started and stored in app.state.")
    except Exception as e:
        logger.critical(f"[STARTUP_CRITICAL] Failed to start BatchProcessor: {e}", exc_info=True)
        # Consider if failure to start critical workers should halt startup

    # Example: Start AssessmentWorker
    try:
        db_for_worker = get_database() # Re-get in case it's needed specifically by the worker
        if db_for_worker is not None:
            aw_instance = AssessmentWorker(db=db_for_worker) # Ensure AssessmentWorker is imported
            _original_fastapi_app.state.assessment_worker_instance = aw_instance
            _original_fastapi_app.state.assessment_worker_task = asyncio.create_task(aw_instance.run())
            logger.info("AssessmentWorker started and stored in app.state.")
        else:
            logger.error("[STARTUP_CRITICAL] Failed to get DB for AssessmentWorker. Worker not started.")
            # Consider if this should halt startup
    except Exception as e:
        logger.critical(f"[STARTUP_CRITICAL] Failed to start AssessmentWorker: {e}", exc_info=True)
        # Consider if failure to start critical workers should halt startup
    # --- End Background Workers ---

    logger.info("[STARTUP_EVENT] >>> FastAPI startup_event function COMPLETED SUCCESSFULLY.")


@_original_fastapi_app.on_event("shutdown")
async def shutdown_event():
    """Stop batch processor, assessment worker, and disconnect from MongoDB on application shutdown."""
    logger.info("Executing shutdown event...")

    # Stop batch processor
    bp_instance = getattr(_original_fastapi_app.state, 'batch_processor_instance', None)
    bp_task = getattr(_original_fastapi_app.state, 'batch_processor_task', None)
    if bp_instance and hasattr(bp_instance, 'stop'):
        logger.info("Requesting BatchProcessor to stop...")
        bp_instance.stop() # Signal stop
        if bp_task and not bp_task.done():
            logger.info("Waiting for BatchProcessor task to complete...")
            try:
                await asyncio.wait_for(bp_task, timeout=10.0) # Wait for graceful exit
                logger.info("BatchProcessor task completed.")
            except asyncio.TimeoutError:
                logger.warning("BatchProcessor task timed out during shutdown. Cancelling...")
                bp_task.cancel()
                try: await bp_task
                except asyncio.CancelledError: logger.info("BatchProcessor task successfully cancelled.")
            except Exception as e_bp_shutdown:
                logger.error(f"Error during BatchProcessor task shutdown: {e_bp_shutdown}", exc_info=True)
    
    # Stop assessment worker
    aw_instance = getattr(_original_fastapi_app.state, 'assessment_worker_instance', None)
    aw_task = getattr(_original_fastapi_app.state, 'assessment_worker_task', None)
    if aw_instance and hasattr(aw_instance, 'stop'):
        logger.info("Requesting AssessmentWorker to stop...")
        aw_instance.stop() # Signal stop
        if aw_task and not aw_task.done():
            logger.info("Waiting for AssessmentWorker task to complete...")
            try:
                # Use a reasonable timeout, perhaps related to its poll interval
                timeout_aw = getattr(aw_instance, 'poll_interval', 5.0) + 5.0 
                await asyncio.wait_for(aw_task, timeout=timeout_aw) # Wait for graceful exit
                logger.info("AssessmentWorker task completed.")
            except asyncio.TimeoutError:
                logger.warning("AssessmentWorker task timed out during shutdown. Cancelling...")
                aw_task.cancel()
                try: await aw_task
                except asyncio.CancelledError: logger.info("AssessmentWorker task successfully cancelled.")
            except Exception as e_aw_shutdown:
                logger.error(f"Error during AssessmentWorker task shutdown: {e_aw_shutdown}", exc_info=True)

    logger.info("Disconnecting from database...")
    await close_mongo_connection()
    logger.info("Database connection closed. Shutdown event complete.")

# --- API Endpoints ---
@_original_fastapi_app.get("/", tags=["Root"], include_in_schema=False) # Keep include_in_schema=False if intended
async def read_root():
    """Root endpoint welcome message."""
    return {"message": f"Welcome to {settings.PROJECT_NAME}"} # Use settings.PROJECT_NAME

@_original_fastapi_app.get("/health", status_code=status.HTTP_200_OK, tags=["Health Check"]) # Use status from fastapi
async def health_check() -> Dict[str, Any]:
    """
    Comprehensive health check endpoint that verifies:
    - Application status and metrics (uptime, memory)
    - Database connectivity and collections
    """
    db_health = await check_database_health()
    process = psutil.Process(os.getpid()) # Get current process
    memory_info = process.memory_info()
    uptime_seconds = time.time() - APP_START_TIME
    uptime = str(timedelta(seconds=int(uptime_seconds)))

    health_info = {
        "status": "OK", # Default to OK, will be overridden if DB has issues
        "application": {
            "name": settings.PROJECT_NAME, # Use settings
            "version": settings.VERSION,     # Use settings
            "status": "OK",
            "uptime": uptime,
            "memory_usage": {
                "rss_bytes": memory_info.rss,
                "vms_bytes": memory_info.vms,
                "percent": f"{process.memory_percent():.2f}%"
            }
        },
        "database": db_health,
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z" # Standard ISO format
    }

    # Override overall status based on DB health
    if db_health.get("status") == "ERROR":
        health_info["status"] = "ERROR"
    elif db_health.get("status") == "WARNING": # If db_health can return WARNING
        health_info["status"] = "WARNING"
        
    # Determine appropriate HTTP status code based on overall health
    if health_info["status"] == "ERROR":
        # This endpoint is tricky. If /health returns 503, K8s might restart it.
        # Usually /health is for "is it running at all?" (should be 200 if so)
        # and /readyz is for "can it take traffic?".
        # For now, keeping 200 but reflecting error in payload.
        pass # Default status_code=200 from decorator

    return health_info

# --- Liveness and Readiness Probes ---
@_original_fastapi_app.get("/healthz", tags=["Probes"], status_code=status.HTTP_200_OK)
async def liveness_probe():
    """Liveness probe: Checks if the application process is running and responsive."""
    return {"status": "live"}

@_original_fastapi_app.get("/readyz", tags=["Probes"])
async def readiness_probe(response: Response): # Inject Response to modify status code
    """Readiness probe: Checks if the application is ready to serve traffic (e.g., DB connected)."""
    db_health = await check_database_health()
    if db_health.get("status") == "OK":
        response.status_code = status.HTTP_200_OK
        return {"status": "ready", "database": db_health}
    else:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        # Log why it's not ready
        logger.warning(f"Readiness probe failed: Database status is {db_health.get('status')}")
        return {"status": "not_ready", "database": db_health}

# --- Include API Routers ---
# Use settings.API_V1_PREFIX for consistency
_original_fastapi_app.include_router(schools_router, prefix=settings.API_V1_PREFIX, tags=["Schools"])
_original_fastapi_app.include_router(teachers_router, prefix=settings.API_V1_PREFIX, tags=["Teachers"])
_original_fastapi_app.include_router(class_groups_router, prefix=settings.API_V1_PREFIX, tags=["Class Groups"])
_original_fastapi_app.include_router(students_router, prefix=settings.API_V1_PREFIX, tags=["Students"])
# _original_fastapi_app.include_router(assignments_router, prefix=settings.API_V1_PREFIX, tags=["Assignments"]) # COMMENTED OUT
_original_fastapi_app.include_router(documents_router, prefix=settings.API_V1_PREFIX, tags=["Documents"])
_original_fastapi_app.include_router(results_router, prefix=settings.API_V1_PREFIX, tags=["Results"])
_original_fastapi_app.include_router(dashboard_router, prefix=settings.API_V1_PREFIX, tags=["Dashboard"])
_original_fastapi_app.include_router(analytics_router, prefix=f"{settings.API_V1_PREFIX}/analytics", tags=["Analytics"])
_original_fastapi_app.include_router(admin_router, prefix=f"{settings.API_V1_PREFIX}", tags=["Admin"])

# --- NEW: Include Stripe Subscription and Webhook Routers ---
_original_fastapi_app.include_router(
    subscriptions_router,
    prefix=f"{settings.API_V1_PREFIX}/subscriptions", # Ensure this matches your API structure
    tags=["Subscriptions"]
)
_original_fastapi_app.include_router(
    stripe_webhook_router,
    prefix=f"{settings.API_V1_PREFIX}/webhooks/stripe", # This prefix + "/stripe" from the webhook router itself = /webhooks/stripe
    tags=["Stripe Webhooks"]
)
# --- END NEW ROUTER INCLUSIONS ---


# This test endpoint might be redundant if you have a proper root or health check
# If it's for a specific test, ensure it's clear.
@_original_fastapi_app.get(f"{settings.API_V1_PREFIX}/test-health", tags=["Test"]) # Use settings prefix
def read_root_test_health():
    return {"Status": "OK", "Message": "API v1 test health endpoint is responsive."}

# Assign to 'app' for uvicorn or other ASGI servers to find
app = _original_fastapi_app
