# tests/conftest.py
import pytest
import pytest_asyncio # <-- ADD IMPORT for pytest_asyncio.fixture
import pytest_dotenv # <-- ADDED for explicit plugin loading
# import pytest_httpx # Add explicit import

# Force plugin loading for pytest-dotenv and pytest-asyncio
pytest_plugins = [
    "pytest_dotenv",
    "pytest_asyncio",
    "pytest_mock", # Already in pytest.ini but being explicit here too
    "anyio"        # Already in pytest.ini but being explicit here too
]

# Explicitly check for and import pytest-httpx to encourage registration
# pytest.importorskip("pytest_httpx") # Removed this line

# Remove TestClient import, httpx.AsyncClient will be handled by pytest-httpx
# from fastapi.testclient import TestClient
import asyncio
import sys
import os
from pathlib import Path # Added for path manipulation
from motor.motor_asyncio import AsyncIOMotorClient # Added Motor import
from fastapi import FastAPI # <-- ADD FastAPI IMPORT
from contextlib import asynccontextmanager # Need this for LifespanManager
from asgi_lifespan import LifespanManager # <-- ADD LifespanManager IMPORT
import logging # <-- ADD logging IMPORT
import time
from typing import Dict, Any, AsyncGenerator
from pytest_mock import MockerFixture # <-- ADD MockerFixture IMPORT
from unittest.mock import AsyncMock, patch # MODIFIED: Added patch

# Setup logger for conftest early
logger = logging.getLogger(__name__)

# --- Global Patcher for Blob Storage ---
# Applied via pytest_configure to ensure it's active before most module imports
blob_uploader_patcher = None

def pytest_configure(config):
    """Apply global mocks before test collection and most module imports."""
    global blob_uploader_patcher
    logger.info("pytest_configure: Patching backend.app.services.blob_storage.upload_file_to_blob globally.")
    # Ensure the target string is exactly how it's imported in the module to be tested
    blob_uploader_patcher = patch('backend.app.services.blob_storage.upload_file_to_blob', new_callable=AsyncMock)
    mock_blob_uploader = blob_uploader_patcher.start()
    # Set a default return value; tests can override this if needed by accessing the mock
    mock_blob_uploader.return_value = "conftest_default_blob.pdf"

def pytest_unconfigure(config):
    """Stop global mocks after tests are done."""
    global blob_uploader_patcher
    if blob_uploader_patcher:
        logger.info("pytest_unconfigure: Stopping global patch for backend.app.services.blob_storage.upload_file_to_blob.")
        blob_uploader_patcher.stop()
        blob_uploader_patcher = None
# --- End Global Patcher ---

# Now, other imports that might trigger loading of application modules
# --- START: Add project root to sys.path ---
# This helps ensure modules like 'backend' can be found
# Use Path for better cross-platform compatibility
project_root = Path(__file__).resolve().parent.parent
backend_root = project_root / 'backend' # Corrected string literal

if str(project_root) not in sys.path:
    print(f"Adding project root to sys.path from conftest: {project_root}")
    sys.path.insert(0, str(project_root))
# Also add backend directory if needed, though pythonpath in pytest.ini might handle this
if str(backend_root) not in sys.path:
    print(f"Adding backend root to sys.path from conftest: {backend_root}")
    sys.path.insert(0, str(backend_root)) # Add backend for potential direct imports
# --- END: Add project root ---

# --- Import App and Settings ---
try:
    # Attempt to import the main FastAPI app instance
    # This 'fastapi_app' is the actual FastAPI instance from your main application
    from backend.app.main import _original_fastapi_app as fastapi_app_instance # UPDATED IMPORT
    from backend.app.core.config import settings # Import settings
    from backend.app.core.security import get_current_user_payload # For dependency override key
    print("Successfully imported '_original_fastapi_app', 'settings' and 'get_current_user_payload' from backend modules")
except ImportError as e:
    print(f"Conftest Import Error: Failed to import from backend modules: {e}")
    # Define dummy settings to allow tests to load if main settings fail
    # REMOVED: fastapi_app = FastAPI(title="Dummy App for Test Loading")
    class DummySettings:
        DB_NAME = "dummy_db"
        MONGODB_URL = None
    settings = DummySettings()
# --------------------------------

# --- Import lifecycle functions to mock ---
# Assuming these are the correct paths based on main.py
from backend.app.db.database import connect_to_mongo, close_mongo_connection, get_database
from backend.app.tasks import batch_processor

# --- Fixtures ---

@pytest_asyncio.fixture(scope="function")
# No event_loop needed with pytest-asyncio auto mode
async def managed_fastapi_app(mocker: MockerFixture) -> AsyncGenerator[FastAPI, None]:
    """Creates a FastAPI app instance for each test function, mocking startup/shutdown events."""

    # --- Explicitly manage event loop for this fixture ---
    # loop = asyncio.new_event_loop()
    # asyncio.set_event_loop(loop)
    # --- This explicit loop management might not be needed with asyncio_mode = auto or strict ---
    # --- and can sometimes conflict if pytest-asyncio is already managing the loop. ---
    # --- Reverted this change as it's generally handled by pytest-asyncio ---

    # --- Mock Lifecycle Functions BEFORE app import/lifespan ---
    logger.info("Mocking DB connect/disconnect and batch processor for app fixture...")

    # Mock database connection functions from main.py's perspective
    mocker.patch("backend.app.main.connect_to_mongo", return_value=True) # Simulate successful connection
    mocker.patch("backend.app.main.close_mongo_connection", return_value=None)
    # Mock get_database to prevent index creation attempt during startup
    mocker.patch("backend.app.main.get_database", return_value=None)

    # Mock batch processor methods on the instance imported into main.py
    mocker.patch('backend.app.main.batch_processor.process_batches', return_value=None)
    mocker.patch('backend.app.main.batch_processor.stop', return_value=None)

    # REMOVED: Mock for blob storage service upload_file_to_blob is now handled globally by pytest_configure
    # mocker.patch(
    #     'app.services.blob_storage.upload_file_to_blob', # String path to the function
    #     new_callable=AsyncMock, 
    #     return_value="default_conftest_blob.pdf" # Default return, test can override if needed
    # )
    # --- End Mocking --- 

    # Import the app *after* patching dependencies
    from backend.app.main import app as fastapi_app

    # It's crucial that the app instance is the one from main.py
    if not fastapi_app or not isinstance(fastapi_app, FastAPI):
         pytest.fail("Failed to import the FastAPI app from backend.app.main after patching.")

    logger.info("Running LifespanManager with mocked startup/shutdown...")
    try:
        # Use asgi-lifespan to manage the app's lifespan events within the test
        # Timeout can likely be reduced now mocks are in place, but 15s is safe.
        async with LifespanManager(fastapi_app, startup_timeout=15, shutdown_timeout=15) as manager: # Added 'as manager'
            yield manager.app # Yield the app from the manager
    except TimeoutError:
        # This shouldn't happen now with mocked handlers
        logger.error("LifespanManager timed out unexpectedly even with mocked handlers.")
        pytest.fail("App startup timed out (15s) despite mocked handlers.")
    except Exception as e:
        logger.error(f"Error during LifespanManager execution: {e}", exc_info=True)
        pytest.fail(f"LifespanManager failed: {e}")


@pytest_asyncio.fixture(scope="function")
async def db() -> AsyncIOMotorClient:
    """Provides a dedicated test database session that is dropped after each test."""
    # Ensure that pytest-dotenv has loaded .env and backend/.env.test
    # MONGO_URL_TEST and MONGO_TEST_DB_NAME should be available in settings

    if not settings.MONGO_URL_TEST:
        pytest.fail(
            "MONGO_URL_TEST environment variable is not set or not loaded into settings. "
            "Ensure it is defined in .env or backend/.env.test and loaded by core.config.py."
        )
    if not settings.MONGO_TEST_DB_NAME:
        pytest.fail(
            "MONGO_TEST_DB_NAME environment variable is not set or not loaded into settings. "
            "Ensure it is defined in .env or backend/.env.test and loaded by core.config.py."
        )

    # Use the specific test database name from settings
    test_db_name = settings.MONGO_TEST_DB_NAME 
    mongo_url_for_tests = settings.MONGO_URL_TEST

    logger.info(f"Connecting to MongoDB test database via 'db' fixture: {test_db_name} using URL ending with ...{mongo_url_for_tests[-30:]}")

    client = AsyncIOMotorClient(mongo_url_for_tests, serverSelectionTimeoutMS=5000)
    try:
        # Check connection
        await client.admin.command('ping')
        logger.info("DB fixture connection successful.")
    except Exception as e:
        pytest.fail(f"Could not connect to MongoDB for 'db' fixture: {e}")
        
    db_instance = client[test_db_name]
    yield db_instance

    logger.info(f"Dropping test database via 'db' fixture: {test_db_name}")
    await client.drop_database(test_db_name)
    client.close()
    logger.info("Test database connection (db fixture) closed.")


@pytest_asyncio.fixture(scope="function")
async def app_with_mock_auth(managed_fastapi_app: FastAPI) -> FastAPI:
    """Fixture that provides the FastAPI app with auth dependency overridden."""
    
    default_mock_payload = {
        "sub": "mock_kinde_user_id_from_fixture", 
        "iss": settings.KINDE_DOMAIN or "mock_issuer",
        "aud": [settings.KINDE_AUDIENCE] if settings.KINDE_AUDIENCE else ["mock_audience"],
        "exp": time.time() + 3600,
        "iat": time.time(),
        "roles": ["teacher"] # Default role for this mock
    }

    async def override_get_current_user_payload() -> Dict[str, Any]:
        logger.info("Dependency Override: Using override_get_current_user_payload from app_with_mock_auth fixture")
        return default_mock_payload

    logger.info(f"Applying dependency override for {get_current_user_payload} in app_with_mock_auth")
    # Store if there was a pre-existing override for this key, though unlikely with function scope
    # pre_existing_override = app.dependency_overrides.get(get_current_user_payload)
    managed_fastapi_app.dependency_overrides[get_current_user_payload] = override_get_current_user_payload
    
    yield managed_fastapi_app
    
    logger.info(f"Cleaning up dependency override for {get_current_user_payload} in app_with_mock_auth")
    # More robust cleanup: only delete if we added it, or restore if it pre-existed.
    # For simplicity with function scope, just delete the key we set.
    if get_current_user_payload in managed_fastapi_app.dependency_overrides and \
       managed_fastapi_app.dependency_overrides[get_current_user_payload] == override_get_current_user_payload:
        del managed_fastapi_app.dependency_overrides[get_current_user_payload]
    # elif pre_existing_override: # If we wanted to restore a more complex pre-existing state
    #     app.dependency_overrides[get_current_user_payload] = pre_existing_override


# --- Pytest-httpx Diagnostic Hook --- (Keep if pytest-httpx is ever re-enabled)
# def pytest_report_header(config):
#     """Add pytest-httpx version and path to report header.""" 
#     try:
#         import pytest_httpx
#         version = getattr(pytest_httpx, "__version__", "unknown")
#         path = getattr(pytest_httpx, "__file__", "unknown")
#         return [f"pytest-httpx: version={version}, path={path}"]
#     except ImportError:
#         return ["pytest-httpx: NOT FOUND"] # Should not happen if -p no:httpx is active
# # ------------------------------------ 