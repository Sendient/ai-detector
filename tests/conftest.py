# tests/conftest.py
import pytest
import pytest_asyncio
import asyncio
import sys
import os
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import FastAPI
from contextlib import asynccontextmanager
from asgi_lifespan import LifespanManager
import logging
import time
from typing import Dict, Any, AsyncGenerator
from pytest_mock import MockerFixture
from unittest.mock import AsyncMock, patch, Mock

# Setup logger for conftest early with ERROR level only
logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)

# --- Global Patcher for Blob Storage ---
blob_uploader_patcher = None

def pytest_configure(config):
    """Apply global mocks before test collection and most module imports."""
    global blob_uploader_patcher
    blob_uploader_patcher = patch('backend.app.services.blob_storage.upload_file_to_blob', new_callable=AsyncMock)
    mock_blob_uploader = blob_uploader_patcher.start()
    mock_blob_uploader.return_value = "conftest_default_blob.pdf"
    mock_blob_uploader.reset_mock = Mock()  # Add reset_mock method

    # Set logging level for backend.app.core.config to ERROR
    config_logger = logging.getLogger("backend.app.core.config")
    config_logger.setLevel(logging.ERROR)

def pytest_unconfigure(config):
    """Stop global mocks after tests are done."""
    global blob_uploader_patcher
    if blob_uploader_patcher:
        blob_uploader_patcher.stop()
        blob_uploader_patcher = None

# --- START: Add project root to sys.path ---
project_root = Path(__file__).resolve().parent.parent
backend_root = project_root / 'backend'

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

# --- Import App and Settings ---
try:
    from backend.app.core.config import settings
    from app.core.security import get_current_user_payload
except ImportError as e:
    logger.error(f"Error importing backend modules: {e}")
    class DummySettings:
        DB_NAME = "dummy_db"
        MONGODB_URL = None
    settings = DummySettings()

# --- Import lifecycle functions to mock ---
from backend.app.db.database import connect_to_mongo, close_mongo_connection, get_database
from backend.app.tasks import batch_processor

@pytest_asyncio.fixture(scope="function")
async def app(mocker: MockerFixture) -> AsyncGenerator[FastAPI, None]:
    """Creates a FastAPI app instance for each test function, mocking startup/shutdown events."""
    # Mock database connection functions
    mocker.patch("backend.app.main.connect_to_mongo", return_value=True)
    mocker.patch("backend.app.main.close_mongo_connection", return_value=None)
    
    # Create a mock database instance
    mock_db_instance = AsyncMock()
    
    # Create mock collections for all used collections
    mock_collections = {
        "teachers": AsyncMock(),
        "schools": AsyncMock(),
        "class_groups": AsyncMock(),
        "students": AsyncMock(),
        "documents": AsyncMock(),
        "results": AsyncMock(),
        "batches": AsyncMock(),
        "assessment_tasks": AsyncMock()
    }
    
    # Configure each mock collection with proper methods
    for name, collection in mock_collections.items():
        # Configure create_index to return None
        collection.create_index = AsyncMock(return_value=None)
        
        # Configure find to return an AsyncMock that can be awaited
        mock_cursor = AsyncMock()
        
        # Make mock_cursor itself an async iterable (e.g., by mocking __aiter__)
        # It will yield items from an empty list by default.
        # Tests requiring specific find results should mock .find().return_value.__aiter__ or .to_list()
        async def mock_aiter_impl():
            if hasattr(mock_cursor, '_custom_find_results'):
                for item in mock_cursor._custom_find_results:
                    yield item
                return
            for item in []: # Default empty list
                yield item
        
        mock_cursor.__aiter__ = Mock(side_effect=mock_aiter_impl) # Use Mock for synchronous __aiter__ assignment
        
        # Configure skip and limit to return the same mock_cursor instance
        # So that collection.find().skip().limit() works and returns the iterable mock_cursor
        mock_cursor.skip = Mock(return_value=mock_cursor)
        mock_cursor.limit = Mock(return_value=mock_cursor)
        
        # Configure to_list to return an empty list by default
        mock_cursor.to_list = AsyncMock(return_value=[])

        collection.find = Mock(return_value=mock_cursor)
        
        # Configure find_one to return None by default
        collection.find_one = AsyncMock(return_value=None)
        
        # Configure count_documents to return 0 by default
        collection.count_documents = AsyncMock(return_value=0)
        
        # Configure insert_one to return a mock result
        mock_insert_result = AsyncMock()
        mock_insert_result.inserted_id = "mock_id"
        collection.insert_one = AsyncMock(return_value=mock_insert_result)
        
        # Configure update_one to return a mock result
        mock_update_result = AsyncMock()
        mock_update_result.modified_count = 1
        collection.update_one = AsyncMock(return_value=mock_update_result)
        
        # Configure delete_one to return a mock result
        mock_delete_result = AsyncMock()
        mock_delete_result.deleted_count = 1
        collection.delete_one = AsyncMock(return_value=mock_delete_result)

        # ADDED: Default find_one_and_update mock for all collections
        # This can be overridden per collection if needed (like for 'batches' below)
        collection.find_one_and_update = AsyncMock(return_value=None)
    
    # ADDED: Explicitly set find_one_and_update for assessment_tasks to return None
    mock_collections["assessment_tasks"].find_one_and_update = AsyncMock(return_value=None)

    # Configure the mock database to return appropriate collections
    def get_collection(name):
        return mock_collections.get(name, AsyncMock())
    
    # Use Mock instead of AsyncMock for get_collection since it's not async
    mock_db_instance.get_collection = Mock(side_effect=get_collection)
    
    # Add an initialized flag to prevent "not initialized" warnings
    mock_db_instance.is_initialized = True
    
    # Mock get_database to return the database instance directly, not a coroutine
    # This matches the actual implementation in database.py where get_database() is not async
    mocker.patch("backend.app.main.get_database", return_value=mock_db_instance)
    mocker.patch("backend.app.db.database.get_database", return_value=mock_db_instance)
    
    # Mock the crud module's _get_collection function
    mocker.patch("backend.app.db.crud._get_collection", side_effect=get_collection)

    # Mock the batch processor if it exists
    try:
        from backend.app.tasks.batch_processor import BatchProcessor
        # Create a properly mocked BatchProcessor that doesn't leave hanging coroutines
        mock_batch_processor = AsyncMock()
        mock_batch_processor.start = AsyncMock()
        mock_batch_processor.stop = AsyncMock()
        
        # Use a simple dict instead of trying to mock __getitem__
        mock_batch_dict = {"_id": "mocked_batch_id"}
        
        # Mock the find_one_and_update to return the dict directly for 'batches' specifically
        # This will override the default None set above for the 'batches' collection
        mock_collections["batches"].find_one_and_update = AsyncMock(return_value=mock_batch_dict)
        
        # Replace real BatchProcessor with mock version
        mocker.patch("backend.app.tasks.batch_processor.BatchProcessor", return_value=mock_batch_processor)

        # ADDED: Mock AssessmentWorker's _run_loop to prevent it from actually running
        # try:
        #     mocker.patch("backend.app.main.AssessmentWorker._run_loop", new_callable=AsyncMock)
        # except AttributeError: # If the class or method doesn't exist, pass silently
        #     pass

        # NEW: Patch the entire AssessmentWorker class in main to be an AsyncMock
        # mocker.patch("backend.app.main.AssessmentWorker", new_callable=AsyncMock)

        # REVISED: Patch AssessmentWorker to return a specific AsyncMock instance
        mock_aw_instance = AsyncMock(name="MockAssessmentWorkerInstance")
        mock_aw_instance.run = AsyncMock(name="MockAssessmentWorkerInstance.run") 
        mock_aw_instance.stop = Mock(name="MockAssessmentWorkerInstance.stop")
        mocker.patch("backend.app.main.AssessmentWorker", return_value=mock_aw_instance)

    except ImportError:
        pass

    from backend.app.main import app as fastapi_app

    if not fastapi_app or not isinstance(fastapi_app, FastAPI):
         pytest.fail("Failed to import the FastAPI app from backend.app.main after patching.")

    try:
        async with LifespanManager(fastapi_app, startup_timeout=15, shutdown_timeout=15):
            yield fastapi_app
    except TimeoutError:
        logger.error("LifespanManager timed out unexpectedly even with mocked handlers.")
        pytest.fail("App startup timed out (15s) despite mocked handlers.")
    except Exception as e:
        logger.error(f"Error during LifespanManager execution: {e}", exc_info=True)
        pytest.fail(f"LifespanManager failed: {e}")
    finally:
        # Ensure any pending tasks are properly cleaned up
        # This helps prevent "Task was destroyed but it is pending!" warnings
        mock_batch_processor.process_batches.reset_mock()
        mock_batch_processor.stop.reset_mock()
        
        # Cancel any pending tasks to prevent warnings
        tasks = asyncio.all_tasks()
        for task in tasks:
            if task is not asyncio.current_task() and not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=0.5)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

@pytest_asyncio.fixture(scope="function")
async def db(app: FastAPI) -> AsyncIOMotorClient:
    if not settings.MONGODB_URL:
        pytest.fail("MONGODB_URL environment variable is not set for tests.")

    test_db_name = settings.DB_NAME + "_test_via_db_fixture"
    client = AsyncIOMotorClient(settings.MONGODB_URL, serverSelectionTimeoutMS=5000)
    try:
        await client.admin.command('ping')
    except Exception as e:
        logger.error(f"Could not connect to MongoDB for 'db' fixture: {e}")
        pytest.fail(f"Could not connect to MongoDB for 'db' fixture: {e}")
        
    db_instance = client[test_db_name]
    yield db_instance

    await client.drop_database(test_db_name)
    client.close()

@pytest_asyncio.fixture(scope="function")
async def app_with_mock_auth(app: FastAPI) -> FastAPI:
    """Fixture that provides the FastAPI app with auth dependency overridden."""
    default_mock_payload = {
        "sub": "mock_kinde_user_id_from_fixture", 
        "email": "mock_user@example.com",
        "iss": settings.KINDE_DOMAIN or "mock_issuer",
        "aud": [settings.KINDE_AUDIENCE] if settings.KINDE_AUDIENCE else ["mock_audience"],
        "exp": time.time() + 3600,
        "iat": time.time(),
        "roles": ["teacher"]
    }

    async def override_get_current_user_payload() -> Dict[str, Any]:
        return default_mock_payload

    app.dependency_overrides[get_current_user_payload] = override_get_current_user_payload
    yield app
    
    if get_current_user_payload in app.dependency_overrides and \
       app.dependency_overrides[get_current_user_payload] == override_get_current_user_payload:
        del app.dependency_overrides[get_current_user_payload]

@pytest_asyncio.fixture(scope="function")
async def app_without_auth(app: FastAPI) -> FastAPI:
    """Fixture that provides the FastAPI app with auth dependency removed."""
    # Store original override if it exists
    original_override = app.dependency_overrides.get(get_current_user_payload)
    
    # Remove the auth dependency
    if get_current_user_payload in app.dependency_overrides:
        del app.dependency_overrides[get_current_user_payload]
    
    yield app
    
    # Restore original override if it existed
    if original_override:
        app.dependency_overrides[get_current_user_payload] = original_override

# --- Pytest Hooks for Logging ---

def pytest_collectreport(report):
    """Log collection errors with more detail."""
    if report.failed:
        # Safely access nodeid, provide a default if not present
        node_name = getattr(report, 'nodeid', 'Initial Collection Phase') 
        # Ensure longreprtext is a string before logging
        longrepr_text = str(getattr(report, 'longreprtext', 'No longrepr available'))
        logger.error(f"Test collection failed for {node_name}: {longrepr_text}")

def pytest_exception_interact(node, call, report):
    """Log details of exceptions during test execution."""
    if report.failed:
        logger.error(f"Test {node.nodeid} failed during {call.when}:")