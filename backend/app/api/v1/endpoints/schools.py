# app/api/v1/endpoints/schools.py

import uuid
import logging # Import logging
from typing import List, Dict, Any # Add Dict, Any
from fastapi import APIRouter, HTTPException, status, Query, Depends # Add Depends

# Import Pydantic models for request/response validation
from app.models.school import School, SchoolCreate, SchoolUpdate
# Import CRUD functions for database interaction
from app.db import crud # Assuming crud functions are in app/db/crud.py
# Import the authentication dependency
from app.core.security import get_current_user_payload # Adjust path

# Setup logger for this module
logger = logging.getLogger(__name__)

# Create the router instance
router = APIRouter(
    prefix="/schools",
    tags=["Schools"]
)

# === API Endpoints (Now Protected) ===

@router.post(
    "/",
    response_model=School,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new school (Protected)", # Updated summary
    description="Creates a new school record in the database. Requires authentication." # Updated description
)
async def create_new_school(
    school_in: SchoolCreate,
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to create a new school.
    - **school_in**: School data based on the SchoolCreate model.
    """
    user_kinde_id = current_user_payload.get("sub") # Get user ID from token payload
    logger.info(f"User {user_kinde_id} attempting to create school: {school_in.school_name}")
    # TODO: Add authorization check - does this user have permission to create schools?

    # Call the corresponding CRUD function
    created_school = await crud.create_school(school_in=school_in)
    if not created_school:
        # This could happen if there's a database error during creation
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create the school record."
        )
    logger.info(f"School '{created_school.school_name}' created successfully by user {user_kinde_id}.")
    return created_school

@router.get(
    "/{school_id}",
    response_model=School,
    status_code=status.HTTP_200_OK,
    summary="Get a specific school by ID (Protected)", # Updated summary
    description="Retrieves the details of a single school using its unique ID. Requires authentication." # Updated description
)
async def read_school(
    school_id: uuid.UUID, # Use UUID type hint for path parameter validation
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to retrieve a specific school by its ID.
    - **school_id**: The UUID of the school to retrieve.
    """
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to read school ID: {school_id}")
    # TODO: Add authorization check - does this user have permission to view this school?

    school = await crud.get_school_by_id(school_id=school_id)
    if school is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"School with ID {school_id} not found."
        )
    return school

@router.get(
    "/",
    response_model=List[School],
    status_code=status.HTTP_200_OK,
    summary="Get a list of schools (Protected)", # Updated summary
    description="Retrieves a list of schools with optional pagination. Requires authentication." # Updated description
)
async def read_schools(
    skip: int = Query(0, ge=0, description="Number of records to skip for pagination"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of records to return"),
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to retrieve a list of schools. Supports pagination via skip/limit query parameters.
    - **skip**: Number of records to skip.
    - **limit**: Maximum number of records per page.
    """
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to read list of schools (skip={skip}, limit={limit}).")
    # TODO: Add authorization check - e.g., only show schools user is associated with?

    schools = await crud.get_all_schools(skip=skip, limit=limit)
    # No need to raise 404 if list is empty, an empty list is a valid response
    return schools

@router.put(
    "/{school_id}",
    response_model=School,
    status_code=status.HTTP_200_OK,
    summary="Update an existing school (Protected)", # Updated summary
    description="Updates the details of an existing school identified by its ID. Requires authentication." # Updated description
)
async def update_existing_school(
    school_id: uuid.UUID,
    school_in: SchoolUpdate, # Use the SchoolUpdate model for partial updates
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to update an existing school.
    - **school_id**: The UUID of the school to update.
    - **school_in**: The school data fields to update, based on SchoolUpdate model.
    """
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to update school ID: {school_id}")
    # TODO: Add authorization check - does this user have permission to update this school?

    updated_school = await crud.update_school(school_id=school_id, school_in=school_in)
    if updated_school is None:
        # This happens if the school_id doesn't exist
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"School with ID {school_id} not found or update failed."
        )
    logger.info(f"School ID {school_id} updated successfully by user {user_kinde_id}.")
    return updated_school

@router.delete(
    "/{school_id}",
    status_code=status.HTTP_204_NO_CONTENT, # Standard response for successful DELETE
    summary="Delete a school (Protected)", # Updated summary
    description="Deletes a school record from the database using its unique ID. Requires authentication." # Updated description
)
async def delete_existing_school(
    school_id: uuid.UUID,
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to delete a specific school by its ID.
    - **school_id**: The UUID of the school to delete.
    """
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to delete school ID: {school_id}")
    # TODO: Add authorization check - does this user have permission to delete this school? (Likely admin only)

    deleted_successfully = await crud.delete_school(school_id=school_id)
    if not deleted_successfully:
        # This happens if the school_id doesn't exist
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"School with ID {school_id} not found."
        )
    logger.info(f"School ID {school_id} deleted successfully by user {user_kinde_id}.")
    # If deletion was successful, return None. FastAPI handles the 204 response.
    return None

# --- End of Endpoints ---
