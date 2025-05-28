# app/api/v1/endpoints/teachers.py

import uuid
import logging
from typing import List, Dict, Any, Optional
# Import Request (kept as per user's file)
from fastapi import APIRouter, HTTPException, status, Query, Depends, Request
# Import Pydantic validation error
from pydantic import ValidationError

# Import Pydantic models for Teacher
from ....models.teacher import Teacher, TeacherCreate, TeacherUpdate, TeacherProfile
# Import CRUD functions for Teacher
from ....db import crud
# Import the authentication dependency
from ....core.security import get_current_user_payload
from ....core.config import settings
from ....models.enums import SubscriptionPlan

# Setup logger for this module
logger = logging.getLogger(__name__)

# Create the router instance
router = APIRouter(
    prefix="/teachers",
    tags=["Teachers"]
)

# === Teacher API Endpoints (Updated Flow) ===

# --- GET /me endpoint (Fetch Only) ---
@router.get(
    "/me",
    response_model=TeacherProfile,
    status_code=status.HTTP_200_OK,
    summary="Get current user's teacher profile (Protected)",
    description=(
        "Retrieves the teacher profile associated with the currently authenticated user, "
        "identified by Kinde ID. Returns 404 if the profile does not exist."
    ),
    responses={
        404: {"description": "Teacher profile not found for the current user"},
        400: {"description": "User identifier missing from token"},
    }
)
async def read_current_user_profile(
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Retrieves the current user's teacher profile. Returns 404 if not found.
    Does NOT create the profile automatically.
    """
    user_kinde_id_str = current_user_payload.get("sub")
    if not user_kinde_id_str:
        logger.error("Kinde 'sub' claim missing from token payload.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User identifier missing from token.")

    logger.info(f"Attempting to retrieve profile for Kinde ID: {user_kinde_id_str}")

    # 1. Try to get the existing teacher profile
    teacher = await crud.get_teacher_by_kinde_id(kinde_id=user_kinde_id_str)

    if teacher:
        logger.info(f"Found existing teacher profile for Kinde ID: {user_kinde_id_str}, Internal ID: {teacher.id}")
        
        # MODIFIED: Populate plan limits
        word_limit = None
        char_limit = None
        
        if teacher.current_plan == SubscriptionPlan.FREE:
            word_limit = settings.FREE_PLAN_MONTHLY_WORD_LIMIT
            char_limit = settings.FREE_PLAN_MONTHLY_CHAR_LIMIT
        elif teacher.current_plan == SubscriptionPlan.PRO:
            word_limit = settings.PRO_PLAN_MONTHLY_WORD_LIMIT
            char_limit = settings.PRO_PLAN_MONTHLY_CHAR_LIMIT
        elif teacher.current_plan == SubscriptionPlan.SCHOOLS:
            word_limit = None # Or some indicator of "unlimited"
            char_limit = None # Or some indicator of "unlimited"
            
        # Create the TeacherProfile response
        teacher_profile_response = TeacherProfile(
            **teacher.model_dump(),
            current_plan_word_limit=word_limit,
            current_plan_char_limit=char_limit
        )
        return teacher_profile_response
    else:
        # 2. Profile not found, return 404
        logger.warning(f"Teacher profile not found for Kinde ID: {user_kinde_id_str}. Returning 404.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher profile not found. Please complete your profile." # Keep message consistent with frontend expectation
        )

# --- PUT /me endpoint (Update or Create - Upsert Logic - CORRECTED for User Version) ---
@router.put(
    "/me",
    response_model=Teacher,
    status_code=status.HTTP_200_OK, # Return 200 for both update and create via PUT
    summary="Update or Create current user's teacher profile (Protected)",
    description=(
        "Updates the teacher profile associated with the currently authenticated user. "
        "If the profile does not exist, it creates a new one using the provided data "
        "and the Kinde ID from the token."
    ),
     responses={
        # 404 is less likely now unless DB fails during check
        404: {"description": "Teacher profile not found (should not happen with create logic unless DB error)"},
        400: {"description": "User identifier missing from token or invalid update data"},
        422: {"description": "Validation Error in request body"},
        500: {"description": "Internal server error during profile creation/update"},
    }
)
async def update_or_create_current_user_profile(
    request: Request, # Keep for potential raw body logging on error (as per user's code)
    teacher_data: TeacherUpdate, # Use TeacherUpdate which allows optional fields
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to update the current user's teacher profile.
    If the profile doesn't exist, it creates it using the provided data.
    """
    user_kinde_id_str = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id_str} attempting to update or create their profile.")
    # Use exclude_unset=True to only log fields explicitly sent by the client
    logger.debug(f"Received profile data (TeacherUpdate model): {teacher_data.model_dump(exclude_unset=True)}")

    if not user_kinde_id_str:
        logger.error("Kinde 'sub' claim missing from token payload during profile update/create.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User identifier missing from token.")

    # 1. Try to find the existing teacher
    existing_teacher = await crud.get_teacher_by_kinde_id(kinde_id=user_kinde_id_str)

    if existing_teacher:
        # --- UPDATE PATH ---
        logger.info(f"Found existing profile for {user_kinde_id_str} (ID: {existing_teacher.id}). Proceeding with update.")
        try:
            # Pass only fields that were actually set in the request to the CRUD function
            # NOTE: Using teacher_data directly as per user's original code.
            # Ensure crud.update_teacher handles TeacherUpdate model correctly,
            # potentially ignoring unset fields internally or using model_dump(exclude_unset=True).
            update_payload_for_log = teacher_data.model_dump(exclude_unset=True)
            if not update_payload_for_log:
                 logger.warning(f"Update request for Kinde ID {user_kinde_id_str} contained no fields to update.")
                 # Return existing teacher data if no changes were sent
                 return existing_teacher

            logger.debug(f"Calling crud.update_teacher for Kinde ID {user_kinde_id_str} with data: {update_payload_for_log}")
            updated_teacher = await crud.update_teacher(kinde_id=user_kinde_id_str, teacher_in=teacher_data)

            if updated_teacher is None:
                 # This might happen if the record disappeared between check and update, or DB error
                 logger.error(f"Update failed unexpectedly for teacher Kinde ID {user_kinde_id_str}. Profile might not exist or DB error occurred.")
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher profile not found during update attempt.")

            logger.info(f"Teacher profile for Kinde ID {user_kinde_id_str} updated successfully.")
            return updated_teacher

        except ValidationError as e:
            # This might occur if crud.update_teacher does internal validation that fails
            logger.error(f"Pydantic validation failed during teacher update for Kinde ID {user_kinde_id_str}: {e.errors()}", exc_info=False)
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.errors())
        except Exception as e:
            logger.error(f"CRUD update_teacher failed for Kinde ID {user_kinde_id_str}: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update profile due to server error.")

    else:
        # --- CREATE PATH ---
        logger.warning(f"No existing profile found for {user_kinde_id_str}. Proceeding with creation via PUT.")

        # We MUST get email from token for creation.
        email_from_token = current_user_payload.get("email")
        if not email_from_token:
             logger.error(f"Cannot create profile for {user_kinde_id_str}: Email missing from token.")
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email missing from authentication token. Cannot create profile.")

        # Validate that required fields for creation are present in the request body (teacher_data)
        required_fields_for_create = ['first_name', 'last_name', 'school_name', 'role', 'country', 'state_county']
        missing_required = []
        payload_for_create = {} # This will hold data for the TeacherCreate model

        # Populate required fields from teacher_data (TeacherUpdate instance)
        for field in required_fields_for_create:
            # Use getattr to safely access fields from the TeacherUpdate object
            value = getattr(teacher_data, field, None)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing_required.append(field)
            else:
                payload_for_create[field] = value

        if missing_required:
             logger.error(f"Cannot create profile for {user_kinde_id_str}: Required fields missing from request body: {missing_required}")
             raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Missing required profile fields: {', '.join(missing_required)}")

        # Add email from token
        payload_for_create['email'] = email_from_token

        # *** CORRECTED: Safely add optional fields using getattr ***
        how_did_you_hear_value = getattr(teacher_data, 'how_did_you_hear', None)
        if how_did_you_hear_value: # Add only if value exists and is not empty/None
            payload_for_create['how_did_you_hear'] = how_did_you_hear_value
            logger.debug(f"Adding 'how_did_you_hear': {how_did_you_hear_value}")
        else:
             logger.debug("'how_did_you_hear' not provided or empty.")


        description_value = getattr(teacher_data, 'description', None)
        if description_value: # Add only if value exists and is not empty/None
            payload_for_create['description'] = description_value
            logger.debug(f"Adding 'description': {description_value}")
        else:
            logger.debug("'description' not provided or empty.")

        # is_active defaults to True in TeacherCreate model, so no need to set explicitly unless needed

        logger.debug(f"Constructing TeacherCreate payload: {payload_for_create}")

        # Construct the TeacherCreate object
        try:
            teacher_create_payload = TeacherCreate(**payload_for_create)
        except ValidationError as e:
             logger.error(f"Pydantic validation failed constructing TeacherCreate for Kinde ID {user_kinde_id_str}: {e.errors()}", exc_info=False)
             # Provide more specific error details if possible
             raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid profile data provided for creation: {e.errors()}")

        # Call CRUD create function
        try:
            # Pass kinde_id separately to the CRUD function
            logger.debug(f"Calling crud.create_teacher for Kinde ID {user_kinde_id_str} with payload: {teacher_create_payload.model_dump()}")
            created_teacher = await crud.create_teacher(teacher_in=teacher_create_payload, kinde_id=user_kinde_id_str)

            if created_teacher:
                logger.info(f"Successfully created new teacher profile via PUT for Kinde ID: {user_kinde_id_str}, Internal ID: {created_teacher.id}")
                return created_teacher
            else:
                # This case implies crud.create_teacher returned None.
                # This typically means the uniqueness check within crud.create_teacher found an existing user.
                logger.warning(f"crud.create_teacher returned None for Kinde ID {user_kinde_id_str}, likely due to pre-existing user. Attempting to fetch.")
                # Attempt to fetch the teacher again, as it might have been created concurrently or the initial check missed it.
                refetched_teacher = await crud.get_teacher_by_kinde_id(kinde_id=user_kinde_id_str)
                if refetched_teacher:
                    logger.info(f"Successfully fetched teacher for Kinde ID {user_kinde_id_str} after create_teacher returned None.")
                    return refetched_teacher
                else:
                    # If it's still not found, then it's a genuine issue.
                    logger.error(f"crud.create_teacher returned None AND re-fetch failed for Kinde ID: {user_kinde_id_str}. This is unexpected.")
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create or retrieve teacher profile after attempted creation.")
        except Exception as e:
            # Catch potential exceptions from the CRUD operation (e.g., database errors, unique constraints)
            logger.error(f"Exception during teacher creation via PUT for Kinde ID {user_kinde_id_str}: {e}", exc_info=True)
            # Check for specific DB errors if possible, otherwise return generic 500
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred while creating the teacher profile.")


# --- POST / Endpoint ---
# (Code remains the same as user provided)
@router.post(
    "/",
    response_model=Teacher,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new teacher profile (Protected)",
    description="Creates a new teacher profile linked to the authenticated user's Kinde ID. Returns 409 if profile already exists. (Consider if PUT /me replaces this for user creation)",
    responses={
        409: {"description": "Teacher profile already exists for this user"},
        422: {"description": "Validation Error"},
        500: {"description": "Internal Server Error"}
    }
)
async def create_new_teacher(
    request: Request, # Keep Request to log raw body
    # teacher_in: TeacherCreate, # Temporarily remove Pydantic validation here
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to create a new teacher profile for the calling user.
    NOTE: PUT /me now handles initial profile creation. This endpoint might
    only be needed for specific scenarios or admin actions.
    """
    raw_body_str = ""
    try:
        raw_body = await request.body()
        raw_body_str = raw_body.decode()
        logger.debug(f"Raw body received for POST /teachers/: {raw_body_str}")
    except Exception as e:
        logger.error(f"Could not read raw request body: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not read request body.")

    # --- Explicit Pydantic Validation with Logging ---
    try:
        # Manually parse the raw body using the TeacherCreate model
        teacher_data = TeacherCreate.model_validate_json(raw_body_str)
        logger.info(f"Manual validation successful. Data: {teacher_data.model_dump()}")
    except ValidationError as e:
        logger.error(f"Pydantic validation failed for POST /teachers/: {e.errors()}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.errors()
        )
    except Exception as e:
        logger.error(f"Error parsing request body for POST /teachers/: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid request body format: {e}")
    # --- End Explicit Validation ---

    user_kinde_id_str = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id_str} attempting to create teacher profile using validated data: {teacher_data.model_dump()}")

    if not user_kinde_id_str:
        logger.error("Kinde 'sub' claim missing from token payload during teacher creation.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User identifier missing from token.")

    # Check if profile already exists for this Kinde ID
    existing_teacher = await crud.get_teacher_by_kinde_id(kinde_id=user_kinde_id_str)
    if existing_teacher:
        logger.warning(f"Attempt to create profile failed: Teacher profile already exists for Kinde ID {user_kinde_id_str}.")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Teacher profile already exists for this user."
        )

    logger.debug(f"Calling crud.create_teacher for Kinde ID {user_kinde_id_str} with validated data: {teacher_data.model_dump()}")
    try:
        # Pass the validated Pydantic object and kinde_id to the CRUD function
        created_teacher = await crud.create_teacher(teacher_in=teacher_data, kinde_id=user_kinde_id_str)
    except Exception as e:
        logger.error(f"CRUD create_teacher failed for Kinde ID {user_kinde_id_str}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create profile due to server error.")

    if not created_teacher:
        logger.error(f"crud.create_teacher returned None unexpectedly for Kinde ID {user_kinde_id_str}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create the teacher record due to an internal error."
        )

    logger.info(f"Teacher profile '{created_teacher.first_name} {created_teacher.last_name}' created successfully for user {user_kinde_id_str}.")
    return created_teacher


# --- PUT /me Endpoint for Updating Profile (Now handled by update_or_create_current_user_profile) ---
# This specific function is replaced by the upsert logic above.
# Keeping the original signature here for reference if needed, but it's effectively replaced.
# @router.put(...)
# async def update_current_user_profile(...): ...


# --- GET / Endpoint (List all teachers - likely admin only) ---
# (Code remains the same as user provided)
@router.get(
    "/",
    response_model=List[Teacher],
    status_code=status.HTTP_200_OK,
    summary="Get a list of teachers (Protected)",
    description="Retrieves a list of teachers with optional pagination. Requires authentication (likely admin)."
)
async def read_teachers(
    skip: int = Query(0, ge=0, description="Records to skip"),
    limit: int = Query(100, ge=1, le=500, description="Max records to return"),
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to read list of teachers (skip={skip}, limit={limit}).")
    # TODO: Add authorization check - Only allow admins?

    teachers = await crud.get_all_teachers(skip=skip, limit=limit)
    return teachers


# --- DELETE /me Endpoint (Updated to use Kinde ID) ---
# (Code remains the same as user provided)
@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete current user's teacher profile (Protected)",
    description="Deletes the teacher profile associated with the currently authenticated user.",
     responses={
        404: {"description": "Teacher profile not found for the current user"},
        400: {"description": "User identifier missing from token"},
    }
)
async def delete_current_user_profile(
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to delete the current user's teacher profile.
    Identifies the user via the Kinde ID in the token.
    """
    user_kinde_id_str = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id_str} attempting to delete their own teacher profile.")

    if not user_kinde_id_str:
        logger.error("Kinde 'sub' claim missing from token payload during profile deletion.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User identifier missing from token.")

    # Call CRUD function using Kinde ID to identify the teacher to delete
    # Ensure crud.delete_teacher supports deletion by kinde_id
    try:
        deleted_successfully = await crud.delete_teacher(kinde_id=user_kinde_id_str)
    except Exception as e:
        logger.error(f"Unexpected error during deletion of teacher profile for Kinde ID {user_kinde_id_str}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred while deleting the teacher profile.")

    if not deleted_successfully:
        # crud.delete_teacher returning False likely means the record wasn't found
        logger.warning(f"Attempted to delete non-existent teacher profile for Kinde ID: {user_kinde_id_str}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Teacher profile for Kinde ID {user_kinde_id_str} not found."
        )

    logger.info(f"Teacher profile for Kinde ID {user_kinde_id_str} deleted successfully.")
    # Return None for 204 No Content response
    return None
