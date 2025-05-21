# backend/app/api/v1/endpoints/documents.py

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

# Import Text Extraction Service
from app.services.text_extraction import extract_text_from_bytes
from app.queue import enqueue_assessment_task

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
    if document.status not in [DocumentStatus.UPLOADED, DocumentStatus.ERROR, DocumentStatus.FAILED]:
        logger.warning(f"Document {document_id} status is '{document.status}'. Assessment cannot be triggered.")
        # Return the existing result instead of erroring if it's already completed/processing
        existing_result = await crud.get_result_by_document_id(document_id=document_id, teacher_id=auth_teacher_id) # Pass teacher_id here too
        if existing_result:
            # Return 200 OK with the existing result if already completed or processing
            if existing_result.status in [ResultStatus.COMPLETED, ResultStatus.ASSESSING]:
                 logger.info(f"Assessment already completed or in progress for doc {document_id}. Returning existing result.")
                 return existing_result
            else:
                 # If status is PENDING or ERROR, allow re-triggering below
                 pass
        else:
            # This case is odd (doc status implies assessment happened, but no result found)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Assessment cannot be triggered. Document status is {document.status}, but no result found."
            )

    # --- Update Status to PROCESSING ---
    await crud.update_document_status(document_id=document_id, teacher_id=auth_teacher_id, status=DocumentStatus.PROCESSING)
    result = await crud.get_result_by_document_id(document_id=document_id, teacher_id=auth_teacher_id) # Pass teacher_id
    if result:
        # --- Pass dictionary directly to crud.update_result ---
        await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ASSESSING}, teacher_id=auth_teacher_id) # Added teacher_id if update_result supports it
        logger.info(f"Existing result record found for doc {document_id}, updated status to ASSESSING.")
    else:
        # Handle case where result record didn't exist (should have been created on upload)
        logger.warning(f"Result record missing for document {document_id} during assessment trigger. Creating one now.")
        result_data = ResultCreate(
            score=None, 
            status=ResultStatus.ASSESSING, # Start with ASSESSING status
            result_timestamp=datetime.now(timezone.utc), 
            document_id=document_id, 
            teacher_id=auth_teacher_id # Use the authenticated user's ID
        )
        created_result = await crud.create_result(result_in=result_data)
        if not created_result:
            logger.error(f"Failed to create missing result record for document {document_id}. Assessment cannot proceed.")
            # If creation fails even here, revert doc status and raise error
            await crud.update_document_status(document_id=document_id, teacher_id=auth_teacher_id, status=DocumentStatus.ERROR)
            raise HTTPException(status_code=500, detail="Internal error: Failed to create necessary result record.")
        else:
            logger.info(f"Successfully created missing result record {created_result.id} for doc {document_id} with status ASSESSING.")
            result = created_result # Use the newly created result for subsequent steps

    # --- Text Extraction ---
    extracted_text: Optional[str] = None
    character_count: Optional[int] = None # Initialize
    word_count: Optional[int] = None      # Initialize
    try:
        # Convert file_type string back to Enum member if needed
        file_type_enum_member: Optional[FileType] = None
        if isinstance(document.file_type, str):
            for member in FileType:
                if member.value.lower() == document.file_type.lower():
                    file_type_enum_member = member
                    break
        elif isinstance(document.file_type, FileType):
            file_type_enum_member = document.file_type

        if not file_type_enum_member:
            logger.error(f"Could not map document.file_type '{document.file_type}' to FileType enum for doc {document_id}")
            raise HTTPException(status_code=500, detail="Internal error: Could not determine file type for text extraction.")

        # Download blob as bytes
        file_bytes = await download_blob_as_bytes(document.storage_blob_path)
        if file_bytes is None:
            logger.error(f"Failed to download blob {document.storage_blob_path} for document {document_id}")
            # Update status to error and raise
            await crud.update_document_status(document_id=document_id, teacher_id=auth_teacher_id, status=DocumentStatus.ERROR)
            if result: # Check if result exists before trying to update it
                await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id)
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to retrieve document content from storage for assessment.")

        # Call the synchronous extract_text_from_bytes in a separate thread
        logger.info(f"Offloading text extraction for document {document_id} to a separate thread.")
        extracted_text = await asyncio.to_thread(extract_text_from_bytes, file_bytes, file_type_enum_member)
        logger.info(f"Text extraction completed for document {document_id}. Chars: {len(extracted_text) if extracted_text else 0}")

        if extracted_text is None:
            # This implies an error during extraction or unsupported type by the extraction func itself
            logger.warning(f"Text extraction returned None for document {document.id} ({document.file_type}).")
            # Return empty string if extraction fails, or raise specific error if preferred
            return "" # Or raise HTTPException(500, "Text extraction failed.")
        
        # Calculate character count
        character_count = len(extracted_text)
        # Calculate word count (split by whitespace, filter empty)
        words = re.split(r'\s+', extracted_text.strip()) # Use regex for robust splitting
        word_count = len([word for word in words if word]) # Count non-empty strings
        logger.info(f"Calculated counts for document {document_id}: Chars={character_count}, Words={word_count}")

    except FileNotFoundError:
        logger.error(f"File not found in blob storage for document {document_id} at path {document.storage_blob_path}", exc_info=True)
        await crud.update_document_status(
            document_id=document.id, 
            teacher_id=auth_teacher_id, 
            status=DocumentStatus.ERROR,
            # Optionally pass character_count and word_count as None or 0 if known
        )
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id) # Added teacher_id if update_result supports it
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error accessing document file for text extraction.")
    except ValueError as e: # Catch specific error from text_extraction if it raises one for unsupported types
        logger.error(f"Text extraction error for document {document.id}: {e}", exc_info=True)
        await crud.update_document_status(
            document_id=document.id, 
            teacher_id=auth_teacher_id, 
            status=DocumentStatus.ERROR
        )
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id) # Added teacher_id if update_result supports it
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during text extraction for document {document_id}: {e}", exc_info=True)
        await crud.update_document_status(
            document_id=document.id, 
            teacher_id=auth_teacher_id, 
            status=DocumentStatus.ERROR
        )
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id) # Added teacher_id if update_result supports it
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to extract text from document.")

    if extracted_text is None: # Should be caught by specific exceptions above, but as a safeguard
        logger.error(f"Text extraction resulted in None for document {document_id}")
        await crud.update_document_status(document_id=document.id, teacher_id=auth_teacher_id, status=DocumentStatus.ERROR)
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id) # Added teacher_id if update_result supports it
        raise HTTPException(status_code=500, detail="Text content could not be extracted.")
        
    # --- ML API Call ---
    ai_score: Optional[float] = None
    ml_label: Optional[str] = None
    ml_ai_generated: Optional[bool] = None
    ml_human_generated: Optional[bool] = None
    # --- Store the RAW list of paragraph dicts ---
    ml_paragraph_results_raw: Optional[List[Dict[str, Any]]] = None
    # --- END ---

    try:
        ml_payload = {"text": extracted_text if extracted_text else ""}
        headers = {'Content-Type': 'application/json'}

        logger.info(f"Calling ML API for document {document_id} at {ML_API_URL}")
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(ML_API_URL, json=ml_payload, headers=headers)
            response.raise_for_status()

            ml_response_data = response.json()
            logger.info(f"ML API response for document {document_id}: {ml_response_data}")

            if isinstance(ml_response_data, dict):
                ml_ai_generated = ml_response_data.get("ai_generated")
                ml_human_generated = ml_response_data.get("human_generated")
                if not isinstance(ml_ai_generated, bool): ml_ai_generated = None
                if not isinstance(ml_human_generated, bool): ml_human_generated = None

                if ("results" in ml_response_data and isinstance(ml_response_data["results"], list)):
                    # --- Store the raw list directly ---
                    ml_paragraph_results_raw = ml_response_data["results"]
                    logger.info(f"Extracted {len(ml_paragraph_results_raw)} raw paragraph results.")
                    # --- END ---

                    if len(ml_paragraph_results_raw) > 0 and isinstance(ml_paragraph_results_raw[0], dict):
                        first_result = ml_paragraph_results_raw[0]
                        ml_label = first_result.get("label")
                        if not isinstance(ml_label, str): ml_label = None

                        score_value = first_result.get("probability")
                        if isinstance(score_value, (int, float)):
                            ai_score = float(score_value)
                            ai_score = max(0.0, min(1.0, ai_score))
                            logger.info(f"Extracted overall AI probability score from first paragraph: {ai_score}")
                        else:
                            logger.warning(f"ML API returned non-numeric probability in first result: {score_value}")
                            ai_score = None
                    else: logger.warning("ML API 'results' list is empty or first item is not a dict.")
                else: logger.warning("ML API response missing 'results' list.")
            else: raise ValueError("ML API response format unexpected (not a dict).")

    # ... (error handling for ML API call remains the same) ...
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error calling ML API for document {document_id}: {e.response.status_code} - {e.response.text}", exc_info=False)
        await crud.update_document_status(
            document_id=document_id,
            teacher_id=auth_teacher_id,
            status=DocumentStatus.ERROR,
            character_count=character_count,
            word_count=word_count
        )
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id) # Added teacher_id
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error communicating with AI detection service: {e.response.status_code}")
    except ValueError as e:
        logger.error(f"Error processing ML API response for document {document_id}: {e}", exc_info=True)
        await crud.update_document_status(
            document_id=document_id,
            teacher_id=auth_teacher_id,
            status=DocumentStatus.ERROR,
            character_count=character_count,
            word_count=word_count
        )
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id) # Added teacher_id
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to process AI detection result: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during ML API call or processing for document {document_id}: {e}", exc_info=True)
        await crud.update_document_status(
            document_id=document_id,
            teacher_id=auth_teacher_id,
            status=DocumentStatus.ERROR,
            character_count=character_count,
            word_count=word_count
        )
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id) # Added teacher_id
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get AI detection result: {e}")


    # --- Update DB with Result ---
    final_result: Optional[Result] = None
    try:
        if result:
            # --- MODIFIED: Prepare a simple dictionary for the update ---
            update_payload_dict = {
                "status": ResultStatus.COMPLETED.value, # Store enum value
                "result_timestamp": datetime.now(timezone.utc)
            }
            if ai_score is not None: update_payload_dict["score"] = ai_score
            if ml_label is not None: update_payload_dict["label"] = ml_label
            if ml_ai_generated is not None: update_payload_dict["ai_generated"] = ml_ai_generated
            if ml_human_generated is not None: update_payload_dict["human_generated"] = ml_human_generated
            # Add the raw list of paragraph dicts if available
            if ml_paragraph_results_raw is not None:
                 # Basic check: ensure it's a list of dicts before saving
                 if isinstance(ml_paragraph_results_raw, list) and all(isinstance(item, dict) for item in ml_paragraph_results_raw):
                     update_payload_dict["paragraph_results"] = ml_paragraph_results_raw
                 else:
                     logger.error(f"ml_paragraph_results_raw is not a list of dicts for doc {document_id}. Skipping save.")

            # --- Call CRUD update function with the dictionary ---
            # +++ ADDED: Log payload before update +++
            logger.debug(f"Attempting to update Result {result.id} with payload: {update_payload_dict}")
            final_result = await crud.update_result(result_id=result.id, update_data=update_payload_dict, teacher_id=auth_teacher_id) # Added teacher_id

            if final_result:
                logger.info(f"Successfully updated result for document {document_id}")
                # Update document status to COMPLETED after successfully updating result
                logger.debug(
                    f"Calling update_document_status for COMPLETED. Doc ID: {document_id}, "
                    f"Char Count: {character_count}, Word Count: {word_count}"
                )
                await crud.update_document_status(
                    document_id=document_id,
                    teacher_id=auth_teacher_id,
                    status=DocumentStatus.COMPLETED,
                    character_count=character_count, # Pass calculated counts
                    word_count=word_count
                )
            else:
                logger.error(f"Failed to update result record for document {document_id} after ML processing.")
                # If result update failed, set document status back to ERROR
                await crud.update_document_status(
                    document_id=document_id,
                    teacher_id=auth_teacher_id,
                    status=DocumentStatus.ERROR,
                    character_count=character_count, # Still pass counts even on error
                    word_count=word_count
                )
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save analysis results.")

        else:
            # This case should ideally not be reached if result creation on upload is robust
            logger.error(f"Result record not found during final update stage for document {document_id}")
            # Update document status back to ERROR
            await crud.update_document_status(
                document_id=document_id,
                teacher_id=auth_teacher_id,
                status=DocumentStatus.ERROR,
                character_count=character_count, # Pass counts
                word_count=word_count
            )
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error: Result record missing during final update.")

    except Exception as e:
        logger.error(f"Failed to update database after successful ML API call for document {document_id}: {e}", exc_info=True)
        await crud.update_document_status(
            document_id=document_id,
            teacher_id=auth_teacher_id,
            status=DocumentStatus.ERROR,
            character_count=character_count, # Pass counts if calculated
            word_count=word_count
        )
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id) # Added teacher_id
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save assessment result.")


    if not final_result:
         logger.error(f"Final result object is None after attempting DB update for doc {document_id}.")
         raise HTTPException(status_code=500, detail="Failed to retrieve final result after update.")

    return final_result # Return the complete, updated Result object


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
        teacher_id=user_kinde_id # <<< ADDED
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document with ID {document_id} not found.")
    # TODO: Add fine-grained authorization check
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

    # --- Get Document & Authorization Check ---
    document = await crud.get_document_by_id(
        document_id=document_id,
        teacher_id=user_kinde_id # Ensures document belongs to the user
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document with ID {document_id} not found or not accessible by user.")

    # Convert file_type string from DB (if it's a string) to FileType enum member
    file_type_enum_member: Optional[FileType] = None
    if isinstance(document.file_type, str):
        for member in FileType:
            if member.value.lower() == document.file_type.lower():
                file_type_enum_member = member
                break
    elif isinstance(document.file_type, FileType):
        file_type_enum_member = document.file_type # It's already an enum

    if not file_type_enum_member:
        logger.error(f"Could not map document.file_type '{document.file_type}' to FileType enum for doc {document_id} in get_document_text")
        raise HTTPException(status_code=500, detail="Internal error: Could not determine file type for text extraction.")

    # Check if text extraction is supported for this file type
    if file_type_enum_member not in [FileType.PDF, FileType.DOCX, FileType.TXT, FileType.TEXT]:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Text extraction not supported for file type: {document.file_type}. Supported types for text extraction: PDF, DOCX, TXT."
        )

    # --- Download and Extract Text ---
    try:
        file_bytes = await download_blob_as_bytes(document.storage_blob_path)
        if file_bytes is None:
            logger.error(f"Failed to download blob {document.storage_blob_path} for document {document_id} text retrieval")
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Error downloading file content.")
        
        # Call the synchronous extract_text_from_bytes in a separate thread
        logger.info(f"Offloading text extraction for document {document_id} (get_document_text) to a separate thread.")
        extracted_text = await asyncio.to_thread(extract_text_from_bytes, file_bytes, file_type_enum_member)
        logger.info(f"Text extraction completed for document {document_id} (get_document_text). Chars: {len(extracted_text) if extracted_text else 0}")

        if extracted_text is None:
            # This implies an error during extraction or unsupported type by the extraction func itself
            logger.warning(f"Text extraction returned None for document {document.id} ({document.file_type}).")
            # Return empty string if extraction fails, or raise specific error if preferred
            return "" # Or raise HTTPException(500, "Text extraction failed.")
        
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
    """Protected endpoint to retrieve a list of document metadata."""
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to read list of documents with filters/sorting.")
    # TODO: Add authorization logic (filter results based on user's access)

    # Map sort_order_str to integer
    if sort_order_str.lower() == "asc":
        sort_order_int = 1
    elif sort_order_str.lower() == "desc":
        sort_order_int = -1
    else:
        # Raise error if the value is invalid
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid sort_order value. Use 'asc' or 'desc'."
        )

    documents = await crud.get_all_documents(
        teacher_id=user_kinde_id, # Pass teacher_id
        student_id=student_id,
        assignment_id=assignment_id,
        status=status,
        skip=skip,
        limit=limit,
        sort_by=sort_by,
        sort_order=sort_order_int
    )
    # <<< START EDIT: Add debug log before returning >>>
    # Log the content being returned, limiting length if needed for brevity
    docs_to_log = []
    for doc in documents:
        try:
            # Use model_dump to get a dict, might reveal issues if model is complex
            docs_to_log.append(doc.model_dump(mode='json')) 
        except Exception as log_e:
            logger.warning(f"Could not serialize document {getattr(doc, 'id', 'N/A')} for logging: {log_e}")
            docs_to_log.append({"id": str(getattr(doc, 'id', 'N/A')), "error": "Serialization failed for log"})
    logger.debug(f"Returning documents for GET /documents endpoint: {docs_to_log}")
    # <<< END EDIT >>>
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
    status_update: DocumentUpdate, # Expects {'status': DocumentStatus}
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """Protected endpoint to update the status of a document."""
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to update status for document ID: {document_id} to {status_update.status}")
    if status_update.status is None: raise HTTPException(status.HTTP_400_BAD_REQUEST, "Status field is required.")

    # --- Authorization Check ---
    # Check if the document exists AND belongs to the current user before updating status
    doc_to_update = await crud.get_document_by_id(
        document_id=document_id,
        teacher_id=user_kinde_id # Use authenticated user's ID
    )
    if not doc_to_update:
        # Raise 404 whether it doesn't exist or belongs to another user
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found or access denied."
        )
    # --- End Authorization Check ---

    # Proceed with status update only if the check above passed
    updated_document = await crud.update_document_status(document_id=document_id, status=status_update.status)
    if updated_document is None:
        # This might happen if the doc was deleted between the check and the update (race condition)
        # Or if crud.update_document_status failed for another reason
        logger.error(f"Failed to update status for doc {document_id} even after ownership check passed for user {user_kinde_id}.")
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Document {document_id} not found during status update.")
    # Log the string value from the input
    logger.info(f"Document {document_id} status updated to {status_update.status.value} by user {user_kinde_id}.")
    return updated_document

@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document and associated data (Protected)",
    description="Soft-deletes a document metadata record, and attempts to delete the associated file from Blob Storage and the analysis result. Requires authentication."
)
async def delete_document(
    document_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to soft-delete a document and its associated blob/result.
    Deletion is handled by the CRUD layer.
    """
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to delete document ID: {document_id}")

    try:
        # Call the updated CRUD function which now handles auth, blob, result, and soft delete
        success = await crud.delete_document(document_id=document_id, teacher_id=user_kinde_id)

        if not success:
            logger.warning(f"crud.delete_document returned False for document {document_id} initiated by user {user_kinde_id}.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found or delete operation failed.")

        logger.info(f"Successfully processed delete request for document {document_id} by user {user_kinde_id}.")
        # No explicit return needed here for 204 status code

    except Exception as e: # Catch ALL exceptions here
        if isinstance(e, HTTPException):
            # If it's an HTTPException we intentionally raised (like the 404)
            raise e # Re-raise it as is
        else:
            # For any other unexpected exception
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
    """
    Protected endpoint to upload multiple documents in a batch, store them,
    create metadata, and initiate the analysis process.
    """
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to upload batch of {len(files)} documents")

    # Create batch record
    batch_data = BatchCreate(
        teacher_id=user_kinde_id,
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

    documents = []
    failed_files = []

    # Process each file
    for file in files:
        try:
            original_filename = file.filename or "unknown_file"
            
            # File type validation
            content_type = file.content_type
            file_extension = os.path.splitext(original_filename)[1].lower()
            file_type_enum = None
            
            if file_extension == ".pdf" and content_type == "application/pdf": 
                file_type_enum = FileType.PDF
            elif file_extension == ".docx" and content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document": 
                file_type_enum = FileType.DOCX
            elif file_extension == ".txt" and content_type == "text/plain": 
                file_type_enum = FileType.TXT
            elif file_extension == ".png" and content_type == "image/png": 
                file_type_enum = FileType.PNG
            elif file_extension in [".jpg", ".jpeg"] and content_type == "image/jpeg": 
                file_type_enum = FileType.JPG

            if file_type_enum is None:
                failed_files.append({
                    "filename": original_filename,
                    "error": f"Unsupported file type: {content_type}"
                })
                continue

            # Upload to blob storage
            blob_name = await upload_file_to_blob(upload_file=file)
            if not blob_name:
                failed_files.append({
                    "filename": original_filename,
                    "error": "Failed to upload to storage"
                })
                continue

            # Create document record
            now = datetime.now(timezone.utc)
            # Convert priority enum to integer
            priority_value = 0  # Default
            if priority == BatchPriority.LOW:
                priority_value = 0
            elif priority == BatchPriority.NORMAL:
                priority_value = 1
            elif priority == BatchPriority.HIGH:
                priority_value = 2
            elif priority == BatchPriority.URGENT:
                priority_value = 3

            document_data = DocumentCreate(
                original_filename=original_filename,
                storage_blob_path=blob_name,
                file_type=file_type_enum,
                upload_timestamp=now,
                student_id=student_id,
                assignment_id=assignment_id,
                status=DocumentStatus.UPLOADED,
                batch_id=batch.id,
                queue_position=len(documents) + 1,
                processing_priority=priority_value,  # Use the converted integer value
                teacher_id=user_kinde_id
            )
            
            document = await crud.create_document(document_in=document_data)
            if not document:
                failed_files.append({
                    "filename": original_filename,
                    "error": "Failed to create document record"
                })
                continue

            # Create initial result record
            result_data = ResultCreate(
                score=None,
                status=ResultStatus.PENDING,
                result_timestamp=now,
                document_id=document.id,
                teacher_id=user_kinde_id
            )
            created_result = await crud.create_result(result_in=result_data)
            # --- ADDED: Log result creation outcome ---
            if created_result:
                logger.info(f"Successfully created initial Result record {created_result.id} for Document {document.id}")
            else:
                logger.error(f"!!! Failed to create initial Result record for Document {document.id}. crud.create_result returned None.")
            # --- END ADDED ---

            # Enqueue document for assessment and update status if successful
            enqueue_success = await enqueue_assessment_task(
                document_id=document.id,
                user_id=user_kinde_id,
                priority_level=priority_value,
            )
            if enqueue_success:
                updated_doc = await crud.update_document_status(
                    document_id=document.id,
                    teacher_id=user_kinde_id,
                    status=DocumentStatus.QUEUED,
                )
                if updated_doc:
                    document = updated_doc
            else:
                logger.error(
                    f"Failed to enqueue assessment task for document {document.id}"
                )

            documents.append(document)

        except Exception as e:
            logger.error(f"Error processing file {file.filename}: {str(e)}")
            failed_files.append({
                "filename": file.filename,
                "error": str(e)
            })

    # Update batch status
    batch_update = BatchUpdate(
        completed_files=0,
        failed_files=len(failed_files),
        status=BatchStatus.QUEUED if documents else BatchStatus.ERROR,
        error_message=f"Failed to process {len(failed_files)} files" if failed_files else None
    )
    updated_batch = await crud.update_batch(batch_id=batch.id, batch_in=batch_update)

    if not documents:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Failed to process any files in the batch",
                "failed_files": failed_files
            }
        )

    return BatchWithDocuments(
        **updated_batch.dict(),
        document_ids=[doc.id for doc in documents]
    )

@router.get(
    "/batch/{batch_id}",
    response_model=BatchWithDocuments,
    status_code=status.HTTP_200_OK,
    summary="Get batch upload status (Protected)",
    description="Get the status of a batch upload including all documents in the batch. Requires authentication."
)
async def get_batch_status(
    batch_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to get the status of a batch upload and its documents.
    """
    user_kinde_id = current_user_payload.get("sub")
    
    # Get batch
    batch = await crud.get_batch_by_id(batch_id=batch_id)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Batch with ID {batch_id} not found"
        )

    # Authorization check
    if batch.user_id != user_kinde_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this batch"
        )

    # Get all documents in batch
    documents = await crud.get_documents_by_batch_id(batch_id=batch_id)
    
    return BatchWithDocuments(
        **batch.dict(),
        document_ids=[doc.id for doc in documents]
    )

@router.post(
    "/{document_id}/reset",
    status_code=status.HTTP_200_OK,
    summary="Reset a stuck document assessment (Protected)",
    description="Sets the status of a document and its associated result back to ERROR. Useful for assessments stuck in PROCESSING/ASSESSING.",
    response_model=Dict[str, str] # Simple confirmation message
)
async def reset_assessment_status(
    document_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    if not user_kinde_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    logger.info(f"User {user_kinde_id} attempting to reset status for document {document_id}")

    # --- Get Document and Result (Check Ownership) ---
    document = await crud.get_document_by_id(document_id=document_id, teacher_id=user_kinde_id, include_deleted=True)
    if not document:
        logger.warning(f"Reset attempt failed: Document {document_id} not found or not owned by user {user_kinde_id}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found or access denied.")

    result = await crud.get_result_by_document_id(document_id=document_id, include_deleted=True)

    # --- Update Document Status ---    
    logger.info(f"Resetting document {document_id} status to ERROR.")
    updated_doc = await crud.update_document_status(
        document_id=document_id,
        teacher_id=document.teacher_id, # ADDED teacher_id from the fetched document
        status=DocumentStatus.ERROR
        # Note: We don't know the counts here, so don't provide them
    )
    if not updated_doc:
        logger.error(f"Failed to update document status to ERROR during reset for {document_id}.")
        # Proceed to try and update result anyway, but log this issue

    # --- Update Result Status --- 
    if result:
        logger.info(f"Resetting result {result.id} status to ERROR.")
        updated_result = await crud.update_result(
            result_id=result.id,
            update_data={"status": ResultStatus.ERROR}
        )
        if not updated_result:
            logger.error(f"Failed to update result status to ERROR during reset for {result.id} (doc: {document_id}).")
            # If document update succeeded but result failed, raise error
            if updated_doc: 
                 raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fully reset result status.")
            # If both failed, let the final error handle it
    else:
        logger.warning(f"No result record found to reset for document {document_id}. Document status may have been reset.")

    # If either update failed earlier, this might not be reached if an exception was raised
    if not updated_doc and not result: # If doc failed and no result found
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to reset document status (no result found)." )
    elif not updated_doc and result and not updated_result: # If both failed
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to reset both document and result status.")

    logger.info(f"Successfully reset status for document {document_id} and associated result (if found).")
    return {"message": f"Successfully reset status for document {document_id} to ERROR."}

@router.post(
    "/{document_id}/cancel",
    status_code=status.HTTP_200_OK,
    summary="Cancel a stuck document assessment (Protected)",
    description="Sets the status of a document (if PROCESSING) and its associated result (if ASSESSING) back to ERROR. Functionally similar to reset, provides a cancel semantic.",
    response_model=Dict[str, str] # Simple confirmation message
)
async def cancel_assessment_status(
    document_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    if not user_kinde_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    logger.info(f"User {user_kinde_id} attempting to CANCEL status for document {document_id}")

    # --- Get Document and Result (Check Ownership) ---
    # Fetch document, including deleted=True just in case it was soft-deleted during processing
    document = await crud.get_document_by_id(document_id=document_id, teacher_id=user_kinde_id, include_deleted=True)
    if not document:
        logger.warning(f"Cancel attempt failed: Document {document_id} not found or not owned by user {user_kinde_id}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found or access denied.")

    # --- Check if Cancellable --- 
    # Only allow cancellation if it's actually in a processing state
    if document.status not in [DocumentStatus.PROCESSING]: # Only allow cancelling PROCESSING doc status
         logger.warning(f"Document {document_id} is not in PROCESSING state (currently {document.status}). Cannot cancel.")
         raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Cannot cancel assessment. Document status is {document.status}.")

    result = await crud.get_result_by_document_id(document_id=document_id, include_deleted=True)

    # --- Update Document Status to ERROR ---    
    logger.info(f"Cancelling document {document_id} by setting status to ERROR.")
    updated_doc = await crud.update_document_status(
        document_id=document_id,
        teacher_id=document.teacher_id, # ADDED teacher_id from the fetched document
        status=DocumentStatus.ERROR
    )
    if not updated_doc:
        logger.error(f"Failed to update document status to ERROR during cancel for {document_id}.")
        # Proceed to try and update result anyway, but log this issue

    # --- Update Result Status to ERROR (if applicable) --- 
    updated_result = None # Initialize to track if update was attempted and failed
    result_updated_or_skipped = False # Track if update succeeded OR was skipped correctly

    if result:
         # Only try to update result if it's currently ASSESSING
        if result.status == ResultStatus.ASSESSING:
            logger.info(f"Cancelling result {result.id} by setting status to ERROR.")
            updated_result = await crud.update_result(
                result_id=result.id,
                update_data={"status": ResultStatus.ERROR}
            )
            if not updated_result:
                logger.error(f"Failed to update result status to ERROR during cancel for {result.id} (doc: {document_id}).")
                # If document update succeeded but result failed, raise error now
                if updated_doc: 
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fully cancel result status after updating document.")
                result_updated_or_skipped = False # Mark as failed
            else:
                 result_updated_or_skipped = True # Mark as succeeded
        else:
            logger.info(f"Result {result.id} status is {result.status} (not ASSESSING). Not changing result status during cancel.")
            result_updated_or_skipped = True # Mark as skipped correctly
    else:
        logger.warning(f"No result record found to cancel for document {document_id}. Document status may have been set to ERROR.")
        result_updated_or_skipped = True # Treat as success since there was no result to update

    # --- Final Check & Response --- 
    # Raise error if document update failed AND result update/skip failed
    if not updated_doc and not result_updated_or_skipped: 
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to cancel document and result status.")
    # Raise error if only document update failed (and result was ok/skipped)
    elif not updated_doc: 
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to cancel document status.")
    # If result update failed after doc succeeded, exception was already raised inside the block

    logger.info(f"Successfully cancelled assessment processing for document {document_id} (set status to ERROR).")
    return {"message": f"Successfully cancelled assessment for document {document_id}. Status set to ERROR."}

