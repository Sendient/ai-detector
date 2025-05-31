# app/api/v1/endpoints/students.py

import uuid
import logging # Import logging
from typing import List, Optional, Dict, Any # Add Dict, Any
from fastapi import APIRouter, HTTPException, status, Query, Depends # Add Depends

# Use absolute imports from the 'app' package root
from ....models.student import Student, StudentCreate, StudentUpdate
from ....models.bulk import StudentBulkCreateRequest, StudentBulkCreateResponse, StudentBulkResponseItem # Added bulk models
from ....models.class_group import ClassGroupCreate # Import ClassGroupCreate
from ....db import crud
from ....core.security import get_current_user_payload

# Setup logger for this module
logger = logging.getLogger(__name__)

# Create the router instance
router = APIRouter(
    prefix="/students",
    tags=["Students"],
    redirect_slashes=False  # Explicitly disable automatic trailing slash redirects
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
    "",
    response_model=List[Student],
    status_code=status.HTTP_200_OK,
    summary="Get a list of students (Protected)",
    description="Retrieves a list of students with optional filtering and pagination. Requires authentication."
)
async def read_students(
    external_student_id: Optional[str] = Query(None, description="Filter by external student ID"),
    first_name: Optional[str] = Query(None, description="Filter by first name (case-insensitive)"),
    last_name: Optional[str] = Query(None, description="Filter by last name (case-insensitive)"),
    year_group: Optional[str] = Query(None, description="Filter by year group"),
    class_id: Optional[uuid.UUID] = Query(None, description="Filter by class group ID"),
    skip: int = Query(0, ge=0, description="Records to skip"),
    limit: int = Query(100, ge=1, le=500, description="Max records to return"),
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to retrieve a list of students. Supports filtering and pagination.
    Can filter by class_id to get students belonging to a specific class.
    """
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to read list of students with filters (class_id: {class_id}).")

    # TODO: Further authorization logic for listing students might be needed.

    students = await crud.get_all_students(
        teacher_id=user_kinde_id,
        external_student_id=external_student_id,
        first_name=first_name,
        last_name=last_name,
        year_group=year_group,
        class_id=class_id,
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

# === NEW BULK UPLOAD ENDPOINT ===
@router.post(
    "/bulk-upload",
    response_model=StudentBulkCreateResponse,
    status_code=status.HTTP_200_OK, # Or 207 Multi-Status if returning partial successes/failures
    summary="Bulk upload students from CSV data (Protected)",
    description="Processes a list of student records for bulk creation and class assignment. Requires authentication."
)
async def bulk_upload_students(
    bulk_request: StudentBulkCreateRequest,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    if not user_kinde_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

    # Get the teacher's internal ID (UUID)
    teacher = await crud.get_teacher_by_kinde_id(kinde_id=user_kinde_id)
    if not teacher or not teacher.id:
        logger.error(f"Could not find teacher or teacher.id for kinde_id: {user_kinde_id} during bulk upload.")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Teacher profile not found or incomplete.")
    teacher_internal_id = teacher.id # This is the UUID

    logger.info(f"User {user_kinde_id} (Internal ID: {teacher_internal_id}) initiating bulk student upload with {len(bulk_request.students)} records.")

    response_items: List[StudentBulkResponseItem] = []
    processed_count = 0
    succeeded_count = 0
    failed_count = 0

    for i, student_item in enumerate(bulk_request.students):
        processed_count += 1
        row_num = i + 1 # 1-indexed for user feedback
        class_group_to_assign = None
        class_group_id_assigned = None
        class_name_processed_for_msg = None
        response_status = "FAILED"
        response_message = ""
        created_student_id = None
        student_full_name = f"{student_item.FirstName or 'N/A'} {student_item.LastName or 'N/A'}".strip()

        try:
            # 1. Validate input student data
            if not student_item.FirstName or not student_item.LastName:
                raise ValueError("FirstName and LastName are required.")

            # 2. Handle Class Assignment if AssignToClass is provided
            if student_item.AssignToClass:
                class_name_to_find_or_create = student_item.AssignToClass.strip()
                class_name_processed_for_msg = class_name_to_find_or_create
                if not class_name_to_find_or_create:
                    # If AssignToClass was provided but is empty after stripping, treat as no class assignment intended
                    logger.info(f"Row {row_num}: AssignToClass was whitespace, treating as no class assignment.")
                    class_name_processed_for_msg = None # Reset for message clarity
                else:
                    logger.info(f"Row {row_num}: Processing class '{class_name_to_find_or_create}' for teacher {user_kinde_id}.")
                    # Look for existing class with name and no academic year
                    class_group_to_assign = await crud.get_class_group_by_name_year_and_teacher(
                        class_name=class_name_to_find_or_create,
                        teacher_id=teacher_internal_id,
                        academic_year=None # Explicitly look for academic_year = None
                    )
                    if not class_group_to_assign:
                        logger.info(f"Row {row_num}: Class '{class_name_to_find_or_create}' not found for teacher {user_kinde_id} (Kinde ID) with no academic year. Creating new class.")
                        class_create_payload = ClassGroupCreate(
                            class_name=class_name_to_find_or_create,
                            teacher_id=teacher_internal_id, # Use teacher's internal UUID here
                            academic_year=None # Explicitly set academic_year to None
                        )
                        class_group_to_assign = await crud.create_class_group(
                            class_group_in=class_create_payload
                            # Removed redundant teacher_id=user_kinde_id from here
                        )
                        if not class_group_to_assign:
                            raise Exception(f"Failed to create new class '{class_name_to_find_or_create}'.")
                        response_status = "CREATED_WITH_NEW_CLASS"
                        logger.info(f"Row {row_num}: New class '{class_group_to_assign.class_name}' (ID: {class_group_to_assign.id}) created.")
                    else:
                        response_status = "CREATED_WITH_EXISTING_CLASS"
                        logger.info(f"Row {row_num}: Found existing class '{class_group_to_assign.class_name}' (ID: {class_group_to_assign.id}).")
                    class_group_id_assigned = class_group_to_assign.id
            else:
                response_status = "CREATED_NO_CLASS" # Student created, no class assignment attempted

            # 3. Create Student
            student_create_payload = StudentCreate(
                first_name=student_item.FirstName,
                last_name=student_item.LastName,
                email=student_item.EmailAddress if student_item.EmailAddress else None,
                external_student_id=student_item.ExternalID if student_item.ExternalID else None,
                descriptor=student_item.Descriptor if student_item.Descriptor else None,
                teacher_id=user_kinde_id # crud.create_student still expects Kinde ID based on its current implementation
            )
            created_student = await crud.create_student(student_in=student_create_payload, teacher_id=user_kinde_id)
            if not created_student:
                raise Exception("Failed to create student record in database.")
            created_student_id = created_student.id
            logger.info(f"Row {row_num}: Student '{student_full_name}' (ID: {created_student_id}) created.")

            # 4. Add Student to Class Group if applicable
            if class_group_to_assign and created_student_id:
                added_to_class = await crud.add_student_to_class_group(
                    class_group_id=class_group_to_assign.id, 
                    student_id=created_student_id
                )
                if not added_to_class:
                    # This is a soft failure for the overall row; student is created but not assigned.
                    # The status would already be CREATED_WITH_NEW_CLASS or CREATED_WITH_EXISTING_CLASS
                    response_message = f"Student created (ID: {created_student_id}), but failed to add to class '{class_group_to_assign.class_name}'."
                    logger.warning(f"Row {row_num}: {response_message}")
                    # Decide if this makes the row a partial success or if status should change.
                    # For now, keeping the class-related status and adding to message.
                else:
                    logger.info(f"Row {row_num}: Student {created_student_id} added to class {class_group_to_assign.id}.")
            
            # Final success status determination if not already set by class creation path
            if response_status == "FAILED": # Should have been updated by now if successful
                response_status = "CREATED_NO_CLASS" if not class_group_to_assign else response_status
            
            response_message = response_message or f"Student '{student_full_name}' processed successfully."
            if class_name_processed_for_msg:
                response_message += f" Class: '{class_name_processed_for_msg}'."
            succeeded_count += 1

        except ValueError as ve:
            logger.warning(f"Row {row_num}: Validation error for student '{student_full_name}' - {str(ve)}")
            response_message = f"Validation Error: {str(ve)}"
            failed_count += 1
        except Exception as e:
            logger.error(f"Row {row_num}: Error processing student '{student_full_name}': {str(e)}", exc_info=True)
            response_message = f"Processing Error: {str(e)}"
            failed_count += 1
            # Ensure status reflects failure if an exception occurred after potential class status set
            response_status = "FAILED"

        response_items.append(
            StudentBulkResponseItem(
                row_number=row_num,
                status=response_status,
                student_id=created_student_id,
                student_name=student_full_name,
                class_group_id=class_group_id_assigned,
                class_name_processed=class_name_processed_for_msg,
                message=response_message
            )
        )
    
    return StudentBulkCreateResponse(
        results=response_items,
        summary={
            "total_processed": processed_count,
            "total_succeeded": succeeded_count, 
            "total_failed": failed_count
        }
    )

