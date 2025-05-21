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

# --- RESOLVED CONFLICT 1: Imports ---
# Import Blob Storage Service
from ....services.blob_storage import upload_file_to_blob, download_blob_as_bytes # Relative import

# Import Text Extraction Service
from ....services.text_extraction import extract_text_from_bytes # Relative import
from ....queue import enqueue_assessment_task # Relative import (ensured present once)
# --- END RESOLVED CONFLICT 1 ---

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
    student_id: uuid.UUID = Form(..., description="Internal ID of the student associated with the document"),
    assignment_id: uuid.UUID = Form(..., description="ID of the assignment associated with the document"),
    file: UploadFile = File(..., description="The document file to upload (PDF, DOCX, TXT, PNG, JPG)"),
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    original_filename = file.filename or "unknown_file"
    logger.info(f"User {user_kinde_id} attempting to upload document '{original_filename}' for student {student_id}, assignment {assignment_id}")

    logger.warning(f"Authorization check needed for user {user_kinde_id} uploading for student {student_id} / assignment {assignment_id}")

    content_type = file.content_type
    file_extension = os.path.splitext(original_filename)[1].lower()
    file_type_enum : Optional[FileType] = None
    if file_extension == ".pdf" and content_type == "application/pdf": file_type_enum = FileType.PDF
    elif file_extension == ".docx" and content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document": file_type_enum = FileType.DOCX
    elif file_extension == ".txt" and content_type == "text/plain": file_type_enum = FileType.TXT
    elif file_extension == ".png" and content_type == "image/png": file_type_enum = FileType.PNG
    elif file_extension in [".jpg", ".jpeg"] and content_type == "image/jpeg": file_type_enum = FileType.JPG
    elif file_extension == ".txt" and file_type_enum is None: file_type_enum = FileType.TEXT

    if file_type_enum is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {original_filename} ({content_type}). Supported types: PDF, DOCX, TXT, PNG, JPG/JPEG."
        )

    try:
        blob_name = await upload_file_to_blob(upload_file=file)
        if blob_name is None:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,"Failed to upload file to storage.")
    except Exception as e:
        logger.error(f"Error during file upload service call: {e}", exc_info=True)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,"An error occurred during file upload processing.")

    now = datetime.now(timezone.utc)
    # Initial status changed to UPLOADED as per previous resolutions. Will be QUEUED after successful enqueue.
    document_data = DocumentCreate(
        original_filename=original_filename,
        storage_blob_path=blob_name,
        file_type=file_type_enum,
        upload_timestamp=now,
        student_id=student_id,
        assignment_id=assignment_id,
        status=DocumentStatus.UPLOADED, 
        teacher_id=user_kinde_id
    )
    created_document = await crud.create_document(document_in=document_data)
    if not created_document:
        logger.error(f"Failed to create document metadata record in DB for blob {blob_name}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,"Failed to save document metadata after upload.")

    result_data = ResultCreate(
        score=None, status=ResultStatus.PENDING, result_timestamp=now, document_id=created_document.id, teacher_id=user_kinde_id
    )
    created_result = await crud.create_result(result_in=result_data)
    if not created_result:
        logger.error(f"Failed to create initial pending result record for document {created_document.id}")

    # Enqueue document for assessment - (This logic was based on my refined version from a previous turn)
    enqueue_success = await enqueue_assessment_task(
        document_id=created_document.id,
        user_id=user_kinde_id,
        priority_level=created_document.processing_priority or 0,
    )

    if enqueue_success:
        updated_doc = await crud.update_document_status(
            document_id=created_document.id,
            teacher_id=user_kinde_id,
            status=DocumentStatus.QUEUED, # Change from UPLOADED to QUEUED
        )
        if updated_doc:
            created_document = updated_doc
            logger.info(f"Document {created_document.id} uploaded and successfully queued for assessment.")
        else:
            logger.error(f"Document {created_document.id} enqueued, but failed to update status to QUEUED. Current status: {created_document.status.value}")
    else:
        logger.error(f"Failed to enqueue assessment task for document {created_document.id}. Updating status to ERROR.")
        error_doc = await crud.update_document_status(
            document_id=created_document.id,
            teacher_id=user_kinde_id,
            status=DocumentStatus.ERROR, # Set to ERROR if enqueue fails
        )
        if error_doc:
            created_document = error_doc
        else:
            logger.critical(f"Failed to enqueue document {created_document.id} AND failed to update its status to ERROR.")
            
    return created_document


@router.post(
    "/{document_id}/assess",
    response_model=Result,
    status_code=status.HTTP_200_OK,
    summary="Trigger AI Assessment and get Result (Protected)",
    description="Fetches document text, calls the external ML API for AI detection, "
                "updates the result/document status, and returns the final result. "
                "Requires authentication."
)
async def trigger_assessment(
    document_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to trigger assessment for document ID: {document_id}")

    document = await crud.get_document_by_id(
        document_id=document_id,
        teacher_id=user_kinde_id
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document with ID {document_id} not found or not accessible by user.")

    auth_teacher_id = document.teacher_id if document.teacher_id else user_kinde_id
    if not auth_teacher_id:
        logger.error(f"Critical: teacher_id is missing for document {document_id} during assessment trigger by user {user_kinde_id}.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error: Missing teacher identifier.")

    logger.warning(f"Authorization check needed for user {user_kinde_id} triggering assessment for document {document_id}")

    # --- RESOLVED CONFLICT 2: Document status check ---
    # Combining statuses from both branches for when assessment can be triggered.
    # Allowing QUEUED from HEAD, and multi-line formatting.
    # Using RETRYING for existing_result.status from Codex.
    if document.status not in [
        DocumentStatus.UPLOADED,
        DocumentStatus.QUEUED,   # Added from HEAD branch logic
        DocumentStatus.ERROR,
        DocumentStatus.FAILED,
    ]:
        logger.warning(f"Document {document_id} status is '{document.status.value}'. Assessment cannot be triggered directly for this status.")
        existing_result = await crud.get_result_by_document_id(document_id=document_id, teacher_id=auth_teacher_id)
        if existing_result:
            if existing_result.status in [
                ResultStatus.COMPLETED,
                ResultStatus.ASSESSING,
                ResultStatus.RETRYING, # From Codex branch logic
            ]:
                logger.info(f"Assessment already completed or in progress for doc {document_id}. Returning existing result.")
                return existing_result
            # else: (if existing_result is PENDING or ERROR) - fall through to allow re-assessment
        else: # No existing result, and document status is not one that allows fresh assessment
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Assessment cannot be triggered. Document status is {document.status.value}, and no suitable existing result for re-assessment."
            )
    # --- END RESOLVED CONFLICT 2 ---

    await crud.update_document_status(document_id=document_id, teacher_id=auth_teacher_id, status=DocumentStatus.PROCESSING)
    result = await crud.get_result_by_document_id(document_id=document_id, teacher_id=auth_teacher_id)
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
        logger.info(f"Text extraction completed for document {document_id}. Chars: {len(extracted_text) if extracted_text is not None else 'None'}") # Use is not None for len

        # --- RESOLVED CONFLICT 3: Handle extracted_text is None ---
        if extracted_text is None:
            # This implies an error during extraction or an unsupported type by the extraction function itself.
            logger.warning(f"Text extraction returned None for document {document.id} ({document.file_type}). Setting text to empty string.")
            extracted_text = "" # Ensure it's a string for later use and API call
        
        # Calculate character count (moved after the None check and assignment to "")
        character_count = len(extracted_text)
        # --- END RESOLVED CONFLICT 3 ---
        words = re.split(r'\s+', extracted_text.strip())
        word_count = len([word for word in words if word])
        logger.info(f"Calculated counts for document {document_id}: Chars={character_count}, Words={word_count}")

    except FileNotFoundError:
        logger.error(f"File not found in blob storage for document {document_id} at path {document.storage_blob_path}", exc_info=True)
        await crud.update_document_status(document_id=document.id, teacher_id=auth_teacher_id, status=DocumentStatus.ERROR)
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error accessing document file for text extraction.")
    except ValueError as e: 
        logger.error(f"Text extraction error for document {document.id}: {e}", exc_info=True)
        await crud.update_document_status(document_id=document.id, teacher_id=auth_teacher_id, status=DocumentStatus.ERROR)
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id)
        # --- RESOLVED CONFLICT 4: ValueError handling ---
        # Using HEAD branch's more specific error message distinction
        if "Unsupported file type for text extraction" in str(e):
            raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(e))
        else:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Text extraction processing error: {e}")
        # --- END RESOLVED CONFLICT 4 ---
    except Exception as e:
        logger.error(f"Unexpected error during text extraction for document {document_id}: {e}", exc_info=True)
        await crud.update_document_status(document_id=document.id, teacher_id=auth_teacher_id, status=DocumentStatus.ERROR)
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to extract text from document.")

    # --- RESOLVED CONFLICT 5: Safeguard if extracted_text is None ---
    # Kept commented out as preferred by Codex branch, assuming prior logic handles it.
    # if extracted_text is None: 
    #     logger.error(f"Text extraction unexpectedly resulted in None for document {document_id} after error handling.")
    #     await crud.update_document_status(document_id=document.id, teacher_id=auth_teacher_id, status=DocumentStatus.ERROR)
    #     if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id)
    #     raise HTTPException(status_code=500, detail="Text content could not be extracted due to an internal error.")
    # --- END RESOLVED CONFLICT 5 ---
        
    ai_score: Optional[float] = None
    ml_label: Optional[str] = None
    ml_ai_generated: Optional[bool] = None
    ml_human_generated: Optional[bool] = None
    ml_paragraph_results_raw: Optional[List[Dict[str, Any]]] = None

    try:
        # --- RESOLVED CONFLICT 6: ML API Payload ---
        ml_payload = {"text": extracted_text} # extracted_text is guaranteed to be a string now
        # --- END RESOLVED CONFLICT 6 ---
        headers = {'Content-Type': 'application/json'}

        logger.info(f"Calling ML API for document {document_id} at {ML_API_URL} with text length {len(extracted_text)}")
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(ML_API_URL, json=ml_payload, headers=headers)
            response.raise_for_status()
            ml_response_data = response.json()
            logger.debug(f"ML API raw response for document {document_id}: {ml_response_data}")

            if isinstance(ml_response_data, dict):
                ml_ai_generated = ml_response_data.get("ai_generated")
                ml_human_generated = ml_response_data.get("human_generated")
                if not isinstance(ml_ai_generated, bool): ml_ai_generated = None
                if not isinstance(ml_human_generated, bool): ml_human_generated = None

                if ("results" in ml_response_data and isinstance(ml_response_data["results"], list)):
                    ml_paragraph_results_raw = ml_response_data["results"]
                    # Corrected indentation for the log based on analysis
                    logger.info(f"Extracted {len(ml_paragraph_results_raw)} raw paragraph results for doc {document_id}.")
                    
                    if len(ml_paragraph_results_raw) > 0 and isinstance(ml_paragraph_results_raw[0], dict):
                        # --- RESOLVED CONFLICT 7: Variable name ---
                        first_paragraph_result = ml_paragraph_results_raw[0] # Using clearer name from Codex
                        # --- END RESOLVED CONFLICT 7 ---
                        ml_label = first_paragraph_result.get("label")
                        if not isinstance(ml_label, str): ml_label = None
                        score_value = first_paragraph_result.get("probability")
                        if isinstance(score_value, (int, float)):
                            ai_score = float(score_value)
                            ai_score = max(0.0, min(1.0, ai_score))
                            logger.info(f"Extracted overall AI probability score from first paragraph result: {ai_score} for doc {document_id}")
                        else:
                            logger.warning(f"ML API returned non-numeric probability in first result for doc {document_id}: {score_value}")
                            ai_score = None
                    else: logger.warning(f"ML API 'results' list is empty or first item is not a dict for doc {document_id}.")
                else: logger.warning(f"ML API response missing 'results' list or not a list for doc {document_id}.")
            else: 
                logger.error(f"ML API response format unexpected (not a dict) for doc {document_id}: {ml_response_data}")
                raise ValueError("ML API response format unexpected.")

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error calling ML API for document {document_id}: {e.response.status_code} - {e.response.text}", exc_info=False)
        await crud.update_document_status(
            document_id=document_id, teacher_id=auth_teacher_id, status=DocumentStatus.ERROR,
            character_count=character_count, word_count=word_count
        )
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id)
        # --- RESOLVED CONFLICT 8: Exception detail ---
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error communicating with AI detection service: {e.response.status_code}") # Concise version
        # --- END RESOLVED CONFLICT 8 ---
    except ValueError as e:
        logger.error(f"Error processing ML API response for document {document_id}: {e}", exc_info=True)
        await crud.update_document_status(
            document_id=document_id, teacher_id=auth_teacher_id, status=DocumentStatus.ERROR,
            character_count=character_count, word_count=word_count
        )
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to process AI detection result: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during ML API call or processing for document {document_id}: {e}", exc_info=True)
        await crud.update_document_status(
            document_id=document_id, teacher_id=auth_teacher_id, status=DocumentStatus.ERROR,
            character_count=character_count, word_count=word_count
        )
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id)
        # --- RESOLVED CONFLICT 9: Exception detail ---
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get AI detection result: {e}") # More informative {e}
        # --- END RESOLVED CONFLICT 9 ---

    # --- RESOLVED CONFLICTS 10, 11, 12: DB Update logic ---
    final_result_obj: Optional[Result] = None 
    try:
        if not result: 
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
            await crud.update_document_status(
                document_id=document_id, teacher_id=auth_teacher_id, status=DocumentStatus.COMPLETED,
                character_count=character_count, word_count=word_count
            )
        else: 
            logger.error(f"Failed to update result record for document {document_id} after ML processing. crud.update_result returned None.")
            await crud.update_document_status(
                document_id=document_id, teacher_id=auth_teacher_id, status=DocumentStatus.ERROR,
                character_count=character_count, word_count=word_count
            )
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save analysis results after ML processing.")

    except Exception as e: 
        logger.error(f"Failed to update database after ML API call for document {document_id}: {e}", exc_info=True)
        try:
            await crud.update_document_status(
                document_id=document_id, teacher_id=auth_teacher_id, status=DocumentStatus.ERROR,
                character_count=character_count, word_count=word_count
            )
            if result: 
                await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id)
        except Exception as db_error_on_error:
            logger.error(f"Further error setting status to ERROR for doc {document_id} after initial DB update failure: {db_error_on_error}", exc_info=True)
        
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to save assessment result to database: {e}")

    if not final_result_obj: 
        logger.error(f"Final result object is None after attempting DB update for doc {document_id}, and no exception was raised. This indicates a logic flaw.")
        raise HTTPException(status_code=500, detail="Failed to retrieve final result after update due to an unexpected internal state.")
    # --- END RESOLVED CONFLICTS 10, 11, 12 ---

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
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to read document ID: {document_id}")
    document = await crud.get_document_by_id(document_id=document_id, teacher_id=user_kinde_id)
    if document is None:
        # --- RESOLVED CONFLICT 13: 404 detail ---
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document with ID {document_id} not found or not accessible by user.")
        # --- END RESOLVED CONFLICT 13 ---
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
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to retrieve text for document ID: {document_id}")

    document = await crud.get_document_by_id(document_id=document_id, teacher_id=user_kinde_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document with ID {document_id} not found or not accessible by user.")

    file_type_enum_member: Optional[FileType] = None
    # --- RESOLVED CONFLICT 14: FileType conversion ---
    if isinstance(document.file_type, str):
        try:
            file_type_enum_member = FileType(document.file_type.lower())
        except ValueError:
            logger.warning(f"Document {document_id} has an invalid file_type string '{document.file_type}' in DB for get_document_text.")
            file_type_enum_member = None 
    # --- END RESOLVED CONFLICT 14 ---
    elif isinstance(document.file_type, FileType):
        file_type_enum_member = document.file_type

    if not file_type_enum_member:
        logger.error(f"Could not map document.file_type '{document.file_type}' to FileType enum for doc {document_id} in get_document_text")
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Could not determine file type for text extraction due to invalid stored type.")

    if file_type_enum_member not in [FileType.PDF, FileType.DOCX, FileType.TXT, FileType.TEXT]:
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
        
        # --- RESOLVED CONFLICT 15: Handling extracted_text is None ---
        if extracted_text is None:
            logger.warning(f"Text extraction returned None for document {document.id} ({document.file_type}) in get_document_text. This implies an extraction issue or unsupported content.")
            raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Text extraction failed or resulted in no content for the given file type.")
            
        logger.info(f"Text extraction completed for document {document_id} (get_document_text). Chars: {len(extracted_text)}")
        return extracted_text
        # --- END RESOLVED CONFLICT 15 ---
    except ValueError as e: 
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
    sort_order_str: str = Query("desc", alias="sort_order", description="Sort order: 'asc' or 'desc'"),
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    # --- RESOLVED CONFLICT 16a: Initial Log ---
    logger.info(f"User {user_kinde_id} attempting to read list of documents with filters/sorting: student_id={student_id}, assignment_id={assignment_id}, status={status}, skip={skip}, limit={limit}, sort_by='{sort_by}', sort_order='{sort_order_str}'")
    # --- END RESOLVED CONFLICT 16a ---

    sort_order_int: int
    if sort_order_str.lower() == "asc": sort_order_int = 1
    elif sort_order_str.lower() == "desc": sort_order_int = -1
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid sort_order value. Use 'asc' or 'desc'.")

    documents = await crud.get_all_documents(
        teacher_id=user_kinde_id, student_id=student_id, assignment_id=assignment_id,
        status=status, skip=skip, limit=limit, sort_by=sort_by, sort_order=sort_order_int
    )
    
    # --- RESOLVED CONFLICT 16b: Return Log ---
    logged_doc_ids = [str(doc.id) for doc in documents[:5]] 
    count_suffix = f"... (total {len(documents)})" if len(documents) > 5 else ""
    logger.debug(f"Returning {len(documents)} documents for GET /documents. IDs (first 5 or less): {logged_doc_ids}{count_suffix}")
    # --- END RESOLVED CONFLICT 16b ---
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
    # --- RESOLVED CONFLICT 17: Parameter comment ---
    status_update: DocumentUpdate, # Expects {'status': DocumentStatus} in request body
    # --- END RESOLVED CONFLICT 17 ---
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    
    if status_update.status is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Status field is required in the request body.")
    # Using .value for logging enum string
    logger.info(f"User {user_kinde_id} attempting to update status for document ID: {document_id} to {status_update.status.value}")

    # Using HEAD's comments and variable name doc_to_check
    # Authorization: Check if the document exists AND belongs to the current user
    # crud.update_document_status should ideally handle this by taking teacher_id
    # First, verify existence and ownership if update_document_status doesn't return specific auth errors
    doc_to_check = await crud.get_document_by_id(document_id=document_id, teacher_id=user_kinde_id)
    if not doc_to_check:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document with ID {document_id} not found or access denied for user {user_kinde_id}.")

    # --- RESOLVED CONFLICT 18: Update logic and error handling ---
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
    # --- END RESOLVED CONFLICT 18 ---
    return updated_document

@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document and associated data (Protected)",
    description="Soft-deletes a document metadata record, and attempts to delete the associated file from Blob Storage and the analysis result. Requires authentication."
)
# --- RESOLVED CONFLICT 19: Function name (no change needed, just ensuring one version) ---
async def delete_document_endpoint(
# --- END RESOLVED CONFLICT 19 ---
    document_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to delete document ID: {document_id}")

    try:
        # --- RESOLVED CONFLICT 20: Comment ---
        # crud.delete_document is expected to handle auth via teacher_id, blob deletion, result deletion, and soft delete
        # --- END RESOLVED CONFLICT 20 ---
        success = await crud.delete_document(document_id=document_id, teacher_id=user_kinde_id)
        if not success:
            logger.warning(f"crud.delete_document returned False for document {document_id} initiated by user {user_kinde_id}. Document likely not found or delete failed.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found or delete operation failed.")
        
        # --- RESOLVED CONFLICT 21: Comments in exception block ---
        logger.info(f"Successfully processed delete request for document {document_id} by user {user_kinde_id}.")
        # No content returned for 204
    
    except HTTPException: # Re-raise HTTPExceptions we know about (like the 404 above)
        raise
    except Exception as e: 
        logger.error(f"Unexpected error in delete document endpoint for {document_id} by user {user_kinde_id}: {e}", exc_info=True)
        # --- END RESOLVED CONFLICT 21 ---
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
        # --- RESOLVED CONFLICT 22: Comment for teacher_id ---
        teacher_id=user_kinde_id, # user_id in Batch model, maps to teacher_id here
        # --- END RESOLVED CONFLICT 22 ---
        total_files=len(files),
        status=BatchStatus.UPLOADING, 
        priority=priority
    )
    batch = await crud.create_batch(batch_in=batch_data)
    if not batch:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create batch record")
    logger.info(f"Batch {batch.id} created for user {user_kinde_id}.")

    # --- RESOLVED CONFLICT 23: Variable names for lists ---
    created_documents_in_batch = [] 
    failed_files_info = []      
    # --- END RESOLVED CONFLICT 23 ---
    now = datetime.now(timezone.utc) # Initialized once outside the loop

    priority_value_map = { BatchPriority.LOW: 0, BatchPriority.NORMAL: 1, BatchPriority.HIGH: 2, BatchPriority.URGENT: 3 }
    doc_processing_priority = priority_value_map.get(priority, 1)

    # --- RESOLVED CONFLICT 24a: Loop variable ---
    for index, file_item in enumerate(files): # Using enumerate for index, file_item for clarity
    # --- END RESOLVED CONFLICT 24a ---
        original_filename = file_item.filename or f"unknown_file_{index+1}" # Using index
        try:
            logger.info(f"Processing file {index+1}/{len(files)}: '{original_filename}' for batch {batch.id}")
            
            content_type = file_item.content_type
            file_extension = os.path.splitext(original_filename)[1].lower()
            file_type_enum: Optional[FileType] = None
            
            if file_extension == ".pdf" and content_type == "application/pdf": file_type_enum = FileType.PDF
            elif file_extension == ".docx" and content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document": file_type_enum = FileType.DOCX
            # --- RESOLVED CONFLICT 24b: TXT file type check ---
            elif file_extension == ".txt" and (content_type == "text/plain" or file_extension == ".txt"): file_type_enum = FileType.TXT # More lenient
            # --- END RESOLVED CONFLICT 24b ---
            elif file_extension == ".png" and content_type == "image/png": file_type_enum = FileType.PNG
            elif file_extension in [".jpg", ".jpeg"] and content_type == "image/jpeg": file_type_enum = FileType.JPG

            # --- RESOLVED CONFLICT 25: Logging and error detail for unsupported file type ---
            if file_type_enum is None:
                logger.warning(f"Unsupported file type for '{original_filename}' (type: {content_type}, ext: {file_extension}) in batch {batch.id}.")
                failed_files_info.append({
                    "filename": original_filename,
                    "error": f"Unsupported file type: {content_type or file_extension}"
                })
                continue
            # --- END RESOLVED CONFLICT 25 ---

            # --- RESOLVED CONFLICT 26: upload_file_to_blob call and logging ---
            blob_name = await upload_file_to_blob(upload_file=file_item) # Using file_item
            if not blob_name:
                logger.error(f"Failed to upload '{original_filename}' to storage for batch {batch.id}.")
                failed_files_info.append({"filename": original_filename, "error": "Failed to upload to storage"})
                continue
            logger.info(f"File '{original_filename}' uploaded to blob: {blob_name} for batch {batch.id}")
            # 'now' is initialized outside the loop
            # --- END RESOLVED CONFLICT 26 ---
            
            # --- RESOLVED CONFLICT 27: DocumentCreate and create_document ---
            document_data = DocumentCreate(
                original_filename=original_filename, storage_blob_path=blob_name, file_type=file_type_enum,
                upload_timestamp=now, student_id=student_id, assignment_id=assignment_id,
                status=DocumentStatus.UPLOADED, # Initial status before queuing attempt
                batch_id=batch.id,
                # queue_position: Omitting as per HEAD's preference (priority driven)
                processing_priority=doc_processing_priority, 
                teacher_id=user_kinde_id
            )
            
            document = await crud.create_document(document_in=document_data) # Using 'document'
            if not document:
                logger.error(f"Failed to create document record for '{original_filename}' in batch {batch.id}.")
                # TODO: Consider deleting blob if DB record fails (from HEAD)
                failed_files_info.append({"filename": original_filename, "error": "Failed to create document record"})
                continue
            # --- END RESOLVED CONFLICT 27 --- (Conflict 28 was identical log)
            logger.info(f"Document record {document.id} created for '{original_filename}' in batch {batch.id}")

            # --- RESOLVED CONFLICT 29 & 30: Result creation and Enqueue logic ---
            # Using HEAD's variable naming style, logic is similar in both.
            result_data = ResultCreate(
                score=None, status=ResultStatus.PENDING, result_timestamp=now, 
                document_id=document.id, teacher_id=user_kinde_id
            )
            created_result_for_doc = await crud.create_result(result_in=result_data)
            if created_result_for_doc:
                logger.info(f"Initial Result record {created_result_for_doc.id} created for Document {document.id} in batch {batch.id}")
            else:
                logger.error(f"Failed to create initial Result for Document {document.id} in batch {batch.id}.")

            enqueue_success_for_doc = await enqueue_assessment_task(
                document_id=document.id, user_id=user_kinde_id, priority_level=doc_processing_priority,
            )
            if enqueue_success_for_doc:
                updated_doc_status = await crud.update_document_status(
                    document_id=document.id, teacher_id=user_kinde_id, status=DocumentStatus.QUEUED,
                )
                if updated_doc_status:
                    document = updated_doc_status 
                    logger.info(f"Document {document.id} successfully enqueued for batch {batch.id}, status QUEUED.")
                else: 
                    logger.error(f"Document {document.id} enqueued for batch {batch.id}, but failed to update status to QUEUED. Remains {document.status.value}.")
            else:
                logger.error(f"Failed to enqueue document {document.id} for batch {batch.id}. Updating status to ERROR.")
                error_doc_status = await crud.update_document_status(
                    document_id=document.id, teacher_id=user_kinde_id, status=DocumentStatus.ERROR
                )
                if error_doc_status: document = error_doc_status 
                else: logger.critical(f"Failed to update doc {document.id} to ERROR after enqueue failure for batch {batch.id}")
            
            created_documents_in_batch.append(document)
            # --- END RESOLVED CONFLICT 29 & 30 ---
        except Exception as e:
            logger.error(f"Unhandled error processing file '{original_filename}' in batch {batch.id}: {str(e)}", exc_info=True)
            failed_files_info.append({"filename": original_filename, "error": f"Unexpected processing error: {type(e).__name__}"})

    # --- RESOLVED CONFLICT 31: Final batch status and response ---
    final_batch_status = BatchStatus.QUEUED
    if not created_documents_in_batch and failed_files_info and files: # All files failed if files were provided
        final_batch_status = BatchStatus.ERROR
    elif failed_files_info: # Some files failed
        final_batch_status = BatchStatus.PARTIAL_FAILURE
    elif not created_documents_in_batch and not files: # No input files (should be caught earlier but defensive)
        final_batch_status = BatchStatus.EMPTY 
    elif not created_documents_in_batch and files : # Files provided, but none processed (all failed before doc creation)
        final_batch_status = BatchStatus.ERROR


    batch_update_data = BatchUpdate(
        completed_files=0, # This will be updated by workers.
        failed_files=len(failed_files_info), 
        status=final_batch_status,
        error_message=f"Failed to process {len(failed_files_info)} files during initial upload/enqueue." if failed_files_info else None
    )
    updated_batch = await crud.update_batch(batch_id=batch.id, batch_in=batch_update_data)
    if not updated_batch:
        logger.error(f"Failed to update final status for batch {batch.id}. Using originally created batch object for response.")
        updated_batch = batch 

    if not created_documents_in_batch and files:
        logger.warning(f"No documents were successfully processed for batch {batch.id}. Failed files: {failed_files_info}")
    
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
        document_ids=[doc.id for doc in created_documents_in_batch]
    )
    # --- END RESOLVED CONFLICT 31 ---

@router.get(
    "/batch/{batch_id}",
    response_model=BatchWithDocuments,
    status_code=status.HTTP_200_OK,
    summary="Get batch upload status (Protected)",
    description="Get the status of a batch upload including documents in the batch. Requires authentication."
)
# --- RESOLVED CONFLICT 32a: Function name ---
async def get_batch_status_endpoint( 
# --- END RESOLVED CONFLICT 32a ---
    batch_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to get status for batch ID: {batch_id}")
    
    # --- RESOLVED CONFLICT 32b: Variable name 'batch' ---
    batch = await crud.get_batch_by_id(batch_id=batch_id) 
    if not batch:
    # --- END RESOLVED CONFLICT 32b ---
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Batch with ID {batch_id} not found.")

    # --- RESOLVED CONFLICT 33a: Batch user_id check and log ---
    if batch.user_id != user_kinde_id:
        logger.warning(f"User {user_kinde_id} forbidden to access batch {batch_id} owned by {batch.user_id}.")
    # --- END RESOLVED CONFLICT 33a ---
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this batch.")

    # --- RESOLVED CONFLICT 33b: Variable name and comments ---
    # Using 'documents_in_batch' and HEAD's comments
    # crud.get_documents_by_batch_id is expected to be scoped by teacher_id internally or here
    documents_in_batch = await crud.get_documents_by_batch_id(batch_id=batch_id, teacher_id=user_kinde_id)
    # --- END RESOLVED CONFLICT 33b ---
    
    return BatchWithDocuments(
        id=batch.id, user_id=batch.user_id, created_at=batch.created_at, 
        updated_at=batch.updated_at, total_files=batch.total_files,
        completed_files=batch.completed_files, failed_files=batch.failed_files,
        status=batch.status, priority=batch.priority, error_message=batch.error_message,
        document_ids=[doc.id for doc in documents_in_batch]
    )

@router.post(
    "/{document_id}/reset",
    status_code=status.HTTP_200_OK,
    summary="Reset a stuck document assessment (Protected)",
    description="Sets the status of a document and its associated result back to ERROR. Useful for assessments stuck in PROCESSING/ASSESSING.",
    response_model=Dict[str, str] 
)
# --- RESOLVED CONFLICT 34a: Function name ---
async def reset_assessment_status_endpoint(
# --- END RESOLVED CONFLICT 34a ---
    document_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to RESET status for document {document_id}")

    # --- RESOLVED CONFLICT 34b: Variable names and logic (preferring HEAD) ---
    document = await crud.get_document_by_id(document_id=document_id, teacher_id=user_kinde_id, include_deleted=True)
    if not document:
        logger.warning(f"Reset attempt failed: Document {document_id} not found or not owned by user {user_kinde_id}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found or access denied.")

    auth_teacher_id_for_update = document.teacher_id 
    if not auth_teacher_id_for_update:
        logger.error(f"Critical: auth_teacher_id_for_update is missing for document {document.id} during reset by user {user_kinde_id}")
        raise HTTPException(status_code=500, detail="Internal error: Teacher ID missing for reset operation.")

    logger.info(f"Resetting document {document.id} (current status: {document.status.value}) to ERROR.")
    updated_doc = await crud.update_document_status(
        document_id=document.id, teacher_id=auth_teacher_id_for_update, status=DocumentStatus.ERROR
    )
    doc_reset_failed = not updated_doc # Simpler flag based on HEAD's style
    if doc_reset_failed: 
        logger.error(f"Failed to update document status to ERROR during reset for {document.id}.")

    result_to_reset = await crud.get_result_by_document_id(document_id=document.id, teacher_id=auth_teacher_id_for_update, include_deleted=True)
    result_reset_failed = False # Simpler flag
    if result_to_reset:
        logger.info(f"Resetting result {result_to_reset.id} (current status: {result_to_reset.status.value}) to ERROR for document {document.id}.")
        updated_result = await crud.update_result(
            result_id=result_to_reset.id, teacher_id=auth_teacher_id_for_update, 
            update_data={"status": ResultStatus.ERROR.value}
        )
        if not updated_result:
            logger.error(f"Failed to update result status to ERROR during reset for result {result_to_reset.id} (doc: {document.id}).")
            result_reset_failed = True
    else:
        logger.warning(f"No result record found to reset for document {document.id}.")

    # --- RESOLVED CONFLICT 35: Final error checking (preferring HEAD's structure) ---
    if doc_reset_failed and (not result_to_reset or result_reset_failed):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to reset document and related result status.")
    if doc_reset_failed:
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to reset document status, result handling may have varied.")
    if result_reset_failed: # Implies doc_reset was OK
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Document status reset, but failed to reset result status.")
    # --- END RESOLVED CONFLICT 35 & 34b ---
    
    final_doc_status_value = updated_doc.status.value if updated_doc else "ERROR (update failed)" # For log
    logger.info(f"Successfully processed reset request for document {document_id}. Final document status: {final_doc_status_value}.")
    return {"message": f"Successfully reset assessment status for document {document_id} to ERROR."}


@router.post(
    "/{document_id}/cancel",
    status_code=status.HTTP_200_OK,
    # --- RESOLVED CONFLICT 36a: Description ---
    summary="Cancel a stuck document assessment (Protected)",
    description="Sets the status of a document (if PROCESSING, QUEUED, UPLOADED or RETRYING) and its associated result (if ASSESSING, PENDING or RETRYING) back to ERROR.",
    # --- END RESOLVED CONFLICT 36a ---
    response_model=Dict[str, str] 
)
# --- RESOLVED CONFLICT 36b: Function name ---
async def cancel_assessment_status_endpoint(
# --- END RESOLVED CONFLICT 36b ---
    document_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to CANCEL assessment for document {document_id}")

    # --- RESOLVED CONFLICT 36c: Variable names and initial checks (using HEAD convention) ---
    document = await crud.get_document_by_id(document_id=document_id, teacher_id=user_kinde_id, include_deleted=True)
    if not document:
        logger.warning(f"Cancel attempt failed: Document {document_id} not found or not owned by user {user_kinde_id}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found or access denied.")

    auth_teacher_id_for_update = document.teacher_id
    if not auth_teacher_id_for_update:
        logger.error(f"Critical: auth_teacher_id_for_update is missing for document {document.id} during cancel by user {user_kinde_id}")
        raise HTTPException(status_code=500, detail="Internal error: Teacher ID missing for cancel operation.")

    # Using Codex's more comprehensive list of cancellable document statuses
    cancellable_doc_statuses = [DocumentStatus.PROCESSING, DocumentStatus.RETRYING, DocumentStatus.QUEUED, DocumentStatus.UPLOADED] 
    if document.status not in cancellable_doc_statuses: 
        logger.warning(f"Document {document.id} is in status '{document.status.value}', which is not cancellable. Valid: {[s.value for s in cancellable_doc_statuses]}.")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Cannot cancel assessment. Document status is '{document.status.value}'.")

    logger.info(f"Cancelling document {document.id} (current status: {document.status.value}) by setting its status to ERROR.")
    updated_doc = await crud.update_document_status(
        document_id=document.id, teacher_id=auth_teacher_id_for_update, status=DocumentStatus.ERROR
    )
    doc_cancel_failed = not updated_doc # Simpler flag
    if doc_cancel_failed: 
        logger.error(f"Failed to update document status to ERROR during cancel for {document.id}.")

    result_to_cancel = await crud.get_result_by_document_id(document_id=document.id, teacher_id=auth_teacher_id_for_update, include_deleted=True)
    result_handling_issue = False # Simpler flag

    if result_to_cancel:
        # Using Codex's more comprehensive list of cancellable result statuses
        cancellable_result_statuses = [ResultStatus.ASSESSING, ResultStatus.RETRYING, ResultStatus.PENDING]
        if result_to_cancel.status in cancellable_result_statuses:
            logger.info(f"Cancelling result {result_to_cancel.id} (current status: {result_to_cancel.status.value}) to ERROR for document {document.id}.")
            updated_cancelled_result = await crud.update_result(
                result_id=result_to_cancel.id, teacher_id=auth_teacher_id_for_update,
                update_data={"status": ResultStatus.ERROR.value}
            )
            if not updated_cancelled_result:
                logger.error(f"Failed to update result status to ERROR during cancel for result {result_to_cancel.id} (doc: {document.id}).")
                result_handling_issue = True
        else:
            logger.info(f"Result {result_to_cancel.id} for document {document.id} is in status '{result_to_cancel.status.value}'. No status change needed during cancel.")
    else:
        logger.warning(f"No result record found to cancel for document {document.id}.")
    
    # Using HEAD's style of final error checking
    if doc_cancel_failed and (not result_to_cancel or result_handling_issue):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to cancel document and encountered issues with result handling.")
    if doc_cancel_failed:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to cancel document status; result handling may have varied.")
    if result_handling_issue: # Implies doc_cancel was OK
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Document status cancelled, but failed to update associated result status.")
    # --- END RESOLVED CONFLICT 36c ---
    
    final_doc_status_value = updated_doc.status.value if updated_doc else "ERROR (update failed)"
    logger.info(f"Successfully cancelled assessment processing for document {document_id}. Final document status: {final_doc_status_value}.")
    return {"message": f"Successfully cancelled assessment for document {document_id}. Status set to ERROR."}