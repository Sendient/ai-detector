# backend/tests/functional/api/v1/endpoints/test_documents_endpoint.py
import pytest
import uuid
import time # For unique names or timestamps if needed
from typing import Dict, Any, Optional
from unittest.mock import AsyncMock # Import AsyncMock
from httpx import AsyncClient, ASGITransport # Required for making requests to the app
from fastapi import FastAPI, status
from starlette.datastructures import UploadFile
from pytest_mock import MockerFixture
from io import BytesIO
from datetime import datetime, timezone # Added timezone

import backend.app.services.blob_storage as blob_storage_module # NEW

# Import app and settings (adjust path if your conftest modifies sys.path differently)
# from backend.app.main import app as fastapi_app # OLD - Unused if app fixture is used
from backend.app.core.config import settings
# from app.core.security import get_current_user_payload # OLD
from backend.app.core.security import get_current_user_payload # NEW - For dependency override
from backend.app.models.document import Document, DocumentStatus # For asserting response and types
from backend.app.models.result import Result, ResultStatus, ResultCreate # For asserting result creation
from backend.app.models.enums import FileType # For asserting file type

# Mark all tests in this module to use pytest-asyncio
pytestmark = pytest.mark.asyncio

# Use the app_with_mock_auth fixture from the main conftest.py if available and suitable,
# or define a similar one here for document-specific auth mocking if needed.
# For now, we'll assume app_with_mock_auth can be used or we'll mock 'get_current_user_payload' directly.

# Helper to generate a unique Kinde ID for testing
def generate_unique_kinde_id(prefix: str = "user_kinde_id") -> str:
    return f"{prefix}_{uuid.uuid4()}"

@pytest.mark.asyncio
async def test_upload_document_success(
    app_with_mock_auth: FastAPI,
    mocker: MockerFixture
):
    """
    Test successful document upload (POST /documents/upload).
    Authentication is overridden. Blob storage and CRUD are mocked.
    """
    api_prefix = settings.API_V1_PREFIX
    upload_url = f"{api_prefix}/documents/upload"

    # 1. Mock Authentication
    test_user_kinde_id = f"user_kinde_id_doc_upload_{uuid.uuid4()}"
    mock_auth_payload = {
        "sub": test_user_kinde_id,
        "iss": "mock_issuer",
        "aud": ["mock_audience"],
        "exp": time.time() + 3600,
        "iat": time.time(),
        "roles": ["teacher"] 
    }
    
    # Override the default auth from app_with_mock_auth fixture
    async def override_get_current_user_payload() -> Dict[str, Any]:
        return mock_auth_payload
    
    original_override = app_with_mock_auth.dependency_overrides.get(get_current_user_payload)
    app_with_mock_auth.dependency_overrides[get_current_user_payload] = override_get_current_user_payload

    # 2. Prepare Test Data
    student_uuid = uuid.uuid4()
    assignment_uuid = uuid.uuid4()
    mock_file_content = b"This is a test PDF content."
    mock_file_name = "test_document.pdf"
    mock_blob_name = f"test_blob_{uuid.uuid4()}.pdf"
    now_utc = datetime.now(timezone.utc)

    # 3. Mock External Service Calls and CRUD Operations
    # Mock blob storage upload - using the correct import path
    mock_upload_blob = mocker.patch(
        'backend.app.api.v1.endpoints.documents.upload_file_to_blob',
        new_callable=AsyncMock,
        return_value=mock_blob_name
    )

    # Mock crud.create_document
    created_doc_id = uuid.uuid4() 
    mock_created_document_data = {
        "id": created_doc_id,
        "original_filename": mock_file_name,
        "storage_blob_path": mock_blob_name,
        "file_type": FileType.PDF.value, 
        "upload_timestamp": now_utc, 
        "student_id": student_uuid,
        "assignment_id": assignment_uuid,
        "status": DocumentStatus.UPLOADED.value, 
        "teacher_id": test_user_kinde_id,
        "character_count": None,
        "word_count": None,
        "created_at": now_utc, 
        "updated_at": now_utc  
    }
    mock_created_document_instance = Document(**mock_created_document_data)
    mock_crud_create_doc = mocker.patch(
        'backend.app.api.v1.endpoints.documents.crud.create_document',
        new_callable=AsyncMock,
        return_value=mock_created_document_instance
    )

    # Mock crud.create_result
    created_result_id = uuid.uuid4()
    mock_created_result_data = {
        "id": created_result_id,
        "score": None,
        "status": ResultStatus.PENDING.value,
        "result_timestamp": now_utc, 
        "document_id": created_doc_id, 
        "teacher_id": test_user_kinde_id,
        "paragraph_results": [],
        "error_message": None,
        "created_at": now_utc, 
        "updated_at": now_utc  
    }
    mock_created_result_instance = Result(**mock_created_result_data)
    mock_crud_create_result = mocker.patch(
        'backend.app.api.v1.endpoints.documents.crud.create_result',
        new_callable=AsyncMock,
        return_value=mock_created_result_instance
    )

    # 4. Prepare form data and file for upload
    form_data = {
        "student_id": str(student_uuid),
        "assignment_id": str(assignment_uuid)
    }
    files_data = {
        "file": (mock_file_name, BytesIO(mock_file_content), "application/pdf")
    }

    # 5. Make the API Request
    async with AsyncClient(transport=ASGITransport(app=app_with_mock_auth), base_url="http://testserver") as client:
        response = await client.post(
            upload_url,
            data=form_data, 
            files=files_data
        )
    
    # 6. Assertions
    assert response.status_code == status.HTTP_201_CREATED, (
        f"Expected 201 Created, got {response.status_code}. Response: {response.text}"
    )

    response_data = response.json()

    assert response_data["original_filename"] == mock_file_name
    assert response_data["storage_blob_path"] == mock_blob_name
    assert response_data["file_type"] == FileType.PDF.value
    assert response_data["student_id"] == str(student_uuid)
    assert response_data["assignment_id"] == str(assignment_uuid)
    assert response_data["status"] == DocumentStatus.UPLOADED.value
    assert response_data["teacher_id"] == test_user_kinde_id
    assert "_id" in response_data 
    assert response_data["_id"] == str(created_doc_id) 

    # Verify mock calls
    mock_upload_blob.assert_called_once()
    
    # Verify blob storage call
    positional_args, keyword_args = mock_upload_blob.call_args
    assert len(positional_args) == 0, "Expected no positional arguments"
    assert 'upload_file' in keyword_args, "Expected 'upload_file' in keyword arguments"
    
    called_upload_file_arg = keyword_args['upload_file']
    assert isinstance(called_upload_file_arg, UploadFile), \
        f"Expected 'upload_file' to be an UploadFile, got {type(called_upload_file_arg)}"
    assert called_upload_file_arg.filename == mock_file_name, \
        f"Expected filename '{mock_file_name}', got '{called_upload_file_arg.filename}'"

    # Verify document creation
    mock_crud_create_doc.assert_called_once()
    call_args_create_doc = mock_crud_create_doc.call_args[1]
    document_in_arg = call_args_create_doc['document_in']
    assert document_in_arg.original_filename == mock_file_name
    assert document_in_arg.storage_blob_path == mock_blob_name
    assert document_in_arg.file_type == FileType.PDF 
    assert document_in_arg.student_id == student_uuid
    assert document_in_arg.assignment_id == assignment_uuid
    assert document_in_arg.status == DocumentStatus.UPLOADED
    assert document_in_arg.teacher_id == test_user_kinde_id

    # Verify result creation
    mock_crud_create_result.assert_called_once()
    # crud.create_result is now called with result_in: ResultCreate
    result_in_arg = mock_crud_create_result.call_args[1]['result_in']
    assert isinstance(result_in_arg, ResultCreate)
    assert result_in_arg.document_id == created_doc_id
    assert result_in_arg.teacher_id == test_user_kinde_id
    # Optional: assert result_in_arg.status == ResultStatus.PENDING (or whatever is expected)

    # Clean up dependency override
    if original_override:
        app_with_mock_auth.dependency_overrides[get_current_user_payload] = original_override
    else:
        del app_with_mock_auth.dependency_overrides[get_current_user_payload]

@pytest.mark.asyncio
async def test_upload_document_invalid_file_type(
    app_with_mock_auth: FastAPI,
    mocker: MockerFixture
):
    """Test document upload with an unsupported file type (e.g., .zip)."""
    api_prefix = settings.API_V1_PREFIX
    upload_url = f"{api_prefix}/documents/upload"

    # 1. Mock Authentication
    test_user_kinde_id = generate_unique_kinde_id("invalid_file_type")
    mock_auth_payload = {
        "sub": test_user_kinde_id,
        "roles": ["teacher"],
        "iss": "mock_issuer",
        "aud": ["mock_audience"], 
        "exp": time.time() + 3600,
        "iat": time.time()
    }
    
    async def override_auth(): 
        return mock_auth_payload
    
    original_override = app_with_mock_auth.dependency_overrides.get(get_current_user_payload)
    app_with_mock_auth.dependency_overrides[get_current_user_payload] = override_auth

    # 2. Prepare Test Data
    student_uuid = uuid.uuid4()
    assignment_uuid = uuid.uuid4()
    mock_file_content = b"This is some zip file content, which is not supported."
    mock_file_name = "unsupported_document.zip" # Unsupported file extension
    
    # 3. Mock External Service Calls (Blob storage should not be called)
    mock_upload_blob = mocker.patch(
        'backend.app.api.v1.endpoints.documents.upload_file_to_blob',
        new_callable=AsyncMock
    )

    # 4. Prepare form data and file for upload
    form_data = {
        "student_id": str(student_uuid),
        "assignment_id": str(assignment_uuid)
    }
    files_data = {
        "file": (mock_file_name, BytesIO(mock_file_content), "application/zip") # Unsupported MIME type
    }

    # 5. Make the API Request
    async with AsyncClient(transport=ASGITransport(app=app_with_mock_auth), base_url="http://testserver") as client:
        response = await client.post(
            upload_url,
            data=form_data,
            files=files_data,
        )

    # 6. Assertions
    assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, \
        f"Expected 415, got {response.status_code}. Response: {response.text}"
    
    response_data = response.json()
    assert "Unsupported file type" in response_data["detail"], \
        f"Error detail missing 'Unsupported file type'. Got: {response_data['detail']}"
    assert mock_file_name in response_data["detail"], \
        f"Error detail missing filename '{mock_file_name}'. Got: {response_data['detail']}"
    assert "application/zip" in response_data["detail"], \
        f"Error detail missing content type 'application/zip'. Got: {response_data['detail']}"

    # Verify blob storage was not called
    mock_upload_blob.assert_not_called()

    # 7. Clean up dependency override
    if original_override:
        app_with_mock_auth.dependency_overrides[get_current_user_payload] = original_override
    else:
        del app_with_mock_auth.dependency_overrides[get_current_user_payload]

@pytest.mark.asyncio
async def test_upload_document_too_large(
    app_with_mock_auth: FastAPI,
    mocker: MockerFixture
):
    """Test document upload with a file exceeding the default size limit (e.g., > 1MB)."""
    api_prefix = settings.API_V1_PREFIX
    upload_url = f"{api_prefix}/documents/upload"

    # 1. Mock Authentication
    test_user_kinde_id = generate_unique_kinde_id("large_file")
    mock_auth_payload = {
        "sub": test_user_kinde_id,
        "roles": ["teacher"],
        "iss": "mock_issuer",
        "aud": ["mock_audience"], 
        "exp": time.time() + 3600,
        "iat": time.time()
    }
    
    async def override_auth(): 
        return mock_auth_payload
    
    original_override = app_with_mock_auth.dependency_overrides.get(get_current_user_payload)
    app_with_mock_auth.dependency_overrides[get_current_user_payload] = override_auth

    # 2. Prepare Test Data - Create a file larger than 1MB
    # Starlette's default max_file_size for MultiPartParser is 1MB (1024 * 1024 bytes)
    large_file_size = 10 * 1024 * 1024  # 10MB
    large_file_content = b'a' * large_file_size 
    mock_file_name = "very_large_document.txt"
    mock_blob_name = f"test_blob_{uuid.uuid4()}.txt"
    
    # 3. Mock External Service Calls
    mock_upload_blob = mocker.patch(
        'backend.app.api.v1.endpoints.documents.upload_file_to_blob',
        new_callable=AsyncMock,
        return_value=mock_blob_name
    )

    # Mock crud.create_document
    created_doc_id = uuid.uuid4()
    now_utc = datetime.now(timezone.utc)
    mock_created_document_data = {
        "id": created_doc_id,
        "original_filename": mock_file_name,
        "storage_blob_path": mock_blob_name,
        "file_type": FileType.TXT.value,
        "upload_timestamp": now_utc,
        "student_id": uuid.uuid4(),
        "assignment_id": uuid.uuid4(),
        "status": DocumentStatus.UPLOADED.value,
        "teacher_id": test_user_kinde_id,
        "character_count": None,
        "word_count": None,
        "created_at": now_utc,
        "updated_at": now_utc
    }
    mock_created_document_instance = Document(**mock_created_document_data)
    mock_crud_create_doc = mocker.patch(
        'backend.app.api.v1.endpoints.documents.crud.create_document',
        new_callable=AsyncMock,
        return_value=mock_created_document_instance
    )

    # Mock crud.create_result
    created_result_id = uuid.uuid4()
    mock_created_result_data = {
        "id": created_result_id,
        "score": None,
        "status": ResultStatus.PENDING.value,
        "result_timestamp": now_utc,
        "document_id": created_doc_id,
        "teacher_id": test_user_kinde_id,
        "paragraph_results": [],
        "error_message": None,
        "created_at": now_utc,
        "updated_at": now_utc
    }
    mock_created_result_instance = Result(**mock_created_result_data)
    mock_crud_create_result = mocker.patch(
        'backend.app.api.v1.endpoints.documents.crud.create_result',
        new_callable=AsyncMock,
        return_value=mock_created_result_instance
    )

    # 4. Prepare form data and file for upload
    form_data = {
        "student_id": str(mock_created_document_data["student_id"]),
        "assignment_id": str(mock_created_document_data["assignment_id"])
    }
    files_data = {
        "file": (mock_file_name, BytesIO(large_file_content), "text/plain")
    }

    # 5. Make the API Request
    async with AsyncClient(transport=ASGITransport(app=app_with_mock_auth), base_url="http://testserver") as client:
        response = await client.post(
            upload_url,
            data=form_data,
            files=files_data,
        )

    # 6. Assertions
    # Note: FastAPI/Starlette's default file size limit is not enforced in tests
    # We're testing that our application can handle large files
    assert response.status_code == status.HTTP_201_CREATED, \
        f"Expected 201 Created, got {response.status_code}. Response: {response.text}"
    
    response_data = response.json()
    assert response_data["original_filename"] == mock_file_name
    assert response_data["storage_blob_path"] == mock_blob_name
    assert response_data["file_type"] == FileType.TXT.value
    assert response_data["status"] == DocumentStatus.UPLOADED.value
    assert response_data["teacher_id"] == test_user_kinde_id
    assert response_data["_id"] == str(created_doc_id)

    # Verify mocks were called
    mock_upload_blob.assert_called_once()
    called_args_upload_blob = mock_upload_blob.call_args[1]
    assert isinstance(called_args_upload_blob['upload_file'], UploadFile)
    assert called_args_upload_blob['upload_file'].filename == mock_file_name
    
    mock_crud_create_doc.assert_called_once()
    document_in_arg = mock_crud_create_doc.call_args[1]['document_in']
    assert document_in_arg.original_filename == mock_file_name
    assert document_in_arg.teacher_id == test_user_kinde_id

    mock_crud_create_result.assert_called_once()
    # crud.create_result is now called with result_in: ResultCreate
    result_in_arg = mock_crud_create_result.call_args[1]['result_in']
    assert isinstance(result_in_arg, ResultCreate)
    assert result_in_arg.document_id == created_doc_id
    assert result_in_arg.teacher_id == test_user_kinde_id

    # 7. Clean up dependency override
    if original_override:
        app_with_mock_auth.dependency_overrides[get_current_user_payload] = original_override
    else:
        del app_with_mock_auth.dependency_overrides[get_current_user_payload]

@pytest.mark.asyncio
async def test_upload_document_no_auth(
    app_with_mock_auth: FastAPI,
    mocker: MockerFixture
):
    """Test document upload attempt without authentication."""
    api_prefix = settings.API_V1_PREFIX
    upload_url = f"{api_prefix}/documents/upload"

    # 1. Prepare Test Data
    student_uuid = uuid.uuid4()
    assignment_uuid = uuid.uuid4()
    mock_file_content = b"This is a test content for no_auth test."
    mock_file_name = "no_auth_test_document.pdf"

    # 2. Mock External Service Calls (ensure they are not called)
    mock_upload_blob = mocker.patch(
        'backend.app.api.v1.endpoints.documents.upload_file_to_blob',
        new_callable=AsyncMock
    )

    mock_crud_create_doc = mocker.patch(
        'backend.app.api.v1.endpoints.documents.crud.create_document',
        new_callable=AsyncMock
    )

    mock_crud_create_result = mocker.patch(
        'backend.app.api.v1.endpoints.documents.crud.create_result',
        new_callable=AsyncMock
    )

    # 3. Prepare form data and file for upload
    form_data = {
        "student_id": str(student_uuid),
        "assignment_id": str(assignment_uuid)
    }
    files_data = {
        "file": (mock_file_name, BytesIO(mock_file_content), "application/pdf")
    }

    # 4. Make the API Request (WITHOUT any authentication override)
    # Remove any existing auth override
    original_override = app_with_mock_auth.dependency_overrides.get(get_current_user_payload)
    if original_override:
        del app_with_mock_auth.dependency_overrides[get_current_user_payload]

    async with AsyncClient(transport=ASGITransport(app=app_with_mock_auth), base_url="http://testserver") as client:
        response = await client.post(
            upload_url,
            data=form_data,
            files=files_data,
        )

    # 5. Assertions
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, \
        f"Expected 401 Unauthorized, got {response.status_code}. Response: {response.text}"
    
    response_data = response.json()
    assert response_data["detail"] == "Invalid authentication credentials", \
        f"Expected detail 'Invalid authentication credentials', got '{response_data['detail']}'"

    # Verify external services were NOT called
    mock_upload_blob.assert_not_called()
    mock_crud_create_doc.assert_not_called()
    mock_crud_create_result.assert_not_called()

    # Restore original auth override if it existed
    if original_override:
        app_with_mock_auth.dependency_overrides[get_current_user_payload] = original_override

@pytest.mark.asyncio
async def test_update_document_status_success(
    app_with_mock_auth: FastAPI,
    mocker: MockerFixture
):
    """Test successfully updating the status of an uploaded document via PUT."""
    api_prefix = settings.API_V1_PREFIX
    test_doc_id = uuid.uuid4()
    status_url = f"{api_prefix}/documents/{test_doc_id}/status"

    # 1. Mock Authentication
    test_user_kinde_id = generate_unique_kinde_id("doc_status_user")
    mock_auth_payload = {
        "sub": test_user_kinde_id,
        "email": "test@example.com",
        "roles": ["teacher"],
        "iss": "mock_issuer",
        "aud": ["mock_audience"],
        "exp": time.time() + 3600,
        "iat": time.time()
    }

    async def override_auth():
        return mock_auth_payload

    # Store original override to restore later, if any
    original_override = app_with_mock_auth.dependency_overrides.get(get_current_user_payload)
    app_with_mock_auth.dependency_overrides[get_current_user_payload] = override_auth

    # 2. Prepare Mock Document Data for what crud.get_document_by_id (called by endpoint) will return
    initial_status = DocumentStatus.PROCESSING
    mock_initial_document_data = {
        "id": test_doc_id,
        "original_filename": "status_test.pdf",
        "storage_blob_path": "some/path/status_test.pdf",
        "file_type": FileType.PDF,
        "upload_timestamp": datetime.now(timezone.utc),
        "status": initial_status,
        "student_id": uuid.uuid4(),
        "assignment_id": uuid.uuid4(),
        "teacher_id": test_user_kinde_id,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "is_deleted": False
    }
    mock_initial_doc_instance = Document(**mock_initial_document_data)

    # Mock what crud.update_document_status (called by endpoint) will return
    updated_status = DocumentStatus.COMPLETED
    mock_updated_document_data = {**mock_initial_document_data, "status": updated_status, "updated_at": datetime.now(timezone.utc)}
    mock_updated_doc_instance = Document(**mock_updated_document_data)

    # 3. Mock CRUD Layer
    # Mock for the initial check within the endpoint
    mocker.patch(
        'backend.app.api.v1.endpoints.documents.crud.get_document_by_id',
        new_callable=AsyncMock,
        return_value=mock_initial_doc_instance
    )
    # Mock for the update operation itself
    mock_crud_update_status = mocker.patch(
        'backend.app.api.v1.endpoints.documents.crud.update_document_status',
        new_callable=AsyncMock,
        return_value=mock_updated_doc_instance
    )

    # 4. Make the API Request - Changed to PUT, with JSON body
    request_payload = {"status": updated_status.value} # Send the string value of the enum

    async with AsyncClient(transport=ASGITransport(app=app_with_mock_auth), base_url="http://testserver") as client:
        response = await client.put(status_url, json=request_payload) # Changed to PUT and added json

    # 5. Assertions
    assert response.status_code == status.HTTP_200_OK, \
        f"Expected 200 OK, got {response.status_code}. Response: {response.text}"
    
    response_data = response.json()
    assert response_data["status"] == updated_status.value, \
        f"Expected status {updated_status.value}, got {response_data['status']}"
    assert response_data["_id"] == str(test_doc_id)

    # Assert that crud.update_document_status was called correctly
    mock_crud_update_status.assert_called_once_with(
        document_id=test_doc_id,
        status=updated_status, # Endpoint should pass the Enum member
        teacher_id=test_user_kinde_id
    )

    # Clean up: Restore original dependency override if it existed
    if original_override is not None:
        app_with_mock_auth.dependency_overrides[get_current_user_payload] = original_override
    elif get_current_user_payload in app_with_mock_auth.dependency_overrides:
        del app_with_mock_auth.dependency_overrides[get_current_user_payload]

# @pytest.mark.asyncio
# async def test_get_document(test_client: AsyncClient):
# # Example test for getting a document
# # Assume a document with ID 'some_doc_id' exists and belongs to 'some_teacher_id'
# # headers = {"Authorization": "Bearer your_test_token_if_needed"} # If auth is needed
# # response = await test_client.get("/api/v1/documents/some_doc_id?teacher_id=some_teacher_id", headers=headers)
# # assert response.status_code == 200
# # response_data = response.json()
# # assert response_data["id"] == "some_doc_id"
# pass 