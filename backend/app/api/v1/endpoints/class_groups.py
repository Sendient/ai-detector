# app/api/v1/endpoints/class_groups.py

import uuid # Corrected Indentation
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, status, Query, Depends # Removed , Request
from pydantic import ValidationError # Added ValidationError

# Import Pydantic models for ClassGroup
from ....models.class_group import ClassGroup, ClassGroupCreate, ClassGroupUpdate
# Import CRUD functions for ClassGroup
from ....db import crud
# Import the authentication dependency
from ....core.security import get_current_user_payload

# Setup logger for this module
logger = logging.getLogger(__name__)

# Create the router instance
router = APIRouter(
    prefix="/classgroups",
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

@router.post(
    "/",
    response_model=ClassGroup,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new class group (Protected)",
    description="Creates a new class group record. Requires authentication. The teacher ID is taken from the authenticated user."
)
async def create_new_class_group(
    class_group_in: ClassGroupCreate, # Removed request: Request
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """Creates a new class group, assigning the authenticated user as the teacher."""
    # Removed the "EXTREME DEBUGGING" block
    logger.info(f"Attempting to create new class group. User payload: {current_user_payload.get('sub')}") # This is the first log line

    user_kinde_id_str = current_user_payload.get("sub")

    # --- Get Teacher's Internal UUID ---
    teacher_internal_id: Optional[uuid.UUID] = None
    try:
        teacher_record = await crud.get_teacher_by_kinde_id(kinde_id=user_kinde_id_str)
        if teacher_record:
            teacher_internal_id = teacher_record.id
        else:
            logger.error(f"Could not find teacher record for authenticated user Kinde ID: {user_kinde_id_str}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Authenticated user's teacher profile not found in database."
            )
    except Exception as e:
         logger.error(f"Error looking up teacher by Kinde ID '{user_kinde_id_str}': {e}", exc_info=True)
         raise HTTPException(
             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
             detail="Error retrieving teacher information."
         )

    if not teacher_internal_id:
         raise HTTPException(status_code=500, detail="Could not determine teacher ID.")
    # --- End Get Teacher ID ---

    # TODO: Add further checks? Does the specified school_id exist?

    try:
        logger.info(f"User {user_kinde_id_str} attempting to create class group with data from Pydantic model: {class_group_in.model_dump()}")

        created_cg = await crud.create_class_group(
            class_group_in=class_group_in,
            teacher_id=teacher_internal_id # Pass the internal ID
        )

        if not created_cg:
            logger.error(f"CRUD create_class_group returned None for user {user_kinde_id_str} with data {class_group_in.model_dump()}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not create the class group record (CRUD function returned None)."
            )
        logger.info(f"ClassGroup '{created_cg.class_name}' (ID: {created_cg.id}) created successfully by user {user_kinde_id_str} (Teacher ID: {teacher_internal_id}).")
        return created_cg
    except ValidationError as e:
        logger.error(f"Pydantic ValidationError manually caught in create_new_class_group for user {user_kinde_id_str}. Errors: {e.errors()}", exc_info=True)
        error_details = []
        for error in e.errors():
            field = " -> ".join(str(loc) for loc in error.get("loc", []))
            message = error.get("msg", "Unknown validation error")
            error_type = error.get("type", "Unknown type")
            error_details.append({"field": field, "message": message, "type": error_type})
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Validation Error caught in endpoint", "errors": error_details}
        )
    except HTTPException as http_exc:
        logger.warning(f"HTTPException caught in create_new_class_group for user {user_kinde_id_str}: {http_exc.detail}", exc_info=True)
        raise http_exc
    except Exception as e:
        # Log the incoming data if possible, but be cautious with sensitive info
        logged_data = "Error accessing class_group_in for logging"
        try:
            logged_data = class_group_in.model_dump(exclude_none=True)
        except Exception:
            pass # Keep default error string
        logger.error(f"Unexpected error creating class group for user {user_kinde_id_str} with data {logged_data}: {e}", exc_info=True)
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
    "/",
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
    user_kinde_id_str = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id_str} attempting to update class group ID: {class_group_id}")

    existing_class_group = await crud.get_class_group_by_id(class_group_id=class_group_id)
    if existing_class_group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Class group with ID {class_group_id} not found."
        )
    # Use the restored async auth check
    await _check_user_is_teacher_of_group(existing_class_group, current_user_payload, action="update")

    updated_cg = await crud.update_class_group(class_group_id=class_group_id, class_group_in=class_group_in)
    if updated_cg is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update class group with ID {class_group_id}."
        )
    logger.info(f"ClassGroup ID {class_group_id} updated successfully by user {user_kinde_id_str}.")
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
    user_kinde_id_str = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id_str} attempting to delete class group ID: {class_group_id}")

    existing_class_group = await crud.get_class_group_by_id(class_group_id=class_group_id)
    if existing_class_group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Class group with ID {class_group_id} not found."
        )
    # Use the restored async auth check
    await _check_user_is_teacher_of_group(existing_class_group, current_user_payload, action="delete")

    deleted_successfully = await crud.delete_class_group(class_group_id=class_group_id)
    if not deleted_successfully:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete class group with ID {class_group_id}."
        )
    logger.info(f"ClassGroup ID {class_group_id} deleted successfully by user {user_kinde_id_str}.")
    return None

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
    logger.info(f"User {user_kinde_id_str} attempting to add student {student_id} to class group {class_group_id}")

    # --- Authorization Check (Uses Restored Helper) ---
    existing_class_group = await crud.get_class_group_by_id(class_group_id=class_group_id)
    if existing_class_group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Class group with ID {class_group_id} not found."
        )
    # Use the restored async auth check
    await _check_user_is_teacher_of_group(existing_class_group, current_user_payload, action="add student to")
    # --- End Authorization Check ---

    # --- Validate Student Exists (and belongs to the same teacher) ---
    # Use the teacher_id from the class group, which we know matches the authenticated user
    student = await crud.get_student_by_id(
        student_internal_id=student_id,
        teacher_id=user_kinde_id_str # <<< Use Kinde ID for student check
    )
    if student is None:
        # Student doesn't exist OR doesn't belong to this teacher
        logger.warning(f"Attempt to add non-existent or unauthorized student {student_id} to class group {class_group_id} by user {user_kinde_id_str}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with ID {student_id} not found or you do not have access."
        )
    # --- End Student Validation ---

    # Attempt to add the student ID to the class group's student_ids list
    success = await crud.add_student_to_class_group(class_group_id=class_group_id, student_id=student_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add student {student_id} to class group {class_group_id}."
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
 