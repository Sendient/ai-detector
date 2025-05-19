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
from app.core.config import PROJECT_NAME, API_V1_PREFIX, VERSION
from app.db.database import connect_to_mongo, close_mongo_connection, check_database_health, get_database
from app.db.init_db import init_db_indexes

# Import all endpoint routers
# Adjust path '.' based on where main.py is relative to 'api'
# Includes routers for all entities: schools, teachers, class_groups, students, assignments, documents, results
from app.api.v1.endpoints.schools import router as schools_router
from app.api.v1.endpoints.teachers import router as teachers_router
from app.api.v1.endpoints.class_groups import router as class_groups_router
from app.api.v1.endpoints.students import router as students_router
# from app.api.v1.endpoints.assignments import router as assignments_router # COMMENTED OUT
from app.api.v1.endpoints.documents import router as documents_router
from app.api.v1.endpoints.results import router as results_router
from app.api.v1.endpoints.dashboard import router as dashboard_router
from app.api.v1.endpoints.analytics import router as analytics_router

# Import batch processor
from app.tasks import batch_processor

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
app = FastAPI(
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

# --- Event Handlers for DB Connection and Batch Processor ---
@app.on_event("startup")
async def startup_event():
    """
    Event handler for application startup.
    Connects to the database and ensures necessary indexes are created.
    """
    logger.info("Executing startup event: Connecting to database...")
    try:
        await connect_to_mongo() # Ensure this is awaited
        logger.info("Startup event: Database connection successful.")
    except Exception as e:
        logger.error(f"Startup event: Failed to connect to database: {e}", exc_info=True)
        raise

    logger.info("Ensuring all database collections and indexes via init_db_indexes...")
    try:
        await init_db_indexes()
        logger.info("All collections and indexes ensured by init_db_indexes.")
    except Exception as e:
        logger.error(f"An error occurred during init_db_indexes: {e}", exc_info=True)
        raise

    # Start background tasks if any (like BatchProcessor)
    try:
        from app.tasks.batch_processor import BatchProcessor # Local import to avoid circular dependency issues
        processor = BatchProcessor()
        asyncio.create_task(processor.process_batches())
        logger.info("Batch processor started")
    except Exception as e:
        logger.error(f"Failed to start batch processor: {e}", exc_info=True)

@app.on_event("shutdown")
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
@app.get("/", tags=["Root"], include_in_schema=False) # Hide from API docs if desired
async def read_root():
    """Root endpoint welcome message."""
    return {"message": f"Welcome to {PROJECT_NAME}"}

@app.get("/health", status_code=200, tags=["Health Check"])
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
@app.get("/healthz", tags=["Probes"], status_code=status.HTTP_200_OK)
async def liveness_probe():
    """Liveness probe: Checks if the application process is running and responsive."""
    return {"status": "live"}

@app.get("/readyz", tags=["Probes"])
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
app.include_router(schools_router, prefix=API_V1_PREFIX)
app.include_router(teachers_router, prefix=API_V1_PREFIX)
app.include_router(class_groups_router, prefix=API_V1_PREFIX)
app.include_router(students_router, prefix=API_V1_PREFIX)
# app.include_router(assignments_router, prefix=API_V1_PREFIX) # COMMENTED OUT
app.include_router(documents_router, prefix=API_V1_PREFIX) # Includes documents router
app.include_router(results_router, prefix=API_V1_PREFIX)   # Includes results router
app.include_router(dashboard_router, prefix=API_V1_PREFIX) # NEW: Include dashboard router
app.include_router(analytics_router, prefix=API_V1_PREFIX)

# Add a simple health check endpoint directly to the app
@app.get("/api/v1/test-health")
def read_root():
    return {"Status": "OK"}

# --- TODOs & Future Enhancements ---
# TODO: Add middleware, CORS configuration, and global exception handlers
# from fastapi.middleware.cors import CORSMiddleware
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],  # SECURITY: Update for production environments!
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

