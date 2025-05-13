# tests/conftest.py
import pytest
from fastapi.testclient import TestClient
import asyncio
import sys
import os

# --- START: Add project root to sys.path ---
# This helps ensure modules like 'backend' can be found
script_path = os.path.abspath(__file__)
tests_dir = os.path.dirname(script_path)
project_root = os.path.dirname(tests_dir) # Assumes tests dir is at project root

if project_root not in sys.path:
    print(f"Adding project root to sys.path from conftest: {project_root}")
    sys.path.insert(0, project_root)
# --- END: Add project root ---


# --- Adjust this import to point to your main FastAPI app instance ---
# Using the likely path based on project structure:
try:
    from backend.app.main import app
    print("Successfully imported 'app' from backend.app.main")
except ImportError as e:
    print(f"Error importing 'app' from backend.app.main: {e}")
    print("Please ensure backend/app/main.py exists and defines the FastAPI 'app' instance.")
    # Define a dummy app to allow tests to load, though they might fail later
    from fastapi import FastAPI
    app = FastAPI(title="Dummy App for Test Loading")
# --------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop():
    """
    Creates an event loop for the test session.
    Needed by pytest-asyncio for session-scoped async fixtures.
    """
    print("Creating session event loop...")
    try:
        loop = asyncio.get_running_loop()
        print("Re-using existing running loop for session.")
    except RuntimeError:
        print("Creating new event loop for session.")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop) # Set the loop for the current context

    yield loop
    print("Closing session event loop...")
    if not loop.is_closed():
        loop.close()


@pytest.fixture(scope="module") # Or "session" if you prefer
def client():
    """
    Provides a FastAPI TestClient instance for making requests to the app.
    """
    print("Creating TestClient fixture...")
    # You can add specific test headers here if needed, e.g., for auth
    # headers = {"Authorization": "Bearer testtoken"}
    # with TestClient(app, headers=headers) as c:
    #    yield c

    with TestClient(app) as c:
        yield c
    print("TestClient fixture teardown.")

# Add other fixtures here as needed, e.g., for:
# - Mocking database connections (Motor)
# - Mocking external services (Kinde, Stripe, Azure Blob Storage)
# - Setting up test data 