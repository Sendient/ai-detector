# backend/app/api/v1/endpoints/admin.py

import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, status, HTTPException, Query
import uuid # Added for student_id path parameter

from ....core.security import require_kinde_admin_role, get_current_user_payload
from ....db import crud # For DB operations
from ....models.student import Student # Changed from TeacherProfile to Student
from ....models.teacher import TeacherProfile  # Assuming a Teacher model to represent the data, IMPORT TeacherProfile
from ....models.document import Document # <-- Import the Document model
from ....models.enums import UserRoleEnum, SubscriptionPlan # Added SubscriptionPlan
from ....core.config import settings # Added settings

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
    "/students", # REVERTED PATH
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

# Pydantic model for the response. We might need a more detailed one later.
# For now, using the existing Teacher model, but it might miss some fields from your example.
# We will need to create a TeacherAdminView model that includes ALL fields.

# TeacherAdminView inherits from TeacherProfile, which includes comprehensive teacher data
# (including fields from TeacherInDBBase like kinde_id, stripe_customer_id, etc.)
# and calculated fields like plan limits and remaining words.
# If additional fields (e.g., last_login_date) are required in the future,
# they would need to be added to the base models and database schema.
class TeacherAdminView(TeacherProfile):
    pass

@router.get(
    "/teachers/all",
    response_model=List[TeacherAdminView], # Will be List[TeacherAdminView]
    summary="Get all teacher profiles (Admin Only)",
    description="Retrieves a comprehensive list of all teacher profiles in the system, including all MongoDB attributes."
)
async def get_all_teachers_admin(
    skip: int = Query(0, ge=0, description="Records to skip for pagination"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    # current_user_payload: Dict[str, Any] = Depends(get_current_user_payload) # Handled by router dependency
):
    """
    Admin-only endpoint to retrieve all teacher records with all their attributes.
    Supports pagination via skip and limit query parameters.
    """
    logger.info(f"GET /admin/teachers/all called. Skip: {skip}, Limit: {limit}")
    try:
        teachers_db_models = await crud.get_all_teachers_admin_view(skip=skip, limit=limit)
        
        if not teachers_db_models:
            logger.info("GET /admin/teachers/all: No teachers found.")
            return []
            
        response_teachers = []
        for teacher_db_model in teachers_db_models:
            word_limit = None
            char_limit = None # Initialize char_limit

            # Determine word_limit and char_limit based on the teacher's current plan
            if teacher_db_model.current_plan == SubscriptionPlan.FREE:
                word_limit = settings.FREE_PLAN_MONTHLY_WORD_LIMIT
                char_limit = settings.FREE_PLAN_MONTHLY_CHAR_LIMIT
            elif teacher_db_model.current_plan == SubscriptionPlan.PRO:
                word_limit = settings.PRO_PLAN_MONTHLY_WORD_LIMIT
                char_limit = settings.PRO_PLAN_MONTHLY_CHAR_LIMIT
            elif teacher_db_model.current_plan == SubscriptionPlan.SCHOOLS:
                word_limit = None # Unlimited
                char_limit = None # Unlimited

            # Calculate remaining_words
            remaining_words = None
            words_used = teacher_db_model.words_used_current_cycle if teacher_db_model.words_used_current_cycle is not None else 0
            
            if word_limit is not None: # For Free or Pro plans
                remaining_words = max(0, word_limit - words_used)
            # For SCHOOLS plan, remaining_words stays None, which is handled by TeacherAdminView and frontend.

            # Prepare data for TeacherAdminView instance
            teacher_data_for_view = teacher_db_model.model_dump()
            teacher_data_for_view['current_plan_word_limit'] = word_limit
            teacher_data_for_view['remaining_words_current_cycle'] = remaining_words
            teacher_data_for_view['current_plan_char_limit'] = char_limit # Add char_limit

            # Create TeacherAdminView instance with all data including calculated fields
            teacher_admin_view = TeacherAdminView(**teacher_data_for_view)
            response_teachers.append(teacher_admin_view)

        logger.info(f"GET /admin/teachers/all: Returning {len(response_teachers)} teacher records with calculated usage.")
        return response_teachers

    except HTTPException as http_exc:
        logger.error(f"GET /admin/teachers/all: HTTPException - {http_exc.status_code} - {http_exc.detail}", exc_info=True)
        raise http_exc
    except Exception as e:
        logger.error(f"GET /admin/teachers/all: An unexpected error occurred: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while fetching teacher data."
        )

@router.get(
    "/documents/all",
    response_model=List[Document],
    summary="Get all documents (Admin Only)",
    description="Retrieves a comprehensive list of all documents in the system. Requires admin privileges."
)
async def get_all_documents_admin(
    skip: int = Query(0, ge=0, description="Records to skip for pagination"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    # current_user_payload: Dict[str, Any] = Depends(get_current_user_payload) # Handled by router dependency
):
    logger.info(f"GET /admin/documents/all called. Skip: {skip}, Limit: {limit}")
    try:
        documents = await crud.get_all_documents_admin(skip=skip, limit=limit) # Assumes a new CRUD function
        if not documents:
            logger.info("GET /admin/documents/all: No documents found.")
            return []
        
        logger.info(f"GET /admin/documents/all: Returning {len(documents)} document records.")
        return documents
    except HTTPException as http_exc:
        logger.error(f"GET /admin/documents/all: HTTPException - {http_exc.status_code} - {http_exc.detail}", exc_info=True)
        raise http_exc
    except Exception as e:
        logger.error(f"GET /admin/documents/all: An unexpected error occurred: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while fetching document data."
        )

# TODO:
# 1. Define the TeacherAdminView Pydantic model fully, incorporating all fields from the user's MongoDB example.
#    Ensure it inherits or aligns with the base Teacher model as appropriate.
# 2. Implement the crud.get_all_teachers_admin_view function in backend/app/db/crud.py.
#    This function should fetch all specified fields from MongoDB and handle pagination.
# 3. Add this new admin_router to the FastAPI application in backend/app/main.py.
# 4. Ensure the `require_admin_privileges` dependency correctly protects the endpoint.

# Add other admin-specific endpoints here in the future 