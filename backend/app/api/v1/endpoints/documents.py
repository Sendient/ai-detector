import uuid
import logging
import os # Needed for path operations (splitext)
from typing import List, Optional, Dict, Any, Union
from fastapi import (
    APIRouter, HTTPException, status, Query, Depends,
    UploadFile, File, Form
)
# Add PlainTextResponse for the new endpoint's return type
from fastapi.responses import PlainTextResponse, JSONResponse # Added JSONResponse
from starlette.responses import Response # Added Response
from datetime import datetime, timezone
import httpx # Import httpx for making external API calls
import re # Import re for word count calculation
import asyncio # Added for asyncio.to_thread
import string # Added for string.punctuation

# Import models
from ....models.document import Document, DocumentCreate, DocumentUpdate, DocumentAssignStudentRequest
from ....models.result import Result, ResultCreate, ResultUpdate, ParagraphResult
from ....models.enums import DocumentStatus, ResultStatus, FileType, BatchPriority, BatchStatus, SubscriptionPlan
from ....models.batch import Batch, BatchCreate, BatchUpdate, BatchWithDocuments

# Import CRUD functions
from ....db import crud

# Import Authentication Dependency
from ....core.security import get_current_user_payload

# Import Blob Storage Service
from ....services.blob_storage import upload_file_to_blob, download_blob_as_bytes, delete_blob

# Import Text Extraction Service
from ....services.text_extraction import extract_text_from_bytes
from ....queue import enqueue_assessment_task, AssessmentTask # Added AssessmentTask if needed for other parts, ensure enqueue is there

# Import external API URL from config (assuming you add it there)
from ....core.config import settings # Import settings

# Setup logger
logger = logging.getLogger(__name__)

# Add logging right at module import time
logger.info("---- documents.py module loaded ----")

# --- IMPORTANT: Define the router instance ---
router = APIRouter(
    prefix="/documents",
    tags=["Documents"]
)
# --- End router definition ---

# === Document API Endpoints (Protected) ===

@router.post(
    "/upload",
    response_model=Document, # Return document metadata on successful upload
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new document for analysis (Protected)",
    description="Uploads a file (PDF, DOCX, TXT, PNG, JPG), stores it in blob storage, "
                "creates a document metadata record, and queues it for analysis. "
                "Requires authentication."
)
async def upload_document(
    # Use Form(...) for fields sent alongside the file
    student_id: Optional[uuid.UUID] = Form(None, description="Internal ID of the student associated with the document"),
    assignment_id: Optional[uuid.UUID] = Form(None, description="ID of the assignment associated with the document"),
    # Use File(...) for the file upload itself
    file: UploadFile = File(..., description="The document file to upload (PDF, DOCX, TXT, PNG, JPG)"),
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to upload a document, store it, create metadata,
    and initiate the analysis process.
    """
    user_kinde_id = current_user_payload.get("sub")
    original_filename = file.filename or "unknown_file"
    logger.info(f"User {user_kinde_id} attempting to upload document '{original_filename}' for student {student_id}, assignment {assignment_id}")

    # --- Validate Student Ownership ---
    if student_id is not None:
        student = await crud.get_student_by_id(student_internal_id=student_id, teacher_id=user_kinde_id)
        if not student:
            logger.warning(f"User {user_kinde_id} attempting to upload document for non-existent or unauthorized student {student_id}.")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Student with ID {student_id} not found or not associated with your account."
            )
    # --- End Student Ownership Validation ---

    # --- Authorization Check ---
    # TODO: Implement proper authorization. Can this user upload a document for this student/assignment?
    logger.warning(f"Authorization check needed for user {user_kinde_id} uploading for student {student_id} / assignment {assignment_id}")
    # --- End Authorization Check ---

    # --- File Type Validation ---
    content_type = file.content_type
    file_extension = os.path.splitext(original_filename)[1].lower()
    file_type_enum : Optional[FileType] = None
    if file_extension == ".pdf" and content_type == "application/pdf": file_type_enum = FileType.PDF
    elif file_extension == ".docx" and content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document": file_type_enum = FileType.DOCX
    elif file_extension == ".txt" and content_type == "text/plain": file_type_enum = FileType.TXT
    elif file_extension == ".png" and content_type == "image/png": file_type_enum = FileType.PNG
    elif file_extension in [".jpg", ".jpeg"] and content_type == "image/jpeg": file_type_enum = FileType.JPG # Store as JPG
    # Add TEXT as alias for TXT if needed based on your enum
    elif file_extension == ".txt" and file_type_enum is None: file_type_enum = FileType.TEXT

    if file_type_enum is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {original_filename} ({content_type}). Supported types: PDF, DOCX, TXT, PNG, JPG/JPEG."
        )
    # --- End File Type Validation ---

    # 1. Upload file to Blob Storage
    try:
        blob_name = await upload_file_to_blob(upload_file=file)
        if blob_name is None:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,"Failed to upload file to storage.")
    except Exception as e:
        logger.error(f"Error during file upload service call: {e}", exc_info=True)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,"An error occurred during file upload processing.")

    # 2. Create Document metadata record in DB
    now = datetime.now(timezone.utc)
    document_data = DocumentCreate(
        original_filename=original_filename,
        storage_blob_path=blob_name,
        file_type=file_type_enum,
        upload_timestamp=now,
        student_id=student_id,
        assignment_id=assignment_id,
        status=DocumentStatus.UPLOADED, # Correctly uses Enum
        teacher_id=user_kinde_id # ADDED: Pass the teacher's Kinde ID
    )
    created_document = await crud.create_document(document_in=document_data)
    if not created_document:
        # TODO: Consider deleting the uploaded blob if DB record creation fails
        logger.error(f"Failed to create document metadata record in DB for blob {blob_name}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,"Failed to save document metadata after upload.")

    # 3. Create initial Result record
    result_create_data = ResultCreate(
        document_id=created_document.id,
        teacher_id=user_kinde_id,
        # status is optional in ResultCreate and defaults to PENDING in the model
    )
    created_result = await crud.create_result(result_in=result_create_data)
    if not created_result:
        logger.error(f"Failed to create initial pending result record for document {created_document.id}")
        # Decide if this should cause the whole upload request to fail - maybe not?

    # 4. Enqueue document for assessment
    enqueue_success = await enqueue_assessment_task(
        document_id=created_document.id,
        user_id=user_kinde_id,
        priority_level=created_document.processing_priority or 0,
    )

    if enqueue_success:
        updated_doc = await crud.update_document_status(
            document_id=created_document.id,
            teacher_id=user_kinde_id,
            status=DocumentStatus.QUEUED,
        )
        if updated_doc:
            created_document = updated_doc
        else:
            # This case is tricky: task is in queue, but doc status not updated.
            # Log critically. The worker might pick it up if it finds a PENDING/IN_PROGRESS task,
            # but the document status in the main documents table will be UPLOADED.
            # This could lead to inconsistencies.
            logger.critical(
                f"CRITICAL: Task for document {created_document.id} was enqueued, "\
                f"but FAILED to update document status to QUEUED. Document remains UPLOADED."
            )
            # Potentially set an error status or a specific 'NEEDS_ATTENTION' status here.
            # For now, just critical logging. The assessment worker should still process based on the task queue.
    else:
        logger.error(
            f"Failed to enqueue assessment task for document {created_document.id}. "\
            f"Updating document status to ERROR."
        )
        # Set document status to ERROR if enqueuing failed
        error_updated_doc = await crud.update_document_status(
            document_id=created_document.id,
            teacher_id=user_kinde_id,
            status=DocumentStatus.ERROR, # Set to ERROR
        )
        if error_updated_doc:
            created_document = error_updated_doc
        else:
            logger.error(
                f"Failed to update document {created_document.id} status to ERROR after enqueue failure."
            )

    logger.info(
        f"Document {created_document.id} (status: {created_document.status}) processed by upload endpoint." # Updated log
    )

    return created_document


@router.post(
    "/{document_id}/assess",
    response_model=Result,
    status_code=status.HTTP_200_OK,
    summary="Trigger or Check AI Assessment Status (Protected)",
    description="Checks the status of an assessment. If PENDING or ERROR, it attempts to re-queue it. "
                "If already COMPLETED, ASSESSING, or RETRYING, it returns the current result."
)
async def trigger_assessment(
    document_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    logger.critical(f"--- TRIGGER_ASSESSMENT ENDPOINT CALLED for doc_id: {document_id} by user {user_kinde_id} ---")

    document = await crud.get_document_by_id(document_id=document_id, teacher_id=user_kinde_id)
    if not document:
        logger.warning(f"User {user_kinde_id} failed to trigger assessment: Document {document_id} not found or not accessible.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {document_id} not found or not accessible.")

    auth_teacher_id = document.teacher_id # Should be same as user_kinde_id due to above check

    logger.info(f"User {user_kinde_id} checking/triggering assessment for document {document.id} (current doc status: {document.status})")

    # Get the current result associated with the document
    current_result = await crud.get_result_by_document_id(document_id=document.id, teacher_id=auth_teacher_id)

    if current_result:
        logger.debug(f"Found existing result {current_result.id} with status {current_result.status} for doc {document.id}")
        if current_result.status in [ResultStatus.COMPLETED.value, ResultStatus.PROCESSING.value, ResultStatus.RETRYING.value]:
            logger.info(f"Assessment for doc {document.id} is already {current_result.status}. Returning current result.")
            return current_result
        
        # If PENDING or FAILED, we can attempt to re-queue via the AssessmentTask mechanism
        if current_result.status in [ResultStatus.PENDING.value, ResultStatus.FAILED.value]:
            logger.info(f"Result for doc {document.id} is {current_result.status}. Attempting to re-queue for assessment.")
            
            # MODIFIED: Add pre-emptive limit check for retry if status is LIMIT_EXCEEDED
            if document.status == DocumentStatus.LIMIT_EXCEEDED:
                teacher_db = await crud.get_teacher_by_kinde_id(kinde_id=auth_teacher_id)
                if not teacher_db:
                    logger.error(f"Teacher {auth_teacher_id} not found when attempting to retry LIMIT_EXCEEDED doc {document.id}")
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User profile not found, cannot verify limits for retry.")

                if teacher_db.current_plan == SubscriptionPlan.SCHOOLS:
                    logger.info(f"Teacher {auth_teacher_id} is on SCHOOLS plan. Allowing retry for LIMIT_EXCEEDED doc {document.id} without pre-check.")
                else:
                    usage_stats = await crud.get_usage_stats_for_period(
                        teacher_id=auth_teacher_id,
                        period='monthly',
                        target_date=datetime.now(timezone.utc).date()
                    )
                    current_monthly_words = usage_stats.get("total_words", 0) if usage_stats else 0
                    current_monthly_chars = usage_stats.get("total_characters", 0) if usage_stats else 0
                    
                    doc_word_count = document.word_count if document.word_count is not None else 0
                    doc_char_count = document.character_count if document.character_count is not None else 0

                    plan_word_limit = None
                    plan_char_limit = None

                    if teacher_db.current_plan == SubscriptionPlan.FREE:
                        plan_word_limit = settings.FREE_PLAN_MONTHLY_WORD_LIMIT
                        plan_char_limit = settings.FREE_PLAN_MONTHLY_CHAR_LIMIT
                    elif teacher_db.current_plan == SubscriptionPlan.PRO:
                        plan_word_limit = settings.PRO_PLAN_MONTHLY_WORD_LIMIT
                        plan_char_limit = settings.PRO_PLAN_MONTHLY_CHAR_LIMIT
                    else: # Should not happen if not SCHOOLS, but as a safeguard
                        logger.warning(f"Unknown plan {teacher_db.current_plan} during retry check for doc {document.id}. Denying retry.")
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot verify limits for current plan for retry.")

                    # Pre-emptive check
                    # Note: The assessment_worker subtracts the current doc's count before adding, here we check if adding it now would exceed.
                    # Actually, the worker now compares the total *after* update. So this check should be prospective.
                    if (current_monthly_words + doc_word_count) > plan_word_limit:
                        logger.warning(f"Retry for doc {document.id} denied for teacher {auth_teacher_id}. Word limit would still be exceeded (current: {current_monthly_words}, doc: {doc_word_count}, limit: {plan_word_limit}).")
                        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Retry unavailable: Monthly word limit would still be exceeded.")
                    
                    if (current_monthly_chars + doc_char_count) > plan_char_limit:
                        logger.warning(f"Retry for doc {document.id} denied for teacher {auth_teacher_id}. Character limit would still be exceeded (current: {current_monthly_chars}, doc: {doc_char_count}, limit: {plan_char_limit}).")
                        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Retry unavailable: Monthly character limit would still be exceeded.")
                    
                    logger.info(f"Pre-emptive limit check passed for doc {document.id} for teacher {auth_teacher_id}. Proceeding with retry.")
            # End MODIFIED

            # Ensure document status is also appropriate for re-queue (e.g., not already COMPLETED)
            if document.status not in [DocumentStatus.COMPLETED.value, DocumentStatus.PROCESSING.value]: # Compare with .value
                enqueue_success = await enqueue_assessment_task(
                    document_id=document.id,
                    user_id=auth_teacher_id,
                    priority_level=document.processing_priority or 0
                )
                if enqueue_success:
                    # For LIMIT_EXCEEDED, we need to ensure the status is updated from LIMIT_EXCEEDED, not just any FAILED status.
                    # Also, ensure the result error message is cleared if it was related to limits.
                    update_doc_status_to = DocumentStatus.QUEUED
                    result_update_payload = {"status": ResultStatus.PENDING.value, "error_message": None} # Clear error message
                    
                    updated_doc = await crud.update_document_status(document_id=document.id, teacher_id=auth_teacher_id, status=update_doc_status_to)
                    logger.info(f"Successfully re-queued doc {document.id}. Document status set to {update_doc_status_to.value}. Worker will pick it up.")
                    
                    await crud.update_result(result_id=current_result.id, update_data=result_update_payload, teacher_id=auth_teacher_id)
                    current_result = await crud.get_result_by_document_id(document_id=document.id, teacher_id=auth_teacher_id)
                    return current_result # Should now be PENDING
                else:
                    logger.error(f"Failed to re-enqueue doc {document.id}. Current result status: {current_result.status}") # Removed .value
                    # Fall through to raise an error or return current (error) state
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to re-queue document for assessment.")
            else:
                logger.info(f"Document {document.id} is already {document.status}. Not re-queueing. Returning current result {current_result.id} ({current_result.status}).") # Removed .value
                return current_result
    else:
        # No result record exists. This is unusual if upload creates one.
        # Try to create a PENDING result and enqueue.
        logger.warning(f"No result record found for doc {document.id}. Attempting to create one and enqueue.")
        new_result_data = ResultCreate(document_id=document.id, teacher_id=auth_teacher_id, status=ResultStatus.PENDING)
        created_result = await crud.create_result(result_in=new_result_data)
        if not created_result:
            logger.error(f"Failed to create a new PENDING result for doc {document.id} for re-queue attempt.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to initialize result for assessment.")
        
        enqueue_success = await enqueue_assessment_task(
            document_id=document.id, 
            user_id=auth_teacher_id,
            priority_level=document.processing_priority or 0
        )
        if enqueue_success:
            await crud.update_document_status(document_id=document.id, teacher_id=auth_teacher_id, status=DocumentStatus.QUEUED)
            logger.info(f"Created new result {created_result.id} and enqueued doc {document.id}. Worker will pick it up.")
            return created_result # Return the newly created PENDING result
        else:
            logger.error(f"Created new result {created_result.id} but failed to enqueue doc {document.id}.")
            # Result is PENDING but doc not QUEUED. This is an inconsistent state.
            # Might set doc to ERROR here.
            await crud.update_document_status(document_id=document.id, teacher_id=auth_teacher_id, status=DocumentStatus.ERROR)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to queue document after creating result.")

    # Fallback if no specific condition above was met to return/raise (should be rare)
    logger.error(f"Reached end of trigger_assessment for doc {document.id} without explicit return. Result status: {current_result.status if current_result else 'None'}") # Removed .value
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not determine appropriate action for assessment trigger.")


@router.get(
    "/{document_id}",
    response_model=Document,
    status_code=status.HTTP_200_OK,
    summary="Get a specific document's metadata by ID (Protected)",
    description="Retrieves the metadata of a single document using its unique ID. Requires authentication."
)
async def read_document(
    document_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """Protected endpoint to retrieve specific document metadata by its ID."""
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to read document ID: {document_id}")
    document = await crud.get_document_by_id(
        document_id=document_id,
        teacher_id=user_kinde_id 
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document with ID {document_id} not found.")
    return document

@router.get(
    "/{document_id}/text",
    response_class=PlainTextResponse,
    status_code=status.HTTP_200_OK,
    summary="Get extracted plain text content of a document (Protected)",
    description="Downloads the document file from storage, extracts its plain text content "
                "for supported types (PDF, DOCX, TXT), and returns it. Requires authentication.",
    responses={
        200: {"content": {"text/plain": {"schema": {"type": "string"}}}},
        404: {"description": "Document not found"},
        415: {"description": "Text extraction not supported for this file type"},
        500: {"description": "Error downloading file or during text extraction"},
    }
)
async def get_document_text(
    document_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
) -> str:
    """
    Protected endpoint to retrieve the extracted plain text for a specific document.
    """
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to retrieve text for document ID: {document_id}")

    document = await crud.get_document_by_id(
        document_id=document_id,
        teacher_id=user_kinde_id 
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document with ID {document_id} not found or not accessible by user.")

    file_type_enum_member: Optional[FileType] = None
    if isinstance(document.file_type, str):
        try: # Attempt to convert string to Enum
            file_type_enum_member = FileType(document.file_type.lower())
        except ValueError:
            logger.error(f"Invalid file_type string '{document.file_type}' from DB for doc {document_id} in get_document_text")
            # Fall through, will be handled by "if not file_type_enum_member"
    elif isinstance(document.file_type, FileType):
        file_type_enum_member = document.file_type

    if not file_type_enum_member:
        logger.error(f"Could not map document.file_type '{document.file_type}' to FileType enum for doc {document_id} in get_document_text")
        raise HTTPException(status_code=500, detail="Internal error: Could not determine file type for text extraction.")

    if file_type_enum_member not in [FileType.PDF, FileType.DOCX, FileType.TXT, FileType.TEXT]:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Text extraction not supported for file type: {document.file_type}. Supported types for text extraction: PDF, DOCX, TXT."
        )

    try:
        file_bytes = await download_blob_as_bytes(document.storage_blob_path)
        if file_bytes is None:
            logger.error(f"Failed to download blob {document.storage_blob_path} for document {document_id} text retrieval")
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Error downloading file content.")
        
        logger.info(f"Offloading text extraction for document {document_id} (get_document_text) to a separate thread.")
        extracted_text = await asyncio.to_thread(extract_text_from_bytes, file_bytes, file_type_enum_member)
        logger.info(f"Text extraction completed for document {document_id} (get_document_text). Chars: {len(extracted_text) if extracted_text else 0}")

        if extracted_text is None:
            logger.warning(f"Text extraction returned None for document {document.id} ({document.file_type}).")
            return "" 
        
        return extracted_text
    except Exception as e:
        logger.error(f"Error during text retrieval for document {document.id}: {e}", exc_info=True)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "An unexpected error occurred during text retrieval.")

@router.get(
    "/",
    response_model=List[Document],
    status_code=status.HTTP_200_OK,
    summary="Get a list of documents (Protected)",
    description="Retrieves a list of document metadata records, with optional filtering, sorting, and pagination. Requires authentication."
)
async def read_documents(
    student_id: Optional[uuid.UUID] = Query(None, description="Filter by student UUID"),
    assignment_id: Optional[uuid.UUID] = Query(None, description="Filter by assignment UUID"),
    status: Optional[DocumentStatus] = Query(None, description="Filter by document processing status"),
    skip: int = Query(0, ge=0, description="Number of records to skip for pagination"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of records to return"),
    sort_by: Optional[str] = Query(None, description="Field to sort by (e.g., 'upload_timestamp', 'original_filename')"),
    sort_order_str: str = Query("desc", description="Sort order: 'asc' or 'desc'"),
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to read list of documents with filters/sorting.")

    sort_order_int: int
    if sort_order_str.lower() == "asc":
        sort_order_int = 1
    elif sort_order_str.lower() == "desc":
        sort_order_int = -1
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid sort_order value. Use 'asc' or 'desc'."
        )

    documents = await crud.get_all_documents(
        teacher_id=user_kinde_id, 
        student_id=student_id,
        assignment_id=assignment_id,
        status=status,
        skip=skip,
        limit=limit,
        sort_by=sort_by,
        sort_order=sort_order_int
    )
    docs_to_log = []
    for i, doc in enumerate(documents):
        try:
            docs_to_log.append(doc.model_dump(mode='json')) 
        except Exception as log_e:
            logger.error(f"Could not serialize document at index {i} for logging. Doc ID: {getattr(doc, 'id', 'N/A')}, Type: {type(doc)}. Error: {log_e}", exc_info=True)
            # Try a more basic representation if model_dump fails
            doc_repr = {}
            try:
                doc_repr['id'] = str(doc.id) if hasattr(doc, 'id') else 'N/A'
                doc_repr['original_filename'] = doc.original_filename if hasattr(doc, 'original_filename') else 'N/A'
                doc_repr['status'] = str(doc.status) if hasattr(doc, 'status') else 'N/A'
                doc_repr['error_detail'] = f"Serialization failed: {log_e}"
            except Exception as repr_e:
                doc_repr['critical_error'] = f"Failed to even create basic repr: {repr_e}"
            docs_to_log.append(doc_repr)
    logger.debug(f"Returning documents for GET /documents endpoint. Processed for logging: {docs_to_log}")
    return documents

@router.put(
    "/{document_id}/status",
    response_model=Document,
    status_code=status.HTTP_200_OK,
    summary="Update a document's processing status (Protected)",
    description="Updates the processing status of a document. Requires authentication. (Typically for internal use)."
)
async def update_document_processing_status(
    document_id: uuid.UUID,
    status_update: DocumentUpdate, 
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to update status for document ID: {document_id} to {status_update.status}")
    if status_update.status is None: raise HTTPException(status.HTTP_400_BAD_REQUEST, "Status field is required.")

    doc_to_update = await crud.get_document_by_id(
        document_id=document_id,
        teacher_id=user_kinde_id 
    )
    if not doc_to_update:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found or access denied."
        )

    # Pass teacher_id to update_document_status for scoped update
    updated_document = await crud.update_document_status(
        document_id=document_id, 
        status=status_update.status, 
        teacher_id=user_kinde_id 
    )
    if updated_document is None:
        logger.error(f"Failed to update status for doc {document_id} even after ownership check passed for user {user_kinde_id}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {document_id} not found during status update.")
    
    logger.info(f"Document {document_id} status updated to {status_update.status} by user {user_kinde_id}.")
    return updated_document

@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document and associated data (Protected)",
    description="Soft-deletes a document metadata record, and attempts to delete the associated file from Blob Storage and the analysis result. Requires authentication."
)
async def delete_document_endpoint( # Renamed to avoid potential clash
    document_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to delete document {document_id}")

    # Step 1: Soft-delete the document record (this is transactional)
    # crud.delete_document now returns (bool_success, blob_path_or_none)
    doc_delete_success, blob_to_delete_path = await crud.delete_document(document_id=document_id, teacher_id=user_kinde_id)

    if not doc_delete_success:
        # If doc_delete_success is False, it means the document was not found, not owned, or already deleted.
        # Or an actual DB error occurred during the transaction.
        # The crud.delete_document function logs these cases.
        # We still might have a blob_path if the document record was initially found but the update failed.
        # For now, we treat this as a failure to find/delete the primary record.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {document_id} not found, not accessible, or already deleted.")

    # Step 2: If document soft-deletion was successful, soft-delete associated result (separate transaction)
    logger.info(f"Document {document_id} soft-deleted. Attempting to soft-delete associated result.")
    result_delete_success = await crud.soft_delete_result_by_document_id(document_id=document_id, teacher_id=user_kinde_id)
    
    if not result_delete_success:
        # Log this, but don't necessarily fail the whole operation if the primary document was deleted.
        # The result might not have existed, or was already deleted, or an error occurred.
        # crud.soft_delete_result_by_document_id logs details.
        logger.warning(f"Failed to soft-delete result for document {document_id}, or no active result found. Document deletion was successful.")
    else:
        logger.info(f"Successfully soft-deleted result for document {document_id}.")

    # Step 3: If document soft-deletion was successful, attempt to delete the blob
    blob_delete_successful = False
    if blob_to_delete_path:
        logger.info(f"Attempting to delete blob: {blob_to_delete_path} for document {document_id}")
        try:
            # Assuming delete_blob is an async function
            # It was changed to return a single boolean
            if asyncio.iscoroutinefunction(delete_blob):
                blob_delete_successful = await delete_blob(blob_to_delete_path)
            else:
                blob_delete_successful = await asyncio.to_thread(delete_blob, blob_to_delete_path)
            
            if blob_delete_successful:
                logger.info(f"Successfully deleted blob: {blob_to_delete_path} for document {document_id}")
            else:
                # This else block might be redundant if delete_blob raises an exception on failure rather than returning False.
                # Adjust based on actual behavior of delete_blob.
                logger.warning(f"Blob deletion service reported failure for blob: {blob_to_delete_path} for document {document_id}. The DB records were soft-deleted.")
        except ResourceNotFoundError: # Specific exception for Azure Blob Storage if blob not found
            logger.warning(f"Blob {blob_to_delete_path} not found during deletion for document {document_id}. It might have been already deleted.")
            blob_delete_successful = True # Consider it a success in terms of overall flow if blob is already gone
        except Exception as e:
            # Log error but don't fail the request if DB records were deleted
            logger.error(f"Error deleting blob {blob_to_delete_path} for document {document_id}: {e}. DB records were soft-deleted.", exc_info=True)
    else:
        logger.info(f"No blob path found or returned for document {document_id}. Skipping blob deletion.")
        # If no blob path, we can consider blob deletion part vacuously successful for the overall operation status
        blob_delete_successful = True 

    # If document and result (if any) DB deletions were successful, and blob (if any) was handled, return 204
    # The critical part is doc_delete_success.
    logger.info(f"Delete process completed for document {document_id}. Doc delete: {doc_delete_success}, Result delete: {result_delete_success}, Blob handled: {blob_delete_successful or not blob_to_delete_path}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post(
    "/batch",
    response_model=BatchWithDocuments,
    status_code=status.HTTP_201_CREATED,
    summary="Upload multiple documents in a batch (Protected)",
    description="Uploads multiple files, creates a batch record, and queues them for processing. Requires authentication."
)
async def upload_batch(
    student_id: Optional[uuid.UUID] = Form(None, description="Internal ID of the student associated with the documents"),
    assignment_id: Optional[uuid.UUID] = Form(None, description="ID of the assignment associated with the documents"),
    files: List[UploadFile] = File(..., description="The document files to upload (PDF, DOCX, TXT, PNG, JPG)"),
    priority: BatchPriority = Form(BatchPriority.NORMAL, description="Processing priority for the batch"),
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    if not user_kinde_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User Kinde ID not found in token.")

    logger.info(f"User {user_kinde_id} attempting to upload a batch of {len(files)} files.")

    # --- Pre-emptive Usage Limit Check for Batch ---
    teacher_db = await crud.get_teacher_by_kinde_id(kinde_id=user_kinde_id)
    if not teacher_db:
        # This case should ideally not happen if user is authenticated and in DB
        logger.error(f"User {user_kinde_id} not found in teacher DB for batch upload limit check.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="User profile not found for usage check.")

    current_plan = teacher_db.current_plan
    logger.info(f"User {user_kinde_id} on plan {current_plan} attempting batch upload.")

    # Pre-calculate total words and characters for the batch 
    batch_total_words = 0
    batch_total_chars = 0
    temp_extracted_texts = [] # Store extracted texts, counts, and their original filenames for later use

    for file in files:
        original_filename = file.filename or "unknown_file"
        file_bytes_content = await file.read()
        await file.seek(0) # Reset file pointer for potential re-read by blob upload
        
        file_type_enum_member: Optional[FileType] = None
        file_extension = os.path.splitext(original_filename)[1].lower()
        if file_extension == ".pdf": file_type_enum_member = FileType.PDF
        elif file_extension == ".docx": file_type_enum_member = FileType.DOCX
        elif file_extension == ".txt": file_type_enum_member = FileType.TXT
        elif file_extension == ".png": file_type_enum_member = FileType.PNG
        elif file_extension in [".jpg", ".jpeg"]: file_type_enum_member = FileType.JPG
        
        word_count_for_file = 0
        char_count_for_file = 0
        extracted_text_for_file_to_store = "" # Default to empty string

        if not file_type_enum_member:
            logger.warning(f"Unsupported file type '{original_filename}' in batch for user {user_kinde_id}. Skipping for counts.")
        else:
            try:
                extracted_text_for_file = await asyncio.to_thread(extract_text_from_bytes, file_bytes_content, file_type_enum_member)
                if extracted_text_for_file is None: extracted_text_for_file = ""
                extracted_text_for_file_to_store = extracted_text_for_file # Store for later
                
                raw_tokens_for_file = re.split(r'\s+', extracted_text_for_file.strip())
                cleaned_tokens_for_file = [token.strip(string.punctuation) for token in raw_tokens_for_file]
                words_for_file = [token for token in cleaned_tokens_for_file if token]
                word_count_for_file = len(words_for_file)
                char_count_for_file = len(extracted_text_for_file)
            except Exception as extraction_err:
                logger.error(f"Error extracting text from {original_filename} in batch for counts: {extraction_err}")
        
        batch_total_words += word_count_for_file
        batch_total_chars += char_count_for_file
        temp_extracted_texts.append({
            "original_filename": original_filename, 
            "text": extracted_text_for_file_to_store, 
            "file_type": file_type_enum_member,
            "word_count": word_count_for_file, 
            "char_count": char_count_for_file
        })

    logger.info(f"Total words for incoming batch for user {user_kinde_id}: {batch_total_words}")
    logger.info(f"Total chars for incoming batch for user {user_kinde_id}: {batch_total_chars}")

    if current_plan != SubscriptionPlan.SCHOOLS:
        usage_stats = await crud.get_usage_stats_for_period(
            teacher_id=user_kinde_id,
            period='monthly',
            target_date=datetime.now(timezone.utc).date()
        )
        current_monthly_words = usage_stats.get("total_words", 0) if usage_stats else 0
        current_monthly_chars = usage_stats.get("total_characters", 0) if usage_stats else 0
        
        limit_exceeded = False
        exceeded_by = ""
        error_detail_for_user = ""

        if current_plan == SubscriptionPlan.FREE:
            plan_word_limit_free = settings.FREE_PLAN_MONTHLY_WORD_LIMIT
            plan_char_limit_free = settings.FREE_PLAN_MONTHLY_CHAR_LIMIT
            logger.info(f"Batch Upload FREE Plan: Current words: {current_monthly_words}, Batch words: {batch_total_words}, Word Limit: {plan_word_limit_free}")
            logger.info(f"Batch Upload FREE Plan: Current chars: {current_monthly_chars}, Batch chars: {batch_total_chars}, Char Limit: {plan_char_limit_free}")

            if (current_monthly_words + batch_total_words) > plan_word_limit_free:
                limit_exceeded = True
                exceeded_by = "word"
                error_detail_for_user = f"Batch upload would exceed your monthly word limit. Current usage: {current_monthly_words}/{plan_word_limit_free} words. Batch words: {batch_total_words}."
                logger.warning(f"Batch upload for user {user_kinde_id} (batch words: {batch_total_words}) would exceed FREE plan word limit of {plan_word_limit_free} (current: {current_monthly_words}).")
            
            if not limit_exceeded and (current_monthly_chars + batch_total_chars) > plan_char_limit_free:
                limit_exceeded = True
                exceeded_by = "character"
                error_detail_for_user = f"Batch upload would exceed your monthly character limit. Current usage: {current_monthly_chars}/{plan_char_limit_free} characters. Batch characters: {batch_total_chars}."
                logger.warning(f"Batch upload for user {user_kinde_id} (batch chars: {batch_total_chars}) would exceed FREE plan char limit of {plan_char_limit_free} (current: {current_monthly_chars}).")

        elif current_plan == SubscriptionPlan.PRO:
            plan_word_limit_pro = settings.PRO_PLAN_MONTHLY_WORD_LIMIT
            plan_char_limit_pro = settings.PRO_PLAN_MONTHLY_CHAR_LIMIT
            logger.info(f"Batch Upload PRO Plan: Current words: {current_monthly_words}, Batch words: {batch_total_words}, Word Limit: {plan_word_limit_pro}")
            logger.info(f"Batch Upload PRO Plan: Current chars: {current_monthly_chars}, Batch chars: {batch_total_chars}, Char Limit: {plan_char_limit_pro}")

            if (current_monthly_words + batch_total_words) > plan_word_limit_pro:
                limit_exceeded = True
                exceeded_by = "word"
                error_detail_for_user = f"Batch upload would exceed your monthly word limit. Current usage: {current_monthly_words}/{plan_word_limit_pro} words. Batch words: {batch_total_words}."
                logger.warning(f"Batch upload for user {user_kinde_id} (batch words: {batch_total_words}) would exceed PRO plan word limit of {plan_word_limit_pro} (current: {current_monthly_words}).")
            
            if not limit_exceeded and (current_monthly_chars + batch_total_chars) > plan_char_limit_pro:
                limit_exceeded = True
                exceeded_by = "character"
                error_detail_for_user = f"Batch upload would exceed your monthly character limit. Current usage: {current_monthly_chars}/{plan_char_limit_pro} characters. Batch characters: {batch_total_chars}."
                logger.warning(f"Batch upload for user {user_kinde_id} (batch chars: {batch_total_chars}) would exceed PRO plan char limit of {plan_char_limit_pro} (current: {current_monthly_chars}).")
        else: # Fallback for unknown non-SCHOOLS plan - use FREE plan character limit as the primary fallback
            plan_char_limit_fallback = settings.FREE_PLAN_MONTHLY_CHAR_LIMIT
            logger.warning(f"Unknown plan {current_plan} for user {user_kinde_id} during batch upload. Applying free plan character limit ({plan_char_limit_fallback}) as a fallback.")
            logger.info(f"Batch Upload FALLBACK Plan: Current monthly chars: {current_monthly_chars}, Batch chars: {batch_total_chars}, Limit: {plan_char_limit_fallback}")
            if (current_monthly_chars + batch_total_chars) > plan_char_limit_fallback:
                limit_exceeded = True
                exceeded_by = "character (fallback)"
                error_detail_for_user = f"Batch upload would exceed your monthly character limit (fallback). Current usage: {current_monthly_chars}/{plan_char_limit_fallback} characters. Batch characters: {batch_total_chars}."
                logger.warning(f"Batch upload for user {user_kinde_id} (batch chars: {batch_total_chars}) would exceed FALLBACK char limit of {plan_char_limit_fallback} (current: {current_monthly_chars}).")

        if limit_exceeded:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=error_detail_for_user
            )
    else:
        logger.info(f"User {user_kinde_id} on SCHOOLS plan. Bypassing batch usage limit pre-check.")
    # --- End Pre-emptive Usage Limit Check ---

    # If checks pass, proceed to create batch and document records
    # ... (rest of the batch creation logic)

    # Create Batch DB record
    now = datetime.now(timezone.utc)
    batch_data = BatchCreate(
        teacher_id=user_kinde_id,
        student_id=student_id,
        assignment_id=assignment_id,
        priority=priority,
        status=BatchStatus.PROCESSING, # Initial status
        upload_timestamp=now
    )
    created_batch = await crud.create_batch(batch_in=batch_data)
    if not created_batch:
        logger.error(f"Failed to create batch record for user {user_kinde_id}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create batch record.")

    logger.info(f"Batch record {created_batch.id} created for user {user_kinde_id}.")
    
    created_documents_list: List[Document] = []
    tasks_to_enqueue: List[AssessmentTask] = []

    # Process each pre-validated file detail
    for file_data in temp_extracted_texts:
        try:
            # 2a. Upload file to Blob Storage (using stored bytes)
            # We need to wrap bytes in an UploadFile-like object or adapt upload_file_to_blob
            # For now, assuming upload_file_to_blob can handle bytes directly or adapt it.
            # A simpler way: pass original UploadFile object if stored, or reconstruct if necessary.
            # Let's find the original UploadFile object that matches this detail to pass to upload_file_to_blob
            
            # Find the original UploadFile object
            original_upload_file: Optional[UploadFile] = None
            for up_file in files:
                if up_file.filename == file_data["original_filename"]:
                    original_upload_file = up_file
                    break
            
            if not original_upload_file:
                logger.error(f"Could not find original UploadFile for {file_data['original_filename']} after text extraction. Skipping.")
                continue # Should not happen if logic is correct

            # Ensure the file pointer is at the beginning for upload_file_to_blob
            await original_upload_file.seek(0)

            blob_name = await upload_file_to_blob(upload_file=original_upload_file)
            if blob_name is None:
                logger.error(f"Failed to upload {file_data['original_filename']} to blob storage for batch {created_batch.id}.")
                # Mark this document as error or skip? For now, skip.
                # Potentially update batch status to PARTIAL_FAILURE or similar.
                continue 

            # 2b. Create Document metadata record in DB
            document_data = DocumentCreate(
                original_filename=file_data["original_filename"],
                storage_blob_path=blob_name,
                file_type=file_data["file_type"],
                upload_timestamp=now,
                student_id=student_id,
                assignment_id=assignment_id,
                status=DocumentStatus.UPLOADED,
                teacher_id=user_kinde_id,
                batch_id=created_batch.id,
                character_count=file_data["char_count"],
                word_count=file_data["word_count"]
            )
            created_document = await crud.create_document(document_in=document_data)
            if not created_document:
                logger.error(f"Failed to create document metadata in DB for {blob_name} (batch {created_batch.id}).")
                # TODO: Consider deleting the uploaded blob if DB record creation fails
                continue

            created_documents_list.append(created_document)
            logger.info(f"Document {created_document.id} ({created_document.original_filename}) created for batch {created_batch.id}.")

            # 2c. Create initial Result record
            created_result = await crud.create_result(
                document_id=created_document.id, 
                teacher_id=user_kinde_id
            )
            if not created_result:
                logger.error(f"Failed to create initial result for document {created_document.id} in batch {created_batch.id}. Document status set to ERROR.")
                await crud.update_document_status(document_id=created_document.id, teacher_id=user_kinde_id, status=DocumentStatus.ERROR)
                continue

            # 2d. Prepare AssessmentTask for enqueuing
            tasks_to_enqueue.append(
                AssessmentTask(
                    document_id=created_document.id,
                    user_id=user_kinde_id, # teacher_id
                    priority_level=created_document.processing_priority or BatchPriority.NORMAL.value # Use doc's priority
                )
            )
        except Exception as e_doc_processing:
            logger.error(f"Error processing file {file_data['original_filename']} within batch {created_batch.id} after limit check: {e_doc_processing}", exc_info=True)
            # This document failed, continue to next in batch.
            # Consider adding to a list of failed documents to report to user.

    # 3. Enqueue all tasks and update document statuses
    successful_queues = 0
    if not tasks_to_enqueue: # if all files failed processing or were skipped
        logger.warning(f"No valid documents processed or tasks to enqueue for batch {created_batch.id} from user {user_kinde_id}.")
        # Update batch status if no documents were successfully processed
        if not created_documents_list:
            await crud.update_batch(batch_id=created_batch.id, batch_in=BatchUpdate(status=BatchStatus.FAILED, error_message="No valid files in batch or all files failed processing."))
            # Return the BatchWithDocuments with empty documents list.
            return BatchWithDocuments(
                id=created_batch.id,
                teacher_id=created_batch.teacher_id,
                student_id=created_batch.student_id,
                assignment_id=created_batch.assignment_id,
                priority=created_batch.priority,
                status=BatchStatus.FAILED,
                upload_timestamp=created_batch.upload_timestamp,
                updated_at=datetime.now(timezone.utc), # ensure updated_at is fresh
                documents=[]
            )


    for task in tasks_to_enqueue:
        enqueue_success = await enqueue_assessment_task(
            document_id=task.document_id,
            user_id=task.user_id,
            priority_level=task.priority_level
        )
        if enqueue_success:
            updated_doc = await crud.update_document_status(
                document_id=task.document_id,
                teacher_id=user_kinde_id,
                status=DocumentStatus.QUEUED
            )
            if updated_doc:
                successful_queues +=1
                # Update the document in created_documents_list if needed, or refetch batch.
                for i, doc in enumerate(created_documents_list):
                    if doc.id == updated_doc.id:
                        created_documents_list[i] = updated_doc
                        break
            else:
                logger.error(f"Failed to update document {task.document_id} status to QUEUED after successful enqueue (batch {created_batch.id}).")
        else:
            logger.error(f"Failed to enqueue task for document {task.document_id} (batch {created_batch.id}). Setting doc status to ERROR.")
            await crud.update_document_status(document_id=task.document_id, teacher_id=user_kinde_id, status=DocumentStatus.ERROR)
            # Update the document in created_documents_list to reflect ERROR status
            for i, doc in enumerate(created_documents_list):
                if doc.id == task.document_id:
                    # Refetch or manually update status, for now, just log
                    # Potentially, a full refetch of the document might be better
                    error_doc = await crud.get_document_by_id(document_id=task.document_id, teacher_id=user_kinde_id)
                    if error_doc: created_documents_list[i] = error_doc
                    break
    
    # 4. Update Batch status based on outcomes
    final_batch_status = BatchStatus.COMPLETED_WITH_FAILURES
    if successful_queues == len(tasks_to_enqueue) and len(tasks_to_enqueue) > 0:
        final_batch_status = BatchStatus.COMPLETED_SUCCESSFULLY
    elif successful_queues == 0 and len(tasks_to_enqueue) > 0 : # All tasks failed to enqueue
        final_batch_status = BatchStatus.FAILED
    elif not tasks_to_enqueue and not created_documents_list: # No files processed at all
         final_batch_status = BatchStatus.FAILED # Already handled above, but as a safeguard
    # else: remains COMPLETED_WITH_FAILURES if some succeeded, some failed, or some files skipped pre-task stage

    updated_batch_data = BatchUpdate(status=final_batch_status)
    if final_batch_status == BatchStatus.FAILED and not created_documents_list:
        updated_batch_data.error_message = "No valid files were processed from the batch."

    final_updated_batch = await crud.update_batch(batch_id=created_batch.id, batch_in=updated_batch_data)
    if not final_updated_batch:
        logger.error(f"Failed to update final status for batch {created_batch.id}. Current status might be inaccurate.")
        # Fallback to the batch object before status update attempt for the return
        final_updated_batch = created_batch 
        final_updated_batch.status = updated_batch_data.status # Manually update status for response
        final_updated_batch.updated_at = datetime.now(timezone.utc)


    logger.info(f"Batch {created_batch.id} processing finished. Tasks enqueued: {successful_queues}/{len(tasks_to_enqueue)}. Final Batch Status: {final_updated_batch.status if final_updated_batch else 'Unknown'}")

    return BatchWithDocuments(
        id=final_updated_batch.id if final_updated_batch else created_batch.id,
        teacher_id=final_updated_batch.teacher_id if final_updated_batch else created_batch.teacher_id,
        student_id=final_updated_batch.student_id if final_updated_batch else created_batch.student_id,
        assignment_id=final_updated_batch.assignment_id if final_updated_batch else created_batch.assignment_id,
        priority=final_updated_batch.priority if final_updated_batch else created_batch.priority,
        status=final_updated_batch.status if final_updated_batch else BatchStatus.UNKNOWN, # provide a fallback
        upload_timestamp=final_updated_batch.upload_timestamp if final_updated_batch else created_batch.upload_timestamp,
        updated_at=final_updated_batch.updated_at if final_updated_batch else datetime.now(timezone.utc),
        error_message=final_updated_batch.error_message if final_updated_batch and hasattr(final_updated_batch, 'error_message') else None,
        documents=created_documents_list # Return list of docs that were attempted to be created
    )

@router.get(
    "/batch/{batch_id}",
    response_model=BatchWithDocuments,
    status_code=status.HTTP_200_OK,
    summary="Get batch upload status (Protected)",
    description="Get the status of a batch upload including all documents in the batch. Requires authentication."
)
async def get_batch_status_endpoint( # Renamed
    batch_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    
    batch_obj = await crud.get_batch_by_id(batch_id=batch_id) # Renamed
    if not batch_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Batch with ID {batch_id} not found"
        )

    if batch_obj.teacher_id != user_kinde_id: # Check against user_id from Batch model
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this batch"
        )

    batch_documents = await crud.get_documents_by_batch_id(batch_id=batch_id, teacher_id=user_kinde_id) # Scoped document fetch
    
    return BatchWithDocuments(
        id=batch_obj.id,
        teacher_id=batch_obj.teacher_id,
        created_at=batch_obj.created_at,
        updated_at=batch_obj.updated_at,
        total_files=batch_obj.total_files,
        completed_files=batch_obj.completed_files,
        failed_files=batch_obj.failed_files,
        status=batch_obj.status,
        priority=batch_obj.priority,
        error_message=batch_obj.error_message,
        document_ids=[doc.id for doc in batch_documents]
    )

@router.post(
    "/{document_id}/reset",
    status_code=status.HTTP_200_OK,
    summary="Reset a stuck document assessment (Protected)",
    description="Sets the status of a document and its associated result back to ERROR. Useful for assessments stuck in PROCESSING/ASSESSING.",
    response_model=Dict[str, str] 
)
async def reset_assessment_status_endpoint( # Renamed
    document_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    # No need to check user_kinde_id for None as Depends handles it

    logger.info(f"User {user_kinde_id} attempting to reset status for document {document_id}")

    document_obj = await crud.get_document_by_id(document_id=document_id, teacher_id=user_kinde_id, include_deleted=True) # Renamed
    if not document_obj:
        logger.warning(f"Reset attempt failed: Document {document_id} not found or not owned by user {user_kinde_id}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found or access denied.")

    # Use teacher_id from the fetched document for subsequent scoped CRUD calls
    auth_teacher_id = document_obj.teacher_id
    if not auth_teacher_id: # Should be present if fetched with teacher_id scope
        logger.error(f"Critical: auth_teacher_id is missing for document {document_obj.id} during reset operation by {user_kinde_id}")
        raise HTTPException(status_code=500, detail="Internal error: Teacher identifier missing.")


    logger.info(f"Resetting document {document_obj.id} status to ERROR.")
    updated_doc_obj = await crud.update_document_status( # Renamed
        document_id=document_obj.id,
        teacher_id=auth_teacher_id, 
        status=DocumentStatus.ERROR
    )
    doc_reset_failed = not updated_doc_obj
    if doc_reset_failed:
        logger.error(f"Failed to update document status to ERROR during reset for {document_obj.id}.")

    result_obj = await crud.get_result_by_document_id(document_id=document_obj.id, teacher_id=auth_teacher_id, include_deleted=True) # Renamed, scoped
    result_reset_failed = False
    if result_obj:
        logger.info(f"Resetting result {result_obj.id} status to FAILED.") # Corrected to FAILED
        updated_result_obj = await crud.update_result( # Renamed
            result_id=result_obj.id,
            teacher_id=auth_teacher_id, # Pass teacher_id if supported for scoping
            update_data={"status": ResultStatus.FAILED.value} # Use .value for enums in payload, corrected to FAILED
        )
        if not updated_result_obj:
            logger.error(f"Failed to update result status to FAILED during reset for {result_obj.id} (doc: {document_obj.id}).") # Corrected to FAILED
            result_reset_failed = True
    else:
        logger.warning(f"No result record found to reset for document {document_obj.id}. Document status reset attempt was made.")

    if doc_reset_failed and (not result_obj or result_reset_failed):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to reset document and related result status.")
    if doc_reset_failed:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to reset document status, result handling may have varied.")
    if result_reset_failed: # Implies doc_reset was OK
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Document status reset, but failed to reset result status.")

    logger.info(f"Successfully reset status for document {document_obj.id} and associated result (if found).")
    return {"message": f"Successfully reset status for document {document_id} to ERROR."}

@router.post(
    "/{document_id}/cancel",
    status_code=status.HTTP_200_OK,
    summary="Cancel a stuck document assessment (Protected)",
    description="Sets the status of a document (if PROCESSING or RETRYING) and its associated result (if ASSESSING or RETRYING) back to ERROR.",
    response_model=Dict[str, str] 
)
async def cancel_assessment_status_endpoint( # Renamed
    document_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to cancel assessment for document {document_id}")

    # Fetch the document to verify ownership and current status
    document = await crud.get_document_by_id(document_id=document_id, teacher_id=user_kinde_id)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {document_id} not found or not accessible.")

    # Check if the document is in a state that allows cancellation
    if document.status not in [DocumentStatus.PROCESSING.value, DocumentStatus.QUEUED.value, DocumentStatus.RETRYING.value]: # Added QUEUED
        logger.warning(f"Document {document_id} is in status {document.status}, not cancellable from PROCESSING/QUEUED/RETRYING.")
        # Allow to proceed to result check, as result might be in ASSESSING even if doc isn't.
        # This might happen if doc status update failed but task was picked up.

    # Fetch the result
    result = await crud.get_result_by_document_id(document_id=document_id, teacher_id=user_kinde_id)
    
    doc_updated = False
    res_updated = False

    # Reset Document status to ERROR if it was PROCESSING, QUEUED, or RETRYING
    if document.status in [DocumentStatus.PROCESSING.value, DocumentStatus.QUEUED.value, DocumentStatus.RETRYING.value]: # Added QUEUED
        updated_doc = await crud.update_document_status(
            document_id=document_id,
            teacher_id=user_kinde_id,
            status=DocumentStatus.ERROR
        )
        if updated_doc:
            doc_updated = True
            logger.info(f"Document {document_id} status reset to ERROR from {document.status}.")
        else:
            logger.error(f"Failed to reset document {document_id} status from {document.status} to ERROR.")

    if result:
        # Reset Result status to FAILED if it was ASSESSING or RETRYING
        if result.status in [ResultStatus.PROCESSING.value, ResultStatus.RETRYING.value]: # Changed from ASSESSING to PROCESSING
            updated_res = await crud.update_result_status(
                result_id=result.id,
                status=ResultStatus.FAILED,
                teacher_id=user_kinde_id,
                label="Manually cancelled by user"
            )
            if updated_res:
                res_updated = True
                logger.info(f"Result {result.id} for document {document_id} status reset to FAILED from {result.status}.")
            else:
                logger.error(f"Failed to reset result {result.id} status from {result.status} to FAILED.")
        else:
            logger.info(f"Result {result.id} for document {document_id} is in status {result.status}, not cancellable from PROCESSING/RETRYING.")
    else:
        logger.warning(f"No result found for document {document_id} during cancel operation.")

    if not doc_updated and not res_updated:
        # If neither was updated, it means the document/result wasn't in a cancellable state
        # or an update error occurred which was already logged.
        # Return a message indicating nothing was changed or eligible for change.
        return {"message": f"Document {document_id} and its result were not in a state that required cancellation, or an update error occurred."}

    return {"message": f"Attempted to cancel assessment for document {document_id}. Document updated: {doc_updated}. Result updated: {res_updated}."}

@router.post(
    "/{document_id}/reprocess",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Reprocess a document (Protected)",
    description="Sets a document and its result for reprocessing by queueing a new assessment task. Requires authentication.",
    response_model=Dict[str, str]
)
async def reprocess_document_endpoint(
    document_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to reprocess document {document_id}")

    success = await crud.reprocess_document_and_result(
        document_id=document_id,
        teacher_id=user_kinde_id
    )

    if not success:
        # The CRUD function logs specifics, so a generic error here is okay.
        # It could be due to document not found, DB error, or enqueue failure.
        # We might want to distinguish based on what reprocess_document_and_result can return
        # if we add more detailed return values from it.
        logger.error(f"Failed to trigger reprocessing for document {document_id} by user {user_kinde_id}.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reprocess document {document_id}. Check logs for details."
        )

    return {"message": f"Document {document_id} successfully queued for reprocessing."}

@router.put(
    "/{document_id}/assign-student",
    response_model=Document,
    status_code=status.HTTP_200_OK,
    summary="Assign a student to a document (Protected)",
    description="Updates the student_id for a given document. Requires authentication."
)
async def assign_student_to_document(
    document_id: uuid.UUID,
    request_body: DocumentAssignStudentRequest,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to assign student {request_body.student_id} to document {document_id}")

    # Verify the document exists and belongs to the current user (teacher)
    document = await crud.get_document_by_id(document_id=document_id, teacher_id=user_kinde_id)
    if not document:
        logger.warning(f"User {user_kinde_id} failed assign student: Document {document_id} not found or not accessible.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found or not accessible."
        )

    # Verify the student exists (optional, but good practice)
    # student = await crud.get_student_by_id(student_id=request_body.student_id, teacher_kinde_id=user_kinde_id)
    # if not student:
    #     logger.warning(f"User {user_kinde_id} failed assign student: Student {request_body.student_id} not found or not accessible.")
    #     raise HTTPException(
    #         status_code=status.HTTP_404_NOT_FOUND,
    #         detail=f"Student {request_body.student_id} not found or not accessible to this teacher."
    #     )
    
    # Update the document
    updated_document = await crud.update_document_student_id(
        document_id=document_id,
        student_id=request_body.student_id,
        teacher_id=user_kinde_id
    )

    if not updated_document:
        logger.error(f"Failed to update student_id for document {document_id} for user {user_kinde_id}.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to assign student to document."
        )
    
    logger.info(f"Successfully assigned student {request_body.student_id} to document {document_id} for user {user_kinde_id}.")
    return updated_document

# === Helper function to check Recaptcha (if ever needed) ===
# async def verify_recaptcha(token: str) -> bool: