# app/api/v1/endpoints/results.py

import uuid
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, status, Query, Depends

# Import models
from ....models.result import Result
from ....models.document import Document # Needed for auth check

# Import CRUD functions
from ....db import crud

# Import Authentication Dependency
from ....core.security import get_current_user_payload

# Setup logger
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/results",
    tags=["Results"]
)

# === Result API Endpoints (Protected - Read Only) ===

# NOTE: POST, PUT, DELETE for results are omitted as it's assumed results
# are created/updated internally by the document analysis process.

@router.get(
    "/document/{document_id}",
    response_model=Result,
    status_code=status.HTTP_200_OK,
    summary="Get the result for a specific document (Protected)",
    description="Retrieves the AI analysis result associated with a given document ID. Requires authentication."
)
async def read_result_for_document(
    document_id: uuid.UUID,
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to retrieve the result for a specific document.
    """
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to read result for document ID: {document_id}")

    # --- Authorization Check (Based on Document Access) ---
    # First, check if the associated document exists and if the user can access it
    # Assuming get_document_by_id respects soft delete if implemented
    document = await crud.get_document_by_id(
        document_id=document_id,
        teacher_id=user_kinde_id
    )
    if document is None:
        # If the document doesn't exist OR doesn't belong to the user, the result cannot be accessed
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found or access denied."
        )
    # Authorization confirmed by successful fetch above
    # TODO: Add fine-grained authorization check:
    # Can user 'user_kinde_id' view this document (and therefore its result)?
    # (e.g., check relationship via student/assignment/classgroup/teacher)
    # logger.warning(f"Authorization check needed for user {user_kinde_id} reading result for document {document_id}")
    # --- End Authorization Check ---

    # If authorized to view document, attempt to get the result
    # Assuming get_result_by_document_id respects soft delete if implemented
    result = await crud.get_result_by_document_id(document_id=document_id)
    if result is None:
        # Result might not exist yet (pending/failed) or could be (soft) deleted
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Result for document ID {document_id} not found (may still be processing or failed)."
        )
    return result

@router.get(
    "/{result_id}",
    response_model=Result,
    status_code=status.HTTP_200_OK,
    summary="Get a specific result by its ID (Protected)",
    description="Retrieves a specific result using its unique ID. Requires authentication."
)
async def read_result(
    result_id: uuid.UUID,
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to retrieve a specific result by its ID.
    (Less common use case than getting result by document ID).
    """
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to read result ID: {result_id}")

    # Assuming get_result_by_id respects soft delete if implemented
    result = await crud.get_result_by_id(result_id=result_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Result with ID {result_id} not found."
        )

    # --- Authorization Check (Based on Document Access) ---
    # Need to check if user can access the associated document
    # Assuming get_document_by_id respects soft delete if implemented
    document = await crud.get_document_by_id(
        document_id=result.document_id,
        teacher_id=user_kinde_id
    )
    if document is None:
         # Should not happen if result exists, implies data inconsistency OR access denied
         logger.warning(f"Document {result.document_id} not found or access denied for user {user_kinde_id} when fetching result {result_id}.")
         # Return 404 for the result, as the context is broken or forbidden
         raise HTTPException(status_code=404, detail="Result not found or access denied.")
    # Authorization confirmed by successful fetch above
    # TODO: Add fine-grained authorization check:
    # Can user 'user_kinde_id' view this document (and therefore its result)?
    # logger.warning(f"Authorization check needed for user {user_kinde_id} reading result {result_id} linked to document {result.document_id}")
    # --- End Authorization Check ---

    return result