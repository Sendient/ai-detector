# backend/app/api/v1/endpoints/admin.py

import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, status, HTTPException, Query
import uuid # Added for student_id path parameter

from ....core.security import require_kinde_admin_role, get_current_user_payload
from ....db import crud # For DB operations
from ....models.student import Student # Changed from TeacherProfile to Student
# If you create a specific AdminTeacherView model later, you can use that.
from ....models.enums import UserRoleEnum

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(require_kinde_admin_role)] # Apply to all routes in this router
)

@router.get(
    "/overview",
    status_code=status.HTTP_200_OK,
    summary="Get Admin Dashboard Overview (Protected)",
    description="Provides a basic overview for the admin dashboard. Requires admin privileges."
)
async def get_admin_overview(
    # current_user_payload: Dict[str, Any] = Depends(require_kinde_admin_role) # Dependency already at router level
    # If you need the payload specifically in the function, you can still add it:
    payload: Dict[str, Any] = Depends(require_kinde_admin_role) # Or Depends(get_current_user_payload) if you want it without re-validating role here
) -> Dict[str, str]:
    logger.info(f"Admin user {payload.get('sub')} accessed admin overview.")
    return {"message": "Welcome to the Admin Dashboard! You have admin access."}

# --- RBAC Helper Function (can be moved to a shared security/utils module if used elsewhere) ---
def _ensure_admin_privileges(payload: Dict[str, Any]):
    """Validates if the current user has admin privileges based on Kinde role and email domain."""
    user_email = payload.get("email")
    kinde_roles = payload.get("roles", []) # Get roles, default to empty list if not present

    # Check for 'Admin' role key within the list of role dictionaries
    has_admin_role_key = any(role.get("key") == UserRoleEnum.ADMIN.value for role in kinde_roles)
    # MODIFIED: Make email check case-insensitive
    is_sendient_email = user_email and user_email.lower().endswith("@sendient.ai")

    if not (has_admin_role_key and is_sendient_email):
        logger.warning(
            f"Admin access DENIED for user {user_email}. "
            f"Has Admin role key: {has_admin_role_key}, Is Sendient email: {is_sendient_email}. "
            f"Kinde roles: {kinde_roles}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have sufficient privileges for this operation."
        )
    logger.info(f"Admin access GRANTED for user {user_email}") # Log successful admin access

# --- Admin Endpoints --- 

@router.get(
    "/students",
    response_model=List[Student],
    summary="Get all student profiles (Admin)",
    description="Retrieves all student profiles. Requires admin privileges."
)
async def get_all_students(
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    logger.info("Admin endpoint /admin/students called.")
    _ensure_admin_privileges(current_user_payload) # Perform RBAC check

    # No need for admin_kinde_id or is_caller_admin for this simplified query
    try:
        # MODIFIED: Call the new CRUD function for fetching all students
        students = await crud.get_all_students_admin()
        logger.info(f"Successfully fetched {len(students)} student profiles for admin.")
        return students
    except Exception as e:
        logger.error(f"Error fetching all students for admin: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while fetching student data."
        )

@router.delete(
    "/students/{student_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a student by ID (Admin)",
    description="Deletes a specific student by their internal ID. Requires admin privileges."
)
async def delete_student_admin(
    student_id: uuid.UUID, # Path parameter for the student's internal ID
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload) # For RBAC
):
    logger.info(f"Admin endpoint /admin/students/{student_id} DELETE called by {current_user_payload.get('sub')}.")
    _ensure_admin_privileges(current_user_payload) # Perform RBAC check

    try:
        # MODIFIED: Call the new admin-specific CRUD function for deleting students
        # It now only requires student_id. Hard delete is False by default.
        deleted = await crud.delete_student_admin(student_id=student_id) # Default to soft delete
        if not deleted:
            logger.warning(f"Failed to delete student {student_id} via admin endpoint. Student not found, already deleted, or delete operation failed in CRUD.")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Student with ID {student_id} not found."
            )
        logger.info(f"Successfully deleted student {student_id}.")
        return # Returns 204 No Content on success
    except HTTPException as http_exc: # Re-raise HTTPException if it's from our logic
        raise http_exc
    except Exception as e:
        logger.error(f"Error deleting student {student_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred while deleting student {student_id}."
        )

# Add other admin-specific endpoints here in the future 