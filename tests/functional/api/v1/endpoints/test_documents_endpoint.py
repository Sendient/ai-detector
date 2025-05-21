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

# Removed: import backend.app.services.blob_storage as blob_storage_module # Not directly used after conflict resolution

from backend.app.core.config import settings
from backend.app.core.security import get_current_user_payload # NEW - For dependency override
from backend.app.models.document import Document, DocumentStatus # For asserting response and types
from backend.app.models.result import Result, ResultStatus # For asserting result creation
from backend.app.models.enums import FileType # For asserting file type

# Mark all tests in this module to use pytest-asyncio
pytestmark = pytest.mark.asyncio

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
    mock_upload_blob = mocker.patch(
        'backend.app.api.v1.endpoints.documents.upload_file_to_blob',
        new_callable=AsyncMock,
        return_value=mock_blob_name
    )

    created_doc_id = uuid.uuid4()
    mock_created_document_data = {
        "id": created_doc_id,
        "original_filename": mock_file_name,
        "storage_blob_path": mock_blob_name,
        "file_type": FileType.PDF.value,
        "upload_timestamp": now_utc,
        "student_id": student_uuid,
        "assignment_id": assignment_uuid,
        "status": DocumentStatus.QUEUED.value, # Assuming enqueue_assessment_task sets this
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

    enqueue_mock = mocker.patch(
        'backend.app.api.v1.endpoints.documents.enqueue_assessment_task', # Corrected path
        new_callable=AsyncMock,
        return_value=True, # Assuming it returns True on success
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
    assert response_data["status"] == DocumentStatus.QUEUED.value # Matches mock_created_document_data
    assert response_data["teacher_id"] == test_user_kinde_id
    assert "_id" in response_data
    assert response_data["_id"] == str(created_doc_id)

    # Verify mock calls
    mock_upload_blob.assert_called_once()
    positional_args, keyword_args = mock_upload_blob.call_args
    assert len(positional_args) == 0, "Expected no positional arguments"
    assert 'upload_file' in keyword_args, "Expected 'upload_file' in keyword arguments"

    called_upload_file_arg = keyword_args['upload_file']
    assert isinstance(called_upload_file_arg, UploadFile), \
        f"Expected 'upload_file' to be an UploadFile, got {type(called_upload_file_arg)}"
    assert called_upload_file_arg.filename == mock_file_name, \
        f"Expected filename '{mock_file_name}', got '{called_upload_file_arg.filename}'"

    mock_crud_create_doc.assert_called_once()
    call_args_create_doc = mock_crud_create_doc.call_args[1] # Keyword arguments are at index 1
    document_in_arg = call_args_create_doc['document_in']
    assert document_in_arg.original_filename == mock_file_name
    assert document_in_arg.storage_blob_path == mock_blob_name
    assert document_in_arg.file_type == FileType.PDF
    assert document_in_arg.student_id == student_uuid
    assert document_in_arg.assignment_id == assignment_uuid
    # The document is created with QUEUED status if enqueue is successful and sets it
    # or it might be created with an initial status like UPLOADED then updated.
    # Based on mock_created_document_data, it's QUEUED.
    assert document_in_arg.status == DocumentStatus.QUEUED
    assert document_in_arg.teacher_id == test_user_kinde_id

    mock_crud_create_result.assert_called_once()
    call_args_create_result = mock_crud_create_result.call_args[1] # Keyword arguments
    result_in_arg = call_args_create_result['result_in']
    assert result_in_arg.document_id == created_doc_id
    assert result_in_arg.teacher_id == test_user_kinde_id
    assert result_in_arg.status == ResultStatus.PENDING

    enqueue_mock.assert_awaited_once_with(
        document_id=created_doc_id,
        user_id=test_user_kinde_id, # Assuming user_id is teacher_id here
        priority_level=0, # Assuming default priority
    )

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
    """Test document upload with a file exceeding the default size limit (e.g., > 1MB).
    Note: This test assumes the application logic itself doesn't impose a strict limit that's
    hit before the endpoint code, or that Starlette's limit isn't hit in the test environment.
    It tests the successful handling path if a large file *is* processed by the endpoint.
    """
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

    # 2. Prepare Test Data - Create a file larger than Starlette's default 1MB if it were enforced
    large_file_size = 10 * 1024 * 1024  # 10MB
    large_file_content = b'a' * large_file_size
    mock_file_name = "very_large_document.txt"
    mock_blob_name = f"test_blob_large_{uuid.uuid4()}.txt" # Unique blob name for this test
    now_utc = datetime.now(timezone.utc)

    # Explicitly define UUIDs for consistency
    student_uuid_for_large_file = uuid.uuid4()
    assignment_uuid_for_large_file = uuid.uuid4()

    # 3. Mock External Service Calls
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
        "file_type": FileType.TXT.value,
        "upload_timestamp": now_utc,
        "student_id": student_uuid_for_large_file, # Use defined UUID
        "assignment_id": assignment_uuid_for_large_file, # Use defined UUID
        "status": DocumentStatus.UPLOADED.value, # Assuming no enqueue step in this specific test flow
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
        "student_id": str(student_uuid_for_large_file), # Use defined UUID
        "assignment_id": str(assignment_uuid_for_large_file) # Use defined UUID
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
    assert response.status_code == status.HTTP_201_CREATED, \
        f"Expected 201 Created, got {response.status_code}. Response: {response.text}"

    response_data = response.json()
    assert response_data["original_filename"] == mock_file_name
    assert response_data["storage_blob_path"] == mock_blob_name
    assert response_data["file_type"] == FileType.TXT.value
    assert response_data["status"] == DocumentStatus.UPLOADED.value # As per mock_created_document_data
    assert response_data["teacher_id"] == test_user_kinde_id
    assert response_data["_id"] == str(created_doc_id)

    # Verify mocks were called
    mock_upload_blob.assert_called_once()
    called_args_upload_blob = mock_upload_blob.call_args[1] # Keyword arguments
    assert isinstance(called_args_upload_blob['upload_file'], UploadFile)
    assert called_args_upload_blob['upload_file'].filename == mock_file_name

    mock_crud_create_doc.assert_called_once()
    document_in_arg = mock_crud_create_doc.call_args[1]['document_in'] # Keyword arguments
    assert document_in_arg.original_filename == mock_file_name
    assert document_in_arg.teacher_id == test_user_kinde_id
    assert document_in_arg.status == DocumentStatus.UPLOADED # As per mock_created_document_data

    mock_crud_create_result.assert_called_once()
    result_in_arg = mock_crud_create_result.call_args[1]['result_in'] # Keyword arguments
    assert result_in_arg.document_id == created_doc_id
    assert result_in_arg.teacher_id == test_user_kinde_id
    assert result_in_arg.status == ResultStatus.PENDING

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
    original_override = app_with_mock_auth.dependency_overrides.pop(get_current_user_payload, None)

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
    # The exact message might depend on your auth setup. "Not authenticated" is common.
    # "Invalid authentication credentials" is also possible for some schemes if a malformed token is sent.
    # If no Authorization header is sent, it's usually "Not authenticated".
    assert "Invalid authentication credentials" in response_data.get("detail", "") or \
           "Not authenticated" in response_data.get("detail", ""), \
           f"Expected detail 'Invalid authentication credentials' or 'Not authenticated', got '{response_data.get('detail')}'"


    # Verify external services were NOT called
    mock_upload_blob.assert_not_called()
    mock_crud_create_doc.assert_not_called()
    mock_crud_create_result.assert_not_called()

    # Restore original auth override if it existed
    if original_override:
        app_with_mock_auth.dependency_overrides[get_current_user_payload] = original_override

@pytest.mark.asyncio
async def test_update_document_status_success( # Renamed for clarity
    app_with_mock_auth: FastAPI,
    mocker: MockerFixture
):
    """Test successfully updating the status of an uploaded document."""
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

    original_override = app_with_mock_auth.dependency_overrides.get(get_current_user_payload)
    app_with_mock_auth.dependency_overrides[get_current_user_payload] = override_auth

    # 2. Prepare Mock Document Data for return value of update
    # The get_document_by_id mock will return the doc *before* update
    # The update_document_status mock will return the doc *after* update
    now_utc = datetime.now(timezone.utc)
    mock_document_data_after_update = {
        "id": test_doc_id,
        "original_filename": "status_test.pdf",
        "storage_blob_path": "some/path/status_test.pdf",
        "file_type": FileType.PDF, # Ensure this is the enum member, not .value
        "upload_timestamp": now_utc,
        "status": DocumentStatus.PROCESSING, # Status after update
        "student_id": uuid.uuid4(),
        "assignment_id": uuid.uuid4(),
        "teacher_id": test_user_kinde_id,
        "created_at": now_utc,
        "updated_at": datetime.now(timezone.utc), # Should be updated
        "character_count": None, # Added for completeness if Document model expects it
        "word_count": None,      # Added for completeness
        "is_deleted": False # Assuming is_deleted field exists
    }
    # Ensure all fields required by Document model are present
    # If your Document model has default values for character_count, word_count, they might not be strictly needed here
    # but it's safer to include them if they are part of the response model.
    mock_doc_instance_after_update = Document(**mock_document_data_after_update)


    # Mock for get_document_by_id (document before update)
    mock_document_data_before_update = mock_document_data_after_update.copy()
    mock_document_data_before_update["status"] = DocumentStatus.UPLOADED # Example initial status
    mock_document_data_before_update["updated_at"] = now_utc # Keep updated_at same as created_at initially
    mock_doc_instance_before_update = Document(**mock_document_data_before_update)


    # 3. Mock CRUD Layer
    mock_crud_get_document = mocker.patch(
        'backend.app.api.v1.endpoints.documents.crud.get_document_by_id',
        new_callable=AsyncMock,
        return_value=mock_doc_instance_before_update # Document as it is before update
    )

    mock_crud_update_status = mocker.patch(
        'backend.app.api.v1.endpoints.documents.crud.update_document_status',
        new_callable=AsyncMock,
        return_value=mock_doc_instance_after_update # Document as it is after update
    )

    # 4. Make the API Request to update status
    async with AsyncClient(transport=ASGITransport(app=app_with_mock_auth), base_url="http://testserver") as client:
        response = await client.put( # This is a PUT request
            status_url,
            json={"status": DocumentStatus.PROCESSING.value} # Payload to update status
        )

    # 5. Assertions
    assert response.status_code == status.HTTP_200_OK, \
        f"Expected 200 OK, got {response.status_code}. Response: {response.text}"

    response_data = response.json()
    assert response_data["_id"] == str(test_doc_id)
    assert response_data["status"] == DocumentStatus.PROCESSING.value # Status should be updated
    assert response_data["teacher_id"] == test_user_kinde_id # Verify teacher_id is still correct
    # Check if updated_at has changed (optional, but good practice)
    # This requires careful handling of datetime objects and their string representations
    # For simplicity, we'll assume the status check is primary.
    # original_updated_at_str = mock_doc_instance_before_update.updated_at.isoformat().replace("+00:00", "Z")
    # assert response_data["updated_at"] != original_updated_at_str


    # Verify CRUD mocks were called correctly
    mock_crud_get_document.assert_called_once_with(
        document_id=test_doc_id,
        teacher_id=test_user_kinde_id # Assuming authorization check involves teacher_id
    )

    mock_crud_update_status.assert_called_once_with(
        document_id=test_doc_id,
        status=DocumentStatus.PROCESSING # The new status enum member
        # db=mocker.ANY # If your crud function takes a db session
    )

    # 6. Clean up dependency override
    if original_override:
        app_with_mock_auth.dependency_overrides[get_current_user_payload] = original_override
    else:
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
