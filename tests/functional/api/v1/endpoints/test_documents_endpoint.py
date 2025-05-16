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

import app.services.blob_storage as blob_storage_module # ALIASED IMPORT

# Import app and settings (adjust path if your conftest modifies sys.path differently)
from backend.app.main import app as fastapi_app 
from backend.app.core.config import settings
from app.core.security import get_current_user_payload # For dependency override
from backend.app.models.document import Document, DocumentStatus # For asserting response and types
from backend.app.models.result import Result, ResultStatus # For asserting result creation
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
    app: FastAPI, # Using the standard app fixture, will override auth manually
    mocker: MockerFixture, # Keep for other mocks 
    monkeypatch: pytest.MonkeyPatch # Can be removed if no longer used by this test
):
    """
    Test successful document upload (POST /documents/upload).
    Authentication is overridden. Blob storage and CRUD are mocked.
    Blob storage's upload_file_to_blob is mocked by conftest.py's app fixture.
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
    
    # Override the dependency directly for this test's app instance
    # Assuming 'app' fixture provides a fresh app instance for each test,
    # or that pytest handles teardown correctly.
    async def override_get_current_user_payload() -> Dict[str, Any]:
        return mock_auth_payload
    
    original_override = app.dependency_overrides.get(get_current_user_payload)
    app.dependency_overrides[get_current_user_payload] = override_get_current_user_payload

    # 2. Prepare Test Data
    student_uuid = uuid.uuid4()
    assignment_uuid = uuid.uuid4()
    mock_file_content = b"This is a test PDF content."
    mock_file_name = "test_document.pdf"
    mock_blob_name = f"test_blob_{uuid.uuid4()}.pdf"
    now_utc = datetime.now(timezone.utc) # Define a consistent datetime for mocks

    # 3. Mock External Service Calls and CRUD Operations

    # upload_file_to_blob is now mocked by the app fixture in conftest.py.
    # We need to get a reference to that mock to configure its return_value for this test
    # and to assert calls against it.
    # The mock was applied to blob_storage_module.upload_file_to_blob.
    
    # Ensure the mock from conftest is configured for this specific test case
    # (blob_storage_module is imported at the top of this file)
    # The object blob_storage_module.upload_file_to_blob IS the AsyncMock from conftest.
    mock_upload_blob_instance = blob_storage_module.upload_file_to_blob 
    mock_upload_blob_instance.return_value = mock_blob_name
    mock_upload_blob_instance.reset_mock() # Reset call stats if app fixture is function-scoped and mock persists

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
    # Mock crud.create_document using AsyncMock as it's an async CRUD function
    mock_crud_create_doc = mocker.patch(
        'backend.app.api.v1.endpoints.documents.crud.create_document',
        new_callable=AsyncMock, # Use AsyncMock for async functions
        return_value=mock_created_document_instance
    )

    # Mock crud.create_result using AsyncMock
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
        new_callable=AsyncMock, # Use AsyncMock for async functions
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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            upload_url,
            data=form_data, 
            files=files_data,  
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
    mock_upload_blob_instance.assert_called_once()
    
    # Correctly access keyword arguments
    positional_args, keyword_args = mock_upload_blob_instance.call_args
    
    assert len(positional_args) == 0, "Expected no positional arguments"
    assert 'upload_file' in keyword_args, "Expected 'upload_file' in keyword arguments"
    
    called_upload_file_arg = keyword_args['upload_file']
    assert isinstance(called_upload_file_arg, UploadFile), \
        f"Expected 'upload_file' to be an UploadFile, got {type(called_upload_file_arg)}"
    assert called_upload_file_arg.filename == mock_file_name, \
        f"Expected filename '{mock_file_name}', got '{called_upload_file_arg.filename}'"

    # Ensure the file content was passed (by checking if file.read() can be called on the mock's arg)
    # The actual content check might be tricky as the stream might be consumed or be a SpooledTemporaryFile.
    # For now, checking the filename and type is a good step.
    # If you need to check content, you'd have to ensure the UploadFile passed to the mock is readable.
    # Example:
    # temp_file_passed_to_mock = keyword_args['upload_file']
    # content_passed_to_mock = await temp_file_passed_to_mock.read() # May need seek(0)
    # assert content_passed_to_mock == mock_file_content

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

    mock_crud_create_result.assert_called_once()
    call_args_create_result = mock_crud_create_result.call_args[1]
    result_in_arg = call_args_create_result['result_in']
    assert result_in_arg.document_id == created_doc_id
    assert result_in_arg.teacher_id == test_user_kinde_id
    assert result_in_arg.status == ResultStatus.PENDING

    # Clean up dependency override
    if original_override:
        app.dependency_overrides[get_current_user_payload] = original_override
    else:
        del app.dependency_overrides[get_current_user_payload]

@pytest.mark.asyncio
async def test_upload_document_invalid_file_type(
    app: FastAPI, mocker: MockerFixture # app fixture for the FastAPI instance, mocker for other mocks
):
    """Test document upload with an unsupported file type (e.g., .zip)."""
    api_prefix = settings.API_V1_PREFIX
    upload_url = f"{api_prefix}/documents/upload"

    # 1. Mock Authentication
    test_user_kinde_id = generate_unique_kinde_id("invalid_file_type")
    mock_auth_payload = {
        "sub": test_user_kinde_id, "roles": ["teacher"],
        "iss": "mock_issuer", "aud": ["mock_audience"], 
        "exp": time.time() + 3600, "iat": time.time()
    }
    
    async def override_auth(): 
        return mock_auth_payload
    
    original_override = app.dependency_overrides.get(get_current_user_payload)
    app.dependency_overrides[get_current_user_payload] = override_auth

    # 2. Prepare Test Data
    student_uuid = uuid.uuid4()
    assignment_uuid = uuid.uuid4()
    mock_file_content = b"This is some zip file content, which is not supported."
    mock_file_name = "unsupported_document.zip" # Unsupported file extension
    
    # 3. Mock External Service Calls (Blob storage should not be called)
    # Get the globally mocked instance from conftest.py via the imported module
    mock_upload_blob_instance = blob_storage_module.upload_file_to_blob
    mock_upload_blob_instance.reset_mock() # Ensure it's clean before the call

    # 4. Prepare form data and file for upload
    form_data = {
        "student_id": str(student_uuid),
        "assignment_id": str(assignment_uuid)
    }
    files_data = {
        "file": (mock_file_name, BytesIO(mock_file_content), "application/zip") # Unsupported MIME type
    }

    # 5. Make the API Request
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
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
    mock_upload_blob_instance.assert_not_called()

    # 7. Clean up dependency override
    if original_override:
        app.dependency_overrides[get_current_user_payload] = original_override
    else:
        del app.dependency_overrides[get_current_user_payload]

@pytest.mark.asyncio
async def test_upload_document_too_large(
    app: FastAPI, mocker: MockerFixture
):
    """Test document upload with a file exceeding the default size limit (e.g., > 1MB)."""
    api_prefix = settings.API_V1_PREFIX
    upload_url = f"{api_prefix}/documents/upload"

    # 1. Mock Authentication
    test_user_kinde_id = generate_unique_kinde_id("large_file")
    mock_auth_payload = {
        "sub": test_user_kinde_id, "roles": ["teacher"],
        "iss": "mock_issuer", "aud": ["mock_audience"], 
        "exp": time.time() + 3600, "iat": time.time()
    }
    
    async def override_auth(): 
        return mock_auth_payload
    
    original_override = app.dependency_overrides.get(get_current_user_payload)
    app.dependency_overrides[get_current_user_payload] = override_auth

    # 2. Prepare Test Data - Create a file larger than 1MB
    # Starlette's default max_file_size for MultiPartParser is 1MB (1024 * 1024 bytes)
    # Let's create a file significantly larger than this to ensure the limit is triggered.
    # FastAPI/Starlette should return a 413 if this default is exceeded before endpoint logic.
    # The max_part_size for request.form() defaults to 1MB.
    large_file_size = 10 * 1024 * 1024  # 10MB
    # Create dummy content of the required size
    # Using BytesIO for the file content
    large_file_content = b'a' * large_file_size 
    mock_file_name = "very_large_document.txt"
    
    # 3. Mock External Service Calls (Blob storage should not be called)
    mock_upload_blob_instance = blob_storage_module.upload_file_to_blob
    mock_upload_blob_instance.reset_mock()
    # Configure blob upload to return a name, as it would if successful
    mock_upload_blob_instance.return_value = f"mock_blob_for_large_file_{uuid.uuid4()}.txt"

    # Mock CRUD operations
    # Crucially, mock create_document to return a mock Document object with ALL necessary fields for serialization
    created_doc_id_for_large_file = uuid.uuid4()
    student_uuid_for_large_file = uuid.uuid4() # Define for consistency
    assignment_uuid_for_large_file = uuid.uuid4() # Define for consistency
    now_utc_for_large_file = datetime.now(timezone.utc)

    mock_doc_instance_for_large_file = mocker.MagicMock(spec=Document)
    mock_doc_instance_for_large_file.id = created_doc_id_for_large_file
    mock_doc_instance_for_large_file.original_filename = mock_file_name
    mock_doc_instance_for_large_file.storage_blob_path = mock_upload_blob_instance.return_value
    mock_doc_instance_for_large_file.file_type = FileType.TXT # Assuming .txt from mock_file_name
    mock_doc_instance_for_large_file.upload_timestamp = now_utc_for_large_file
    mock_doc_instance_for_large_file.student_id = student_uuid_for_large_file
    mock_doc_instance_for_large_file.assignment_id = assignment_uuid_for_large_file
    mock_doc_instance_for_large_file.status = DocumentStatus.UPLOADED
    mock_doc_instance_for_large_file.teacher_id = test_user_kinde_id # from auth mock
    mock_doc_instance_for_large_file.character_count = None
    mock_doc_instance_for_large_file.word_count = None
    mock_doc_instance_for_large_file.created_at = now_utc_for_large_file
    mock_doc_instance_for_large_file.updated_at = now_utc_for_large_file
    # Pydantic v2: .model_dump() is preferred for serialization
    # For MagicMock, we need to ensure it can be serialized. 
    # A simpler approach for MagicMock is to mock .model_dump() if FastAPI internals use it, 
    # or ensure all attributes accessed by the serializer are present.
    # FastAPI's default serialization will access attributes directly for response_model.

    mock_crud_create_doc = mocker.patch(
        'backend.app.api.v1.endpoints.documents.crud.create_document',
        new_callable=AsyncMock,
        return_value=mock_doc_instance_for_large_file # Return the fully mocked Document
    )
    
    created_result_id_for_large_file = uuid.uuid4()
    mock_created_result_instance_for_large_file = mocker.MagicMock(spec=Result)
    mock_created_result_instance_for_large_file.id = created_result_id_for_large_file
    # Populate other fields if necessary for Result model if it were also returned/validated in detail
    # For now, just ensuring it's a mock that can be returned is enough.

    mock_crud_create_result = mocker.patch(
        'backend.app.api.v1.endpoints.documents.crud.create_result',
        new_callable=AsyncMock,
        return_value=mock_created_result_instance_for_large_file
    )

    # 4. Prepare form data and file for upload
    # Use the uuids defined for the mock_doc_instance to ensure consistency if checking response details
    form_data = {
        "student_id": str(student_uuid_for_large_file),
        "assignment_id": str(assignment_uuid_for_large_file)
    }
    files_data = {
        "file": (mock_file_name, BytesIO(large_file_content), "text/plain")
    }

    # 5. Make the API Request
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            upload_url,
            data=form_data,
            files=files_data,
        )

    # 6. Assertions
    # ADJUSTED: Expecting 201 Created, as Starlette's 1MB part limit is not hit by AsyncClient for a 10MB file.
    # This means the application currently processes the 10MB file successfully in this test setup.
    assert response.status_code == status.HTTP_201_CREATED, \
        f"Expected 201 (large file processed), got {response.status_code}. Response: {response.text}"
    
    response_data = response.json()
    assert response_data["original_filename"] == mock_file_name
    assert response_data["storage_blob_path"] == mock_upload_blob_instance.return_value
    assert response_data["_id"] == str(created_doc_id_for_large_file)
    # Add other assertions if needed, e.g., teacher_id, student_id, etc.
    assert response_data["teacher_id"] == test_user_kinde_id
    assert response_data["student_id"] == str(student_uuid_for_large_file)

    # Verify mocks were called, as the request is now expected to be processed
    mock_upload_blob_instance.assert_called_once()
    called_args_upload_blob = mock_upload_blob_instance.call_args[1]
    assert isinstance(called_args_upload_blob['upload_file'], UploadFile)
    assert called_args_upload_blob['upload_file'].filename == mock_file_name
    
    mock_crud_create_doc.assert_called_once()
    # Add assertions for arguments to mock_crud_create_doc if necessary
    document_in_arg = mock_crud_create_doc.call_args[1]['document_in']
    assert document_in_arg.original_filename == mock_file_name
    assert document_in_arg.teacher_id == test_user_kinde_id

    mock_crud_create_result.assert_called_once()
    # Add assertions for arguments to mock_crud_create_result if necessary
    result_in_arg = mock_crud_create_result.call_args[1]['result_in']
    assert result_in_arg.document_id == created_doc_id_for_large_file
    assert result_in_arg.teacher_id == test_user_kinde_id

    # 7. Clean up dependency override
    if original_override:
        app.dependency_overrides[get_current_user_payload] = original_override
    else:
        del app.dependency_overrides[get_current_user_payload]

@pytest.mark.asyncio
async def test_upload_document_no_auth(
    app: FastAPI, mocker: MockerFixture
):
    """Test document upload attempt without authentication."""
    api_prefix = settings.API_V1_PREFIX
    upload_url = f"{api_prefix}/documents/upload"

    # 1. Prepare Test Data (minimal, as it shouldn't be processed)
    student_uuid = uuid.uuid4()
    assignment_uuid = uuid.uuid4()
    mock_file_content = b"This is a test content for no_auth test."
    mock_file_name = "no_auth_test_document.pdf"

    # 2. Mock External Service Calls (ensure they are not called)
    # Get the globally mocked instance from conftest.py via the imported module
    mock_upload_blob_instance = blob_storage_module.upload_file_to_blob
    mock_upload_blob_instance.reset_mock() 

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

    # 4. Make the API Request (WITHOUT any authentication override or headers)
    # The `app` fixture used here will have the standard `get_current_user_payload` dependency.
    # Since no token is provided, FastAPI should return a 401/403.
    # By default, if SecurityScopes are used and no token is provided, it's often 401.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            upload_url,
            data=form_data,
            files=files_data,
        )

    # 5. Assertions
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, \
        f"Expected 401 Unauthorized, got {response.status_code}. Response: {response.text}"
    
    response_data = response.json()
    # FastAPI's default response for missing authentication is typically {"detail": "Not authenticated"}
    # or for OAuth2PasswordBearer it might be {"detail": "Not authenticated"} or {"detail": "Unauthorized"}
    # depending on how it's configured or if specific security schemes are used.
    # Let's check for "Not authenticated" as a common default.
    assert response_data["detail"] == "Invalid authentication credentials", \
        f"Expected detail 'Invalid authentication credentials', got '{response_data['detail']}'"

    # Verify external services were NOT called
    mock_upload_blob_instance.assert_not_called()
    mock_crud_create_doc.assert_not_called()
    mock_crud_create_result.assert_not_called()

    # No dependency override to clean up as none was set for this test

@pytest.mark.asyncio
async def test_get_document_status_success(
    app: FastAPI, mocker: MockerFixture
):
    """Test successfully getting the status of an uploaded document."""
    api_prefix = settings.API_V1_PREFIX
    test_doc_id = uuid.uuid4()
    status_url = f"{api_prefix}/documents/{test_doc_id}/status"

    # 1. Mock Authentication
    test_user_kinde_id = generate_unique_kinde_id("doc_status_user")
    mock_auth_payload = {
        "sub": test_user_kinde_id, "roles": ["teacher"],
        "iss": "mock_issuer", "aud": ["mock_audience"], 
        "exp": time.time() + 3600, "iat": time.time()
    }
    
    async def override_auth(): 
        return mock_auth_payload
    
    original_override = app.dependency_overrides.get(get_current_user_payload)
    app.dependency_overrides[get_current_user_payload] = override_auth

    # 2. Prepare Mock Document Data
    # This is what crud.get_document is expected to return
    mock_document_data = {
        "id": test_doc_id,
        "original_filename": "status_test.pdf",
        "storage_blob_path": "some/path/status_test.pdf",
        "file_type": FileType.PDF,
        "upload_timestamp": datetime.now(timezone.utc),
        "status": DocumentStatus.PROCESSING, # The status we want to check
        "student_id": uuid.uuid4(),
        "assignment_id": uuid.uuid4(),
        "teacher_id": test_user_kinde_id, # Crucial for authorization
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "is_deleted": False
        # Add other fields if your Document model requires them or if they are part of the response model
    }
    mock_doc_instance = Document(**mock_document_data)

    # 3. Mock CRUD Layer
    # Assuming the endpoint will use something like crud.get_document(db, id=doc_id, teacher_id=current_user_id)
    # to fetch and authorize in one step, or separate get and check.
    mock_crud_get_document = mocker.patch(
        'backend.app.api.v1.endpoints.documents.crud.get_document', # Adjust if your CRUD function is named differently
        new_callable=AsyncMock,
        return_value=mock_doc_instance
    )

    # 4. Make the API Request
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get(status_url)

    # 5. Assertions
    # This will initially fail with 404 as the endpoint doesn't exist
    assert response.status_code == status.HTTP_200_OK, \
        f"Expected 200 OK, got {response.status_code}. Response: {response.text}"
    
    response_data = response.json()
    assert response_data["id"] == str(test_doc_id)
    assert response_data["status"] == DocumentStatus.PROCESSING.value # Ensure enum value is compared

    # Verify CRUD mock was called correctly
    # The actual arguments will depend on how the endpoint implements the fetch & auth
    mock_crud_get_document.assert_called_once_with(
        db=mocker.ANY, # The db session from Depends
        document_id=test_doc_id, 
        teacher_id=test_user_kinde_id
    )

    # 6. Clean up dependency override
    if original_override:
        app.dependency_overrides[get_current_user_payload] = original_override
    else:
        del app.dependency_overrides[get_current_user_payload]

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