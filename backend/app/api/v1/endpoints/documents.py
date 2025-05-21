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
from ....services.blob_storage import upload_file_to_blob, download_blob_as_bytes

# Import Text Extraction Service
from ....services.text_extraction import extract_text_from_bytes
from ....queue import enqueue_assessment_task # RESOLVED CONFLICT 1

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
    # RESOLVED CONFLICT 2 - Using multi-line style from 'main'
    if document.status not in [
        DocumentStatus.UPLOADED,
        DocumentStatus.ERROR,
        DocumentStatus.FAILED,
    ]:
        logger.warning(f"Document {document_id} status is '{document.status}'. Assessment cannot be triggered.")
        # Return the existing result instead of erroring if it's already completed/processing
        existing_result = await crud.get_result_by_document_id(document_id=document_id, teacher_id=auth_teacher_id) # Pass teacher_id here too
        if existing_result:
            # Return 200 OK with the existing result if already completed or processing
            if existing_result.status in [
                ResultStatus.COMPLETED,
                ResultStatus.ASSESSING,
                ResultStatus.RETRYING,
            ]:
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
    logger.debug(f"Attempting to set document {document_id} to PROCESSING.")
    await crud.update_document_status(document_id=document_id, teacher_id=auth_teacher_id, status=DocumentStatus.PROCESSING)
    logger.debug(f"Document {document_id} status updated to PROCESSING. Fetching result.")

    result = await crud.get_result_by_document_id(document_id=document_id, teacher_id=auth_teacher_id) # Pass teacher_id
    logger.debug(f"Result for doc {document_id} after fetching: {result}")

    if result:
        # --- Pass dictionary directly to crud.update_result ---
        logger.debug(f"Attempting to update existing result {result.id} for doc {document_id} to ASSESSING.")
        update_success = await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ASSESSING}, teacher_id=auth_teacher_id) # Added teacher_id if update_result supports it
        if update_success:
            logger.info(f"Existing result record {result.id} for doc {document_id} updated to status ASSESSING successfully.")
            logger.debug(f"Updated result object: {update_success}") # Log the returned object
        else:
            logger.error(f"Failed to update existing result record {result.id} for doc {document_id} to status ASSESSING.")
    else:
        # Handle case where result record didn't exist (should have been created on upload)
        logger.warning(f"Result record missing for document {document_id} during assessment trigger. Creating one now with ASSESSING status.")
        result_data = ResultCreate(
            score=None, 
            status=ResultStatus.ASSESSING, # Start with ASSESSING status
            # result_timestamp is not part of ResultCreate, it's set by DB model or CRUD
            document_id=document_id, 
            teacher_id=auth_teacher_id # Use the authenticated user's ID
        )
        logger.debug(f"Attempting to create new result for doc {document_id} with data: {result_data.model_dump_json()}")
        created_result = await crud.create_result(result_in=result_data)
        if not created_result:
            logger.error(f"Failed to create missing result record for document {document_id}. Assessment cannot proceed.")
            # If creation fails even here, revert doc status and raise error
            logger.debug(f"Reverting document {document_id} status to ERROR due to failed result creation.")
            await crud.update_document_status(document_id=document_id, teacher_id=auth_teacher_id, status=DocumentStatus.ERROR)
            raise HTTPException(status_code=500, detail="Internal error: Failed to create necessary result record.")
        else:
            logger.info(f"Successfully created missing result record {created_result.id} for doc {document_id} with status ASSESSING.")
            logger.debug(f"Newly created result object: {created_result}")
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
            extracted_text = "" # Ensure it's a string for later use
        
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
        )
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error accessing document file for text extraction.")
    except ValueError as e: # Catch specific error from text_extraction if it raises one for unsupported types
        logger.error(f"Text extraction error for document {document.id}: {e}", exc_info=True)
        await crud.update_document_status(
            document_id=document.id, 
            teacher_id=auth_teacher_id, 
            status=DocumentStatus.ERROR
        )
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id)
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during text extraction for document {document_id}: {e}", exc_info=True)
        await crud.update_document_status(
            document_id=document.id, 
            teacher_id=auth_teacher_id, 
            status=DocumentStatus.ERROR
        )
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id) # Added teacher_id
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to extract text from document.")

    # This check should be redundant if extracted_text = "" is used above when None.
    # if extracted_text is None: 
    #     logger.error(f"Text extraction resulted in None for document {document_id}")
    #     await crud.update_document_status(document_id=document.id, teacher_id=auth_teacher_id, status=DocumentStatus.ERROR)
    #     if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id)
    #     raise HTTPException(status_code=500, detail="Text content could not be extracted.")
        
    # --- ML API Call ---
    ai_score: Optional[float] = None
    ml_label: Optional[str] = None
    ml_ai_generated: Optional[bool] = None
    ml_human_generated: Optional[bool] = None
    ml_paragraph_results_raw: Optional[List[Dict[str, Any]]] = None

    try:
        ml_payload = {"text": extracted_text} # No need for `if extracted_text else ""` due to earlier assignment
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
                    ml_paragraph_results_raw = ml_response_data["results"]
                    logger.info(f"Extracted {len(ml_paragraph_results_raw)} raw paragraph results.")
                    
                    if len(ml_paragraph_results_raw) > 0 and isinstance(ml_paragraph_results_raw[0], dict):
                        first_paragraph_result = ml_paragraph_results_raw[0] # Renamed for clarity
                        ml_label = first_paragraph_result.get("label")
                        if not isinstance(ml_label, str): ml_label = None

                        score_value = first_paragraph_result.get("probability")
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

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error calling ML API for document {document_id}: {e.response.status_code} - {e.response.text}", exc_info=False)
        await crud.update_document_status(
            document_id=document_id,
            teacher_id=auth_teacher_id,
            status=DocumentStatus.ERROR,
            character_count=character_count,
            word_count=word_count
        )
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id)
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
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id)
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
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get AI detection result: {e}")


    # --- Update DB with Result ---
    final_result_obj: Optional[Result] = None # Renamed to avoid clash
    try:
        if result: # Result object should exist
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
                    logger.error(f"ml_paragraph_results_raw is not a list of dicts for doc {document_id}. Skipping save.")

            logger.debug(f"Attempting to update Result {result.id} with payload: {update_payload_dict}")
            final_result_obj = await crud.update_result(result_id=result.id, update_data=update_payload_dict, teacher_id=auth_teacher_id)

            if final_result_obj:
                logger.info(f"Successfully updated result for document {document_id}")
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
            else: # crud.update_result returned None
                logger.error(f"Failed to update result record for document {document_id} after ML processing.")
                await crud.update_document_status(
                    document_id=document_id,
                    teacher_id=auth_teacher_id,
                    status=DocumentStatus.ERROR,
                    character_count=character_count, 
                    word_count=word_count
                )
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save analysis results.")
        else: # This case should ideally not be reached
            logger.error(f"Result record not found during final update stage for document {document_id}")
            await crud.update_document_status(
                document_id=document_id,
                teacher_id=auth_teacher_id,
                status=DocumentStatus.ERROR,
                character_count=character_count, 
                word_count=word_count
            )
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error: Result record missing during final update.")

    except Exception as e:
        logger.error(f"Failed to update database after successful ML API call for document {document_id}: {e}", exc_info=True)
        await crud.update_document_status(
            document_id=document_id,
            teacher_id=auth_teacher_id,
            status=DocumentStatus.ERROR,
            character_count=character_count, 
            word_count=word_count
        )
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=auth_teacher_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save assessment result.")


    if not final_result_obj: # Renamed variable
       logger.error(f"Final result object is None after attempting DB update for doc {document_id}.")
       raise HTTPException(status_code=500, detail="Failed to retrieve final result after update.")

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
    
    logger.info(f"Document {document_id} status updated to {status_update.status.value} by user {user_kinde_id}.")
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

    try:
        success = await crud.delete_document(document_id=document_id, teacher_id=user_kinde_id)
        if not success:
            logger.warning(f"crud.delete_document returned False for document {document_id} initiated by user {user_kinde_id}.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found or delete operation failed.")
        logger.info(f"Successfully processed delete request for document {document_id} by user {user_kinde_id}.")
    except HTTPException: # Re-raise known HTTP exceptions
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
    logger.info(f"User {user_kinde_id} attempting to CANCEL status for document {document_id}")

    document_obj = await crud.get_document_by_id(document_id=document_id, teacher_id=user_kinde_id, include_deleted=True) # Renamed
    if not document_obj:
        logger.warning(f"Cancel attempt failed: Document {document_id} not found or not owned by user {user_kinde_id}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found or access denied.")

    auth_teacher_id = document_obj.teacher_id
    if not auth_teacher_id:
        logger.error(f"Critical: auth_teacher_id is missing for document {document_obj.id} during cancel operation by {user_kinde_id}")
        raise HTTPException(status_code=500, detail="Internal error: Teacher identifier missing.")


    cancellable_doc_statuses = [DocumentStatus.PROCESSING, DocumentStatus.RETRYING, DocumentStatus.QUEUED, DocumentStatus.UPLOADED] # Expanded list
    if document_obj.status not in cancellable_doc_statuses: 
        logger.warning(f"Document {document_obj.id} is not in a cancellable state (currently {document_obj.status}). Cannot cancel.")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Cannot cancel assessment. Document status is {document_obj.status.value}.")

    logger.info(f"Cancelling document {document_obj.id} by setting status to ERROR.")
    updated_doc_obj = await crud.update_document_status( # Renamed
        document_id=document_obj.id,
        teacher_id=auth_teacher_id, 
        status=DocumentStatus.ERROR
    )
    doc_cancel_failed = not updated_doc_obj
    if doc_cancel_failed:
        logger.error(f"Failed to update document status to ERROR during cancel for {document_obj.id}.")

    result_obj = await crud.get_result_by_document_id(document_id=document_obj.id, teacher_id=auth_teacher_id, include_deleted=True) # Renamed, scoped
    result_handling_issue = False

    if result_obj:
        cancellable_result_statuses = [ResultStatus.ASSESSING, ResultStatus.RETRYING, ResultStatus.PENDING] # Expanded list
        if result_obj.status in cancellable_result_statuses:
            logger.info(f"Cancelling result {result_obj.id} by setting status to ERROR.")
            updated_result_obj = await crud.update_result( # Renamed
                result_id=result_obj.id,
                teacher_id=auth_teacher_id, # Pass teacher_id if supported
                update_data={"status": ResultStatus.ERROR.value}
            )
            if not updated_result_obj:
                logger.error(f"Failed to update result status to ERROR during cancel for {result_obj.id} (doc: {document_obj.id}).")
                result_handling_issue = True
        else:
            logger.info(f"Result {result_obj.id} status is {result_obj.status.value} (not actively processing). Not changing result status during cancel.")
    else:
        logger.warning(f"No result record found to cancel for document {document_obj.id}. Document status cancel attempt was made.")
    
    if doc_cancel_failed and (not result_obj or result_handling_issue):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to cancel document and encountered issues with result handling.")
    if doc_cancel_failed:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to cancel document status; result handling may have varied.")
    if result_handling_issue: # Implies doc_cancel was OK
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Document status cancelled, but failed to update associated result status.")

    logger.info(f"Successfully cancelled assessment processing for document {document_obj.id} (set status to ERROR).")
    return {"message": f"Successfully cancelled assessment for document {document_id}. Status set to ERROR."}