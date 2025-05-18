# app/tests/api/v1/test_teachers.py
import pytest
import time
from typing import Any, Dict, Optional
import httpx # <-- ADD THIS IMPORT
from httpx import AsyncClient, ASGITransport # Use this for type hinting
from motor.motor_asyncio import AsyncIOMotorClient  # For DB checks
# backend.app.core.config.settings is imported within the test or via conftest
from backend.app.main import app as fastapi_app # <-- ADD THIS IMPORT
from backend.app.models.teacher import TeacherCreate # Assuming model is here
from backend.app.core.config import settings # Correct: Import the settings instance
from backend.app.models.teacher import TeacherCreate, Teacher # Correct path: models directory
# Import the get_current_user_payload to use as a key for dependency_overrides
from backend.app.core.security import get_current_user_payload # UPDATED IMPORT PATH
from fastapi import FastAPI, status, Depends
from pytest_mock import MockerFixture
from backend.app.models.teacher import Teacher # Import Teacher model for mock return
from backend.app.models.enums import TeacherRole # Import Enum if needed for mock
import uuid
from datetime import datetime, timezone, timedelta
import inspect
from fastapi import HTTPException

# Attempt to import the app instance directly for manual client creation
# This relies on sys.path being correctly configured by the main conftest.py
# from backend.app.main import app as fastapi_app # Removed as it's not needed when using async_client fixture

# Mark all tests in this module to use pytest-asyncio
pytestmark = pytest.mark.asyncio

# Fixture for sample teacher data (ensure this exists, e.g., in conftest.py)
@pytest.fixture(scope="module") # Or function scope if modification happens
def sample_teacher_payload() -> dict[str, Any]:
    timestamp = int(time.time()) # Use time import here too
    return {
        "email": f"alice.smith.test.{timestamp}@example.com",
        "first_name": "Alice",
        "last_name": "Smith",
        "school_name": "Test University",
        "country": "USA",
        "state_county": "CA",
        # "user_id": f"kinde_test_{timestamp}" # This might be derived from token, remove if not needed in request body
        # Add other required fields based on your TeacherCreate model
    }

@pytest.mark.asyncio
async def test_create_teacher_success(
    managed_fastapi_app: FastAPI, # Use the standard 'app' fixture
    mocker: MockerFixture,
    sample_teacher_payload: dict[str, Any]
):
    """Test successful teacher creation (POST /teachers/) by mocking validate_token."""
    api_prefix = settings.API_V1_PREFIX

    # Define a mock payload similar to what Kinde would provide
    default_mock_payload = {
        "sub": f"kinde_id_create_success_{uuid.uuid4()}", # Use a unique Kinde ID
        "iss": settings.KINDE_DOMAIN or "mock_issuer",
        "aud": [settings.KINDE_AUDIENCE] if settings.KINDE_AUDIENCE else ["mock_audience"],
        "exp": time.time() + 3600, # Use time.time()
        "iat": time.time(),      # Use time.time()
        "roles": ["teacher"]     # Ensure the required role is present
    }

    # Mock the validate_token function directly
    mocker.patch('app.core.security.validate_token', return_value=default_mock_payload)

    # --- Mock CRUD functions used by the endpoint --- 
    # Note: Patch the functions *where they are looked up* (in the teachers endpoint module)
    
    # Mock get_teacher_by_kinde_id to return None (teacher doesn't exist)
    mocker.patch('backend.app.api.v1.endpoints.teachers.crud.get_teacher_by_kinde_id', return_value=None)

    # Mock create_teacher to return a simulated Teacher object
    # Create a dictionary matching the Teacher response model structure
    mock_created_teacher_dict = {
        "kinde_id": default_mock_payload["sub"], # Use 'id' and match the mock auth sub
        "first_name": sample_teacher_payload["first_name"],
        "last_name": sample_teacher_payload["last_name"],
        "email": sample_teacher_payload["email"],
        "school_name": sample_teacher_payload["school_name"],
        "country": sample_teacher_payload["country"],
        "state_county": sample_teacher_payload["state_county"],
        "role": TeacherRole.TEACHER.value, # Or whatever the default/expected role is
        "is_administrator": False,
        "how_did_you_hear": None,
        "description": None,
        "is_active": True,
        "created_at": datetime.now(timezone.utc), # Use current time
        "updated_at": datetime.now(timezone.utc)
        # Add any other fields expected in the Teacher model response
    }
    # Instantiate Teacher model using the corrected dictionary
    mocker.patch('backend.app.api.v1.endpoints.teachers.crud.create_teacher', return_value=Teacher(**mock_created_teacher_dict))
    # --- End CRUD Mocking --- 

    headers = {
        "Authorization": "Bearer dummytoken", # Token content doesn't matter now
        "Content-Type": "application/json"
    }

    # Use the standard 'app' fixture
    async with AsyncClient(transport=ASGITransport(app=managed_fastapi_app), base_url="http://testserver") as client:
        response = await client.post(
            f"{api_prefix}/teachers/",
            json=sample_teacher_payload,
            headers=headers
        )

    # --- Assertions ---
    print(f"Response Status: {response.status_code}")
    print(f"Response JSON: {response.text}") # Print response body for debugging

    # Check for successful status code (200 OK or 201 Created)
    assert response.status_code == status.HTTP_201_CREATED # POST should return 201

    # --- Further Assertions ---
    response_data = response.json()
    assert response_data["email"] == sample_teacher_payload["email"]
    assert response_data["first_name"] == sample_teacher_payload["first_name"]
    # Assert using the key present in the actual JSON response ('_id')
    assert response_data["_id"] == default_mock_payload["sub"] # Check _id matches mock auth sub
    # Check other fields match the mock_created_teacher_dict (adjusting for JSON types like datetime strings)
    assert response_data["school_name"] == mock_created_teacher_dict["school_name"]

# Fixture for sample teacher data (if not already in conftest.py)
# @pytest.fixture(scope="module") # Or function scope if modification happens
# def sample_teacher_payload() -> dict[str, Any]:
#     return {
#         "user_id": "kinde_user_abc123", # Example Kinde ID
#         "first_name": "Alice",
#         "last_name": "Smith",
#         "email": "alice.smith@example.com"
#         # Add other required fields for TeacherCreate schema
#     }

# You might need to define or import TeacherCreate and Teacher schemas
# from backend.app.schemas.teacher import TeacherCreate, Teacher

# --- TODO: Add more tests ---
# test_create_teacher_missing_fields() -> Expect 422
# test_create_teacher_unauthorized() -> Expect 401/403 (mock dependency accordingly)
# test_get_teachers_empty()
# test_get_teachers_with_data()
# test_get_single_teacher_success()
# test_get_single_teacher_not_found() -> Expect 404
# test_update_teacher_success()
# test_update_teacher_not_found() -> Expect 404
# test_delete_teacher_success()
# test_delete_teacher_not_found() -> Expect 404 

# --- Test GET Current Teacher ---

@pytest.mark.asyncio
async def test_get_current_teacher_success(
    managed_fastapi_app: FastAPI,
    mocker: MockerFixture
):
    """Test successfully fetching the current authenticated user's teacher profile."""
    api_prefix = settings.API_V1_PREFIX
    test_kinde_id = f"kinde_id_get_current_teacher_{uuid.uuid4()}" # Use a unique Kinde ID

    # Define a mock payload for the authenticated user
    default_mock_payload = {
        "sub": test_kinde_id,
        "iss": settings.KINDE_DOMAIN or "mock_issuer",
        "aud": [settings.KINDE_AUDIENCE] if settings.KINDE_AUDIENCE else ["mock_audience"],
        "exp": time.time() + 3600,
        "iat": time.time(),
        "roles": ["teacher"] # Assuming 'teacher' role is needed
    }

    # Mock the validate_token function
    mocker.patch('app.core.security.validate_token', return_value=default_mock_payload)

    # Mock the CRUD function to return an existing teacher
    # Simulate the Teacher object that would be returned from the DB
    mock_teacher_from_db = Teacher(
        kinde_id=test_kinde_id, # ADD THIS - kinde_id is the string
        email=f"get_test.{int(time.time())}@example.com",
        first_name="GetTest",
        last_name="User",
        school_name="Mock School",
        country="USA",
        state_county="NV",
        role=TeacherRole.TEACHER, # Use the enum
        credits=10,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    mocker.patch('backend.app.api.v1.endpoints.teachers.crud.get_teacher_by_kinde_id', return_value=mock_teacher_from_db)

    # --- Make the Request ---
    headers = {"Authorization": "Bearer dummytoken"} # Token content doesn't matter due to mock

    # Assuming the endpoint to get the current user's teacher profile is /teachers/me
    # Adjust the URL if it's different (e.g., /teachers/{kinde_id})
    get_url = f"{api_prefix}/teachers/me"

    # Use the HTTPX client provided by the 'app' fixture's lifespan manager
    async with httpx.AsyncClient(transport=ASGITransport(app=managed_fastapi_app), base_url="http://test") as client:
        response = await client.get(get_url, headers=headers)

    # --- Assertions ---
    assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}. Response: {response.text}"
    response_data = response.json()

    # Check that the returned data matches the mocked teacher data
    assert response_data["_id"] == test_kinde_id
    assert response_data["email"] == mock_teacher_from_db.email
    assert response_data["first_name"] == mock_teacher_from_db.first_name
    # Add more assertions for other fields...


# --- Test GET Current Teacher Not Found ---

@pytest.mark.asyncio
async def test_get_teacher_not_found(
    managed_fastapi_app: FastAPI,
    mocker: MockerFixture
):
    """Test requesting the current user's profile when it does not exist (expect 404)."""
    api_prefix = settings.API_V1_PREFIX
    test_kinde_id_not_found = "get_teacher_test_kinde_id_not_found"

    # Define a mock payload for an authenticated user
    default_mock_payload = {
        "sub": test_kinde_id_not_found,
        "iss": settings.KINDE_DOMAIN or "mock_issuer",
        "aud": [settings.KINDE_AUDIENCE] if settings.KINDE_AUDIENCE else ["mock_audience"],
        "exp": time.time() + 3600,
        "iat": time.time(),
        "roles": ["teacher"] # Role doesn't strictly matter for this test
    }

    # Mock the validate_token function
    mocker.patch('app.core.security.validate_token', return_value=default_mock_payload)

    # Mock the CRUD function to return None (teacher doesn't exist)
    mocker.patch('backend.app.api.v1.endpoints.teachers.crud.get_teacher_by_kinde_id', return_value=None)

    # --- Make the Request ---
    headers = {"Authorization": "Bearer dummytoken"} # Token content doesn't matter
    get_url = f"{api_prefix}/teachers/me"

    async with httpx.AsyncClient(transport=ASGITransport(app=managed_fastapi_app), base_url="http://test") as client:
        response = await client.get(get_url, headers=headers)

    # --- Assertions ---
    # Expect 404 Not Found because crud.get_teacher_by_kinde_id returned None
    assert response.status_code == status.HTTP_404_NOT_FOUND, \
        f"Expected 404 Not Found, got {response.status_code}. Response: {response.text}"
    # Optionally, assert the detail message if it's consistent
    # response_data = response.json()
    # assert "Teacher profile not found" in response_data["detail"]


# --- Test PUT /me (Update Existing Teacher) ---

@pytest.mark.asyncio
async def test_update_teacher_success(
    managed_fastapi_app: FastAPI,
    mocker: MockerFixture
):
    """Test successfully updating an existing teacher profile via PUT /me."""
    api_prefix = settings.API_V1_PREFIX
    test_kinde_id_update = f"kinde_id_update_teacher_{uuid.uuid4()}" # Use a unique Kinde ID

    # Mock authentication
    default_mock_payload = {
        "sub": test_kinde_id_update,
        "iss": settings.KINDE_DOMAIN or "mock_issuer",
        "aud": [settings.KINDE_AUDIENCE] if settings.KINDE_AUDIENCE else ["mock_audience"],
        "exp": time.time() + 3600,
        "iat": time.time(),
        "roles": ["teacher"]
    }
    mocker.patch('app.core.security.validate_token', return_value=default_mock_payload)

    # Simulate the *existing* teacher data in the DB
    existing_teacher_in_db = Teacher(
        kinde_id=test_kinde_id_update, # ADD THIS
        email=f"update_test_initial.{int(time.time())}@example.com",
        first_name="UpdateTest",
        last_name="UserInitial",
        school_name="Initial School",
        country="UK",
        state_county="London",
        role=TeacherRole.TEACHER,
        credits=5, # Assume credits field exists in DB model if needed
        created_at=datetime.now(timezone.utc) - timedelta(days=1), # Simulate older creation time
        updated_at=datetime.now(timezone.utc) - timedelta(hours=1) # Simulate older update time
    )
    # Mock get_teacher_by_kinde_id to return the existing teacher
    mocker.patch('backend.app.api.v1.endpoints.teachers.crud.get_teacher_by_kinde_id', return_value=existing_teacher_in_db)

    # --- Define the update payload ---
    update_payload = {
        "first_name": "UpdateTestUpdated",
        "last_name": "UserUpdated",
        "school_name": "Updated School Name",
        # Only include fields being updated
    }

    # Simulate the teacher object *after* the update
    # Create a dictionary, update it, then instantiate the model
    existing_data_dict = existing_teacher_in_db.model_dump()
    existing_data_dict.update(update_payload) # Apply the updates
    existing_data_dict['updated_at'] = datetime.now(timezone.utc) # Set new timestamp

    updated_teacher_in_db = Teacher(**existing_data_dict) # Create from combined dict

    # Mock update_teacher to return the updated teacher data
    mocker.patch('backend.app.api.v1.endpoints.teachers.crud.update_teacher', return_value=updated_teacher_in_db)

    # --- Make the Request ---
    headers = {
        "Authorization": "Bearer dummytoken",
        "Content-Type": "application/json"
    }
    put_url = f"{api_prefix}/teachers/me"

    async with httpx.AsyncClient(transport=ASGITransport(app=managed_fastapi_app), base_url="http://test") as client:
        response = await client.put(put_url, headers=headers, json=update_payload)

    # --- Assertions ---
    # PUT for update should return 200 OK
    assert response.status_code == status.HTTP_200_OK, \
        f"Expected 200 OK, got {response.status_code}. Response: {response.text}"

    response_data = response.json()

    # Assert that the returned data matches the *updated* values
    assert response_data["_id"] == test_kinde_id_update
    assert response_data["first_name"] == update_payload["first_name"]
    assert response_data["last_name"] == update_payload["last_name"]
    assert response_data["school_name"] == update_payload["school_name"]
    # Assert that non-updated fields remain the same (e.g., email)
    assert response_data["email"] == existing_teacher_in_db.email
    # Add more assertions...


# --- Test PUT /me (Create New Teacher via Upsert) ---

@pytest.mark.asyncio
async def test_create_teacher_via_put_success(
    managed_fastapi_app: FastAPI,
    mocker: MockerFixture,
    sample_teacher_payload: dict[str, Any] # Re-use for new teacher data
):
    """Test successfully creating a new teacher profile via PUT /me when one doesn't exist."""
    api_prefix = settings.API_V1_PREFIX
    test_kinde_id_create_put = f"kinde_id_create_put_{uuid.uuid4()}" # Use a unique Kinde ID

    # Mock authentication (including email, which is needed for creation)
    default_mock_payload = {
        "sub": test_kinde_id_create_put,
        "iss": settings.KINDE_DOMAIN or "mock_issuer",
        "aud": [settings.KINDE_AUDIENCE] if settings.KINDE_AUDIENCE else ["mock_audience"],
        "exp": time.time() + 3600,
        "iat": time.time(),
        "roles": ["teacher"],
        "email": sample_teacher_payload["email"] # Ensure email is in the token for creation path
    }
    mocker.patch('app.core.security.validate_token', return_value=default_mock_payload)

    # Mock get_teacher_by_kinde_id to return None (teacher doesn't exist)
    mocker.patch('backend.app.api.v1.endpoints.teachers.crud.get_teacher_by_kinde_id', return_value=None)

    # --- Define the payload for creation ---
    # This payload must satisfy TeacherCreate requirements
    create_payload_for_put = {
        "first_name": sample_teacher_payload["first_name"],
        "last_name": sample_teacher_payload["last_name"],
        "school_name": sample_teacher_payload["school_name"],
        "country": sample_teacher_payload["country"],
        "state_county": sample_teacher_payload["state_county"],
        "role": TeacherRole.TEACHER.value # Ensure role is explicitly provided for creation
        # 'email' is taken from the token payload by the endpoint logic
    }

    # Simulate the teacher object that will be created and returned
    newly_created_teacher_in_db = Teacher(
        kinde_id=test_kinde_id_create_put, # ADD THIS
        email=sample_teacher_payload["email"], # Email from token is used
        first_name=create_payload_for_put["first_name"],
        last_name=create_payload_for_put["last_name"],
        school_name=create_payload_for_put["school_name"],
        country=create_payload_for_put["country"],
        state_county=create_payload_for_put["state_county"],
        role=TeacherRole.TEACHER, # Match the payload
        is_administrator=False, # Default
        is_active=True, # Default
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    # Mock create_teacher to return the newly created teacher data
    mocker.patch('backend.app.api.v1.endpoints.teachers.crud.create_teacher', return_value=newly_created_teacher_in_db)

    # --- Make the Request ---
    headers = {
        "Authorization": "Bearer dummytoken",
        "Content-Type": "application/json"
    }
    put_url = f"{api_prefix}/teachers/me"

    async with httpx.AsyncClient(transport=ASGITransport(app=managed_fastapi_app), base_url="http://test") as client:
        response = await client.put(put_url, headers=headers, json=create_payload_for_put)

    # --- Assertions ---
    # PUT for create (upsert) should still return 200 OK as per endpoint definition
    assert response.status_code == status.HTTP_200_OK, \
        f"Expected 200 OK for create via PUT, got {response.status_code}. Response: {response.text}"

    response_data = response.json()

    # Assert that the returned data matches the newly created teacher's values
    assert response_data["_id"] == test_kinde_id_create_put
    assert response_data["email"] == sample_teacher_payload["email"]
    assert response_data["first_name"] == create_payload_for_put["first_name"]
    assert response_data["school_name"] == create_payload_for_put["school_name"]
    # Add more assertions...


# --- Test DELETE /me (Delete Existing Teacher) ---

@pytest.mark.asyncio
async def test_delete_teacher_success(
    managed_fastapi_app: FastAPI,
    mocker: MockerFixture
):
    """Test successfully deleting an existing teacher profile via DELETE /me."""
    api_prefix = settings.API_V1_PREFIX
    test_kinde_id_delete = f"kinde_id_delete_teacher_{uuid.uuid4()}" # Use a unique Kinde ID

    # Mock authentication
    default_mock_payload = {
        "sub": test_kinde_id_delete,
        "iss": settings.KINDE_DOMAIN or "mock_issuer",
        "aud": [settings.KINDE_AUDIENCE] if settings.KINDE_AUDIENCE else ["mock_audience"],
        "exp": time.time() + 3600,
        "iat": time.time(),
        "roles": ["teacher"]
    }
    mocker.patch('app.core.security.validate_token', return_value=default_mock_payload)

    # Simulate an existing teacher to be deleted
    # We don't need the full teacher object here, just need the mock to confirm existence
    mocker.patch('backend.app.api.v1.endpoints.teachers.crud.get_teacher_by_kinde_id', return_value=Teacher(kinde_id=test_kinde_id_delete, email="del@test.com", first_name="Del", last_name="Me", school_name="Any School", country="US", state_county="CA")) # Simplified mock, ensure all required Teacher fields
    # Mock the delete operation
    mock_delete_teacher = mocker.patch('backend.app.api.v1.endpoints.teachers.crud.delete_teacher_by_kinde_id', return_value=True) # Assume it returns True on success

    # --- Make the Request ---
    headers = {"Authorization": "Bearer dummytoken"}
    delete_url = f"{api_prefix}/teachers/me"

    async with httpx.AsyncClient(transport=ASGITransport(app=managed_fastapi_app), base_url="http://test") as client:
        response = await client.delete(delete_url, headers=headers)
        
    # --- Assertions ---
    # DELETE should return 204 No Content on success
    assert response.status_code == status.HTTP_204_NO_CONTENT, \
        f"Expected 204 No Content, got {response.status_code}. Response: {response.text}"

    # Ensure the delete CRUD function was called correctly with the target Kinde ID
    mock_delete_teacher.assert_called_once_with(kinde_id=test_kinde_id_delete)


# --- Test DELETE /me (Teacher Not Found) ---

@pytest.mark.asyncio
async def test_delete_teacher_not_found(
    managed_fastapi_app: FastAPI,
    mocker: MockerFixture
):
    """Test attempting to delete a teacher profile via DELETE /me when it does not exist."""
    api_prefix = settings.API_V1_PREFIX
    test_kinde_id_delete_not_found = "delete_not_found_teacher_kinde_id"

    # Mock authentication
    default_mock_payload = {
        "sub": test_kinde_id_delete_not_found,
        "iss": settings.KINDE_DOMAIN or "mock_issuer",
        "aud": [settings.KINDE_AUDIENCE] if settings.KINDE_AUDIENCE else ["mock_audience"],
        "exp": time.time() + 3600,
        "iat": time.time(),
        "roles": ["teacher"]
    }
    mocker.patch('app.core.security.validate_token', return_value=default_mock_payload)

    # Mock crud.delete_teacher to return False (simulating teacher not found/not deleted)
    delete_crud_mock = mocker.patch('backend.app.api.v1.endpoints.teachers.crud.delete_teacher', return_value=False) 

    # --- Make the Request ---
    headers = {"Authorization": "Bearer dummytoken"}
    delete_url = f"{api_prefix}/teachers/me"

    async with httpx.AsyncClient(transport=ASGITransport(app=managed_fastapi_app), base_url="http://test") as client:
        response = await client.delete(delete_url, headers=headers)

    # --- Assertions ---
    assert response.status_code == status.HTTP_404_NOT_FOUND, \
        f"Expected 404 Not Found, got {response.status_code}. Response: {response.text}"
    
    # Ensure delete_teacher WAS called, and its False return value led to the 404
    delete_crud_mock.assert_called_once_with(kinde_id=test_kinde_id_delete_not_found)


# --- Test POST / (Create Teacher - Conflict) ---

@pytest.mark.asyncio
async def test_create_teacher_conflict(
    managed_fastapi_app: FastAPI,
    mocker: MockerFixture,
    sample_teacher_payload: dict[str, Any] # Re-use for structure
):
    """Test creating a teacher when a profile already exists for the user (expect 409)."""
    api_prefix = settings.API_V1_PREFIX
    test_kinde_id_conflict = f"kinde_id_conflict_teacher_{uuid.uuid4()}" # Use a unique Kinde ID

    # Mock authentication
    default_mock_payload = {
        "sub": test_kinde_id_conflict,
        "iss": settings.KINDE_DOMAIN or "mock_issuer",
        "aud": [settings.KINDE_AUDIENCE] if settings.KINDE_AUDIENCE else ["mock_audience"],
        "exp": time.time() + 3600,
        "iat": time.time(),
        "roles": ["teacher"]
    }
    mocker.patch('app.core.security.validate_token', return_value=default_mock_payload)

    # Mock get_teacher_by_kinde_id to return an existing teacher, simulating a conflict
    existing_teacher = Teacher(
        kinde_id=test_kinde_id_conflict, # ADD THIS
        email=sample_teacher_payload["email"],
        first_name=sample_teacher_payload["first_name"],
        last_name=sample_teacher_payload["last_name"],
        school_name=sample_teacher_payload.get("school_name", "Conflict School"), # Ensure required fields
        country=sample_teacher_payload.get("country", "US"),
        state_county=sample_teacher_payload.get("state_county", "CA")
        # ... other fields can be minimal as we only need to simulate existence
    )
    mocker.patch('backend.app.api.v1.endpoints.teachers.crud.get_teacher_by_kinde_id', return_value=existing_teacher)

    # crud.create_teacher should NOT be called in this scenario
    create_teacher_mock = mocker.patch('backend.app.api.v1.endpoints.teachers.crud.create_teacher')

    # --- Make the Request (using sample_teacher_payload for the body) ---
    headers = {
        "Authorization": "Bearer dummytoken",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(transport=ASGITransport(app=managed_fastapi_app), base_url="http://testserver") as client:
        response = await client.post(
            f"{api_prefix}/teachers/",
            json=sample_teacher_payload, # Attempt to create with this data
            headers=headers
        )

    # --- Assertions ---
    assert response.status_code == status.HTTP_409_CONFLICT, \
        f"Expected 409 Conflict, got {response.status_code}. Response: {response.text}"
    
    create_teacher_mock.assert_not_called() # Verify create_teacher was not attempted


# --- Test POST / (Create Teacher - Missing Required Fields) ---

@pytest.mark.asyncio
async def test_create_teacher_missing_required_fields(
    managed_fastapi_app: FastAPI,
    mocker: MockerFixture,
    sample_teacher_payload: dict[str, Any] # Use for base payload
):
    """Test creating a teacher with missing required fields (expect 422)."""
    api_prefix = settings.API_V1_PREFIX
    test_kinde_id_missing_fields = "missing_fields_kinde_id"

    # Mock authentication
    default_mock_payload = {
        "sub": test_kinde_id_missing_fields,
        "iss": settings.KINDE_DOMAIN or "mock_issuer",
        "aud": [settings.KINDE_AUDIENCE] if settings.KINDE_AUDIENCE else ["mock_audience"],
        "exp": time.time() + 3600,
        "iat": time.time(),
        "roles": ["teacher"]
    }
    mocker.patch('app.core.security.validate_token', return_value=default_mock_payload)

    # CRUD functions should not be called if validation fails first
    get_teacher_mock = mocker.patch('backend.app.api.v1.endpoints.teachers.crud.get_teacher_by_kinde_id')
    create_teacher_mock = mocker.patch('backend.app.api.v1.endpoints.teachers.crud.create_teacher')

    # --- Create a payload that is missing a required field ---
    # Assuming 'school_name' is required by TeacherCreate model. Adjust if different.
    payload_missing_school = sample_teacher_payload.copy()
    if 'school_name' in payload_missing_school:
        del payload_missing_school['school_name'] 
    else:
        # If school_name wasn't in sample, ensure another known required field is missing
        # This part depends on the exact definition of TeacherCreate
        # For now, we'll assume school_name was the target. If not, this needs adjustment.
        pass 

    # --- Make the Request ---
    headers = {
        "Authorization": "Bearer dummytoken",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(transport=ASGITransport(app=managed_fastapi_app), base_url="http://testserver") as client:
        response = await client.post(
            f"{api_prefix}/teachers/",
            json=payload_missing_school,
            headers=headers
        )

    # --- Assertions ---
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, \
        f"Expected 422 Unprocessable Entity, got {response.status_code}. Response: {response.text}"
    
    # Verify that Pydantic validation prevented calls to CRUD layer
    get_teacher_mock.assert_not_called()
    create_teacher_mock.assert_not_called()


# Add more tests below: create_invalid_data_types, list, RBAC tests etc. 

@pytest.mark.asyncio
async def test_update_teacher_invalid_payload(
    app_with_mock_auth: FastAPI, # Uses fixture from conftest.py
    # No need for httpx_client fixture if we create it inside
):
    """Test updating teacher profile via PUT /me with an invalid payload (incorrect data types). Expect 422."""
    api_prefix = settings.API_V1_PREFIX
    put_url = f"{api_prefix}/teachers/me"

    # Payload with incorrect data types
    # TeacherUpdate expects: first_name: Optional[str], is_active: Optional[bool]
    invalid_payload = {
        "first_name": 12345,  # Incorrect: should be string
        "school_name": ["University", "of", "Testing"], # Incorrect: should be string
        "is_active": "maybe", # Incorrect: should be boolean
        "role": 77 # Incorrect: should be a valid TeacherRole enum or string representation
    }

    headers = {
        "Authorization": "Bearer dummytoken", # Token content is handled by app_with_mock_auth
        "Content-Type": "application/json"
    }

    # app_with_mock_auth already has the app instance with mocked authentication
    async with httpx.AsyncClient(transport=ASGITransport(app=app_with_mock_auth), base_url="http://testserver") as client:
        response = await client.put(put_url, headers=headers, json=invalid_payload)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, \
        f"Expected 422 Unprocessable Entity, got {response.status_code}. Response: {response.text}"

    # Optionally, inspect the response detail for more specific error messages
    response_data = response.json()
    assert "detail" in response_data
    # Example check for one of the fields, Pydantic error structure can be nested
    # This depends on how FastAPI formats Pydantic validation errors.
    # Often it's a list of error objects, each with 'loc', 'msg', 'type'.
    found_first_name_error = False
    found_school_name_error = False
    found_is_active_error = False
    found_role_error = False

    for error in response_data.get("detail", []):
        if isinstance(error, dict) and "loc" in error and isinstance(error["loc"], list):
            if len(error["loc"]) > 1:
                field_name = error["loc"][1]
                # Check for string_type error when an int is provided for first_name
                if field_name == "first_name" and error.get("type") == "string_type":
                    found_first_name_error = True
                # Check for string_type error when a list is provided for school_name
                if field_name == "school_name" and error.get("type") == "string_type":
                    found_school_name_error = True
                # Check for bool_parsing error when a string is provided for is_active
                if field_name == "is_active" and error.get("type") == "bool_parsing":
                    found_is_active_error = True
                # For enums, the error type might be 'enum', 'literal_error', or 'missing' if not properly cast
                if field_name == "role" and (
                    error.get("type") == "enum" or
                    error.get("type") == "literal_error" or
                    "Input should be a valid member of TeacherRole" in error.get("msg", "") # More specific message check
                ):
                     found_role_error = True


    assert found_first_name_error, "Validation error for 'first_name' (type 'string_type') not found in response."
    assert found_school_name_error, "Validation error for 'school_name' (type 'string_type') not found in response."
    assert found_is_active_error, "Validation error for 'is_active' (type 'bool_parsing') not found in response."
    assert found_role_error, "Validation error for 'role' (enum or literal type) not found in response." 

@pytest.mark.asyncio
async def test_put_me_create_missing_required_fields(
    app_with_mock_auth: FastAPI, # Original fixture from conftest
    mocker: MockerFixture
):
    """
    Test PUT /me (create path) when payload is missing required fields for profile creation.
    Expects 422 Unprocessable Entity.
    """
    api_prefix = settings.API_V1_PREFIX
    put_url = f"{api_prefix}/teachers/me"
    
    test_kinde_id = "test_create_missing_fields_kinde_id"
    test_email = "test_create_missing@example.com"

    # 1. Customize the get_current_user_payload for this test
    # The app_with_mock_auth fixture already applies an override.
    # We need to ensure *that* override returns an email for the creation path.
    # We can re-override it for this specific test's app instance.
    
    # Get the original override from the fixture to modify its return or re-mock.
    # The fixture in conftest.py sets up a default mock payload.
    # It's simpler to directly mock 'get_current_user_payload' for this app instance.
    
    custom_user_payload = {
        "sub": test_kinde_id,
        "iss": settings.KINDE_DOMAIN or "mock_issuer",
        "aud": [settings.KINDE_AUDIENCE] if settings.KINDE_AUDIENCE else ["mock_audience"],
        "exp": time.time() + 3600,
        "iat": time.time(),
        "roles": ["teacher"],
        "email": test_email # Crucial: email must be present for creation path
    }

    async def override_for_this_test() -> Dict[str, Any]:
        # This log helps confirm our specific override is being used.
        print(f"Dependency Override: Using override_for_this_test for get_current_user_payload, returning: {custom_user_payload}")
        return custom_user_payload

    # The dependency to override is imported as 'from app.core.security import get_current_user_payload'
    # in conftest.py, which should match the one used by FastAPI.
    # We get the actual function object from the app's dependency overrides if already set by app_with_mock_auth,
    # or directly from the app's main dependencies.
    # For simplicity and clarity, we directly target the app instance provided by the fixture.
    
    # Store original override to restore it later, though pytest handles fixture teardown.
    original_override = app_with_mock_auth.dependency_overrides.get(get_current_user_payload)
    app_with_mock_auth.dependency_overrides[get_current_user_payload] = override_for_this_test
    
    # 2. Mock crud.get_teacher_by_kinde_id to return None (triggering create path)
    # This needs to be patched where it's looked up: in the teachers endpoint module.
    mock_get_teacher = mocker.patch(
        'backend.app.api.v1.endpoints.teachers.crud.get_teacher_by_kinde_id',
        return_value=None
    )

    # 3. Construct a payload that is missing a required field for creation.
    # According to teachers.py, required_fields_for_create are:
    # ['first_name', 'last_name', 'school_name', 'role', 'country', 'state_county']
    # The TeacherUpdate model makes all fields optional, so FastAPI won't block this initially.
    # The endpoint's internal logic will catch the missing required fields for creation.
    
    payload_missing_first_name = {
        # "first_name": "Test", # Omitted
        "last_name": "UserCreateMissing",
        "school_name": "Creation Test School",
        "role": TeacherRole.TEACHER.value, # Send the string value
        "country": "Testland",
        "state_county": "Test State",
        "description": "Optional description" 
        # email is taken from token, not payload for creation
    }

    headers = {
        "Authorization": "Bearer dummytoken_for_create_missing_fields", # Token content itself isn't deeply validated due to override
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(transport=ASGITransport(app=app_with_mock_auth), base_url="http://testserver") as client:
        response = await client.put(put_url, headers=headers, json=payload_missing_first_name)

    # 4. Assertions
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, \
        f"Expected 422, got {response.status_code}. Response: {response.text}"

    response_data = response.json()
    assert "detail" in response_data
    
    # The endpoint should return a specific message about missing fields.
    # Based on teachers.py: detail=f"Missing required profile fields: {', '.join(missing_required)}"
    expected_detail_substring = "Missing required profile fields"
    actual_detail = ""
    if isinstance(response_data["detail"], str): # Endpoint returns string detail for this error
        actual_detail = response_data["detail"]
        assert expected_detail_substring in actual_detail, \
            f"Expected detail to contain '{expected_detail_substring}', got '{actual_detail}'"
        assert "first_name" in actual_detail, \
            f"Expected 'first_name' to be listed as missing, got '{actual_detail}'"
    elif isinstance(response_data["detail"], list): # Pydantic validation error format
         # This case shouldn't happen if the endpoint's custom missing field check is hit first
        pytest.fail(f"Expected string detail for missing fields, but got list (Pydantic error format): {response_data['detail']}")
    else:
        pytest.fail(f"Unexpected detail format: {response_data['detail']}")

    # Ensure get_teacher_by_kinde_id was called
    mock_get_teacher.assert_called_once_with(kinde_id=test_kinde_id)

    # Restore original dependency override if necessary (though pytest handles fixture scope)
    if original_override:
        app_with_mock_auth.dependency_overrides[get_current_user_payload] = original_override
    elif get_current_user_payload in app_with_mock_auth.dependency_overrides:
        del app_with_mock_auth.dependency_overrides[get_current_user_payload] 

@pytest.mark.asyncio
async def test_list_teachers_as_admin_success(
    app_with_mock_auth: FastAPI, # Original fixture from conftest
    mocker: MockerFixture
):
    """
    Test GET /teachers/ as an admin user, with and without pagination.
    Expects 200 OK and a list of teachers.
    """
    api_prefix = settings.API_V1_PREFIX
    get_url = f"{api_prefix}/teachers/"
    
    admin_kinde_id = "test_admin_kinde_id"
    admin_email = "admin@example.com"

    # 1. Customize get_current_user_payload for an admin user
    admin_user_payload = {
        "sub": admin_kinde_id,
        "iss": settings.KINDE_DOMAIN or "mock_issuer",
        "aud": [settings.KINDE_AUDIENCE] if settings.KINDE_AUDIENCE else ["mock_audience"],
        "exp": time.time() + 3600,
        "iat": time.time(),
        "roles": ["admin", "teacher"], # Simulate an admin role
        "email": admin_email
    }

    async def override_for_admin_test() -> Dict[str, Any]:
        print(f"Dependency Override: Using override_for_admin_test, payload: {admin_user_payload}")
        return admin_user_payload

    original_override = app_with_mock_auth.dependency_overrides.get(get_current_user_payload)
    app_with_mock_auth.dependency_overrides[get_current_user_payload] = override_for_admin_test

    # 2. Prepare mock teacher data and mock crud.get_all_teachers
    now = datetime.now(timezone.utc)
    mock_teachers_db = [
        Teacher(
            id="teacher_id_1", email="one@test.com", first_name="First", last_name="TeacherOne", 
            role=TeacherRole.TEACHER, created_at=now, updated_at=now, school_name="School A",
            country="Country A", state_county="State A"
        ),
        Teacher(
            id="teacher_id_2", email="two@test.com", first_name="Second", last_name="TeacherTwo", 
            role=TeacherRole.TEACHER, created_at=now, updated_at=now, school_name="School B",
            country="Country B", state_county="State B"
        ),
        Teacher(
            id="teacher_id_3", email="three@test.com", first_name="Third", last_name="TeacherThree", 
            role=TeacherRole.ADMIN, created_at=now, updated_at=now, school_name="School C",
            country="Country C", state_county="State C"
        )
    ]

    def mock_get_all_teachers_side_effect(skip: int, limit: int):
        print(f"mock_get_all_teachers_side_effect called with skip={skip}, limit={limit}")
        return mock_teachers_db[skip : skip + limit]

    mocked_crud_get_all = mocker.patch(
        'backend.app.api.v1.endpoints.teachers.crud.get_all_teachers',
        side_effect=mock_get_all_teachers_side_effect
    )

    headers = {
        "Authorization": "Bearer dummy_admin_token",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(transport=ASGITransport(app=app_with_mock_auth), base_url="http://testserver") as client:
        # Scenario 1: No pagination (defaults to skip=0, limit=100)
        print("Testing GET /teachers/ without pagination...")
        response_no_pagination = await client.get(get_url, headers=headers)
        
        assert response_no_pagination.status_code == status.HTTP_200_OK, \
            f"No pagination: Expected 200, got {response_no_pagination.status_code}. Resp: {response_no_pagination.text}"
        response_data_no_pagination = response_no_pagination.json()
        assert len(response_data_no_pagination) == len(mock_teachers_db)
        # Compare IDs to ensure correct objects were returned and serialized
        returned_ids_no_pagination = [t["_id"] for t in response_data_no_pagination]
        expected_ids_no_pagination = [t.id for t in mock_teachers_db]
        assert returned_ids_no_pagination == expected_ids_no_pagination, \
            "No pagination: Returned teacher list IDs do not match expected IDs."
        mocked_crud_get_all.assert_called_with(skip=0, limit=100) # Default query params

        # Scenario 2: With pagination (e.g., skip=1, limit=1)
        print("Testing GET /teachers/ with pagination (skip=1, limit=1)...")
        test_skip = 1
        test_limit = 1
        response_with_pagination = await client.get(f"{get_url}?skip={test_skip}&limit={test_limit}", headers=headers)
        
        assert response_with_pagination.status_code == status.HTTP_200_OK, \
            f"With pagination: Expected 200, got {response_with_pagination.status_code}. Resp: {response_with_pagination.text}"
        response_data_with_pagination = response_with_pagination.json()
        assert len(response_data_with_pagination) == test_limit
        # Compare IDs for the paginated result
        returned_ids_with_pagination = [t["_id"] for t in response_data_with_pagination]
        expected_ids_with_pagination = [mock_teachers_db[test_skip].id] # Sliced expectation
        assert returned_ids_with_pagination == expected_ids_with_pagination, \
            "With pagination: Returned teacher list IDs do not match expected sliced IDs."
        mocked_crud_get_all.assert_called_with(skip=test_skip, limit=test_limit)

    # Cleanup the dependency override
    if original_override:
        app_with_mock_auth.dependency_overrides[get_current_user_payload] = original_override
    elif get_current_user_payload in app_with_mock_auth.dependency_overrides:
        del app_with_mock_auth.dependency_overrides[get_current_user_payload] 

@pytest.mark.asyncio
async def test_list_teachers_as_non_admin_forbidden(
    app_with_mock_auth: FastAPI, # Original fixture from conftest
    mocker: MockerFixture
):
    """
    Test GET /teachers/ as a non-admin user.
    Expects 403 Forbidden, and crud.get_all_teachers should not be called.
    """
    api_prefix = settings.API_V1_PREFIX
    get_url = f"{api_prefix}/teachers/"
    
    non_admin_kinde_id = "test_non_admin_kinde_id"
    non_admin_email = "teacher_only@example.com"

    # 1. Customize get_current_user_payload for a non-admin user
    non_admin_user_payload = {
        "sub": non_admin_kinde_id,
        "iss": settings.KINDE_DOMAIN or "mock_issuer",
        "aud": [settings.KINDE_AUDIENCE] if settings.KINDE_AUDIENCE else ["mock_audience"],
        "exp": time.time() + 3600,
        "iat": time.time(),
        "roles": ["teacher"], # Simulate a non-admin role (only teacher)
        "email": non_admin_email
    }

    async def override_for_non_admin_test() -> Dict[str, Any]:
        print(f"Dependency Override: Using override_for_non_admin_test, payload: {non_admin_user_payload}")
        return non_admin_user_payload

    original_override = app_with_mock_auth.dependency_overrides.get(get_current_user_payload)
    app_with_mock_auth.dependency_overrides[get_current_user_payload] = override_for_non_admin_test

    # 2. Mock crud.get_all_teachers - we expect it NOT to be called
    mocked_crud_get_all = mocker.patch(
        'backend.app.api.v1.endpoints.teachers.crud.get_all_teachers',
        return_value=[] # Return an empty list if it were called, though it shouldn't be
    )

    headers = {
        "Authorization": "Bearer dummy_non_admin_token",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(transport=ASGITransport(app=app_with_mock_auth), base_url="http://testserver") as client:
        print("Testing GET /teachers/ as non-admin...")
        response = await client.get(get_url, headers=headers)
        
    # 3. Assertions
    # This assertion will fail if the endpoint doesn't have the admin check yet.
    assert response.status_code == status.HTTP_403_FORBIDDEN, \
        f"Expected 403 Forbidden for non-admin, got {response.status_code}. Response: {response.text}"
    
    # Ensure the CRUD function was not called due to failed authorization
    mocked_crud_get_all.assert_not_called()

    # Cleanup the dependency override
    if original_override:
        app_with_mock_auth.dependency_overrides[get_current_user_payload] = original_override
    elif get_current_user_payload in app_with_mock_auth.dependency_overrides:
        del app_with_mock_auth.dependency_overrides[get_current_user_payload] 

@pytest.mark.asyncio
async def test_get_teacher_by_id_as_admin_success(
    app_with_mock_auth: FastAPI,
    mocker: MockerFixture
):
    """
    Test GET /teachers/{teacher_id} as an admin user.
    Expects 200 OK and the specific teacher's data.
    This test assumes such an endpoint exists or will be created for admins.
    """
    api_prefix = settings.API_V1_PREFIX
    
    admin_kinde_id_requesting = "requesting_admin_kinde_id"
    target_teacher_kinde_id = "target_teacher_kinde_id_to_fetch"
    
    get_url = f"{api_prefix}/teachers/{target_teacher_kinde_id}"

    # 1. Customize get_current_user_payload for an admin user
    admin_user_payload = {
        "sub": admin_kinde_id_requesting,
        "iss": settings.KINDE_DOMAIN or "mock_issuer",
        "aud": [settings.KINDE_AUDIENCE] if settings.KINDE_AUDIENCE else ["mock_audience"],
        "exp": time.time() + 3600,
        "iat": time.time(),
        "roles": ["admin", "teacher"], # Admin making the request
        "email": "admin_fetcher@example.com"
    }

    async def override_for_admin_fetch_test() -> Dict[str, Any]:
        return admin_user_payload

    original_override = app_with_mock_auth.dependency_overrides.get(get_current_user_payload)
    app_with_mock_auth.dependency_overrides[get_current_user_payload] = override_for_admin_fetch_test

    # 2. Prepare mock data for the target teacher and mock crud.get_teacher_by_kinde_id
    now = datetime.now(timezone.utc)
    target_teacher_data = Teacher(
        kinde_id=target_teacher_kinde_id, # This is the Kinde ID, mapped to _id in DB model
        email="target_teacher@example.com",
        first_name="Target",
        last_name="Teacher",
        role=TeacherRole.LECTURER,
        school_name="Target University",
        country="Targetland",
        state_county="Target State",
        is_active=True,
        is_administrator=False,
        created_at=now,
        updated_at=now
    )

    mocked_crud_get_by_kinde_id = mocker.patch(
        'backend.app.api.v1.endpoints.teachers.crud.get_teacher_by_kinde_id',
        return_value=target_teacher_data
    )

    headers = {
        "Authorization": "Bearer dummy_admin_token_for_fetch",
    }

    async with httpx.AsyncClient(transport=ASGITransport(app=app_with_mock_auth), base_url="http://testserver") as client:
        response = await client.get(get_url, headers=headers)
        
    # 3. Assertions
    # This will likely fail with 404 if the endpoint GET /teachers/{teacher_id} doesn't exist yet.
    assert response.status_code == status.HTTP_200_OK, \
        f"Expected 200 OK, got {response.status_code}. Response: {response.text}"
    
    response_data = response.json()
    assert response_data["_id"] == target_teacher_data.id
    assert response_data["email"] == target_teacher_data.email
    assert response_data["first_name"] == target_teacher_data.first_name
    assert response_data["role"] == target_teacher_data.role

    # Ensure the correct CRUD function was called with the target teacher's ID
    mocked_crud_get_by_kinde_id.assert_called_once_with(kinde_id=target_teacher_kinde_id)

    # Cleanup the dependency override
    if original_override:
        app_with_mock_auth.dependency_overrides[get_current_user_payload] = original_override
    elif get_current_user_payload in app_with_mock_auth.dependency_overrides:
        del app_with_mock_auth.dependency_overrides[get_current_user_payload] 

@pytest.mark.asyncio
async def test_get_teacher_by_id_as_admin_not_found(
    app_with_mock_auth: FastAPI,
    mocker: MockerFixture
):
    """
    Test GET /teachers/{teacher_id} as an admin user when teacher ID does not exist.
    Expects 404 Not Found.
    """
    api_prefix = settings.API_V1_PREFIX
    
    admin_kinde_id_requesting = "requesting_admin_for_not_found_test"
    non_existent_teacher_kinde_id = "non_existent_teacher_kinde_id"
    
    get_url = f"{api_prefix}/teachers/{non_existent_teacher_kinde_id}"

    # 1. Customize get_current_user_payload for an admin user
    admin_user_payload = {
        "sub": admin_kinde_id_requesting,
        "iss": settings.KINDE_DOMAIN or "mock_issuer",
        "aud": [settings.KINDE_AUDIENCE] if settings.KINDE_AUDIENCE else ["mock_audience"],
        "exp": time.time() + 3600,
        "iat": time.time(),
        "roles": ["admin", "teacher"], # Admin making the request
        "email": "admin_fetcher_not_found@example.com"
    }

    async def override_for_admin_not_found_test() -> Dict[str, Any]:
        return admin_user_payload

    original_override = app_with_mock_auth.dependency_overrides.get(get_current_user_payload)
    app_with_mock_auth.dependency_overrides[get_current_user_payload] = override_for_admin_not_found_test

    # 2. Mock crud.get_teacher_by_kinde_id to return None
    mocked_crud_get_by_kinde_id = mocker.patch(
        'backend.app.api.v1.endpoints.teachers.crud.get_teacher_by_kinde_id',
        return_value=None # Simulate teacher not found
    )

    headers = {
        "Authorization": "Bearer dummy_admin_token_for_not_found",
    }

    async with httpx.AsyncClient(transport=ASGITransport(app=app_with_mock_auth), base_url="http://testserver") as client:
        response = await client.get(get_url, headers=headers)
        
    # 3. Assertions
    assert response.status_code == status.HTTP_404_NOT_FOUND, \
        f"Expected 404 Not Found, got {response.status_code}. Response: {response.text}"
    
    response_data = response.json()
    assert "detail" in response_data
    # Updated assertion to match the actual, more specific message from the endpoint:
    expected_detail_message = f"Teacher profile not found for Kinde ID: {non_existent_teacher_kinde_id}"
    assert response_data["detail"] == expected_detail_message, \
        f"Expected detail message '{expected_detail_message}', got '{response_data['detail']}'"

    # Ensure the correct CRUD function was called with the target teacher's ID
    mocked_crud_get_by_kinde_id.assert_called_once_with(kinde_id=non_existent_teacher_kinde_id)

    # Cleanup the dependency override
    if original_override:
        app_with_mock_auth.dependency_overrides[get_current_user_payload] = original_override
    elif get_current_user_payload in app_with_mock_auth.dependency_overrides:
        del app_with_mock_auth.dependency_overrides[get_current_user_payload] 

@pytest.mark.asyncio
async def test_get_teacher_by_id_as_non_admin_forbidden(
    app_with_mock_auth: FastAPI,
    mocker: MockerFixture
):
    """
    Test GET /teachers/{teacher_id} as a non-admin user trying to access another's profile.
    Expects 403 Forbidden.
    """
    api_prefix = settings.API_V1_PREFIX
    
    requesting_non_admin_kinde_id = "requesting_non_admin_kinde_id"
    target_teacher_kinde_id = "other_teacher_kinde_id_forbidden" # ID of the profile they try to access
    
    get_url = f"{api_prefix}/teachers/{target_teacher_kinde_id}"

    # 1. Customize get_current_user_payload for a non-admin user
    non_admin_user_payload = {
        "sub": requesting_non_admin_kinde_id, # The ID of the user making the request
        "iss": settings.KINDE_DOMAIN or "mock_issuer",
        "aud": [settings.KINDE_AUDIENCE] if settings.KINDE_AUDIENCE else ["mock_audience"],
        "exp": time.time() + 3600,
        "iat": time.time(),
        "roles": ["teacher"], # Non-admin role
        "email": "non_admin_fetcher@example.com"
    }

    async def override_for_non_admin_fetch_test() -> Dict[str, Any]:
        print(f"Dependency Override: Using override_for_non_admin_fetch_test for {inspect.currentframe().f_code.co_name}")
        return non_admin_user_payload

    original_override = app_with_mock_auth.dependency_overrides.get(get_current_user_payload)
    app_with_mock_auth.dependency_overrides[get_current_user_payload] = override_for_non_admin_fetch_test

    # 2. Mock crud.get_teacher_by_kinde_id - we expect it NOT to be called
    # This mock is essential to verify that the request is blocked before DB access.
    mocked_crud_get_by_kinde_id = mocker.patch(
        'backend.app.api.v1.endpoints.teachers.crud.get_teacher_by_kinde_id',
        # Return a dummy teacher if it were called, though it shouldn't be
        return_value=Teacher(kinde_id=target_teacher_kinde_id, email="dummy@example.com", first_name="Dummy", last_name="User")
    )

    headers = {
        "Authorization": "Bearer dummy_non_admin_token_for_fetch_other",
    }

    async with httpx.AsyncClient(transport=ASGITransport(app=app_with_mock_auth), base_url="http://testserver") as client:
        print(f"Requesting URL: {get_url} as non-admin {requesting_non_admin_kinde_id}")
        response = await client.get(get_url, headers=headers)
        
    # 3. Assertions
    # This assertion assumes the endpoint GET /teachers/{teacher_id} has admin-only access control
    # or specific logic to prevent non-admins from fetching arbitrary profiles.
    assert response.status_code == status.HTTP_403_FORBIDDEN, \
        f"Expected 403 Forbidden, got {response.status_code}. Response: {response.text}"
    
    response_data = response.json()
    assert "detail" in response_data
    # The exact detail message might vary based on implementation.
    # e.g., "Not authorized to access this resource" or "User does not have required permissions."
    # For now, we check it contains "Forbidden" or "Not authorized" or "permission"
    detail_text = response_data["detail"].lower()
    assert "forbidden" in detail_text or "not authorized" in detail_text or "permission" in detail_text or "not have the necessary permissions" in detail_text, \
        f"Unexpected detail message: {response_data['detail']}"


    # Ensure the CRUD function was NOT called because authorization should fail first
    mocked_crud_get_by_kinde_id.assert_not_called()

    # Cleanup the dependency override
    if original_override:
        app_with_mock_auth.dependency_overrides[get_current_user_payload] = original_override
    elif get_current_user_payload in app_with_mock_auth.dependency_overrides:
        del app_with_mock_auth.dependency_overrides[get_current_user_payload] 

@pytest.mark.asyncio
async def test_update_teacher_by_id_as_admin_success(
    app_with_mock_auth: FastAPI,
    mocker: MockerFixture
):
    """
    Test PUT /teachers/{teacher_id} as an admin user successfully updating another teacher.
    Expects 200 OK.
    """
    api_prefix = settings.API_V1_PREFIX
    
    admin_kinde_id_requesting = "requesting_admin_for_update_kinde_id"
    target_teacher_kinde_id = "teacher_to_be_updated_by_admin_kinde_id"
    
    put_url = f"{api_prefix}/teachers/{target_teacher_kinde_id}"

    # 1. Customize get_current_user_payload for an admin user
    admin_user_payload = {
        "sub": admin_kinde_id_requesting,
        "iss": settings.KINDE_DOMAIN or "mock_issuer",
        "aud": [settings.KINDE_AUDIENCE] if settings.KINDE_AUDIENCE else ["mock_audience"],
        "exp": time.time() + 3600,
        "iat": time.time(),
        "roles": ["admin", "teacher"], # Admin making the request
        "email": "admin_updater@example.com"
    }

    async def override_for_admin_update_test() -> Dict[str, Any]:
        print(f"Dependency Override: Using override_for_admin_update_test for {inspect.currentframe().f_code.co_name}")
        return admin_user_payload

    original_override = app_with_mock_auth.dependency_overrides.get(get_current_user_payload)
    app_with_mock_auth.dependency_overrides[get_current_user_payload] = override_for_admin_update_test

    # 2. Simulate the existing teacher data in the DB (before update)
    now = datetime.now(timezone.utc)
    existing_teacher_in_db = Teacher(
        kinde_id=target_teacher_kinde_id, # ADD THIS
        email=f"target_before_update.{int(time.time())}@example.com",
        first_name="TargetFirstNameInitial",
        last_name="TargetLastNameInitial",
        school_name="Initial Target School",
        country="Targetland",
        state_county="Target State Initial",
        role=TeacherRole.TEACHER,
        is_active=True,
        is_administrator=False,
        created_at=now - timedelta(days=5),
        updated_at=now - timedelta(days=1)
    )
    # Mock get_teacher_by_kinde_id used by the endpoint to fetch the teacher to update
    # This is important if the endpoint first fetches the teacher before updating.
    mocker.patch(
        'backend.app.api.v1.endpoints.teachers.crud.get_teacher_by_kinde_id',
        return_value=existing_teacher_in_db
    )

    # 3. Define the update payload
    update_payload_by_admin = {
        "first_name": "TargetFirstNameUPDATED",
        "last_name": "TargetLastNameUPDATED",
        "school_name": "Updated Target School Name by Admin",
        "is_active": False, # Example of admin changing activation status
        "role": TeacherRole.LECTURER.value # Example of admin changing role
    }

    # 4. Simulate the teacher object *after* the update
    # Create a dictionary from the existing teacher, update it, then instantiate the model
    updated_data_dict = existing_teacher_in_db.model_dump()
    updated_data_dict.update(update_payload_by_admin) # Apply the admin's updates
    # Ensure 'updated_at' is fresh and 'id' remains consistent
    updated_data_dict['updated_at'] = datetime.now(timezone.utc) 
    updated_data_dict['id'] = target_teacher_kinde_id 

    # Role needs to be actual enum member for Teacher model instantiation
    if 'role' in updated_data_dict and isinstance(updated_data_dict['role'], str):
        updated_data_dict['role'] = TeacherRole(updated_data_dict['role'])
        
    updated_teacher_from_db = Teacher(**updated_data_dict)

    # 5. Mock the actual update operation in CRUD
    # This assumes your endpoint PUT /teachers/{teacher_id} calls crud.update_teacher
    # or a similar function like crud.admin_update_teacher_by_kinde_id.
    # Adjust the patch target if your CRUD function for admin updates by ID is different.
    mock_crud_update_teacher = mocker.patch(
        # Assuming 'update_teacher' can handle updates by a specified kinde_id when called by an admin
        # If there's a specific admin update function, patch that instead.
        'backend.app.api.v1.endpoints.teachers.crud.update_teacher', 
        return_value=updated_teacher_from_db
    )

    headers = {
        "Authorization": "Bearer dummy_admin_token_for_update",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(transport=ASGITransport(app=app_with_mock_auth), base_url="http://testserver") as client:
        print(f"Admin {admin_kinde_id_requesting} updating teacher {target_teacher_kinde_id} at URL: {put_url}")
        response = await client.put(put_url, headers=headers, json=update_payload_by_admin)
        
    # 6. Assertions
    assert response.status_code == status.HTTP_200_OK, \
        f"Expected 200 OK, got {response.status_code}. Response: {response.text}"
    
    response_data = response.json()
    assert response_data["_id"] == target_teacher_kinde_id
    assert response_data["first_name"] == update_payload_by_admin["first_name"]
    assert response_data["last_name"] == update_payload_by_admin["last_name"]
    assert response_data["school_name"] == update_payload_by_admin["school_name"]
    assert response_data["is_active"] == update_payload_by_admin["is_active"]
    assert response_data["role"] == update_payload_by_admin["role"] # Ensure role is compared as string if payload was string
    
    # Verify that non-updated fields from the original object (like email) are preserved
    assert response_data["email"] == existing_teacher_in_db.email 

    # Ensure the update CRUD function was called correctly
    # The arguments to update_teacher might be (db, kinde_id, update_data_model)
    # or (db, existing_teacher_obj, update_data_model).
    # For this test, we'll check it was called, and if specific args are needed, they can be added.
    # The key thing is it's called with the target_teacher_kinde_id and the new data.
    # We check the call based on what the endpoint *sends* to the crud function.
    # The endpoint `PUT /teachers/{teacher_id}` (admin) likely passes the `teacher_id` (kinde_id)
    # and a Pydantic model of the update data (`TeacherAdminUpdate` or `TeacherUpdate`).
    
    # We need to ensure the `update_payload_by_admin` is correctly transformed into the expected Pydantic model
    # by the endpoint before being passed to `crud.update_teacher`.
    # For simplicity, we check the `kinde_id` and that the first argument to the mock (after db) has compatible data.
    
    # Check that the mock was called. The exact arguments depend on crud.update_teacher's signature
    # and how the endpoint prepares the call.
    # If crud.update_teacher expects (db_session, kinde_id_to_update, data_to_update_model):
    mock_crud_update_teacher.assert_called_once()
    # mock.call_args is a tuple: (positional_args, keyword_args)
    # crud.update_teacher is called from the endpoint with keyword arguments:
    # await crud.update_teacher(kinde_id=..., teacher_in=...)
    called_positional_args, called_keyword_args = mock_crud_update_teacher.call_args
    
    # Assert based on keyword arguments
    assert called_keyword_args['kinde_id'] == target_teacher_kinde_id
    
    update_data_arg = called_keyword_args['teacher_in']
    # Convert payload to a dict, handling potential enum values for comparison if necessary
    # The endpoint would create a Pydantic model (e.g., TeacherAdminUpdate(**update_payload_by_admin))
    # We are checking that the data within that model matches our payload.
    assert update_data_arg.first_name == update_payload_by_admin["first_name"]
    assert update_data_arg.school_name == update_payload_by_admin["school_name"]
    assert update_data_arg.is_active == update_payload_by_admin["is_active"]
    assert update_data_arg.role == TeacherRole(update_payload_by_admin["role"]) # Compare with Enum if model has Enum

    # Cleanup the dependency override
    if original_override:
        app_with_mock_auth.dependency_overrides[get_current_user_payload] = original_override
    elif get_current_user_payload in app_with_mock_auth.dependency_overrides:
        del app_with_mock_auth.dependency_overrides[get_current_user_payload] 

@pytest.mark.asyncio
async def test_delete_teacher_by_id_as_admin_success(
    app_with_mock_auth: FastAPI,
    mocker: MockerFixture
):
    """
    Test DELETE /teachers/{teacher_id} as an admin user successfully deleting another teacher.
    Expects 204 No Content.
    """
    api_prefix = settings.API_V1_PREFIX
    
    admin_kinde_id_requesting = "requesting_admin_for_delete_kinde_id"
    target_teacher_kinde_id_to_delete = "teacher_to_be_deleted_by_admin_kinde_id"
    
    delete_url = f"{api_prefix}/teachers/{target_teacher_kinde_id_to_delete}"

    # 1. Customize get_current_user_payload for an admin user
    admin_user_payload = {
        "sub": admin_kinde_id_requesting,
        "iss": settings.KINDE_DOMAIN or "mock_issuer",
        "aud": [settings.KINDE_AUDIENCE] if settings.KINDE_AUDIENCE else ["mock_audience"],
        "exp": time.time() + 3600,
        "iat": time.time(),
        "roles": ["admin", "teacher"], # Admin making the request
        "email": "admin_deleter@example.com"
    }

    async def override_for_admin_delete_test() -> Dict[str, Any]:
        print(f"Dependency Override: Using override_for_admin_delete_test for {inspect.currentframe().f_code.co_name}")
        return admin_user_payload

    original_override = app_with_mock_auth.dependency_overrides.get(get_current_user_payload)
    app_with_mock_auth.dependency_overrides[get_current_user_payload] = override_for_admin_delete_test

    # 2. Mock crud.delete_teacher to indicate success
    # This assumes your endpoint DELETE /teachers/{teacher_id} calls crud.delete_teacher
    # and that crud.delete_teacher returns something truthy on success for this type of delete.
    # The actual endpoint might check if the teacher exists first, then delete.
    # For this test, we focus on the admin being able to *trigger* the delete for an ID.
    
    # Mock get_teacher_by_kinde_id to simulate the teacher exists before deletion
    # (Many DELETE endpoints check for existence first and return 404 if not found)
    mock_existing_teacher = Teacher(
        kinde_id=target_teacher_kinde_id_to_delete,
        email="delete_target@example.com",
        first_name="TargetDelete",
        last_name="User"
    )
    mocker.patch(
        'backend.app.api.v1.endpoints.teachers.crud.get_teacher_by_kinde_id',
        return_value=mock_existing_teacher
    )

    # Mock the actual delete operation in CRUD to return True (or a count > 0)
    mock_crud_delete_teacher = mocker.patch(
        'backend.app.api.v1.endpoints.teachers.crud.delete_teacher',
        return_value=True # Simulate successful deletion in CRUD layer
    )

    headers = {
        "Authorization": "Bearer dummy_admin_token",
    }

    async with httpx.AsyncClient(transport=ASGITransport(app=app_with_mock_auth), base_url="http://testserver") as client:
        print(f"Admin {admin_kinde_id_requesting} deleting teacher {target_teacher_kinde_id_to_delete} at URL: {delete_url}")
        response = await client.delete(delete_url, headers=headers)
        
    # 3. Assertions
    assert response.status_code == status.HTTP_204_NO_CONTENT, \
        f"Expected 204 No Content, got {response.status_code}. Response: {response.text}"
    
    # Ensure the delete CRUD function was called correctly with the target Kinde ID
    mock_crud_delete_teacher.assert_called_once_with(kinde_id=target_teacher_kinde_id_to_delete)

    # Cleanup the dependency override
    if original_override:
        app_with_mock_auth.dependency_overrides[get_current_user_payload] = original_override
    elif get_current_user_payload in app_with_mock_auth.dependency_overrides:
        del app_with_mock_auth.dependency_overrides[get_current_user_payload] 

# Placeholder Kinde ID for unauthorized access tests in path parameters
UNAUTHORIZED_ACCESS_PLACEHOLDER_KINDE_ID = "unauthorized_access_test_id"

# Configuration for protected endpoints: (method, url_suffix, needs_kinde_id_in_path, request_body_if_needed)
# url_suffix is appended to settings.API_V1_PREFIX + "/teachers"
protected_endpoints_config = [
    ("GET", "/me", False, None),
    ("GET", f"/{{kinde_id}}", True, None), # Dynamically format kinde_id placeholder
    ("PUT", "/me", False, {"first_name": "TestUpdateJWTFail"}), # Body for TeacherUpdate
    ("PUT", f"/{{kinde_id}}", True, {"first_name": "TestAdminUpdateJWTFail"}), # Body for TeacherUpdate
    # For POST, TeacherCreate requires: first_name, last_name, email, school_name, role, country, state_county
    ("POST", "/", False, {
        "first_name": "JwtFailTest", "last_name": "User", "email": "jwt.fail.test@example.com",
        "school_name": "AuthFail School", "role": "teacher", "country": "Testlandia", "state_county": "TF"
    }),
    ("GET", "/", False, None), # List teachers
    ("DELETE", "/me", False, None),
    ("DELETE", f"/{{kinde_id}}", True, None)
]

@pytest.mark.asyncio
@pytest.mark.parametrize("method, url_suffix, needs_kinde_id, body", protected_endpoints_config)
async def test_protected_endpoints_unauthorized_access(
    managed_fastapi_app: FastAPI, # Standard app fixture, not app_with_mock_auth
    mocker: MockerFixture,
    method: str,
    url_suffix: str,
    needs_kinde_id: bool,
    body: Optional[Dict[str, Any]]
):
    """
    Tests protected teacher endpoints for unauthorized access (401).
    Scenario 1: No token provided.
    Scenario 2: Invalid/Expired token (simulated by mocking validate_token).
    """
    api_prefix = settings.API_V1_PREFIX
    base_url_path = f"{api_prefix}/teachers"
    
    formatted_url_suffix = url_suffix
    if needs_kinde_id:
        formatted_url_suffix = url_suffix.format(kinde_id=UNAUTHORIZED_ACCESS_PLACEHOLDER_KINDE_ID)
    
    full_url = f"{base_url_path}{formatted_url_suffix}"

    # --- Scenario 1: No token ---
    async with AsyncClient(transport=ASGITransport(app=managed_fastapi_app), base_url="http://testserver") as client:
        response_no_token = None
        if method == "GET":
            response_no_token = await client.get(full_url)
        elif method == "POST":
            response_no_token = await client.post(full_url, json=body)
        elif method == "PUT":
            response_no_token = await client.put(full_url, json=body)
        elif method == "DELETE":
            response_no_token = await client.delete(full_url)
        else:
            pytest.fail(f"Unsupported HTTP method: {method}")

        assert response_no_token.status_code == status.HTTP_401_UNAUTHORIZED, (
            f"No Token: Expected 401 for {method} {full_url}, "
            f"got {response_no_token.status_code}. Response: {response_no_token.text}"
        )
        # FastAPI typically returns a detail for 401 from Depends(Security(...))
        # The exact detail might come from `validate_token` if it catches and re-raises.
        response_data_no_token = response_no_token.json()
        assert "detail" in response_data_no_token, "No Token: Detail missing in 401 response"
        # Example check: Kinde's validate_token often includes "credentials" or "token" in the message
        # This part is less critical than the status code itself.
        # assert "token" in response_data_no_token["detail"].lower() or \
        #        "credentials" in response_data_no_token["detail"].lower() or \
        #        "not authenticated" in response_data_no_token["detail"].lower()


    # --- Scenario 2: Invalid/Expired token (mock validate_token to raise 401) ---
    # We mock validate_token because get_current_user_payload (the dependency) calls it.
    # By mocking validate_token to raise 401, we simulate any JWT validation failure.
    mock_validate_token = mocker.patch(
        'app.core.security.validate_token', # Path to where validate_token is imported/used by get_current_user_payload
        side_effect=HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Simulated invalid/expired token" # Specific detail from our mock
        )
    )
    
    headers_with_bad_token = {"Authorization": "Bearer a_token_that_will_be_mocked_as_invalid"}
    
    async with AsyncClient(transport=ASGITransport(app=managed_fastapi_app), base_url="http://testserver") as client:
        response_invalid_token = None
        if method == "GET":
            response_invalid_token = await client.get(full_url, headers=headers_with_bad_token)
        elif method == "POST":
            response_invalid_token = await client.post(full_url, json=body, headers=headers_with_bad_token)
        elif method == "PUT":
            response_invalid_token = await client.put(full_url, json=body, headers=headers_with_bad_token)
        elif method == "DELETE":
            response_invalid_token = await client.delete(full_url, headers=headers_with_bad_token)
        else:
            pytest.fail(f"Unsupported HTTP method: {method}")

        assert response_invalid_token.status_code == status.HTTP_401_UNAUTHORIZED, (
            f"Invalid Token: Expected 401 for {method} {full_url}, "
            f"got {response_invalid_token.status_code}. Response: {response_invalid_token.text}"
        )
        
        response_data_invalid_token = response_invalid_token.json()
        assert response_data_invalid_token.get("detail") == "Simulated invalid/expired token", (
            "Invalid Token: Detail message did not match mock's message."
        )

    # Ensure mock was called (it should be, as dependency is evaluated)
    mock_validate_token.assert_called()
    # It's good practice to reset/clear mocks if they might affect other tests,
    # though pytest's fixture scoping usually handles this.
    # mocker.stopall() or mock_validate_token.reset_mock() could be used if issues arise.

# --- Test for Missing Claims in Otherwise Valid Token ---

# Configuration for missing claims tests:
# (method_type, url_suffix, request_body, mock_token_payload, expected_status, expected_detail_substring)
# method_type: "GET", "POST", "PUT_UPDATE", "PUT_CREATE", "DELETE"
# PUT_UPDATE assumes user exists. PUT_CREATE assumes user does not exist (triggers create path).
missing_claims_config = [
    # --- Scenarios for Missing 'sub' claim ---
    ("GET", "/me", None, {"email": "subless@example.com", "roles": ["teacher"]}, status.HTTP_400_BAD_REQUEST, "User identifier missing from token"),
    
    # PUT /me (update path) - missing 'sub'
    ("PUT_UPDATE", "/me", {"first_name": "Subless Update"}, {"email": "subless.update@example.com", "roles": ["teacher"]}, status.HTTP_400_BAD_REQUEST, "User identifier missing from token"),
    
    # POST / - missing 'sub' from token (kinde_id comes from token's sub)
    ("POST", "/", {
        "first_name": "SublessPost", "last_name": "User", "email": "subless.post.body@example.com", # email in body
        "school_name": "Subless School", "role": "teacher", "country": "US", "state_county": "CA"
    }, {"email": "subless.post.token@example.com", "roles": ["teacher"]}, status.HTTP_400_BAD_REQUEST, "User identifier missing from token"),
    
    ("DELETE", "/me", None, {"email": "subless.delete@example.com", "roles": ["teacher"]}, status.HTTP_400_BAD_REQUEST, "User identifier missing from token"),

    # PUT /me (create path) - missing 'sub' from token
    ("PUT_CREATE", "/me", { # Body for create
        "first_name": "SublessCreate", "last_name": "User", "school_name": "Create School", 
        "role": "teacher", "country": "US", "state_county": "CA"
    }, {"email": "subless.create.token@example.com", "roles": ["teacher"]}, status.HTTP_400_BAD_REQUEST, "User identifier missing from token"),

    # --- Scenario for PUT /me (create path) - 'sub' present, but missing 'email' in token ---
    ("PUT_CREATE", "/me", { # Body for create
        "first_name": "EmaillessCreate", "last_name": "User", "school_name": "Create School NoEmail", 
        "role": "teacher", "country": "US", "state_county": "CA"
    }, {"sub": "user_for_create_no_email", "roles": ["teacher"]}, status.HTTP_400_BAD_REQUEST, "Email missing from authentication token")
]

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_type, url_suffix, request_body, mock_token_payload, expected_status, expected_detail_substring",
    missing_claims_config
)
async def test_protected_endpoints_missing_claims(
    managed_fastapi_app: FastAPI,
    mocker: MockerFixture,
    method_type: str,
    url_suffix: str,
    request_body: Optional[Dict[str, Any]],
    mock_token_payload: Dict[str, Any],
    expected_status: int,
    expected_detail_substring: str
):
    """
    Tests protected endpoints with tokens that are 'valid' but missing crucial claims.
    - Mocks validate_token to return a payload missing 'sub' or 'email'.
    - For PUT_CREATE/PUT_UPDATE, mocks crud.get_teacher_by_kinde_id appropriately.
    """
    api_prefix = settings.API_V1_PREFIX
    full_url = f"{api_prefix}/teachers{url_suffix}"

    # Mock app.core.security.validate_token to return the deficient payload
    # This mock will be active for the duration of this specific test case.
    mocker.patch('app.core.security.validate_token', return_value=mock_token_payload)

    # --- Setup for specific PUT method types ---
    mock_get_teacher = None
    if method_type == "PUT_UPDATE":
        method = "PUT"
        # Ensure 'sub' is in the mock_token_payload for the mock_existing_teacher to have an ID
        # If 'sub' is what's missing, this path might not be hit as expected, but the test is for missing 'sub'.
        # The endpoint will fail before trying to fetch if 'sub' is missing from token.
        # If 'sub' IS present in token (e.g. testing missing email on update), this mock is relevant.
        existing_teacher_id = mock_token_payload.get("sub", f"dummy_id_for_put_update_{uuid.uuid4()}")
        # Corrected: Provide all required fields for Teacher model
        mock_existing_teacher = Teacher(
            kinde_id=existing_teacher_id, # ADD THIS - kinde_id is the string ID
            email="exists@example.com",
            first_name="ExistsFirstName",
            last_name="ExistsLastName", # Added missing last_name
            school_name="Existing School", # Added
            country="Existing Country", # Added
            state_county="Existing State", # Added
            role=TeacherRole.TEACHER, # Added
            is_active=True, # Added
            is_administrator=False, # Added
            created_at=datetime.now(timezone.utc), # Added
            updated_at=datetime.now(timezone.utc) # Added
        )
        mock_get_teacher = mocker.patch('backend.app.api.v1.endpoints.teachers.crud.get_teacher_by_kinde_id', return_value=mock_existing_teacher)
    elif method_type == "PUT_CREATE":
        method = "PUT"
        mock_get_teacher = mocker.patch('backend.app.api.v1.endpoints.teachers.crud.get_teacher_by_kinde_id', return_value=None)
    else:
        method = method_type

    headers = {"Authorization": "Bearer a_valid_token_format_wise_but_deficient_payload"}

    async with AsyncClient(transport=ASGITransport(app=managed_fastapi_app), base_url="http://testserver") as client:
        response = None
        if method == "GET":
            response = await client.get(full_url, headers=headers)
        elif method == "POST":
            response = await client.post(full_url, json=request_body, headers=headers)
        elif method == "PUT":
            response = await client.put(full_url, json=request_body, headers=headers)
        elif method == "DELETE":
            response = await client.delete(full_url, headers=headers)
        else:
            pytest.fail(f"Unsupported HTTP method_type in test config: {method_type}")

        assert response.status_code == expected_status, (
            f"Expected {expected_status} for {method} {full_url} with payload {mock_token_payload}, "
            f"got {response.status_code}. Response: {response.text}"
        )
        
        response_data = response.json()
        assert "detail" in response_data, f"Detail missing in response for {method} {full_url}. Response: {response.text}"
        assert expected_detail_substring in response_data["detail"], (
            f"Expected detail '{expected_detail_substring}' not found in '{response_data['detail']}' "
            f"for {method} {full_url}. Payload: {mock_token_payload}"
        )

    if mock_get_teacher:
        # Assert that get_teacher_by_kinde_id was called if it was mocked (i.e., for PUT scenarios)
        # It should be called with the 'sub' from the token IF 'sub' was present in the token.
        # If 'sub' was missing, the endpoint should fail before calling this.
        if "sub" in mock_token_payload: # Only expect call if sub was available to be used as kinde_id
             mock_get_teacher.assert_called_once_with(kinde_id=mock_token_payload["sub"])
        else: # If 'sub' was missing in token, endpoint should fail before this CRUD call
            mock_get_teacher.assert_not_called()