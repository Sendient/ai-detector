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

# Import config and database lifecycle functions
# Adjust path '.' based on where main.py is relative to 'core' and 'db'
from app.core.config import PROJECT_NAME, API_V1_PREFIX, VERSION
from app.db.database import connect_to_mongo, close_mongo_connection, check_database_health, get_database

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

# Define allowed origins
origins = [
    "http://localhost:5173",  # Vite frontend
    "http://localhost:3000",  # Alternative frontend port
    "http://127.0.0.1:5173",  # Alternative localhost
    "http://127.0.0.1:3000",  # Alternative localhost
    "https://gray-mud-0fe5b3703.6.azurestaticapps.net", # Production frontend origin
]

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
    """Connect to MongoDB, ensure indexes, and start batch processor on application startup."""
    logger.info("Executing startup event: Connecting to database...")
    connected = await connect_to_mongo()
    if not connected:
        logger.critical("FATAL: Database connection failed on startup. Application might not function correctly.")
    else:
        logger.info("Startup event: Database connection successful.")
        # Ensure indexes after successful connection
        try:
            db_instance = get_database()
            if db_instance is not None:
                logger.info("Ensuring database indexes...")
                # Index for teachers.kinde_id
                # Use the collection name string directly as defined in crud.py or your DB
                teachers_collection_name = "teachers" 
                teachers_collection = db_instance.get_collection(teachers_collection_name)
                
                try:
                    # Create index on kinde_id, make it unique
                    # Naming the index is good practice for manageability
                    await teachers_collection.create_index("kinde_id", name="idx_teacher_kinde_id", unique=True)
                    logger.info(f"Index 'idx_teacher_kinde_id' on {teachers_collection_name}.kinde_id ensured (unique).")
                except OperationFailure as e:
                    if e.code == 67: # Code 67: CannotCreateIndex (Cosmos DB specific for unique on non-empty)
                        logger.warning(
                            f"Could not create unique index 'idx_teacher_kinde_id' on {teachers_collection_name}.kinde_id "
                            f"programmatically because the collection is not empty (Cosmos DB restriction). "
                            f"Please ensure this index is created manually in Azure Portal if it does not exist. Error: {e.details}"
                        )
                    elif e.code == 13: # Code 13: Unauthorized - Cosmos DB index modification restriction
                        logger.warning(
                            f"Could not modify existing unique index 'idx_teacher_kinde_id' on {teachers_collection_name}.kinde_id. "
                            f"Cosmos DB requires removing and recreating the collection to change unique indexes. "
                            f"Ignoring error and continuing startup. Error details: {e.details}"
                        )
                    else: # Other OperationFailure, re-raise or log as more critical
                        logger.error(f"Database OperationFailure while creating index 'idx_teacher_kinde_id': {e}", exc_info=True)
                        # Potentially re-raise if this should halt startup
                except Exception as e_general: # Catch other general errors during index creation
                    logger.error(f"Unexpected error creating index 'idx_teacher_kinde_id': {e_general}", exc_info=True)
                
                # Example for other potential indexes (uncomment and adapt as needed):
                # documents_collection_name = "documents"
                # documents_collection = db_instance.get_collection(documents_collection_name)
                # await documents_collection.create_index([("teacher_id", 1), ("student_id", 1)], name="idx_doc_teacher_student")
                # logger.info(f"Compound index 'idx_doc_teacher_student' on {documents_collection_name} ensured.")
                
                logger.info("Database indexes ensured.")
            else:
                logger.error("Could not get database instance to ensure indexes.")
        except Exception as e:
            logger.error(f"Error ensuring database indexes: {e}", exc_info=True)

    # Start batch processor in background task
    asyncio.create_task(batch_processor.process_batches())
    logger.info("Batch processor started")

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

