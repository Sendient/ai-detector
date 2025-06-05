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
from ....core.security import get_current_user_payload, require_kinde_admin_role
from ....core.config import settings
from ....models.enums import SubscriptionPlan, UserRoleEnum

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
    request: Request,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Retrieves the current user's teacher profile. Returns 404 if not found.
    Ensures is_administrator flag is synchronized with Kinde role and email policy.
    """
    logger.info("-----------------------------------------------------")
    logger.info("GET /me: Endpoint called.")
    
    auth_header = request.headers.get("Authorization")
    logger.info(f"GET /me: Received Authorization header: {auth_header}")
    
    logger.info(f"GET /me: Result of get_current_user_payload (already decoded by dependency): {current_user_payload}")

    user_kinde_id_str = current_user_payload.get("sub")
    logger.info(f"GET /me: Extracted Kinde ID (sub) from payload: {user_kinde_id_str}")

    if not user_kinde_id_str:
        logger.error("GET /me: Kinde 'sub' claim missing from token payload. Raising 400.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User identifier missing from token.")

    logger.info(f"GET /me: Attempting to retrieve profile from DB for Kinde ID: {user_kinde_id_str}")
    
    try:
        teacher = await crud.get_teacher_by_kinde_id(kinde_id=user_kinde_id_str)
        logger.info(f"GET /me: crud.get_teacher_by_kinde_id returned: {teacher}")
    except Exception as e:
        logger.error(f"GET /me: Exception during crud.get_teacher_by_kinde_id: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving teacher profile from database.")

    if teacher:
        # Ensure is_administrator flag is synchronized based on Kinde role and email policy
        # This logic should be authoritative.
        email_from_token = current_user_payload.get("email", "").lower()
        kinde_roles_from_token = current_user_payload.get("roles", [])
        
        logger.info(f"GET /me (User Profile Exists): Admin status determination for Kinde ID {user_kinde_id_str}:")
        logger.info(f"  - Email from token: {email_from_token}")
        logger.info(f"  - Kinde roles from token: {kinde_roles_from_token}")

        is_sendient_email = email_from_token.endswith("@sendient.ai")
        # MODIFIED: Standardized admin role check
        has_kinde_admin_role = any(
            isinstance(role, dict) and role.get("key") == UserRoleEnum.ADMIN.value
            for role in kinde_roles_from_token
        )
        
        logger.info(f"  - Has '{UserRoleEnum.ADMIN.value}' role in Kinde: {has_kinde_admin_role}")
        logger.info(f"  - Is Sendient email (@sendient.ai): {is_sendient_email}")

        authoritative_is_administrator = has_kinde_admin_role and is_sendient_email
        logger.info(f"  - Authoritative is_administrator status: {authoritative_is_administrator}")

        if teacher.is_administrator != authoritative_is_administrator:
            logger.info(f"GET /me: Discrepancy found. DB is_administrator: {teacher.is_administrator}, Authoritative: {authoritative_is_administrator}. Attempting to update DB.")
            try:
                updated_teacher_data = TeacherUpdate(is_administrator=authoritative_is_administrator)
                # Use a method that only updates specific fields or fetches and then updates
                # For simplicity, assuming crud.update_teacher can handle partial updates based on model
                updated_teacher = await crud.update_teacher(
                    kinde_id=user_kinde_id_str, 
                    teacher_in=updated_teacher_data,
                    authoritative_is_admin_status=authoritative_is_administrator,
                    is_sync_update=True # Flag to indicate this is an internal sync
                )
                if updated_teacher:
                    teacher = updated_teacher # Use the updated teacher object
                    logger.info(f"GET /me: Successfully updated is_administrator in DB for Kinde ID {user_kinde_id_str} to {teacher.is_administrator}")
                else:
                    logger.error(f"GET /me: Failed to update is_administrator in DB for Kinde ID {user_kinde_id_str} during sync.")
                    # Potentially raise an error or handle, but for now, proceed with originally fetched teacher
            except Exception as e_update:
                logger.error(f"GET /me: Exception during is_administrator sync update for Kinde ID {user_kinde_id_str}: {e_update}", exc_info=True)
                # Proceed with the originally fetched teacher data if update fails

        logger.info(f"GET /me: Found existing teacher profile for Kinde ID: {user_kinde_id_str}, Internal ID: {teacher.id}, is_admin (after sync attempt): {teacher.is_administrator}")
        # --- END RBAC Sync Logic for GET /me ---
        
        # Populate plan limits (word_limit and char_limit are local variables here)
        word_limit = None
        char_limit = None
        
        if teacher.current_plan == SubscriptionPlan.FREE:
            word_limit = settings.FREE_PLAN_MONTHLY_WORD_LIMIT
            char_limit = settings.FREE_PLAN_MONTHLY_CHAR_LIMIT
        elif teacher.current_plan == SubscriptionPlan.PRO:
            word_limit = settings.PRO_PLAN_MONTHLY_WORD_LIMIT
            char_limit = settings.PRO_PLAN_MONTHLY_CHAR_LIMIT
        elif teacher.current_plan == SubscriptionPlan.SCHOOLS:
            word_limit = None # Represents unlimited
            char_limit = None # Represents unlimited
            
        # Calculate remaining words for the current cycle
        # teacher.words_used_current_cycle is now expected to be populated from the DB
        # word_limit is the allowance for the current plan
        remaining_words = None
        words_used = teacher.words_used_current_cycle if teacher.words_used_current_cycle is not None else 0

        if word_limit is not None: # For Free or Pro plans
            remaining_words = max(0, word_limit - words_used)
        # For unlimited plans (e.g., Schools plan), remaining_words remains None, which is correctly handled by frontend.

        # Create the TeacherProfile response, including the new fields
        teacher_profile_response = TeacherProfile(
            **teacher.model_dump(), # This will include words_used_current_cycle and documents_processed_current_cycle from the teacher object
            current_plan_word_limit=word_limit, # This is the allowance
            current_plan_char_limit=char_limit,
            remaining_words_current_cycle=remaining_words
        )
        logger.info(f"GET /me: Returning teacher profile: {teacher_profile_response.model_dump_json(indent=2)}") # Enhanced logging
        logger.info("-----------------------------------------------------")
        return teacher_profile_response
    else:
        logger.warning(f"GET /me: Teacher profile not found in DB for Kinde ID: {user_kinde_id_str}. Raising 404.")
        logger.info("-----------------------------------------------------")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher profile not found.")

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
    logger.info("-----------------------------------------------------")
    logger.info("PUT /me: Endpoint called.")
    
    auth_header = request.headers.get("Authorization")
    logger.info(f"PUT /me: Received Authorization header: {auth_header}")
    
    logger.info(f"PUT /me: Result of get_current_user_payload (already decoded by dependency): {current_user_payload}")

    user_kinde_id_str = current_user_payload.get("sub")
    logger.info(f"PUT /me: Extracted Kinde ID (sub) from payload: {user_kinde_id_str}")

    if not user_kinde_id_str:
        logger.error("PUT /me: Kinde 'sub' claim missing. Raising 400.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User identifier missing from token.")

    # --- BEGIN RBAC Sync Logic for PUT /me ---
    email_from_token = current_user_payload.get("email")
    kinde_roles = current_user_payload.get("roles", [])
    # MODIFIED: Standardized admin role check
    has_admin_role_in_kinde = any(role.get('key') == UserRoleEnum.ADMIN.value for role in kinde_roles if isinstance(role, dict))
    is_sendient_email = email_from_token and email_from_token.lower().endswith('@sendient.ai') # Make email check case-insensitive here too for consistency
    
    # This is the authoritative is_administrator status based on Kinde role and email policy
    authoritative_is_administrator = has_admin_role_in_kinde and is_sendient_email
    # MODIFIED Log (and removed original less detailed log)
    # +++ ADDED VERBOSE LOGGING +++
    logger.info(f"PUT /me: Admin status determination for Kinde ID {user_kinde_id_str}:")
    logger.info(f"  - Email from token: {email_from_token}")
    logger.info(f"  - Kinde roles from token: {kinde_roles}")
    logger.info(f"  - Has 'Admin' role in Kinde: {has_admin_role_in_kinde}")
    logger.info(f"  - Is Sendient email (@sendient.ai): {is_sendient_email}")
    logger.info(f"  - Authoritative is_administrator status: {authoritative_is_administrator}")
    # +++ END ADDED VERBOSE LOGGING +++
    # --- END RBAC Sync Logic ---

    # 1. Try to find the existing teacher
    existing_teacher = await crud.get_teacher_by_kinde_id(kinde_id=user_kinde_id_str)

    if existing_teacher:
        # --- UPDATE PATH ---
        logger.info(f"Found existing profile for {user_kinde_id_str} (ID: {existing_teacher.id}). Proceeding with update.")
        try:
            update_payload_for_log = teacher_data.model_dump(exclude_unset=True)
            if not update_payload_for_log and existing_teacher.is_administrator == authoritative_is_administrator: # If no data sent and admin status matches
                 logger.warning(f"Update request for Kinde ID {user_kinde_id_str} contained no fields to update and admin status is already in sync.")
                 return existing_teacher

            logger.debug(f"Calling crud.update_teacher for Kinde ID {user_kinde_id_str} with data: {update_payload_for_log} and authoritative_is_administrator: {authoritative_is_administrator}")
            # We will modify crud.update_teacher to accept authoritative_is_administrator
            updated_teacher = await crud.update_teacher(
                kinde_id=user_kinde_id_str, 
                teacher_in=teacher_data, 
                # Pass the determined admin status to the CRUD function
                authoritative_is_admin_status=authoritative_is_administrator 
            )

            if updated_teacher is None:
                 logger.error(f"Update failed unexpectedly for teacher Kinde ID {user_kinde_id_str}. Profile might not exist or DB error occurred.")
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher profile not found during update attempt.")

            logger.info(f"Teacher profile for Kinde ID {user_kinde_id_str} updated successfully. Synced is_administrator to {updated_teacher.is_administrator}")
            return updated_teacher

        except ValidationError as e:
            logger.error(f"Pydantic validation failed during teacher update for Kinde ID {user_kinde_id_str}: {e.errors()}", exc_info=False)
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.errors())
        except Exception as e:
            logger.error(f"CRUD update_teacher failed for Kinde ID {user_kinde_id_str}: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update profile due to server error.")

    else:
        # --- CREATE PATH ---
        logger.warning(f"No existing profile found for {user_kinde_id_str}. Proceeding with creation via PUT.")

        if not email_from_token: # Already fetched for RBAC sync
             logger.error(f"Cannot create profile for {user_kinde_id_str}: Email missing from token.")
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email missing from authentication token. Cannot create profile.")

        required_fields_for_create = ['first_name', 'last_name', 'school_name', 'role', 'country', 'state_county']
        missing_required = []
        payload_for_create = {} 

        for field in required_fields_for_create:
            value = getattr(teacher_data, field, None)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing_required.append(field)
            else:
                payload_for_create[field] = value

        if missing_required:
             logger.error(f"Cannot create profile for {user_kinde_id_str}: Required fields missing from request body: {missing_required}")
             raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Missing required profile fields: {', '.join(missing_required)}")

        payload_for_create['email'] = email_from_token
        
        # Add optional fields
        how_did_you_hear_value = getattr(teacher_data, 'how_did_you_hear', None)
        if how_did_you_hear_value:
            payload_for_create['how_did_you_hear'] = how_did_you_hear_value
        
        description_value = getattr(teacher_data, 'description', None)
        if description_value:
            payload_for_create['description'] = description_value

        # Add the determined is_administrator status to the creation payload
        # This ensures the TeacherCreate model will have it if it's defined there.
        # If TeacherCreate inherits it from TeacherBase, it's already there by default.
        # We are explicitly setting it based on our logic.
        payload_for_create['is_administrator'] = authoritative_is_administrator
        logger.debug(f"Constructing TeacherCreate payload: {payload_for_create}")

        try:
            teacher_create_payload = TeacherCreate(**payload_for_create)
        except ValidationError as e:
             logger.error(f"Pydantic validation failed constructing TeacherCreate for Kinde ID {user_kinde_id_str}: {e.errors()}", exc_info=False)
             raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid profile data provided for creation: {e.errors()}")

        try:
            logger.debug(f"Calling crud.create_teacher for Kinde ID {user_kinde_id_str} with payload: {teacher_create_payload.model_dump()} and authoritative_is_administrator: {authoritative_is_administrator}")
            # We will modify crud.create_teacher to accept/use authoritative_is_administrator
            # The authoritative_is_administrator is already part of teacher_create_payload if the model supports it.
            # If TeacherCreate model does not explicitly have is_administrator but TeacherBase does,
            # it should be inherited. Let's ensure create_teacher is aware.
            created_teacher = await crud.create_teacher(
                teacher_in=teacher_create_payload, 
                kinde_id=user_kinde_id_str
                # Assuming crud.create_teacher will use the is_administrator from teacher_in
                # or we modify it to take an explicit authoritative_is_admin_status if needed
            )

            if created_teacher:
                logger.info(f"Successfully created new teacher profile via PUT for Kinde ID: {user_kinde_id_str}, Internal ID: {created_teacher.id}. Synced is_administrator to {created_teacher.is_administrator}")
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


# --- GET / Endpoint (List all teachers - likely admin only) ---
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
    current_user_payload: Dict[str, Any] = Depends(require_kinde_admin_role)
):
    """
    Retrieves a list of all teachers. Supports pagination.
    
    This endpoint is restricted to users with the 'admin' role.
    """
    logger.info(f"User {current_user_payload.get('sub')} listing all teachers with skip={skip}, limit={limit}")
    teachers = await crud.get_all_teachers(skip=skip, limit=limit)
    if not teachers:
        logger.warning(f"No teachers found for the given skip and limit. Returning empty list.")
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
