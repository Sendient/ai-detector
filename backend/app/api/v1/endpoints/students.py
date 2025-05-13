# app/api/v1/endpoints/students.py

import uuid
import logging # Import logging
from typing import List, Optional, Dict, Any # Add Dict, Any
from fastapi import APIRouter, HTTPException, status, Query, Depends # Add Depends

# Use absolute imports from the 'app' package root
from app.models.student import Student, StudentCreate, StudentUpdate
from app.db import crud
from app.core.security import get_current_user_payload

# Setup logger for this module
logger = logging.getLogger(__name__)

# Create the router instance
router = APIRouter(
    prefix="/students",
    tags=["Students"]
)

# === Student API Endpoints (Now Protected) ===

@router.post(
    "/",
    response_model=Student,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new student (Protected)", # Updated summary
    description="Creates a new student record. Requires authentication. Returns a 409 Conflict error if the optional external_student_id is provided and already exists." # Updated description
)
async def create_new_student(
    student_in: StudentCreate,
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to create a new student.
    - **student_in**: Student data based on the StudentCreate model.
    """
    user_kinde_id = current_user_payload.get("sub")
    if not user_kinde_id:
        logger.warning("Attempted to create student without Kinde ID in token payload.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

    logger.info(f"User {user_kinde_id} attempting to create student: {student_in.first_name} {student_in.last_name}")
    # TODO: Add authorization check - does this user (teacher/admin) have permission to add students?
    # (e.g., are they adding to a class/school they manage?)

    created_student = await crud.create_student(student_in=student_in, teacher_id=user_kinde_id)
    if created_student is None:
        logger.error(f"Failed to create student in DB for teacher {user_kinde_id}.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create student")

    logger.info(f"Student created successfully: {created_student.id} for teacher {user_kinde_id}")
    # Return the full Student model (which includes the id)
    return created_student

@router.get(
    "/{student_internal_id}",
    response_model=Student,
    status_code=status.HTTP_200_OK,
    summary="Get a specific student by internal ID (Protected)", # Updated summary
    description="Retrieves the details of a single student using their internal unique ID. Requires authentication." # Updated description
)
async def read_student(
    student_internal_id: uuid.UUID, # Internal ID ('id' aliased to '_id' in model)
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to retrieve a specific student by their internal ID.
    - **student_internal_id**: The internal UUID of the student to retrieve.
    """
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to read student internal ID: {student_internal_id}")

    student = await crud.get_student_by_id(
        student_internal_id=student_internal_id,
        teacher_id=user_kinde_id
    )
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with internal ID {student_internal_id} not found."
        )

    # TODO: Add authorization check - Can user 'user_kinde_id' view this student?
    # (e.g., is the student in one of the user's ClassGroups? Is the user a school admin?)

    return student

@router.get(
    "/",
    response_model=List[Student],
    status_code=status.HTTP_200_OK,
    summary="Get a list of students (Protected)", # Updated summary
    description="Retrieves a list of students with optional filtering and pagination. Requires authentication." # Updated description
)
async def read_students(
    external_student_id: Optional[str] = Query(None, description="Filter by external student ID"),
    first_name: Optional[str] = Query(None, description="Filter by first name (case-insensitive)"),
    last_name: Optional[str] = Query(None, description="Filter by last name (case-insensitive)"),
    year_group: Optional[str] = Query(None, description="Filter by year group"),
    skip: int = Query(0, ge=0, description="Records to skip"),
    limit: int = Query(100, ge=1, le=500, description="Max records to return"),
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to retrieve a list of students. Supports filtering and pagination.
    """
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to read list of students with filters.")

    # TODO: Add authorization logic. Listing ALL students might require admin rights.
    # Non-admins should likely only see students within their associated ClassGroups or School.
    # This might involve modifying the crud.get_all_students function or adding a new one
    # that accepts a list of permissible student IDs based on the user's context.

    students = await crud.get_all_students(
        teacher_id=user_kinde_id,
        external_student_id=external_student_id,
        first_name=first_name,
        last_name=last_name,
        year_group=year_group,
        skip=skip,
        limit=limit
    )
    return students

@router.put(
    "/{student_internal_id}",
    response_model=Student,
    status_code=status.HTTP_200_OK,
    summary="Update an existing student (Protected)", # Updated summary
    description="Updates details of an existing student. Requires authentication. Returns 404 if student not found. Returns 409 if update violates unique external_student_id." # Updated description
)
async def update_existing_student(
    student_internal_id: uuid.UUID,
    student_in: StudentUpdate,
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to update an existing student.
    """
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to update student internal ID: {student_internal_id}")

    # --- Authorization Check ---
    # First, check if the student exists AND belongs to the current user
    existing_student = await crud.get_student_by_id(
        student_internal_id=student_internal_id,
        teacher_id=user_kinde_id # Use authenticated user's ID
    )
    # --- End Authorization Check ---

    # Using the improved logic: check existence first
    # existing_student = await crud.get_student_by_id(student_internal_id=student_internal_id)
    if not existing_student:
        # This now correctly handles both not found and not authorized
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with internal ID {student_internal_id} not found or access denied."
        )

    # Try to update (we know the user owns the student at this point)
    updated_student = await crud.update_student(
        student_internal_id=student_internal_id, 
        teacher_id=user_kinde_id,  # <<< ADDED teacher_id HERE
        student_in=student_in
    )
    if updated_student is None:
        # If update failed after existence/ownership check, likely a duplicate external_student_id
        if student_in.external_student_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Update failed. Student with external_student_id '{student_in.external_student_id}' may already exist."
            )
        else:
            # Or some other unexpected DB error during update
             raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not update the student record due to an internal error."
            )
    logger.info(f"Student internal ID {student_internal_id} updated successfully by user {user_kinde_id}.")
    return updated_student

@router.delete(
    "/{student_internal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a student (Protected)", # Updated summary
    description="Deletes a student record using their internal unique ID. Requires authentication." # Updated description
)
async def delete_existing_student(
    student_internal_id: uuid.UUID,
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to delete a specific student by their internal ID.
    """
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to delete student internal ID: {student_internal_id}")

    # --- Authorization Check ---
    # Check if the student exists AND belongs to the current user before deleting
    student_to_delete = await crud.get_student_by_id(
        student_internal_id=student_internal_id,
        teacher_id=user_kinde_id # Use authenticated user's ID
    )
    if not student_to_delete:
        # Raise 404 whether it doesn't exist or belongs to another user
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with internal ID {student_internal_id} not found or access denied."
        )
    # --- End Authorization Check ---

    # Proceed with deletion only if the check above passed
    deleted_successfully = await crud.delete_student(student_internal_id=student_internal_id)
    if not deleted_successfully:
        # This case should theoretically not happen if the check passed, but handle defensively
        logger.error(f"Failed to delete student {student_internal_id} even after ownership check passed for user {user_kinde_id}.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not delete student with internal ID {student_internal_id} after authorization."
            # Older code raised 404, but 500 seems more appropriate if it existed moments ago
            # status_code=status.HTTP_404_NOT_FOUND,
            # detail=f"Student with internal ID {student_internal_id} not found."
        )
    logger.info(f"Student internal ID {student_internal_id} deleted successfully by user {user_kinde_id}.")
    # No content returned on successful delete
    return None

