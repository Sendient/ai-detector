# app/api/v1/endpoints/students.py

import uuid
import logging # Import logging
from typing import List, Optional, Dict, Any # Add Dict, Any
from fastapi import APIRouter, HTTPException, status, Query, Depends # Add Depends

# Use absolute imports from the 'app' package root
from ....models.student import Student, StudentCreate, StudentUpdate
from ....models.bulk import StudentBulkCreateRequest, StudentBulkCreateResponse, StudentBulkResponseItem # Added bulk models
from ....models.class_group import ClassGroupCreate # Import ClassGroupCreate
from ....models.enums import UserRoleEnum # ADDED UserRoleEnum
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
    "",
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
    user_roles = current_user_payload.get("roles", [])
    
    # Determine if the user is an admin
    # Kinde roles might be a list of strings or a list of dicts like [{'key': 'Admin'}]
    is_admin = any(
        role == UserRoleEnum.ADMIN.value or (isinstance(role, dict) and role.get("key") == UserRoleEnum.ADMIN.value)
        for role in user_roles
    )

    logger.info(f"User {user_kinde_id} (Admin: {is_admin}) attempting to read student internal ID: {student_internal_id}")

    student_to_fetch_teacher_id = None
    if not is_admin:
        student_to_fetch_teacher_id = user_kinde_id

    student = await crud.get_student_by_id(
        student_internal_id=student_internal_id,
        teacher_id=student_to_fetch_teacher_id # Pass Kinde ID for teachers, None for admins
    )
    
    if student is None:
        # If admin and not found, it's a genuine 404.
        # If teacher and not found, it could be not found OR not theirs.
        # The CRUD log for get_student_by_id will indicate if teacher_id was used in query.
        detail_msg = f"Student with internal ID {student_internal_id} not found"
        if not is_admin:
            detail_msg += " or access denied."
        else:
            detail_msg += "."

        logger.warning(f"Failed to find student {student_internal_id}. Admin: {is_admin}, Queried with teacher_id: {student_to_fetch_teacher_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail_msg
        )

    # Authorization check is now implicitly handled by how crud.get_student_by_id was called
    logger.info(f"Successfully retrieved student {student.id} for user {user_kinde_id} (Admin: {is_admin})")
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
    user_roles = current_user_payload.get("roles", [])
    is_admin = any(
        role == UserRoleEnum.ADMIN.value or (isinstance(role, dict) and role.get("key") == UserRoleEnum.ADMIN.value)
        for role in user_roles
    )

    logger.info(f"User {user_kinde_id} (Admin: {is_admin}) attempting to read list of students with filters (class_id: {class_id}).")

    query_teacher_id = None
    if not is_admin:
        query_teacher_id = user_kinde_id

    # All filters are passed to crud.get_all_students.
    # If query_teacher_id is None (for admin), crud function will not filter by teacher.
    # If query_teacher_id is set (for teacher), crud function will filter by that teacher.
    students = await crud.get_all_students(
        teacher_id=query_teacher_id,
        external_student_id=external_student_id,
        first_name=first_name,
        last_name=last_name,
        year_group=year_group,
        class_id=class_id,
        skip=skip,
        limit=limit
        # include_deleted can be added as a parameter if needed for admins
    )
    logger.info(f"Retrieved {len(students)} students for user {user_kinde_id} (Admin: {is_admin}).")
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
    Admins can update any student. Teachers can only update their own.
    """
    user_kinde_id = current_user_payload.get("sub")
    user_roles = current_user_payload.get("roles", [])
    is_admin = any(
        role == UserRoleEnum.ADMIN.value or (isinstance(role, dict) and role.get("key") == UserRoleEnum.ADMIN.value)
        for role in user_roles
    )

    logger.info(f"User {user_kinde_id} (Admin: {is_admin}) attempting to update student internal ID: {student_internal_id}")

    # Determine the teacher_id to use for querying/updating
    # For admins, this will be None, allowing access to any student.
    # For teachers, this will be their own Kinde ID, restricting access.
    owner_teacher_id_for_query = None
    if not is_admin:
        owner_teacher_id_for_query = user_kinde_id

    # --- Verification Step: Check if the student exists (and if teacher, if they own it) ---
    student_to_verify = await crud.get_student_by_id(
        student_internal_id=student_internal_id,
        teacher_id=owner_teacher_id_for_query # Pass Kinde ID for teachers, None for admins
    )

    if not student_to_verify:
        detail_msg = f"Student with internal ID {student_internal_id} not found"
        if not is_admin:
            detail_msg += " or you do not have permission to access this student."
        else: # Admin context
            detail_msg += "."
        logger.warning(f"Update failed: Student {student_internal_id} not found or not accessible by user {user_kinde_id} (Admin: {is_admin}). Queried with teacher_id: {owner_teacher_id_for_query}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail_msg
        )

    # --- Update Step ---
    # owner_teacher_id_for_query is correctly set for both admin (None) and teacher (user_kinde_id)
    updated_student = await crud.update_student(
        student_internal_id=student_internal_id,
        student_in=student_in,
        teacher_id=owner_teacher_id_for_query # Pass Kinde ID for teachers, None for admins
    )

    if updated_student is None:
        # This can happen due to a few reasons:
        # 1. The student was deleted between the verification and update steps (less likely with proper DB transactions if used at a higher level).
        # 2. A unique constraint violation (e.g., duplicate external_student_id if trying to set it to an existing one).
        # 3. Other unexpected database error.
        # crud.update_student logs a warning if external_student_id is duplicate
        logger.error(f"Update failed for student {student_internal_id} by user {user_kinde_id} (Admin: {is_admin}) even after initial verification. This might be a conflict or DB error.")
        # Check if it was a potential duplicate external_student_id
        if student_in.external_student_id: # Check if external_student_id was part of the update
             # We can't be certain it was a duplicate without another query, but it's a common cause
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Update failed. This could be due to a conflict, such as an existing student with the external ID '{student_in.external_student_id}'."
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not update the student record due to an internal server error or conflict."
            )

    logger.info(f"Student internal ID {student_internal_id} updated successfully by user {user_kinde_id} (Admin: {is_admin}).")
    return updated_student

@router.delete(
    "/{student_internal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a student (Protected)", # Updated summary
    description="Deletes a student record using their internal unique ID. Requires authentication. Admins can delete any student, teachers only their own."
)
async def delete_existing_student(
    student_internal_id: uuid.UUID,
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to delete a specific student by their internal ID.
    Admins can delete any student. Teachers can only delete their own.
    Default is soft delete. Hard delete is not exposed via this API endpoint directly.
    """
    user_kinde_id = current_user_payload.get("sub")
    user_roles = current_user_payload.get("roles", [])
    is_admin = any(
        role == UserRoleEnum.ADMIN.value or (isinstance(role, dict) and role.get("key") == UserRoleEnum.ADMIN.value)
        for role in user_roles
    )

    logger.info(f"User {user_kinde_id} (Admin: {is_admin}) attempting to delete student internal ID: {student_internal_id}")

    owner_teacher_id_for_query = None
    if not is_admin:
        owner_teacher_id_for_query = user_kinde_id

    # --- Verification Step: Check if the student exists (and if teacher, if they own it) ---
    student_to_verify = await crud.get_student_by_id(
        student_internal_id=student_internal_id,
        teacher_id=owner_teacher_id_for_query # Pass Kinde ID for teachers, None for admins
    )

    if not student_to_verify:
        detail_msg = f"Student with internal ID {student_internal_id} not found"
        if not is_admin:
            detail_msg += " or you do not have permission to access this student for deletion."
        else: # Admin context
            detail_msg += "."
        logger.warning(f"Delete failed: Student {student_internal_id} not found or not accessible by user {user_kinde_id} (Admin: {is_admin}). Queried with teacher_id: {owner_teacher_id_for_query}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail_msg
        )

    # --- Deletion Step ---
    # owner_teacher_id_for_query is correctly set for admin (None) or teacher (user_kinde_id)
    # API performs soft delete by default (hard_delete=False in CRUD is default)
    deleted_successfully = await crud.delete_student(
        student_internal_id=student_internal_id,
        teacher_id=owner_teacher_id_for_query # Pass Kinde ID for teachers, None for admins
        # hard_delete parameter defaults to False in crud.delete_student
    )

    if not deleted_successfully:
        # This could happen if the student was deleted by another process between verification and deletion,
        # or if an unexpected error occurred in the CRUD operation.
        logger.error(f"Delete operation failed for student {student_internal_id} by user {user_kinde_id} (Admin: {is_admin}) even after initial verification. CRUD function returned false.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not delete student with internal ID {student_internal_id}. The student may have been deleted by another process or an internal error occurred."
        )

    logger.info(f"Student internal ID {student_internal_id} (soft) deleted successfully by user {user_kinde_id} (Admin: {is_admin}).")
    # No content returned on successful delete (HTTP 204)
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

