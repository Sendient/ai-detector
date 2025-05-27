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
from datetime import datetime, timezone

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
# from backend.app.tasks import batch_processor # This specific import might no longer be needed if class is imported above

@pytest_asyncio.fixture(scope="function")
async def app(mocker: MockerFixture) -> AsyncGenerator[FastAPI, None]:
    """Creates a FastAPI app instance for each test function, mocking startup/shutdown events."""

    # Imports moved inside the fixture for clarity and to ensure they are in scope
    from backend.app.tasks.assessment_worker import AssessmentWorker
    from backend.app.tasks.batch_processor import BatchProcessor

    # Mock database connection functions
    mocker.patch("backend.app.main.connect_to_mongo", return_value=True)
    mocker.patch("backend.app.main.close_mongo_connection", return_value=None)
    
    # --- Mock worker classes and asyncio.create_task for app startup ---
    # This is to prevent real workers from starting during LifespanManager execution
    # (which calls main.py's startup_event)
    mock_assessment_worker_instance = AsyncMock(spec=AssessmentWorker)
    # If AssessmentWorker has methods like start/stop that might be called if not fully mocked:
    # mock_assessment_worker_instance.start = AsyncMock() 
    # mock_assessment_worker_instance.stop = AsyncMock()
    mocker.patch("backend.app.main.AssessmentWorker", return_value=mock_assessment_worker_instance)

    mock_batch_processor_instance = AsyncMock(spec=BatchProcessor)
    # mock_batch_processor_instance.start = AsyncMock()
    # mock_batch_processor_instance.stop = AsyncMock()
    mocker.patch("backend.app.main.BatchProcessor", return_value=mock_batch_processor_instance)

    # Prevent the asyncio.create_task in main.py's startup_event from running the real worker loops
    mocker.patch("backend.app.main.asyncio.create_task", return_value=AsyncMock(name="mocked_startup_worker_task"))
    # --- End worker and asyncio.create_task mocking ---

    # Create a mock database instance
    mock_db_instance = AsyncMock(name="MockMongoDBInstance")
    
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
        
        # Configure find to return a mock cursor object that is an async iterable
        # collection.find() is synchronous and returns a cursor object.
        # This cursor object must then support async iteration.

        # This is the object that will be returned by cursor.__aiter__()
        # and will handle the actual async iteration.
        class AsyncIteratorMock:
            def __init__(self, items):
                self._items = iter(items) # Regular iterator

            async def __anext__(self):
                try:
                    return next(self._items)
                except StopIteration:
                    raise StopAsyncIteration

            def __aiter__(self):
                return self

        # Create the mock_cursor object that collection.find() will return.
        # This should be a standard Mock, not AsyncMock.
        mock_cursor_obj = Mock(name=f"MockCursor_{name}")

        # The __aiter__ method of the mock_cursor_obj should return an instance of our AsyncIteratorMock.
        mock_cursor_obj._custom_find_results = []
        
        # MODIFIED: __aiter__ lambda now accepts 'self_arg' (which will be mock_cursor_obj when called)
        # and uses it to access its _custom_find_results attribute.
        mock_cursor_obj.__aiter__ = lambda self_arg: AsyncIteratorMock(self_arg._custom_find_results)

        # Configure skip and limit to return the same mock_cursor_obj instance
        mock_cursor_obj.skip = Mock(return_value=mock_cursor_obj)
        mock_cursor_obj.limit = Mock(return_value=mock_cursor_obj)
        
        # Configure to_list to return a list from _custom_find_results
        # This needs to be an AsyncMock because to_list() is awaited.
        async def mock_to_list_impl(*args, **kwargs):
            return list(mock_cursor_obj._custom_find_results) # Convert to list
        mock_cursor_obj.to_list = AsyncMock(side_effect=mock_to_list_impl)

        # collection.find is a synchronous method, so it's a standard Mock.
        collection.find = Mock(return_value=mock_cursor_obj)
        
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

    # NEW: Specifically configure documents.find_one_and_update to return a mock document
    # This helps the update_document_status call in the upload endpoint succeed by default.
    # Tests that need specific behavior for update_document_status (like test_update_document_status_success)
    # already mock crud.update_document_status directly.
    # mock_updated_doc_for_default = AsyncMock(name="DefaultUpdatedDocumentMock") # OLD
    # Populate with minimal fields to satisfy Document model instantiation if necessary
    default_doc_data = {
        "id": "mock_updated_doc_id", 
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "teacher_id": "mock_teacher_id",
        "status": "QUEUED", # Or whatever default status makes sense
        "original_filename": "mockfile.pdf",
        "file_type": "PDF",
        "blob_filename": "mock_blob.pdf",
        # Add other required fields for Document model with default values
    }
    mock_updated_doc_for_default = AsyncMock(spec=dict, **default_doc_data) # NEW
    # Configure it to behave like a dict for ** unpacking
    mock_updated_doc_for_default.keys = Mock(return_value=default_doc_data.keys())
    mock_updated_doc_for_default.__getitem__ = Mock(side_effect=lambda key: default_doc_data[key])
    
    mock_collections["documents"].find_one_and_update = AsyncMock(return_value=mock_updated_doc_for_default)

    # Configure the mock database to return appropriate collections
    def get_collection(name):
        return mock_collections.get(name, AsyncMock())
    
    # Use Mock instead of AsyncMock for get_collection since it's not async
    mock_db_instance.get_collection = Mock(side_effect=get_collection)
    
    # NEW: Explicitly set attributes on mock_db_instance for direct access
    for name, configured_collection_mock in mock_collections.items():
        setattr(mock_db_instance, name, configured_collection_mock)
    
    # Add an initialized flag to prevent "not initialized" warnings
    mock_db_instance.is_initialized = True
    
    # Mock get_database to return the database instance directly
    mocker.patch("backend.app.main.get_database", return_value=mock_db_instance)
    mocker.patch("backend.app.db.database.get_database", return_value=mock_db_instance)

    # --- REVISED: Explicitly mock init_database and related module-level variables in database.py ---
    # This ensures that when app.main.connect_to_mongo (which calls init_database) runs via LifespanManager,
    # it uses our mocks and sets up the database module correctly for subsequent get_database calls.
    
    # Additionally, directly patch the module-level variables in database.py that get_database() might rely on.
    # This is a bit belt-and-suspenders but ensures all avenues are covered.
    # These are set when connect_to_mongo (which is mocked at main level) would have run.
    mocker.patch("backend.app.db.database._db", mock_db_instance) # Patching the actual global var name _db
    mocker.patch("backend.app.db.database._client", AsyncMock(name="MockMotorClientGlobal")) # Patching _client
    # --- END REVISED ---
    
    # --- START: Configure session mock for transactions ---
    mock_motor_client = AsyncMock(name="MockMotorClientForSession")
    mock_session_instance = AsyncMock(name="MockSessionInstance")
    
    # Configure mock_session_instance.start_transaction to be an async context manager
    # that yields another AsyncMock (or the session itself if preferred for simplicity in tests)
    mock_transaction_context = AsyncMock(name="MockTransactionContext")
    mock_session_instance.start_transaction = Mock(return_value=mock_transaction_context) #.start_transaction() returns the context
    mock_transaction_context.__aenter__ = AsyncMock(return_value=AsyncMock(name="ActiveMockTransaction")) # __aenter__ returns the active transaction
    mock_transaction_context.__aexit__ = AsyncMock(return_value=None)

    # Configure mock_motor_client.start_session
    # This method is awaited: `await current_db.client.start_session()`
    # So, it should be an AsyncMock.
    # The result of this await is then used in an `async with ... as session`,
    # so the return_value of this AsyncMock must be an async context manager.
    mock_client_session_context = AsyncMock(name="MockClientSessionContextYieldedByAwait")
    mock_client_session_context.__aenter__ = AsyncMock(return_value=mock_session_instance) # This will be 'session'
    mock_client_session_context.__aexit__ = AsyncMock(return_value=None)

    mock_motor_client.start_session = AsyncMock(return_value=mock_client_session_context) # MODIFIED: .start_session is an AsyncMock

    # Ensure the mock_db_instance.client is this configured mock_motor_client
    mock_db_instance.client = mock_motor_client
    # --- END: Configure session mock for transactions ---

    # Mock the crud module's _get_collection function
    mocker.patch("backend.app.db.crud._get_collection", side_effect=get_collection)

    # Mock the batch processor if it exists
    try:
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
        # Use the logging module directly
        current_logger = logging.getLogger(__name__ + ".pytest_collectreport")
        # Safely access nodeid, provide a default if not present
        node_name = getattr(report, 'nodeid', 'Initial Collection Phase') 
        # Ensure longreprtext is a string before logging
        longrepr_text = str(getattr(report, 'longreprtext', 'No longrepr available'))
        current_logger.error(f"Test collection failed for {node_name}: {longrepr_text}")

def pytest_exception_interact(node, call, report):
    """Log details of exceptions during test execution."""
    if report.failed:
        # Use the logging module directly
        current_logger = logging.getLogger(__name__ + ".pytest_exception_interact")
        current_logger.error(f"Test {node.nodeid} failed during {call.when}:")
        # You could add more details from the report or call objects here
        # For example, to print the exception info:
        # excinfo = call.excinfo
        # if excinfo:
        #     current_logger.error(f"  Exception: {excinfo.type.__name__}: {excinfo.value}")
        #     current_logger.error(f"  Traceback: \n{''.join(excinfo.traceback.format())}")

# --- Optional: Setup a root logger for conftest if needed elsewhere ---
# logger = logging.getLogger(__name__) # If you need a module-level logger
# logger.setLevel(logging.DEBUG) # Set your desired level
#
# handler = logging.StreamHandler()
# formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# handler.setFormatter(formatter)
# logger.addHandler(handler)