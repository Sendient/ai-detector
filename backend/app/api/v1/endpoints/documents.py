import uuid
import logging
import os # Needed for path operations (splitext)
from typing import List, Optional, Dict, Any
from fastapi import (
    APIRouter, HTTPException, status, Query, Depends,
    UploadFile, File, Form
)
# Add PlainTextResponse for the new endpoint's return type
from fastapi.responses import PlainTextResponse, JSONResponse # Added JSONResponse
from datetime import datetime, timezone
import httpx # Import httpx for making external API calls
import re # Import re for word count calculation
import asyncio # Added for asyncio.to_thread

# Import models
from ....models.document import Document, DocumentCreate, DocumentUpdate
from ....models.result import Result, ResultCreate, ResultUpdate, ParagraphResult
from ....models.enums import DocumentStatus, ResultStatus, FileType, BatchPriority, BatchStatus
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
# from ....core.config import ML_API_URL, ML_RECAPTCHA_SECRET # Placeholder - add these to config.py
# --- TEMPORARY: Define URLs directly here until added to config ---
# Use the URL provided by the user
ML_API_URL="https://fa-sdt-uks-aitextdet-prod.azurewebsites.net/api/ai-text-detection?code=PZrMzMk1VBBCyCminwvgUfzv_YGhVU-5E1JIs2if7zqiAzFuMhUC-g%3D%3D"
# ML_RECAPTCHA_SECRET="6LfAEWwqAAAAAKCk5TXLVa7L9tSY-850idoUwOgr" # Store securely if needed - currently unused
# --- END TEMPORARY ---

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
    student_id: uuid.UUID = Form(..., description="Internal ID of the student associated with the document"),
    assignment_id: uuid.UUID = Form(..., description="ID of the assignment associated with the document"),
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
    result_data = ResultCreate(
        score=None, status=ResultStatus.PENDING, result_timestamp=now, document_id=created_document.id, teacher_id=user_kinde_id
        # paragraph_results will be None by default from the model
    )
    created_result = await crud.create_result(result_in=result_data)
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
        logger.error(
            f"Failed to enqueue assessment task for document {created_document.id}"
        )

    logger.info(
        f"Document {created_document.id} uploaded and queued for assessment."
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
        if current_result.status in [ResultStatus.COMPLETED, ResultStatus.ASSESSING, ResultStatus.RETRYING]:
            logger.info(f"Assessment for doc {document.id} is already {current_result.status}. Returning current result.")
            return current_result
        
        # If PENDING or ERROR, we can attempt to re-queue via the AssessmentTask mechanism
        if current_result.status in [ResultStatus.PENDING, ResultStatus.ERROR]:
            logger.info(f"Result for doc {document.id} is {current_result.status}. Attempting to re-queue for assessment.")
            # Ensure document status is also appropriate for re-queue (e.g., not already COMPLETED)
            if document.status not in [DocumentStatus.COMPLETED, DocumentStatus.PROCESSING]: # PROCESSING implies worker has it
                enqueue_success = await enqueue_assessment_task(
                    document_id=document.id,
                    user_id=auth_teacher_id,
                    priority_level=document.processing_priority or 0
                )
                if enqueue_success:
                    updated_doc = await crud.update_document_status(document_id=document.id, teacher_id=auth_teacher_id, status=DocumentStatus.QUEUED)
                    logger.info(f"Successfully re-queued doc {document.id}. Document status set to QUEUED. Worker will pick it up.")
                    # Update result status to PENDING to reflect it's waiting for worker again
                    await crud.update_result(result_id=current_result.id, update_data={"status": ResultStatus.PENDING}, teacher_id=auth_teacher_id)
                    # Return the result as it is now (PENDING, and doc QUEUED)
                    # The worker will eventually change this result's status.
                    # Fetch it again to get the PENDING status if update_result doesn't return it directly with that change.
                    current_result = await crud.get_result_by_document_id(document_id=document.id, teacher_id=auth_teacher_id)
                    return current_result # Should now be PENDING
                else:
                    logger.error(f"Failed to re-enqueue doc {document.id}. Current result status: {current_result.status}")
                    # Fall through to raise an error or return current (error) state
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to re-queue document for assessment.")
            else:
                logger.info(f"Document {document.id} is already {document.status}. Not re-queueing. Returning current result {current_result.id} ({current_result.status}).")
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
    logger.error(f"Reached end of trigger_assessment for doc {document.id} without explicit return. Result status: {current_result.status if current_result else 'None'}")
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
    for doc in documents:
        try:
            docs_to_log.append(doc.model_dump(mode='json')) 
        except Exception as log_e:
            logger.warning(f"Could not serialize document {getattr(doc, 'id', 'N/A')} for logging: {log_e}")
            docs_to_log.append({"id": str(getattr(doc, 'id', 'N/A')), "error": "Serialization failed for log"})
    logger.debug(f"Returning documents for GET /documents endpoint: {docs_to_log}")
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Document {document_id} not found during status update.")
    
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
    logger.info(f"User {user_kinde_id} attempting to delete document ID: {document_id}")

    # Try to get the document, EXCLUDING already soft-deleted ones first.
    document = await crud.get_document_by_id(document_id=document_id, teacher_id=user_kinde_id, include_deleted=False)
    
    doc_was_already_soft_deleted = False
    if not document:
        # Not found (or not accessible). Check if it was because it's already soft-deleted.
        logger.info(f"Document {document_id} not found (potentially already soft-deleted or not accessible). Checking with include_deleted=True.")
        document = await crud.get_document_by_id(document_id=document_id, teacher_id=user_kinde_id, include_deleted=True)
        if not document:
            # Still not found, even when including deleted ones and checking ownership.
            logger.warning(f"User {user_kinde_id} failed to delete: Document {document_id} truly not found or not accessible.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {document_id} not found.")
        
        # If found here, it must have been soft-deleted. Mark it as such for logging.
        if document.is_deleted:
            doc_was_already_soft_deleted = True
            logger.info(f"Document {document_id} ({document.original_filename}) was already soft-deleted. Proceeding with remaining cleanup (blob, task).")
        else:
            # This case implies document was found only when include_deleted=True but is_deleted is False.
            # This could mean an ownership issue if teacher_id wasn't part of the initial query correctly or some other inconsistency.
            # For safety, treat as not found for deletion by this user.
            logger.warning(f"User {user_kinde_id} failed to delete: Document {document_id} found only when including deleted records but is_deleted flag is False. Possible data inconsistency or access issue.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {document_id} in an inconsistent state for deletion.")

    # At this point, 'document' object is valid (either was never deleted, or was already soft-deleted and re-fetched).
    try:
        if not doc_was_already_soft_deleted:
            # If it wasn't already soft-deleted by a previous call, attempt soft-deletion now.
            success = await crud.delete_document(document_id=document.id, teacher_id=user_kinde_id)
            if not success:
                logger.warning(f"crud.delete_document failed for {document.id} by user {user_kinde_id}, though it was found initially.")
                # crud.delete_document internally logs if it's already deleted or fails for other reasons.
                # If it returns False here, it implies an issue during the update_one operation.
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to soft-delete document during operation.")
            logger.info(f"Successfully soft-deleted document {document.id} ({document.original_filename}) from DB.")
        
        # --- Delete the file from Blob Storage ---
        if document.storage_blob_path:
            try:
                blob_deleted_successfully = await delete_blob(document.storage_blob_path)
                if blob_deleted_successfully:
                    logger.info(f"Successfully deleted blob {document.storage_blob_path} from Azure Storage.")
                else:
                    logger.warning(f"Failed to delete blob {document.storage_blob_path} from Azure Storage. Document metadata remains soft-deleted.")
            except Exception as e_blob_delete:
                logger.error(f"Error deleting blob {document.storage_blob_path} for document {document.id}: {e_blob_delete}", exc_info=True)
        else:
            logger.info(f"No storage_blob_path for document {document.id}, skipping blob deletion.")

        # --- ATTEMPT TO DELETE THE TASK FROM THE QUEUE ---
        logger.info(f"Attempting to delete assessment task for document {document.id} from queue.")
        try:
            from ....db.database import get_database 
            db_instance = get_database()
            if db_instance:
                delete_result = await db_instance.assessment_tasks.delete_many({"document_id": document.id})
                if delete_result.deleted_count > 0:
                    logger.info(f"Successfully deleted {delete_result.deleted_count} assessment task(s) associated with document {document.id}.")
                else:
                    logger.info(f"No assessment task found for document {document.id} to delete, or it was already deleted.")
            else:
                logger.warning(f"Could not get DB instance to delete assessment task for document {document.id}. Task may remain orphaned.")
        except Exception as e_task_delete:
            logger.error(f"Error attempting to delete assessment task for document {document.id}: {e_task_delete}", exc_info=True)

        return # Returns 204 No Content by default
    except HTTPException: 
        raise
    except Exception as e: 
        logger.error(f"Unexpected error in delete document endpoint for {document_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error during document deletion.")

@router.post(
    "/batch",
    response_model=BatchWithDocuments,
    status_code=status.HTTP_201_CREATED,
    summary="Upload multiple documents in a batch (Protected)",
    description="Uploads multiple files, creates a batch record, and queues them for processing. Requires authentication."
)
async def upload_batch(
    student_id: uuid.UUID = Form(..., description="Internal ID of the student associated with the documents"),
    assignment_id: uuid.UUID = Form(..., description="ID of the assignment associated with the documents"),
    files: List[UploadFile] = File(..., description="The document files to upload (PDF, DOCX, TXT, PNG, JPG)"),
    priority: BatchPriority = Form(BatchPriority.NORMAL, description="Processing priority for the batch"),
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to upload batch of {len(files)} documents")

    batch_data = BatchCreate(
        teacher_id=user_kinde_id, # Assuming Batch model's user_id field stores Kinde ID
        total_files=len(files),
        status=BatchStatus.UPLOADING,
        priority=priority
    )
    batch = await crud.create_batch(batch_in=batch_data)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create batch record"
        )

    created_docs_list = [] # Renamed to avoid clash
    failed_files_list = [] # Renamed

    # Map BatchPriority to integer processing_priority for Document
    priority_value_map = {
        BatchPriority.LOW: 0,
        BatchPriority.NORMAL: 1,
        BatchPriority.HIGH: 2,
        BatchPriority.URGENT: 3,
    }
    doc_processing_priority = priority_value_map.get(priority, 1) # Default to 1 (NORMAL)

    for file_item in files: # Renamed to avoid clash
        original_filename = file_item.filename or "unknown_file"
        try:
            content_type = file_item.content_type
            file_extension = os.path.splitext(original_filename)[1].lower()
            file_type_enum: Optional[FileType] = None
            
            if file_extension == ".pdf" and content_type == "application/pdf": file_type_enum = FileType.PDF
            elif file_extension == ".docx" and content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document": file_type_enum = FileType.DOCX
            elif file_extension == ".txt" and content_type == "text/plain": file_type_enum = FileType.TXT
            elif file_extension == ".png" and content_type == "image/png": file_type_enum = FileType.PNG
            elif file_extension in [".jpg", ".jpeg"] and content_type == "image/jpeg": file_type_enum = FileType.JPG

            if file_type_enum is None:
                failed_files_list.append({
                    "filename": original_filename,
                    "error": f"Unsupported file type: {content_type}"
                })
                continue

            blob_name = await upload_file_to_blob(upload_file=file_item)
            if not blob_name:
                failed_files_list.append({
                    "filename": original_filename,
                    "error": "Failed to upload to storage"
                })
                continue

            now = datetime.now(timezone.utc)
            document_data = DocumentCreate(
                original_filename=original_filename,
                storage_blob_path=blob_name,
                file_type=file_type_enum,
                upload_timestamp=now,
                student_id=student_id,
                assignment_id=assignment_id,
                status=DocumentStatus.UPLOADED, # Start as UPLOADED, then QUEUED after enqueue
                batch_id=batch.id,
                queue_position=len(created_docs_list) + 1, # Tentative, may not be strictly used if priority queue
                processing_priority=doc_processing_priority,
                teacher_id=user_kinde_id
            )
            
            document_obj = await crud.create_document(document_in=document_data) # Renamed
            if not document_obj:
                failed_files_list.append({
                    "filename": original_filename,
                    "error": "Failed to create document record"
                })
                continue

            result_data = ResultCreate(
                score=None, status=ResultStatus.PENDING, result_timestamp=now,
                document_id=document_obj.id, teacher_id=user_kinde_id
            )
            batch_created_result = await crud.create_result(result_in=result_data) # Renamed
            if batch_created_result:
                logger.info(f"Successfully created initial Result record {batch_created_result.id} for Document {document_obj.id}")
            else:
                logger.error(f"!!! Failed to create initial Result record for Document {document_obj.id}. crud.create_result returned None.")

            enqueue_success_item = await enqueue_assessment_task( # Renamed
                document_id=document_obj.id,
                user_id=user_kinde_id,
                priority_level=doc_processing_priority, # Use mapped priority
            )
            if enqueue_success_item:
                updated_doc_item = await crud.update_document_status( # Renamed
                    document_id=document_obj.id,
                    teacher_id=user_kinde_id,
                    status=DocumentStatus.QUEUED,
                )
                if updated_doc_item:
                    document_obj = updated_doc_item # Refresh with new status
            else: # Enqueue failed
                logger.error(f"Failed to enqueue assessment task for document {document_obj.id}. Setting status to ERROR.")
                error_doc_item = await crud.update_document_status( # Renamed
                     document_id=document_obj.id, teacher_id=user_kinde_id, status=DocumentStatus.ERROR
                )
                if error_doc_item: document_obj = error_doc_item # Refresh with ERROR status


            created_docs_list.append(document_obj)

        except Exception as e:
            logger.error(f"Error processing file {original_filename} in batch: {str(e)}", exc_info=True)
            failed_files_list.append({
                "filename": original_filename,
                "error": str(e)
            })

    batch_status_val = BatchStatus.QUEUED # Default if some docs are queued
    if not created_docs_list and failed_files_list: # All failed if files were provided
        batch_status_val = BatchStatus.ERROR
    elif failed_files_list: # Some succeeded, some failed
        batch_status_val = BatchStatus.PARTIAL_FAILURE if created_docs_list else BatchStatus.ERROR

    batch_update = BatchUpdate(
        completed_files=0, # To be updated by worker
        failed_files=len(failed_files_list),
        status=batch_status_val,
        error_message=f"Failed to process {len(failed_files_list)} files during batch upload." if failed_files_list else None
    )
    updated_batch = await crud.update_batch(batch_id=batch.id, batch_in=batch_update)
    if not updated_batch : updated_batch = batch # Fallback if update fails

    if not created_docs_list and files: # If files were provided but none made it to a document object
        # Consider if a 201 is still appropriate or if an error reflecting partial/total failure should be raised.
        # For now, returning 201 as batch object was created. Client inspects BatchWithDocuments.
        logger.warning(f"Batch {updated_batch.id}: No documents successfully processed from the {len(files)} provided files. Failures: {len(failed_files_list)}")


    # Ensure all fields for BatchWithDocuments are correctly populated from updated_batch
    return BatchWithDocuments(
        id=updated_batch.id,
        user_id=updated_batch.user_id, # Ensure this field name matches your Batch model
        created_at=updated_batch.created_at,
        updated_at=updated_batch.updated_at,
        total_files=updated_batch.total_files,
        completed_files=updated_batch.completed_files,
        failed_files=updated_batch.failed_files,
        status=updated_batch.status,
        priority=updated_batch.priority,
        error_message=updated_batch.error_message,
        document_ids=[doc.id for doc in created_docs_list]
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

    if batch_obj.user_id != user_kinde_id: # Check against user_id from Batch model
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this batch"
        )

    batch_documents = await crud.get_documents_by_batch_id(batch_id=batch_id, teacher_id=user_kinde_id) # Scoped document fetch
    
    return BatchWithDocuments(
        id=batch_obj.id,
        user_id=batch_obj.user_id,
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
        logger.info(f"Resetting result {result_obj.id} status to ERROR.")
        updated_result_obj = await crud.update_result( # Renamed
            result_id=result_obj.id,
            teacher_id=auth_teacher_id, # Pass teacher_id if supported for scoping
            update_data={"status": ResultStatus.ERROR.value} # Use .value for enums in payload
        )
        if not updated_result_obj:
            logger.error(f"Failed to update result status to ERROR during reset for {result_obj.id} (doc: {document_obj.id}).")
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
    logger.info(f"User {user_kinde_id} attempting to CANCEL status for document {document_id}. Endpoint called.")

    document = await crud.get_document_by_id(document_id=document_id, teacher_id=user_kinde_id)
    if not document:
        logger.warning(f"User {user_kinde_id} failed to cancel: Document {document_id} not found or not accessible.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {document_id} not found or not accessible.")

    auth_teacher_id = document.teacher_id
    logger.info(f"Current status of document {document.id} is '{document.status}'. Checking if cancellable.")

    # Define cancellable document statuses
    cancellable_doc_statuses = [DocumentStatus.PROCESSING, DocumentStatus.RETRYING, DocumentStatus.QUEUED, DocumentStatus.UPLOADED]
    # Define cancellable result statuses (when document is being cancelled)
    cancellable_res_statuses = [ResultStatus.ASSESSING, ResultStatus.RETRYING, ResultStatus.PENDING]

    document_updated = False
    result_updated = False

    if document.status in cancellable_doc_statuses:
        logger.info(f"Document {document.id} status is '{document.status}'. Attempting to set to ERROR.")
        updated_doc = await crud.update_document_status(
            document_id=document.id, 
            teacher_id=auth_teacher_id, 
            status=DocumentStatus.ERROR
        )
        if updated_doc and updated_doc.status == DocumentStatus.ERROR:
            document_updated = True
            logger.info(f"Successfully set document {document.id} status to ERROR.")
        else:
            logger.error(f"Failed to update document {document.id} status to ERROR. Current status: {updated_doc.status if updated_doc else 'None'}.")

        # Also attempt to set the associated result to ERROR
        current_result = await crud.get_result_by_document_id(document_id=document.id, teacher_id=auth_teacher_id)
        if current_result:
            logger.info(f"Found result {current_result.id} with status '{current_result.status}' for document {document.id}. Checking if cancellable.")
            if current_result.status in cancellable_res_statuses:
                logger.info(f"Result {current_result.id} status is '{current_result.status}'. Attempting to set to ERROR.")
                updated_res = await crud.update_result(
                    result_id=current_result.id, 
                    update_data={"status": ResultStatus.ERROR.value}, 
                    teacher_id=auth_teacher_id
                )
                if updated_res and updated_res.status == ResultStatus.ERROR:
                    result_updated = True
                    logger.info(f"Successfully set result {current_result.id} status to ERROR.")
                else:
                    logger.error(f"Failed to update result {current_result.id} status to ERROR. Current status: {updated_res.status if updated_res else 'None'}.")
            else:
                logger.info(f"Result {current_result.id} status '{current_result.status}' is not in a cancellable state ({cancellable_res_statuses}). No action taken on result.")
        else:
            logger.warning(f"No result record found for document {document.id} during cancellation. Cannot update result status.")
    else:
        logger.warning(f"Document {document.id} is not in a cancellable state (currently '{document.status}'). Valid cancellable states are: {cancellable_doc_statuses}. Cannot cancel.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document status '{document.status}' is not cancellable. "
                   f"Cancellable states are: {[s.value for s in cancellable_doc_statuses]}."
        )
    
    if document_updated or result_updated:
        logger.info(f"Cancellation process completed for document {document.id}. Document updated: {document_updated}, Result updated: {result_updated}.")
        return {"message": f"Attempted cancellation for document {document.id}. Document status set to ERROR: {document_updated}. Result status set to ERROR: {result_updated}."}
    else:
        # This case should ideally be caught by the HTTPException above if doc status wasn't cancellable,
        # or if DB updates failed (logged as errors).
        logger.warning(f"Cancellation attempt for document {document.id} resulted in no changes. Document status remains '{document.status}'.")
        # Return a more informative error if no updates happened despite initial checks passing
        # This might indicate issues with the DB update calls themselves not returning expected objects
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Cancellation for document {document.id} did not result in status changes despite being in a potentially cancellable state. Check logs."
        )

# === Helper function to check Recaptcha (if ever needed) ===
# async def verify_recaptcha(token: str) -> bool: