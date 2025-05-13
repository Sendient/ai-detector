# backend/tests/conftest.py
import sys
from pathlib import Path

# Add project root to sys.path to allow imports like 'backend.app.main'
# Assumes this conftest.py is in backend/tests/, so two parents up is backend/, three parents up is project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pytest
import asyncio # Keep for context, though event_loop fixture is removed
from httpx import AsyncClient # Not strictly needed here if only defining app, but good for context

# Import your FastAPI application instance
# Adjust the import path according to your project structure
from backend.app.main import app as fastapi_app # Renaming to avoid conflict if 'app' is used elsewhere

# @pytest.fixture(scope="session") # Removing custom event_loop fixture
# def event_loop():
#     """Create an instance of the default event loop for session-scoped async fixtures."""
#     loop = asyncio.get_event_loop_policy().new_event_loop()
#     yield loop
#     loop.close()

@pytest.fixture(scope="session")
def app():
    """Yield the FastAPI app instance for pytest-httpx."""
    yield fastapi_app

# The async_client fixture will be automatically provided by pytest-httpx
# if an 'app' fixture is available. pytest-httpx uses the 'app' fixture
# to get the ASGI application to test.
# pytest-asyncio will manage the event loop based on settings in pytest.ini.

# Example fixture for a test database (if you set one up for testing)
# @pytest.fixture(scope="session")
# async def test_db_session():
#     # Setup test database connection
#     # ...
#     # MONGO_URL_TEST = os.getenv("MONGO_URL_TEST", "mongodb://localhost:27017/smarteaid_test")
#     # TEST_DATABASE_NAME = "smarteaid_test" 
#     # test_client = AsyncIOMotorClient(MONGO_URL_TEST)
#     # test_db = test_client[TEST_DATABASE_NAME]
#     # yield test_db # provide the database session
#     # Teardown test database (e.g., drop collections or the database)
#     # await test_client.drop_database(TEST_DATABASE_NAME)
#     # test_client.close()
# pass # Removed pass as we added fixtures
