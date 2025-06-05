# app/api/v1/endpoints/class_groups.py

import uuid # Corrected Indentation
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, status, Query, Depends
from pydantic import ValidationError # Added ValidationError

# Import Pydantic models for ClassGroup
from ....models.class_group import (
    ClassGroup, 
    ClassGroupClientCreate, # Added for client payload
    ClassGroupCreate, 
    ClassGroupUpdate,
)
# Import CRUD functions for ClassGroup
from ....db import crud
# Import the authentication dependency
from ....core.security import get_current_user_payload

# Setup logger for this module
logger = logging.getLogger(__name__)

# Create the router instance
router = APIRouter(
    prefix="/class-groups",
    tags=["Class Groups"]
)

# === Helper for Authorization Check ===
# --- RESTORED ASYNC HELPER ---
async def _check_user_is_teacher_of_group( # Needs async to call crud.get_teacher_by_kinde_id
    class_group: ClassGroup,
    user_payload: Dict[str, Any],
    action: str = "access"
):
    """
    Checks if the authenticated user is the teacher assigned to the class group.
    Compares the internal teacher UUID from the class group with the internal UUID
    associated with the requesting user's Kinde ID.
    """
    requesting_user_kinde_id = user_payload.get("sub")
    logger.debug(f"Auth Check Step 1: Kinde ID from token = {requesting_user_kinde_id} (Type: {type(requesting_user_kinde_id)})")
    if not requesting_user_kinde_id:
         logger.error("Authorization check failed: 'sub' claim missing from token payload.")
         raise HTTPException(
             status_code=status.HTTP_401_UNAUTHORIZED, # Or 400
             detail="Invalid authentication token (missing user identifier)."
         )

    # --- Fetch the Teacher record associated with the requesting user's Kinde ID ---
    requesting_teacher = None # Initialize
    try:
         logger.debug(f"Auth Check Step 2: Fetching teacher by Kinde ID: {requesting_user_kinde_id}")
         requesting_teacher = await crud.get_teacher_by_kinde_id(kinde_id=requesting_user_kinde_id)
    except Exception as e:
         logger.error(f"Auth Check Step 2 FAILED: Error fetching teacher by Kinde ID {requesting_user_kinde_id}: {e}", exc_info=True)
         raise HTTPException(status_code=500, detail="Error retrieving teacher profile.")

    if not requesting_teacher:
        logger.error(f"Authorization check failed: No teacher record found for Kinde ID {requesting_user_kinde_id}.")
        # If the user is authenticated but has no teacher profile, it's likely a setup issue or they aren't a teacher.
        # 403 Forbidden is appropriate as they lack the necessary role/profile in *our* system.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authenticated user does not have a teacher profile in the system."
        )
    logger.debug(f"Auth Check Step 2 SUCCESS: Found teacher record: {requesting_teacher.id}")


    # --- Compare the internal teacher ID from the class group with the fetched teacher's internal ID ---
    teacher_id_in_group = class_group.teacher_id # This should be the internal UUID stored in the ClassGroup document
    requesting_teacher_internal_id = requesting_teacher.id # This is the internal UUID (_id mapped to id) from the Teacher document

    logger.debug(f"Auth Check Step 3: Comparing IDs - ClassGroup Teacher ID = {teacher_id_in_group} (Type: {type(teacher_id_in_group)}), Requesting User's Teacher ID = {requesting_teacher_internal_id} (Type: {type(requesting_teacher_internal_id)})")

    # Ensure both IDs are UUIDs before comparison, attempting conversion if necessary
    try:
        # Convert teacher_id_in_group if it's not already UUID
        if not isinstance(teacher_id_in_group, uuid.UUID):
            logger.debug(f"Auth Check Step 3a: Converting ClassGroup Teacher ID '{teacher_id_in_group}' to UUID...")
            teacher_id_in_group = uuid.UUID(str(teacher_id_in_group))
            logger.debug(f"Auth Check Step 3a: Conversion successful: {teacher_id_in_group}")

        # Convert requesting_teacher_internal_id if it's not already UUID (should be from Pydantic model)
        if not isinstance(requesting_teacher_internal_id, uuid.UUID):
            logger.warning(f"Auth Check Step 3b: Requesting teacher internal ID '{requesting_teacher_internal_id}' is not UUID type, attempting conversion...")
            requesting_teacher_internal_id = uuid.UUID(str(requesting_teacher_internal_id))
            logger.debug(f"Auth Check Step 3b: Conversion successful: {requesting_teacher_internal_id}")

        # Direct comparison of internal UUIDs
        if teacher_id_in_group != requesting_teacher_internal_id:
            logger.warning(f"User {requesting_user_kinde_id} (Teacher ID: {requesting_teacher_internal_id}) attempted to {action} ClassGroup {class_group.id} owned by Teacher ID {teacher_id_in_group}.")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Not authorized to {action} this class group."
            )
        # If IDs match, authorization passes
        logger.debug(f"Authorization successful for user {requesting_user_kinde_id} to {action} ClassGroup {class_group.id}")

    except (ValueError, TypeError) as e:
        # Handle cases where IDs cannot be converted to UUID
        logger.error(f"UUID conversion error during authorization check for class group teacher '{class_group.teacher_id}' or requesting teacher '{requesting_teacher.id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, # Keep 400 for format errors
            detail="Invalid user or teacher ID format in token or database." # This matches frontend log
        )
# --- END RESTORED ASYNC HELPER ---


# === ClassGroup API Endpoints ===

# --- GET /classgroups/all-admin (ADMIN ONLY) ---
@router.get(
    "/all-admin",
    response_model=List[ClassGroup],
    status_code=status.HTTP_200_OK,
    summary="Get all class groups (Admin Only)",
    description="Retrieves a list of all class groups in the system. Requires administrator privileges."
)
async def read_all_class_groups_admin(
    skip: int = Query(0, ge=0, description="Records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Max records to return"), # Increased limit for admin
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    logger.info("<<<<< read_all_class_groups_admin: ENTRY POINT >>>>>") # MODIFIED Log statement
    try:
        logger.info(f"read_all_class_groups_admin: User payload sub: {current_user_payload.get('sub')}, Skip: {skip}, Limit: {limit}") # MODIFIED Log statement
        user_kinde_id = current_user_payload.get("sub")
        logger.info(f"[ADMIN CLASS GROUPS] User Kinde ID: {user_kinde_id}, attempting to read all class groups (skip={skip}, limit={limit}).")

        # --- Check for Administrator Privileges ---
        teacher_db = await crud.get_teacher_by_kinde_id(kinde_id=user_kinde_id)
        if not teacher_db:
            logger.error(f"[ADMIN CLASS GROUPS] Teacher profile not found in DB for Kinde ID: {user_kinde_id}. Denying access.")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Teacher profile not found. Access denied."
            )
        
        if not teacher_db.is_administrator:
            logger.warning(f"[ADMIN CLASS GROUPS] User {user_kinde_id} (DB ID: {teacher_db.id}) attempted to access admin endpoint /class-groups/all-admin without sufficient privileges (is_administrator: {teacher_db.is_administrator}).")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource."
            )
        logger.info(f"[ADMIN CLASS GROUPS] Admin user {user_kinde_id} (DB ID: {teacher_db.id}) granted access to /all-admin.")
        # --- End Check ---

        class_groups = await crud.get_all_class_groups_admin(skip=skip, limit=limit, include_deleted=False)
        
        logger.info(f"[ADMIN CLASS GROUPS] Successfully retrieved {len(class_groups)} class groups for admin user {user_kinde_id}.")
        return class_groups
    except HTTPException as http_exc:
        logger.error(f"[ADMIN CLASS GROUPS] HTTPException in /all-admin: {http_exc.status_code} - {http_exc.detail}", exc_info=True)
        raise # Re-raise HTTPException to let FastAPI handle it
    except ValidationError as val_exc:
        logger.error(f"[ADMIN CLASS GROUPS] Pydantic ValidationError in /all-admin: {str(val_exc)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Data validation error: {str(val_exc)}"
        ) # Raise as 422 to be more specific
    except Exception as e:
        logger.error(f"[ADMIN CLASS GROUPS] Unexpected error in /all-admin for user {user_kinde_id if 'user_kinde_id' in locals() else 'Unknown User'}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected server error occurred: {str(e)}"
        )

@router.post(
    "/",
    response_model=ClassGroup,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new class group (Protected)",
    description="Creates a new class group record. Requires authentication. The teacher ID is taken from the authenticated user's internal ID."
)
async def create_new_class_group(
    class_group_payload: ClassGroupClientCreate, # Changed from ClassGroupCreate
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
    # current_teacher: models.Teacher = Depends(deps.get_current_active_teacher) # Example if you had such a dep
):
    """Creates a new class group, assigning the authenticated user as the teacher."""
    logger.info(f"Attempting to create new class group. User payload: {current_user_payload.get('sub')}, Client Data: {class_group_payload.model_dump()}")

    user_kinde_id_str = current_user_payload.get("sub")
    if not user_kinde_id_str:
        logger.error("Kinde ID ('sub') missing from token payload.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token.")

    teacher_internal_id: Optional[uuid.UUID] = None
    try:
        teacher_record = await crud.get_teacher_by_kinde_id(kinde_id=user_kinde_id_str)
        if teacher_record and teacher_record.id:
            teacher_internal_id = teacher_record.id
        else:
            logger.error(f"Could not find teacher record or teacher ID for authenticated user Kinde ID: {user_kinde_id_str}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Authenticated user's teacher profile not found or incomplete in database."
            )
    except Exception as e:
         logger.error(f"Error looking up teacher by Kinde ID '{user_kinde_id_str}': {e}", exc_info=True)
         raise HTTPException(
             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
             detail="Error retrieving teacher information."
         )

    # Prepare the data for creating the class group, using the internal teacher_id
    # Construct ClassGroupCreate from ClassGroupClientCreate and teacher_id
    class_group_to_create = ClassGroupCreate(
        class_name=class_group_payload.class_name,
        academic_year=class_group_payload.academic_year,
        teacher_id=teacher_internal_id
        # student_ids and is_deleted will take defaults from ClassGroupBase via ClassGroupCreate
    )
    
    # Check for existing class with same name, year, for this teacher
    existing_class = await crud.get_class_group_by_name_year_and_teacher(
        class_name=class_group_to_create.class_name,
        academic_year=class_group_to_create.academic_year,
        teacher_id=teacher_internal_id # Ensure this is the UUID
    )
    if existing_class:
        logger.warning(f"Class group '{class_group_to_create.class_name}' with year '{class_group_to_create.academic_year}' already exists for teacher ID {teacher_internal_id}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A class with the name '{class_group_to_create.class_name}' and academic year '{class_group_to_create.academic_year or "Not specified"}' already exists for you."
        )

    try:
        logger.info(f"User {user_kinde_id_str} (Teacher ID: {teacher_internal_id}) attempting to create class group with data: {class_group_to_create.model_dump()}")

        # Pass the fully prepared ClassGroupCreate model to the CRUD function
        # The crud.create_class_group should NOT take an additional teacher_id parameter if it's already in class_group_to_create
        created_cg = await crud.create_class_group(
            class_group_in=class_group_to_create
        )

        if not created_cg:
            logger.error(f"CRUD create_class_group returned None for teacher {teacher_internal_id} with data {class_group_to_create.model_dump()}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not create the class group record."
            )
        logger.info(f"ClassGroup '{created_cg.class_name}' (ID: {created_cg.id}) created successfully by Teacher ID: {teacher_internal_id}).")
        return created_cg
    except ValidationError as e:
        # This catch block might be redundant if Pydantic validation happens at the input model level (ClassGroupCreateRequest)
        # However, it can catch issues if ClassGroupCreate itself has further validation that fails.
        logger.error(f"Pydantic ValidationError during ClassGroupCreate construction or CRUD operation for teacher {teacher_internal_id}. Errors: {e.errors()}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.errors() # Pydantic errors are already in a good format
        )
    except HTTPException as http_exc:
        # Re-raise HTTPExceptions directly
        raise http_exc
    except Exception as e:
        logger.error(f"Unexpected error creating class group for teacher {teacher_internal_id} with data {class_group_to_create.model_dump()}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )

# --- GET /classgroups/{class_group_id} ---
@router.get(
    "/{class_group_id}",
    response_model=ClassGroup,
    status_code=status.HTTP_200_OK,
    summary="Get a specific class group by ID (Protected)",
    description="Retrieves details of a single class group. Requires authentication."
)
async def read_class_group(
    class_group_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to read class group ID: {class_group_id}")
    class_group = await crud.get_class_group_by_id(class_group_id=class_group_id)
    if class_group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Class group with ID {class_group_id} not found."
        )
    # Apply auth check after fetching - uses the restored async helper
    await _check_user_is_teacher_of_group(class_group, current_user_payload, action="read")
    return class_group

# --- GET /classgroups/ ---
@router.get(
    "",
    response_model=List[ClassGroup],
    status_code=status.HTTP_200_OK,
    summary="Get a list of class groups (Protected)",
    description="Retrieves a list of class groups for the authenticated teacher. Supports pagination."
)
async def read_class_groups(
    skip: int = Query(0, ge=0, description="Records to skip"),
    limit: int = Query(100, ge=1, le=500, description="Max records to return"),
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    logger.info(f"User payload sub: {current_user_payload.get('sub')}, attempting to read class groups (skip={skip}, limit={limit}).")
    user_kinde_id_str = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id_str} attempting to read list of their class groups (skip={skip}, limit={limit}).")

    # --- Get Teacher's Internal UUID ---
    teacher_internal_id: Optional[uuid.UUID] = None
    try:
       # Fetch teacher record to get internal ID
       teacher_record = await crud.get_teacher_by_kinde_id(kinde_id=user_kinde_id_str)
       if teacher_record:
           teacher_internal_id = teacher_record.id
       else:
           logger.warning(f"No teacher profile found for user {user_kinde_id_str} when listing classes.")
           # Return empty list if teacher profile doesn't exist, as they can't own classes
           return []
    except Exception as e:
        logger.error(f"Error looking up teacher by Kinde ID '{user_kinde_id_str}' for listing classes: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving teacher information."
        )

    if not teacher_internal_id:
         # This case should ideally be handled by the check above, but as a fallback:
         logger.warning(f"Could not determine internal teacher ID for user {user_kinde_id_str}. Returning empty class list.")
         return []
    # --- End Get Teacher ID ---

    # Fetch only classes belonging to this teacher
    class_groups = await crud.get_all_class_groups(
        teacher_id=teacher_internal_id, # Filter by teacher's internal ID
        skip=skip,
        limit=limit
    )
    return class_groups

# --- PUT /classgroups/{class_group_id} ---
@router.put(
    "/{class_group_id}",
    response_model=ClassGroup,
    status_code=status.HTTP_200_OK,
    summary="Update an existing class group (Protected)",
    description="Updates details of an existing class group. Requires authentication. Only the assigned teacher can update."
)
async def update_existing_class_group(
    class_group_id: uuid.UUID,
    class_group_in: ClassGroupUpdate,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to update class group ID: {class_group_id}")
    
    class_group = await crud.get_class_group_by_id(class_group_id=class_group_id)
    if class_group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Class group with ID {class_group_id} not found."
        )
    
    # Authorization: Ensure the current user is the teacher of this class group.
    # This helper now compares internal UUIDs after fetching the teacher record for the current user.
    await _check_user_is_teacher_of_group(class_group, current_user_payload, action="update")

    # Fetch the teacher's internal UUID to pass to the CRUD function
    teacher_record = await crud.get_teacher_by_kinde_id(kinde_id=user_kinde_id)
    if not teacher_record or not teacher_record.id:
        logger.error(f"Could not find teacher record or teacher ID for Kinde ID: {user_kinde_id} during class group update.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authenticated user's teacher profile not found or incomplete."
        )
    teacher_internal_uuid = teacher_record.id

    logger.debug(f"Attempting to update ClassGroup {class_group_id} by Teacher (internal UUID) {teacher_internal_uuid} with data: {class_group_in.model_dump(exclude_unset=True)}")
    updated_cg = await crud.update_class_group(
        class_group_id=class_group_id, 
        teacher_id=teacher_internal_uuid, # Pass internal UUID
        class_group_in=class_group_in
    )
    if updated_cg is None:
        # This could be because the class wasn't found again, or the update failed for other reasons (e.g. DB error)
        # The CRUD function logs more details. Here, we return a generic server error or a more specific one if identifiable.
        logger.error(f"Update failed for class group ID {class_group_id} by teacher {teacher_internal_uuid}. CRUD function returned None.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, # Or 404 if it was a not found issue during update
            detail="Failed to update class group."
        )
    logger.info(f"ClassGroup {updated_cg.id} updated successfully by teacher {user_kinde_id}.")
    return updated_cg

# --- DELETE /classgroups/{class_group_id} ---
@router.delete(
    "/{class_group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a class group (Protected)",
    description="Deletes a class group record. Requires authentication. Only the assigned teacher can delete."
)
async def delete_existing_class_group(
    class_group_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to delete class group ID: {class_group_id}")

    class_group = await crud.get_class_group_by_id(class_group_id=class_group_id)
    if class_group is None:
        # If the class group doesn't exist, returning 204 is idempotent for DELETE.
        # However, for RBAC, we might want to ensure it existed and was owned first.
        # For now, let's be strict: if it's not found, we can't verify ownership.
        logger.warning(f"Class group {class_group_id} not found for deletion attempt by user {user_kinde_id}.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Class group with ID {class_group_id} not found."
        )

    # Authorization: Ensure the current user is the teacher of this class group.
    await _check_user_is_teacher_of_group(class_group, current_user_payload, action="delete")

    # Fetch the teacher's internal UUID to pass to the CRUD function
    teacher_record = await crud.get_teacher_by_kinde_id(kinde_id=user_kinde_id)
    if not teacher_record or not teacher_record.id:
        logger.error(f"Could not find teacher record or teacher ID for Kinde ID: {user_kinde_id} during class group deletion.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authenticated user's teacher profile not found or incomplete."
        )
    teacher_internal_uuid = teacher_record.id

    logger.debug(f"Attempting to delete ClassGroup {class_group_id} by Teacher (internal UUID) {teacher_internal_uuid}")
    success = await crud.delete_class_group(class_group_id=class_group_id, teacher_id=teacher_internal_uuid)
    if not success:
        # This could mean the class group was not found by the delete query (e.g., already deleted, or ownership mismatch despite _check_user_is_teacher_of_group)
        # or a database error occurred.
        logger.error(f"Deletion failed for class group ID {class_group_id} by teacher {teacher_internal_uuid}. CRUD function returned False.")
        # Raising 404 if not found, or 500 for other errors. 
        # The CRUD function logs more details, but here we might infer based on `class_group` being found earlier.
        # If `class_group` was found by `get_class_group_by_id`, then a `False` return likely means it was not found by `delete_class_group`'s query *with the teacher_id*.
        # This implies an ownership issue or it was deleted between checks. A 404 or 403 could be suitable.
        # For simplicity, if it was found initially, a failure to delete points to an issue during the delete operation.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, # Or 500. 404 if not found by delete_class_group due to stricter query.
            detail="Failed to delete class group. It might have been already deleted or an error occurred."
        )
    # If successful, FastAPI handles the 204 No Content response automatically.
    logger.info(f"ClassGroup {class_group_id} deleted successfully by teacher {user_kinde_id}.")
    return # FastAPI will return 204 No Content

# --- START: Endpoints for ClassGroup <-> Student Relationship ---

@router.post(
    "/{class_group_id}/students/{student_id}",
    status_code=status.HTTP_200_OK,
    summary="Add a student to a class group (Protected)",
    description="Associates an existing student with an existing class group. Requires authentication. User must be the teacher of the class group.",
    responses={
        200: {"description": "Student added successfully (or already existed)."},
        403: {"description": "Not authorized to modify this class group."},
        404: {"description": "Class group or student not found."},
        500: {"description": "Internal server error adding student."}
    }
)
async def add_student_to_group(
    class_group_id: uuid.UUID,
    student_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """Adds a student to a specific class group."""
    user_kinde_id_str = current_user_payload.get("sub")
    logger.info(f"[add_student_to_group] User {user_kinde_id_str} attempting to add student {student_id} to class group {class_group_id}")

    # --- Get Class Group (Step 1: Fetch the class group) ---
    class_group = await crud.get_class_group_by_id(
        class_group_id=class_group_id
        # REMOVED: teacher_kinde_id=user_kinde_id_str 
    )
    if not class_group:
        logger.error(f"[add_student_to_group] CLASS GROUP NOT FOUND. User: {user_kinde_id_str}, Class Group ID: {class_group_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ADD_STUDENT_ERR:CG_NOT_FOUND" # Modified detail code
        )
    
    # --- Authorization Check (Step 2: Verify teacher owns the class group) ---
    try:
        await _check_user_is_teacher_of_group(class_group, current_user_payload, action="add student to")
    except HTTPException as auth_exc:
        logger.error(f"[add_student_to_group] AUTHORIZATION FAILED. User: {user_kinde_id_str} for Class Group ID: {class_group_id}. Detail: {auth_exc.detail}")
        # Re-raise the auth exception (it already has status code and detail)
        raise auth_exc 
    
    logger.info(f"[add_student_to_group] Class group {class_group.id} (name: {class_group.class_name}) confirmed and authorized for user {user_kinde_id_str}.")
    # --- End Authorization Check ---

    # --- Validate Student Exists (and belongs to the same teacher) ---
    logger.info(f"[add_student_to_group] Attempting to get student. Student ID from URL: {student_id} (type: {type(student_id)}), Teacher Kinde ID from token: '{user_kinde_id_str}' (type: {type(user_kinde_id_str)})") # Keep this log
    student = await crud.get_student_by_id(
        student_internal_id=student_id,
        teacher_id=user_kinde_id_str # Use Kinde ID for student check
    )
    if student is None:
        # Student doesn't exist OR doesn't belong to this teacher
        logger.error(f"[add_student_to_group] STUDENT NOT FOUND or not authorized. User: {user_kinde_id_str}, Student ID: {student_id}. crud.get_student_by_id returned None.") # Error log
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ADD_STUDENT_ERR:S_NOT_FOUND_OR_UNAUTHORIZED" # Unique detail 2
        )
    logger.info(f"[add_student_to_group] Student {student.id} (name: {student.first_name} {student.last_name}) confirmed for user {user_kinde_id_str}.")
    # --- End Student Validation ---

    # Attempt to add the student ID to the class group's student_ids list
    success = await crud.add_student_to_class_group(
        class_group_id=class_group_id,
        student_id=student_id
    )

    if not success:
        # Log the failure at an error level
        logger.error(f"[add_student_to_group] CRUD FAILED to add student {student_id} to class group {class_group_id} for user {user_kinde_id_str}.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, # Potentially a 404 if student was already in group and not handled, or other specific error
            detail="ADD_STUDENT_ERR:CRUD_FAILED" # Unique detail 3
        )

    return {"message": f"Student {student_id} added to class group {class_group_id}."}


@router.delete(
    "/{class_group_id}/students/{student_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a student from a class group (Protected)",
    description="Disassociates a student from a class group. Requires authentication. User must be the teacher of the class group.",
     responses={
        204: {"description": "Student removed successfully."},
        403: {"description": "Not authorized to modify this class group."},
        404: {"description": "Class group not found, or student not found in the class group."},
        500: {"description": "Internal server error removing student."}
    }
)
async def remove_student_from_group(
    class_group_id: uuid.UUID,
    student_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """Removes a student from a specific class group."""
    user_kinde_id_str = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id_str} attempting to remove student {student_id} from class group {class_group_id}")

    # --- Authorization Check (Uses Restored Helper) ---
    existing_class_group = await crud.get_class_group_by_id(class_group_id=class_group_id)
    if existing_class_group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Class group with ID {class_group_id} not found."
        )
    # Use the restored async auth check
    await _check_user_is_teacher_of_group(existing_class_group, current_user_payload, action="remove student from")
    # --- End Authorization Check ---

    # Call the CRUD function to remove the student ID
    success = await crud.remove_student_from_class_group(class_group_id=class_group_id, student_id=student_id)

    if not success:
         raise HTTPException(
             status_code=status.HTTP_404_NOT_FOUND, # Treat as 404 if student wasn't in group or group didn't exist
             detail=f"Failed to remove student {student_id}. Class group {class_group_id} not found, or student not in group."
         )

    # Return No Content on success
    return None

# --- END: NEW ENDPOINTS for ClassGroup <-> Student Relationship --- 