# app/api/v1/endpoints/results.py

import uuid
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, status, Query, Depends

# Import models
from ....models.result import Result
from ....models.document import Document # Needed for auth check
from ....models.enums import UserRoleEnum # ADDED UserRoleEnum

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
    Admins can retrieve any result by document_id.
    Teachers can only retrieve results for documents they own.
    """
    user_kinde_id = current_user_payload.get("sub")
    user_roles = current_user_payload.get("roles", [])
    is_admin = any(
        role == UserRoleEnum.ADMIN.value or (isinstance(role, dict) and role.get("key") == UserRoleEnum.ADMIN.value)
        for role in user_roles
    )

    logger.info(f"User {user_kinde_id} (Admin: {is_admin}) attempting to read result for document ID: {document_id}")

    query_teacher_id = None
    if not is_admin:
        query_teacher_id = user_kinde_id

    # crud.get_result_by_document_id already filters by teacher_id if provided
    result = await crud.get_result_by_document_id(document_id=document_id, teacher_id=query_teacher_id)

    if result is None:
        detail_msg = f"Result for document ID {document_id} not found"
        if not is_admin:
            detail_msg += " or you do not have permission to access it."
        else: # Admin context
            detail_msg += " (it may still be processing or failed)."
        
        logger.warning(f"Result for document {document_id} not found for user {user_kinde_id} (Admin: {is_admin}). Queried with teacher_id: {query_teacher_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail_msg
        )
    
    logger.info(f"Successfully retrieved result {result.id} for document {document_id} by user {user_kinde_id} (Admin: {is_admin}).")
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
    Admins can retrieve any result by result_id.
    Teachers can only retrieve results they own.
    (Less common use case than getting result by document ID).
    """
    user_kinde_id = current_user_payload.get("sub")
    user_roles = current_user_payload.get("roles", [])
    is_admin = any(
        role == UserRoleEnum.ADMIN.value or (isinstance(role, dict) and role.get("key") == UserRoleEnum.ADMIN.value)
        for role in user_roles
    )

    logger.info(f"User {user_kinde_id} (Admin: {is_admin}) attempting to read result ID: {result_id}")

    query_teacher_id = None
    if not is_admin:
        query_teacher_id = user_kinde_id

    # crud.get_result_by_id already filters by teacher_id if provided
    result = await crud.get_result_by_id(result_id=result_id, teacher_id=query_teacher_id)

    if result is None:
        detail_msg = f"Result with ID {result_id} not found"
        if not is_admin:
            detail_msg += " or you do not have permission to access it."
        else: # Admin context
            detail_msg += "."
            
        logger.warning(f"Result {result_id} not found for user {user_kinde_id} (Admin: {is_admin}). Queried with teacher_id: {query_teacher_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail_msg
        )

    # The check for document ownership is implicitly handled by Result.teacher_id
    # and the teacher_id passed to crud.get_result_by_id.
    # No need for an additional crud.get_document_by_id here if Result.teacher_id is authoritative.

    logger.info(f"Successfully retrieved result {result.id} by user {user_kinde_id} (Admin: {is_admin}).")
    return result