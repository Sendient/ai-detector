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
from app.models.document import Document, DocumentCreate, DocumentUpdate
from app.models.result import Result, ResultCreate, ResultUpdate, ParagraphResult
from app.models.enums import DocumentStatus, ResultStatus, FileType, BatchPriority, BatchStatus
from app.models.batch import Batch, BatchCreate, BatchUpdate, BatchWithDocuments

# Import CRUD functions
from app.db import crud

# Import Authentication Dependency
from app.core.security import get_current_user_payload

# Import Blob Storage Service
from app.services.blob_storage import upload_file_to_blob, download_blob_as_bytes
from app.queue import enqueue_assessment_task

# Import Text Extraction Service
from app.services.text_extraction import extract_text_from_bytes
# from app.queue import enqueue_assessment_task # Duplicate import removed

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
        status=DocumentStatus.QUEUED, # Document is initially marked as QUEUED
        teacher_id=user_kinde_id
        # processing_priority is not set here for single uploads, will default in model or be None
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
        # If it does fail, the document is QUEUED but has no PENDING result. Processor needs to handle this.

    # --- RESOLVED CONFLICT BLOCK START ---
    # 4. Enqueue document for assessment
    # Note: created_document.status is currently DocumentStatus.QUEUED from DocumentCreate
    enqueue_success = await enqueue_assessment_task(
        document_id=created_document.id,
        user_id=user_kinde_id,
        priority_level=created_document.processing_priority or 0, # Uses document's priority if set, else 0
    )

    if enqueue_success:
        # Document status is already QUEUED.
        # This update call serves to refresh the 'created_document' object and align with 'upload_batch' pattern.
        updated_doc_after_enqueue = await crud.update_document_status(
            document_id=created_document.id,
            teacher_id=user_kinde_id,
            status=DocumentStatus.QUEUED, # Re-affirming the status
        )
        if updated_doc_after_enqueue:
            created_document = updated_doc_after_enqueue
            logger.info(f"Document {created_document.id} uploaded and successfully queued for assessment.")
        else:
            logger.warning(
                f"Document {created_document.id} was enqueued, but failed to refresh the document object. "
                f"Proceeding with potentially slightly stale document data (status should still be QUEUED)."
            )
            # Log that it was queued despite the refresh failure, using the existing created_document state for info
            logger.info(f"Document {created_document.id} (filename: {created_document.original_filename}) uploaded and queued for assessment (object refresh failed).")

    else: # Enqueue failed
        logger.error(
            f"Failed to enqueue assessment task for document {created_document.id}. Updating document status to ERROR."
        )
        # Update document status to ERROR to reflect the failure
        doc_updated_to_error = await crud.update_document_status(
            document_id=created_document.id,
            teacher_id=user_kinde_id,
            status=DocumentStatus.ERROR,
        )
        if doc_updated_to_error:
            created_document = doc_updated_to_error # Crucial: return document with ERROR status
            logger.info(f"Document {created_document.id} status updated to ERROR due to enqueue failure.")
        else:
            # This is a problematic state: document is in DB with status QUEUED,
            # was not enqueued, and the attempt to update its status to ERROR also failed.
            logger.critical(
                f"CRITICAL: Failed to enqueue document {created_document.id} AND failed to update its status to ERROR. "
                f"Document remains in DB with status '{DocumentStatus.QUEUED.value}' but is NOT in the processing queue."
            )
            # The 'created_document' object at this point still has status QUEUED.
            # Depending on error handling policy, an HTTPException could be raised here.
            # For now, it will return the created_document which is in a misleading state if this path is hit.
    # --- RESOLVED CONFLICT BLOCK END ---

    return created_document


@router.post(
    "/{document_id}/assess",
    response_model=Result, # Return the final Result object
    status_code=status.HTTP_200_OK, # Return 200 OK on successful assessment
    summary="Trigger AI Assessment and get Result (Protected)",
    description="Fetches document text, calls the external ML API for AI detection, "
                "updates the result/document status, and returns the final result. "
                "Requires authentication."
)
async def trigger_assessment(
    document_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to trigger the AI assessment for a document.
    Fetches text, calls external API, updates DB, returns result.
    """
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to trigger assessment for document ID: {document_id}")

    # --- Get Document & Authorization Check ---
    document = await crud.get_document_by_id(
        document_id=document_id,
        teacher_id=user_kinde_id # <<< This ensures the document belongs to the user
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document with ID {document_id} not found or not accessible by user.")

    # Ensure document.teacher_id is available, otherwise use user_kinde_id as a fallback.
    # Given the above fetch, document.teacher_id should match user_kinde_id.
    auth_teacher_id = document.teacher_id if document.teacher_id else user_kinde_id
    if not auth_teacher_id:
        logger.error(f"Critical: teacher_id is missing for document {document_id} during assessment trigger by user {user_kinde_id}.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error: Missing teacher identifier.")


    # TODO: Implement proper authorization check: Can user trigger assessment for this document?
    logger.warning(f"Authorization check needed for user {user_kinde_id} triggering assessment for document {document_id}")

    # Check if assessment can be triggered (e.g., only if UPLOADED or maybe ERROR)
    if document.status not in [DocumentStatus.UPLOADED, DocumentStatus.ERROR, DocumentStatus.FAILED, DocumentStatus.QUEUED]: # Added QUEUED as a state from which assessment can be triggered.
        logger.warning(f"Document {document_id} status is '{document.status}'. Assessment cannot be triggered directly for this status.")
        existing_result = await crud.get_result_by_document_id(document_id=document_id, teacher_id=auth_teacher_id)
        if existing_result:
            if existing_result.status in [ResultStatus.COMPLETED, ResultStatus.ASSESSING]:
                logger.info(f"Assessment already completed or in progress for doc {document_id}. Returning existing result.")
                return existing_result
            # If status is PENDING or ERROR, allow re-triggering below
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Assessment cannot be triggered. Document status is {document.status}, but no result found."
            )

    # --- Update Status to PROCESSING ---
    await crud.update_document_status(document_id=document_id, teacher_id=auth_teacher_id, status=DocumentStatus.PROCESSING)
    result = await crud.get_result_by_document_id(document_id=document_id, teacher_id=auth_teacher_id) # Pass teacher_id
    if result:
        await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ASSESSING}, teacher_id=auth_teacher_id)
        logger.info(f"Existing result record found for doc {document_id}, updated status to ASSESSING.")
    else:
        logger.warning(f"Result record missing for document {document_id} during assessment trigger. Creating one now.")
        result_data = ResultCreate(
            score=None, 
            status=ResultStatus.ASSESSING, 
            result_timestamp=datetime.now(timezone.utc), 
            document_id=document_id, 
            teacher_id=auth_teacher_id
        )
        created_result = await crud.create_result(result_in=result_data)
        if not created_result:
            logger.error(f"Failed to create missing result record for document {document_id}. Assessment cannot proceed.")
            await crud.update_document_status(document_id=document_id, teacher_id=auth_teacher_id, status=DocumentStatus.ERROR)
            raise HTTPException(status_code=500, detail="Internal error: Failed to create necessary result record.")
        result = created_result
        logger.info(f"Successfully created missing result record {result.id} for doc {document_id} with status ASSESSING.")

    # --- Text Extraction ---
    extracted_text: Optional[str] = None
    character_count: Optional[int] = None
    word_count: Optional[int] = None
    try:
        file_type_enum_member: Optional[FileType] = None
        if isinstance(document.file_type, str):
            try:
                file_type_enum_member = FileType(document.file_type.lower())
            except ValueError:
                logger.error(f"Invalid file_type string '{document.file_type}' from DB for doc {document.id}")
                file_type_enum_member = None
        elif isinstance(document.file_type, FileType):
            file_type_enum_member = document.file_type

        if not file_type_enum_member:
            logger.error(f"Could not map document.file_type '{document.file_type}' to FileType enum for doc {document_id}")
            raise HTTPException(status_code=500, detail="Internal error: Could not determine file type for text extraction.")

        file_bytes = await download_blob_as_bytes(document.storage_blob_path)
        if file_bytes is None:
            logger.error(f"Failed to download blob {document.storage_blob_path} for document {document_id}")
            await crud.update_document_status(document_id=document_id, teacher_id=auth_teacher_id, status=DocumentStatus.ERROR)
            if result:
                await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id)
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to retrieve document content from storage for assessment.")

        logger.info(f"Offloading text extraction for document {document_id} to a separate thread.")
        extracted_text = await asyncio.to_thread(extract_text_from_bytes, file_bytes, file_type_enum_member)
        logger.info(f"Text extraction completed for document {document_id}. Chars: {len(extracted_text) if extracted_text else 0}")

        if extracted_text is None: # Should mean error during extraction or unsupported by func
            logger.warning(f"Text extraction returned None for document {document.id} ({document.file_type}). Setting text to empty string.")
            extracted_text = "" # Ensure it's a string for len() and API call

        character_count = len(extracted_text)
        words = re.split(r'\s+', extracted_text.strip())
        word_count = len([word for word in words if word])
        logger.info(f"Calculated counts for document {document_id}: Chars={character_count}, Words={word_count}")

    except FileNotFoundError:
        logger.error(f"File not found in blob storage for document {document_id} at path {document.storage_blob_path}", exc_info=True)
        await crud.update_document_status(
            document_id=document.id, 
            teacher_id=auth_teacher_id, 
            status=DocumentStatus.ERROR,
        )
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error accessing document file for text extraction.")
    except ValueError as e: 
        logger.error(f"Text extraction error for document {document.id}: {e}", exc_info=True)
        await crud.update_document_status(
            document_id=document.id, 
            teacher_id=auth_teacher_id, 
            status=DocumentStatus.ERROR
        )
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id)
        # Check if it's the specific error from extract_text_from_bytes for unsupported types
        if "Unsupported file type for text extraction" in str(e):
             raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(e))
        else:
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Text extraction processing error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during text extraction for document {document_id}: {e}", exc_info=True)
        await crud.update_document_status(
            document_id=document.id, 
            teacher_id=auth_teacher_id, 
            status=DocumentStatus.ERROR
        )
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to extract text from document.")

    # Safeguard: extracted_text should not be None here due to prior handling, but double check.
    if extracted_text is None: 
        logger.error(f"Text extraction unexpectedly resulted in None for document {document_id} after error handling.")
        await crud.update_document_status(document_id=document.id, teacher_id=auth_teacher_id, status=DocumentStatus.ERROR)
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id)
        raise HTTPException(status_code=500, detail="Text content could not be extracted due to an internal error.")
        
    # --- ML API Call ---
    ai_score: Optional[float] = None
    ml_label: Optional[str] = None
    ml_ai_generated: Optional[bool] = None
    ml_human_generated: Optional[bool] = None
    ml_paragraph_results_raw: Optional[List[Dict[str, Any]]] = None

    try:
        ml_payload = {"text": extracted_text} # extracted_text is guaranteed to be a string now
        headers = {'Content-Type': 'application/json'}

        logger.info(f"Calling ML API for document {document_id} at {ML_API_URL} with text length {len(extracted_text)}")
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(ML_API_URL, json=ml_payload, headers=headers)
            response.raise_for_status()

            ml_response_data = response.json()
            logger.debug(f"ML API raw response for document {document_id}: {ml_response_data}") # Log raw for debug

            if isinstance(ml_response_data, dict):
                ml_ai_generated = ml_response_data.get("ai_generated")
                ml_human_generated = ml_response_data.get("human_generated")
                if not isinstance(ml_ai_generated, bool): ml_ai_generated = None
                if not isinstance(ml_human_generated, bool): ml_human_generated = None

                if ("results" in ml_response_data and isinstance(ml_response_data["results"], list)):
                    ml_paragraph_results_raw = ml_response_data["results"]
                    logger.info(f"Extracted {len(ml_paragraph_results_raw)} raw paragraph results for doc {document_id}.")
                    
                    if len(ml_paragraph_results_raw) > 0 and isinstance(ml_paragraph_results_raw[0], dict):
                        first_result_ml = ml_paragraph_results_raw[0] # Renamed to avoid clash
                        ml_label = first_result_ml.get("label")
                        if not isinstance(ml_label, str): ml_label = None

                        score_value = first_result_ml.get("probability")
                        if isinstance(score_value, (int, float)):
                            ai_score = float(score_value)
                            ai_score = max(0.0, min(1.0, ai_score)) # Clamp score
                            logger.info(f"Extracted overall AI probability score from first paragraph result: {ai_score} for doc {document_id}")
                        else:
                            logger.warning(f"ML API returned non-numeric probability in first result for doc {document_id}: {score_value}")
                            ai_score = None # Default to None if not valid
                    else: logger.warning(f"ML API 'results' list is empty or first item is not a dict for doc {document_id}.")
                else: logger.warning(f"ML API response missing 'results' list or not a list for doc {document_id}.")
            else: 
                logger.error(f"ML API response format unexpected (not a dict) for doc {document_id}: {ml_response_data}")
                raise ValueError("ML API response format unexpected.")

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error calling ML API for document {document_id}: {e.response.status_code} - {e.response.text}", exc_info=False) # exc_info=False to avoid logging full text in summary
        await crud.update_document_status(
            document_id=document_id,
            teacher_id=auth_teacher_id,
            status=DocumentStatus.ERROR,
            character_count=character_count,
            word_count=word_count
        )
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error communicating with AI detection service: Status {e.response.status_code}")
    except ValueError as e: # Catch specific ValueErrors from response processing
        logger.error(f"Error processing ML API response for document {document_id}: {e}", exc_info=True)
        await crud.update_document_status(
            document_id=document_id,
            teacher_id=auth_teacher_id,
            status=DocumentStatus.ERROR,
            character_count=character_count,
            word_count=word_count
        )
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to process AI detection result: {e}")
    except Exception as e: # Catch-all for other issues like timeouts, network errors before response
        logger.error(f"Unexpected error during ML API call or processing for document {document_id}: {e}", exc_info=True)
        await crud.update_document_status(
            document_id=document_id,
            teacher_id=auth_teacher_id,
            status=DocumentStatus.ERROR,
            character_count=character_count,
            word_count=word_count
        )
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get AI detection result due to an unexpected error: {type(e).__name__}")


    # --- Update DB with Result ---
    final_result_obj: Optional[Result] = None # Renamed to avoid clash with 'result' variable
    try:
        if not result: # Should not happen if creation logic above is sound
             logger.critical(f"CRITICAL: Result object is None before final update for doc {document_id}. This should not happen.")
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error: Result record vanished before final update.")

        update_payload_dict = {
            "status": ResultStatus.COMPLETED.value, 
            "result_timestamp": datetime.now(timezone.utc)
        }
        if ai_score is not None: update_payload_dict["score"] = ai_score
        if ml_label is not None: update_payload_dict["label"] = ml_label
        if ml_ai_generated is not None: update_payload_dict["ai_generated"] = ml_ai_generated
        if ml_human_generated is not None: update_payload_dict["human_generated"] = ml_human_generated
        
        if ml_paragraph_results_raw is not None:
            if isinstance(ml_paragraph_results_raw, list) and all(isinstance(item, dict) for item in ml_paragraph_results_raw):
                update_payload_dict["paragraph_results"] = ml_paragraph_results_raw
            else:
                logger.error(f"ml_paragraph_results_raw is not a list of dicts for doc {document_id}. Skipping save of paragraph_results.")

        logger.debug(f"Attempting to update Result {result.id} with payload: {update_payload_dict}")
        final_result_obj = await crud.update_result(result_id=result.id, update_data=update_payload_dict, teacher_id=auth_teacher_id)

        if final_result_obj:
            logger.info(f"Successfully updated result {final_result_obj.id} for document {document_id}")
            logger.debug(
                f"Calling update_document_status for COMPLETED. Doc ID: {document_id}, "
                f"Char Count: {character_count}, Word Count: {word_count}"
            )
            await crud.update_document_status(
                document_id=document_id,
                teacher_id=auth_teacher_id,
                status=DocumentStatus.COMPLETED,
                character_count=character_count, 
                word_count=word_count
            )
        else:
            logger.error(f"Failed to update result record for document {document_id} after ML processing. crud.update_result returned None.")
            await crud.update_document_status(
                document_id=document_id,
                teacher_id=auth_teacher_id,
                status=DocumentStatus.ERROR,
                character_count=character_count,
                word_count=word_count
            )
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save analysis results after ML processing.")

    except Exception as e: # Catch errors during the DB update phase
        logger.error(f"Failed to update database after ML API call for document {document_id}: {e}", exc_info=True)
        # Attempt to set document and result status to ERROR
        try:
            await crud.update_document_status(
                document_id=document_id,
                teacher_id=auth_teacher_id,
                status=DocumentStatus.ERROR,
                character_count=character_count, 
                word_count=word_count
            )
            if result: # result object should exist here
                await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id)
        except Exception as db_error_on_error:
            logger.error(f"Further error setting status to ERROR for doc {document_id} after initial DB update failure: {db_error_on_error}", exc_info=True)
        
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to save assessment result to database: {type(e).__name__}")


    if not final_result_obj: # Should have been caught by exceptions above, but as a final safeguard
       logger.error(f"Final result object is None after attempting DB update for doc {document_id}, and no exception was raised. This indicates a logic flaw.")
       raise HTTPException(status_code=500, detail="Failed to retrieve final result after update due to an unexpected internal state.")

    return final_result_obj


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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document with ID {document_id} not found or not accessible by user.")
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
        415: {"description": "Text extraction not supported for this file type or extraction failed"},
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
        try:
            file_type_enum_member = FileType(document.file_type.lower())
        except ValueError:
             logger.warning(f"Document {document_id} has an invalid file_type string '{document.file_type}' in DB for get_document_text.")
             file_type_enum_member = None # Handled below
    elif isinstance(document.file_type, FileType):
        file_type_enum_member = document.file_type

    if not file_type_enum_member:
        logger.error(f"Could not map document.file_type '{document.file_type}' to FileType enum for doc {document_id} in get_document_text")
        # This situation implies bad data or an unhandled file type string from the DB.
        # Returning 415 as it's effectively an unsupported type for this operation if we can't map it.
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, 
            detail="Could not determine file type for text extraction due to invalid stored type."
        )

    # Check if text extraction is supported for this file type by the service
    # (extract_text_from_bytes will also raise ValueError for unsupported types)
    if file_type_enum_member not in [FileType.PDF, FileType.DOCX, FileType.TXT, FileType.TEXT]: # Assuming PNG/JPG are not for plain text extraction here
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Plain text extraction is not supported for file type: {document.file_type}. Supported types for this endpoint: PDF, DOCX, TXT."
        )

    try:
        file_bytes = await download_blob_as_bytes(document.storage_blob_path)
        if file_bytes is None:
            logger.error(f"Failed to download blob {document.storage_blob_path} for document {document_id} text retrieval")
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Error downloading file content for text extraction.")
        
        logger.info(f"Offloading text extraction for document {document_id} (get_document_text) to a separate thread.")
        extracted_text = await asyncio.to_thread(extract_text_from_bytes, file_bytes, file_type_enum_member)
        
        if extracted_text is None:
            logger.warning(f"Text extraction returned None for document {document.id} ({document.file_type}) in get_document_text. This implies an extraction issue.")
            # Return empty string or consider 500 if None means a failure in extraction logic
            # Raising 415 might be more appropriate if 'None' means the type was ultimately not processable by extract_text_from_bytes
            raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Text extraction failed or resulted in no content for the given file type.")
            
        logger.info(f"Text extraction completed for document {document_id} (get_document_text). Chars: {len(extracted_text)}")
        return extracted_text
    except ValueError as e: # Catch specific ValueError from extract_text_from_bytes if it signals unsupported type
        logger.warning(f"ValueError during text extraction for {document.id} in get_document_text: {e}")
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(e))
    except Exception as e:
        logger.error(f"Error during text retrieval for document {document.id}: {e}", exc_info=True)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"An unexpected error occurred during text retrieval: {type(e).__name__}")

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
    sort_order_str: str = Query("desc", alias="sort_order", description="Sort order: 'asc' or 'desc'"), # Added alias
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to read list of documents with filters/sorting: student_id={student_id}, assignment_id={assignment_id}, status={status}, skip={skip}, limit={limit}, sort_by='{sort_by}', sort_order='{sort_order_str}'")

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
        status=status, # Pass the enum member directly if Pydantic handles conversion
        skip=skip,
        limit=limit,
        sort_by=sort_by,
        sort_order=sort_order_int
    )
    
    # Log limited info about the returned documents for brevity if many
    logged_doc_ids = [str(doc.id) for doc in documents[:5]] # Log IDs of first 5
    count_suffix = f"... (total {len(documents)})" if len(documents) > 5 else ""
    logger.debug(f"Returning {len(documents)} documents for GET /documents. IDs (first 5 or less): {logged_doc_ids}{count_suffix}")
    
    return documents

@router.put(
    "/{document_id}/status",
    response_model=Document,
    status_code=status.HTTP_200_OK,
    summary="Update a document's processing status (Protected)",
    description="Updates the processing status of a document. Requires authentication. (Typically for internal use or admin tasks)."
)
async def update_document_processing_status(
    document_id: uuid.UUID,
    status_update: DocumentUpdate, # Expects {'status': DocumentStatus} in request body
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    
    if status_update.status is None: # Pydantic model should enforce this, but good check
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Status field is required in the request body.")
    
    logger.info(f"User {user_kinde_id} attempting to update status for document ID: {document_id} to {status_update.status.value}")

    # Authorization: Check if the document exists AND belongs to the current user
    # crud.update_document_status should ideally handle this by taking teacher_id
    # First, verify existence and ownership if update_document_status doesn't return specific auth errors
    doc_to_check = await crud.get_document_by_id(document_id=document_id, teacher_id=user_kinde_id)
    if not doc_to_check:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found or access denied for user {user_kinde_id}."
        )

    # Proceed with update, passing teacher_id for the CRUD operation's own auth/scoping
    updated_document = await crud.update_document_status(
        document_id=document_id, 
        status=status_update.status, # Pass the enum member
        teacher_id=user_kinde_id # Crucial for scoped update
    )
    
    if updated_document is None:
        # This could happen if, despite the check, the document was deleted, or if update_document_status itself failed
        logger.error(f"Failed to update status for doc {document_id} for user {user_kinde_id}, possibly due to internal CRUD issue or race condition.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, # Or 500 if it implies an internal error post-check
            detail=f"Document {document_id} not found during status update attempt or update failed."
        )
    
    logger.info(f"Document {document_id} status successfully updated to {updated_document.status.value} by user {user_kinde_id}.")
    return updated_document

@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document and associated data (Protected)",
    description="Soft-deletes a document metadata record, and attempts to delete the associated file from Blob Storage and the analysis result. Requires authentication."
)
async def delete_document_endpoint( # Renamed to avoid conflict with imported delete_document if any
    document_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to delete document ID: {document_id}")

    try:
        # crud.delete_document is expected to handle auth via teacher_id, blob deletion, result deletion, and soft delete
        success = await crud.delete_document(document_id=document_id, teacher_id=user_kinde_id)

        if not success:
            # This implies the document wasn't found for that user, or some part of the delete operation failed internally in CRUD
            logger.warning(f"crud.delete_document returned False for document {document_id} initiated by user {user_kinde_id}. Document likely not found or delete failed.")
            # CRUD should raise specific exceptions if possible, but if it returns bool:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found or delete operation failed.")

        logger.info(f"Successfully processed delete request for document {document_id} by user {user_kinde_id}.")
        # No content returned for 204
    
    except HTTPException: # Re-raise HTTPExceptions we know about (like the 404 above)
        raise
    except Exception as e: 
        logger.error(f"Unexpected error in delete document endpoint for {document_id} by user {user_kinde_id}: {e}", exc_info=True)
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
    logger.info(f"User {user_kinde_id} attempting to upload batch of {len(files)} documents with priority {priority.value}")

    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files provided in the batch.")

    batch_data = BatchCreate(
        teacher_id=user_kinde_id, # user_id in Batch model, maps to teacher_id here
        total_files=len(files),
        status=BatchStatus.UPLOADING, # Initial status
        priority=priority
    )
    batch = await crud.create_batch(batch_in=batch_data)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create batch record"
        )
    logger.info(f"Batch {batch.id} created for user {user_kinde_id}.")

    created_documents_in_batch = []
    failed_files_info = []
    now = datetime.now(timezone.utc)

    # Map BatchPriority to an integer for Document.processing_priority
    priority_value_map = {
        BatchPriority.LOW: 0,
        BatchPriority.NORMAL: 1,
        BatchPriority.HIGH: 2,
        BatchPriority.URGENT: 3,
    }
    doc_processing_priority = priority_value_map.get(priority, 1) # Default to NORMAL's value

    for index, file in enumerate(files):
        original_filename = file.filename or f"unknown_file_{index+1}"
        try:
            logger.info(f"Processing file {index+1}/{len(files)}: '{original_filename}' for batch {batch.id}")
            
            content_type = file.content_type
            file_extension = os.path.splitext(original_filename)[1].lower()
            file_type_enum: Optional[FileType] = None
            
            if file_extension == ".pdf" and content_type == "application/pdf": file_type_enum = FileType.PDF
            elif file_extension == ".docx" and content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document": file_type_enum = FileType.DOCX
            elif file_extension == ".txt" and (content_type == "text/plain" or file_extension == ".txt"): file_type_enum = FileType.TXT # More lenient for .txt
            elif file_extension == ".png" and content_type == "image/png": file_type_enum = FileType.PNG
            elif file_extension in [".jpg", ".jpeg"] and content_type == "image/jpeg": file_type_enum = FileType.JPG

            if file_type_enum is None:
                logger.warning(f"Unsupported file type for '{original_filename}' (type: {content_type}, ext: {file_extension}) in batch {batch.id}.")
                failed_files_info.append({
                    "filename": original_filename,
                    "error": f"Unsupported file type: {content_type or file_extension}"
                })
                continue

            blob_name = await upload_file_to_blob(upload_file=file)
            if not blob_name:
                logger.error(f"Failed to upload '{original_filename}' to storage for batch {batch.id}.")
                failed_files_info.append({
                    "filename": original_filename,
                    "error": "Failed to upload to storage"
                })
                continue
            logger.info(f"File '{original_filename}' uploaded to blob: {blob_name} for batch {batch.id}")

            document_data = DocumentCreate(
                original_filename=original_filename,
                storage_blob_path=blob_name,
                file_type=file_type_enum,
                upload_timestamp=now,
                student_id=student_id,
                assignment_id=assignment_id,
                status=DocumentStatus.UPLOADED, # Initial status before queuing attempt
                batch_id=batch.id,
                # queue_position= Not setting here, worker might manage or not needed if priority used
                processing_priority=doc_processing_priority, 
                teacher_id=user_kinde_id
            )
            
            document = await crud.create_document(document_in=document_data)
            if not document:
                logger.error(f"Failed to create document record for '{original_filename}' in batch {batch.id}.")
                # TODO: Consider deleting blob if DB record fails
                failed_files_info.append({
                    "filename": original_filename,
                    "error": "Failed to create document record"
                })
                continue
            logger.info(f"Document record {document.id} created for '{original_filename}' in batch {batch.id}")

            result_data = ResultCreate(
                score=None, status=ResultStatus.PENDING, result_timestamp=now, 
                document_id=document.id, teacher_id=user_kinde_id
            )
            created_result_for_doc = await crud.create_result(result_in=result_data) # Renamed var
            if created_result_for_doc:
                logger.info(f"Initial Result record {created_result_for_doc.id} created for Document {document.id} in batch {batch.id}")
            else:
                logger.error(f"Failed to create initial Result for Document {document.id} in batch {batch.id}. Document status remains UPLOADED.")
                # Document will proceed to enqueue, but processor must handle missing initial result.

            enqueue_success_for_doc = await enqueue_assessment_task( # Renamed var
                document_id=document.id,
                user_id=user_kinde_id,
                priority_level=doc_processing_priority,
            )
            if enqueue_success_for_doc:
                updated_doc_status = await crud.update_document_status(
                    document_id=document.id,
                    teacher_id=user_kinde_id,
                    status=DocumentStatus.QUEUED,
                )
                if updated_doc_status:
                    document = updated_doc_status # Refresh document with new status
                    logger.info(f"Document {document.id} successfully enqueued for batch {batch.id}, status QUEUED.")
                else: # Should be rare
                    logger.error(f"Document {document.id} enqueued for batch {batch.id}, but failed to update status to QUEUED. Remains {document.status.value}.")
            else:
                logger.error(f"Failed to enqueue document {document.id} for batch {batch.id}. Updating status to ERROR.")
                error_doc_status = await crud.update_document_status(
                    document_id=document.id, teacher_id=user_kinde_id, status=DocumentStatus.ERROR
                )
                if error_doc_status: document = error_doc_status # Refresh document
                else: logger.critical(f"Failed to update doc {document.id} to ERROR after enqueue failure for batch {batch.id}")
            
            created_documents_in_batch.append(document) # Add document regardless of minor enqueue/status update issues, main object exists

        except Exception as e:
            logger.error(f"Unhandled error processing file '{original_filename}' in batch {batch.id}: {str(e)}", exc_info=True)
            failed_files_info.append({
                "filename": original_filename,
                "error": f"Unexpected processing error: {type(e).__name__}"
            })
    # After processing all files in the loop
    final_batch_status = BatchStatus.QUEUED
    if not created_documents_in_batch and failed_files_info: # All files failed
        final_batch_status = BatchStatus.ERROR
    elif failed_files_info: # Some files failed
        final_batch_status = BatchStatus.PARTIAL_FAILURE
    elif not created_documents_in_batch and not failed_files_info: # No files processed, no errors recorded (e.g. empty input list already handled)
        final_batch_status = BatchStatus.COMPLETED # Or ERROR if this state is unexpected
        if not files: final_batch_status = BatchStatus.EMPTY # Custom state or handle as error

    batch_update_data = BatchUpdate(
        # completed_files are those successfully processed up to a terminal state by workers, not just uploaded.
        # This endpoint cannot determine 'completed_files' yet. This should be updated by workers.
        # For now, let's consider 'processed_files' as those for which a Document record was created.
        # The Batch model might need fields like 'successfully_uploaded_files' vs 'processed_by_worker_files'.
        # Let's assume 'completed_files' refers to fully processed by AI. So, 0 for now.
        completed_files=0, # This will be updated by workers.
        failed_files=len(failed_files_info), # Files that failed during this upload/initial enqueue step.
        status=final_batch_status,
        error_message=f"Failed to process {len(failed_files_info)} files during initial upload/enqueue." if failed_files_info else None
    )
    updated_batch = await crud.update_batch(batch_id=batch.id, batch_in=batch_update_data)
    if not updated_batch:
        # This is problematic, batch status not updated.
        logger.error(f"Failed to update final status for batch {batch.id}. Using originally created batch object for response.")
        updated_batch = batch # Fallback to original batch object for response structure

    if not created_documents_in_batch and files: # If input files were given, but none resulted in a document record
        logger.warning(f"No documents were successfully processed for batch {batch.id}. Failed files: {failed_files_info}")
        # Return the updated batch info along with errors.
        # The HTTP status is 201 (created batch), but the content indicates issues. Client should check 'failed_files_info'.
        # Or, raise 422 if no files could be processed at all.
        # For consistency, if batch is created, return 201. Client must inspect response.
        # If we want to signal full failure more strongly:
        # raise HTTPException(
        # status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, # Or 500 if it's server-side issues mostly
        # detail={
        # "message": "Failed to process any files in the batch.",
        # "batch_id": updated_batch.id,
        # "batch_status": updated_batch.status.value,
        # "failed_files_details": failed_files_info
        # }
        # )
    
    # Ensure updated_batch is not None for the response model.
    # If crud.update_batch failed and returned None, updated_batch was set to the original 'batch'.
    # The BatchWithDocuments model expects a valid Batch object.

    return BatchWithDocuments(
        id=updated_batch.id,
        user_id=updated_batch.user_id,
        created_at=updated_batch.created_at,
        updated_at=updated_batch.updated_at,
        total_files=updated_batch.total_files,
        completed_files=updated_batch.completed_files,
        failed_files=len(failed_files_info), # Use count from this endpoint's processing
        status=updated_batch.status,
        priority=updated_batch.priority,
        error_message=updated_batch.error_message,
        document_ids=[doc.id for doc in created_documents_in_batch],
        # Add failed_files_info to the response if your BatchWithDocuments model supports it
        # For now, it's not part of the standard model, so relying on batch.error_message
    )


@router.get(
    "/batch/{batch_id}",
    response_model=BatchWithDocuments, # Assuming this includes document details or IDs
    status_code=status.HTTP_200_OK,
    summary="Get batch upload status (Protected)",
    description="Get the status of a batch upload including documents in the batch. Requires authentication."
)
async def get_batch_status(
    batch_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to get status for batch ID: {batch_id}")
    
    batch = await crud.get_batch_by_id(batch_id=batch_id) # Fetches the batch record
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Batch with ID {batch_id} not found."
        )

    # Authorization check: Batch model has user_id (which is Kinde sub)
    if batch.user_id != user_kinde_id:
        logger.warning(f"User {user_kinde_id} forbidden to access batch {batch_id} owned by {batch.user_id}.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this batch."
        )

    # Get all documents associated with this batch_id
    # This assumes your CRUD layer has a function like get_documents_by_batch_id
    # And that these documents are also filtered by the teacher_id for security,
    # although batch ownership check is primary here.
    documents_in_batch = await crud.get_documents_by_batch_id(batch_id=batch_id, teacher_id=user_kinde_id)
    
    # Construct the response using BatchWithDocuments model
    # Ensure all fields required by BatchWithDocuments are populated from 'batch' and 'documents_in_batch'
    return BatchWithDocuments(
        id=batch.id,
        user_id=batch.user_id,
        created_at=batch.created_at,
        updated_at=batch.updated_at,
        total_files=batch.total_files,
        completed_files=batch.completed_files, # This reflects worker updates
        failed_files=batch.failed_files,       # This reflects worker updates or initial upload failures
        status=batch.status,
        priority=batch.priority,
        error_message=batch.error_message,
        document_ids=[doc.id for doc in documents_in_batch]
        # If BatchWithDocuments is meant to return full Document objects:
        # documents=documents_in_batch 
    )


@router.post(
    "/{document_id}/reset",
    status_code=status.HTTP_200_OK,
    summary="Reset a stuck document assessment (Protected)",
    description="Sets the status of a document and its associated result back to ERROR. Useful for assessments stuck in PROCESSING/ASSESSING.",
    response_model=Dict[str, str] 
)
async def reset_assessment_status(
    document_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    # No need to check user_kinde_id for None, Depends(get_current_user_payload) handles unauthorized

    logger.info(f"User {user_kinde_id} attempting to RESET status for document {document_id}")

    document = await crud.get_document_by_id(document_id=document_id, teacher_id=user_kinde_id, include_deleted=True)
    if not document:
        logger.warning(f"Reset attempt failed: Document {document_id} not found or not owned by user {user_kinde_id}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found or access denied.")

    # Document exists and belongs to the user. Proceed to update status.
    # Use document.teacher_id from the fetched document to ensure correct ownership context for updates.
    auth_teacher_id_for_update = document.teacher_id 
    if not auth_teacher_id_for_update: # Should not happen if fetched with teacher_id scope
        logger.error(f"Critical: auth_teacher_id_for_update is missing for document {document.id} during reset by user {user_kinde_id}")
        raise HTTPException(status_code=500, detail="Internal error: Teacher ID missing for reset operation.")


    logger.info(f"Resetting document {document.id} (current status: {document.status.value}) to ERROR.")
    updated_doc = await crud.update_document_status(
        document_id=document.id,
        teacher_id=auth_teacher_id_for_update, 
        status=DocumentStatus.ERROR
        # Not passing char/word counts as they are not being recalculated here.
    )
    if not updated_doc:
        logger.error(f"Failed to update document status to ERROR during reset for {document.id}.")
        # Continue to attempt result reset, but this is an issue.

    # Reset associated result status
    result_to_reset = await crud.get_result_by_document_id(document_id=document.id, teacher_id=auth_teacher_id_for_update, include_deleted=True) # Fetch with auth
    updated_result = None
    if result_to_reset:
        logger.info(f"Resetting result {result_to_reset.id} (current status: {result_to_reset.status.value}) to ERROR for document {document.id}.")
        updated_result = await crud.update_result(
            result_id=result_to_reset.id,
            teacher_id=auth_teacher_id_for_update, # Pass teacher_id here if crud.update_result supports it for scoping
            update_data={"status": ResultStatus.ERROR.value} # Ensure enum value is passed if model expects it
        )
        if not updated_result:
            logger.error(f"Failed to update result status to ERROR during reset for result {result_to_reset.id} (doc: {document.id}).")
    else:
        logger.warning(f"No result record found to reset for document {document.id}. Document status may have been reset if update_doc succeeded.")

    # Final status check and response
    if not updated_doc and (not result_to_reset or not updated_result):
        # If doc update failed AND (no result OR result update failed) -> major failure
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to reset document and/or result status.")
    if not updated_doc: # Doc update failed, but result might have been ok or not present
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to reset document status, though result may have been handled.")
    if result_to_reset and not updated_result: # Doc update ok, but result update failed
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Document status reset, but failed to reset result status.")


    logger.info(f"Successfully processed reset request for document {document_id}. Final document status: {updated_doc.status.value if updated_doc else 'ERROR (update failed)'}.")
    return {"message": f"Successfully reset assessment status for document {document_id} to ERROR."}


@router.post(
    "/{document_id}/cancel",
    status_code=status.HTTP_200_OK,
    summary="Cancel a stuck document assessment (Protected)",
    description="Sets the status of a document (if PROCESSING or QUEUED) and its associated result (if ASSESSING or PENDING) back to ERROR. Useful for stopping an assessment.",
    response_model=Dict[str, str] 
)
async def cancel_assessment_status(
    document_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to CANCEL assessment for document {document_id}")

    document = await crud.get_document_by_id(document_id=document_id, teacher_id=user_kinde_id, include_deleted=True) # Allow operating on soft-deleted if needed by logic
    if not document:
        logger.warning(f"Cancel attempt failed: Document {document_id} not found or not owned by user {user_kinde_id}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found or access denied.")

    auth_teacher_id_for_update = document.teacher_id
    if not auth_teacher_id_for_update:
        logger.error(f"Critical: auth_teacher_id_for_update is missing for document {document.id} during cancel by user {user_kinde_id}")
        raise HTTPException(status_code=500, detail="Internal error: Teacher ID missing for cancel operation.")

    # Check if document is in a state that can be cancelled
    # Typically, PROCESSING, or QUEUED. If already COMPLETED or ERROR, cancel might not make sense.
    cancellable_doc_statuses = [DocumentStatus.PROCESSING, DocumentStatus.QUEUED, DocumentStatus.UPLOADED] # Added UPLOADED
    if document.status not in cancellable_doc_statuses:
        logger.warning(f"Document {document.id} is in status '{document.status.value}', which is not cancellable. Valid cancellable statuses: {[s.value for s in cancellable_doc_statuses]}.")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Cannot cancel assessment. Document status is '{document.status.value}'.")

    logger.info(f"Cancelling document {document.id} (current status: {document.status.value}) by setting its status to ERROR.")
    updated_doc = await crud.update_document_status(
        document_id=document.id,
        teacher_id=auth_teacher_id_for_update,
        status=DocumentStatus.ERROR
    )
    if not updated_doc:
        logger.error(f"Failed to update document status to ERROR during cancel for {document.id}.")
        # Continue to attempt result update, but this is an issue.

    # Update associated result status to ERROR if it's in PENDING or ASSESSING
    result_to_cancel = await crud.get_result_by_document_id(document_id=document.id, teacher_id=auth_teacher_id_for_update, include_deleted=True)
    updated_cancelled_result = None # Renamed
    result_handling_successful = True # Assume true if no result or if update succeeds

    if result_to_cancel:
        cancellable_result_statuses = [ResultStatus.PENDING, ResultStatus.ASSESSING]
        if result_to_cancel.status in cancellable_result_statuses:
            logger.info(f"Cancelling result {result_to_cancel.id} (current status: {result_to_cancel.status.value}) to ERROR for document {document.id}.")
            updated_cancelled_result = await crud.update_result(
                result_id=result_to_cancel.id,
                teacher_id=auth_teacher_id_for_update,
                update_data={"status": ResultStatus.ERROR.value}
            )
            if not updated_cancelled_result:
                logger.error(f"Failed to update result status to ERROR during cancel for result {result_to_cancel.id} (doc: {document.id}).")
                result_handling_successful = False
        else:
            logger.info(f"Result {result_to_cancel.id} for document {document.id} is in status '{result_to_cancel.status.value}'. No status change needed for result during cancel.")
    else:
        logger.warning(f"No result record found to cancel for document {document.id}. Document status may have been updated if doc update succeeded.")

    # Final status check and response
    if not updated_doc and not result_handling_successful : # Both failed
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to cancel document and also failed to handle its result appropriately.")
    if not updated_doc: # Document update failed, result handling might have been ok or N/A
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to cancel document status, though result may have been handled.")
    if not result_handling_successful : # Document update ok, but result handling failed
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Document status cancelled to ERROR, but failed to update associated result status.")
    
    final_doc_status_val = updated_doc.status.value if updated_doc else "ERROR (update failed)"
    logger.info(f"Successfully processed cancel request for document {document_id}. Final document status: {final_doc_status_val}.")
    return {"message": f"Successfully cancelled assessment for document {document_id}. Status set to ERROR."}