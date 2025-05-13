# app/api/v1/endpoints/assignments.py

import uuid
import logging # Import logging
from typing import List, Optional, Dict, Any # Add Dict, Any
from fastapi import APIRouter, HTTPException, status, Query, Depends # Add Depends

# Import Pydantic models
# from app.models.assignment import Assignment, AssignmentCreate, AssignmentUpdate # COMMENTED OUT
# from app.models.class_group import ClassGroup # Needed for auth check # COMMENTED OUT

# Import CRUD functions
# from app.db import crud # COMMENTED OUT

# Import the authentication dependency
# from app.core.security import get_current_user_payload # COMMENTED OUT

# Setup logger for this module
logger = logging.getLogger(__name__)

# Create the router instance - COMMENTED OUT
# router = APIRouter(
#     prefix="/assignments",
#     tags=["Assignments"]
# )

# === Helper for Authorization Check === - COMMENTED OUT
# # Checks if the user is the teacher for the relevant ClassGroup
# async def _authorize_assignment_action(
#     class_group_id: uuid.UUID,
#     user_payload: Dict[str, Any],
#     action: str = "access"
# ):
#     """
#     Checks if the user is authorized to perform an action related to an assignment
#     by checking if they are the teacher of the associated class group.
#     Raises HTTPException if not authorized or if related resources not found.
#     """
#     user_kinde_id_str = user_payload.get("sub")
#     try:
#         user_kinde_id = uuid.UUID(user_kinde_id_str)
#     except (ValueError, TypeError):
#          logger.error(f"Could not convert requesting user ID '{user_kinde_id_str}' to UUID for assignment auth check.")
#          raise HTTPException(
#              status_code=status.HTTP_400_BAD_REQUEST,
#              detail="Invalid user ID format in token."
#          )
#
#     # Fetch the class group the assignment belongs to (or will belong to)
#     # Note: Assumes get_class_group_by_id handles not found by returning None
#     # Pass include_deleted=False if ClassGroup uses soft delete and we only want active groups
#     class_group = await crud.get_class_group_by_id(class_group_id=class_group_id) # Assuming include_deleted=False by default if implemented
#     if not class_group:
#         logger.warning(f"Authorization check failed: ClassGroup {class_group_id} not found during attempt to {action} assignment.")
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=f"Associated ClassGroup {class_group_id} not found."
#         )
#
#     # Check if the current user is the teacher for this group
#     if class_group.teacher_id != user_kinde_id:
#         logger.warning(f"User {user_kinde_id_str} attempted to {action} assignment linked to ClassGroup {class_group_id} owned by {class_group.teacher_id}.")
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN, # 403 Forbidden
#             detail=f"Not authorized to {action} assignments for this class group."
#         )
#     # TODO: Add checks for other roles, like admin, if applicable


# === Assignment API Endpoints (Now Protected) === - COMMENTED OUT

# @router.post(
#     "/",
#     response_model=Assignment,
#     status_code=status.HTTP_201_CREATED,
#     summary="Create a new assignment (Protected)", # Updated summary
#     description="Creates a new assignment record, linked to a class group. Requires authentication. User must be the teacher of the specified class group." # Updated description
# )
# async def create_new_assignment(
#     assignment_in: AssignmentCreate,
#     # === Add Authentication Dependency ===
#     current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
# ):
#     """
#     Protected endpoint to create a new assignment.
#     Ensures the creator is the teacher of the specified class group.
#     - **assignment_in**: Assignment data based on the AssignmentCreate model.
#     """
#     user_kinde_id = current_user_payload.get("sub")
#     logger.info(f"User {user_kinde_id} attempting to create assignment: {assignment_in.assignment_name} for ClassGroup {assignment_in.class_group_id}")
#
#     # --- Authorization Check ---
#     # Check if the user is the teacher of the target class group before creating
#     await _authorize_assignment_action(assignment_in.class_group_id, current_user_payload, action="create assignment for")
#     # --- End Authorization Check ---
#
#     created_assignment = await crud.create_assignment(assignment_in=assignment_in)
#     if not created_assignment:
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Could not create the assignment record."
#         )
#     logger.info(f"Assignment '{created_assignment.assignment_name}' (ID: {created_assignment.id}) created successfully by user {user_kinde_id}.")
#     return created_assignment

# @router.get(
#     "/{assignment_id}",
#     response_model=Assignment,
#     status_code=status.HTTP_200_OK,
#     summary="Get a specific assignment by ID (Protected)", # Updated summary
#     description="Retrieves the details of a single assignment using its unique ID. Requires authentication." # Updated description
# )
# async def read_assignment(
#     assignment_id: uuid.UUID, # Internal ID ('id' aliased to '_id' in model)
#     # === Add Authentication Dependency ===
#     current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
# ):
#     """
#     Protected endpoint to retrieve a specific assignment by its ID.
#     - **assignment_id**: The UUID of the assignment to retrieve.
#     """
#     user_kinde_id = current_user_payload.get("sub")
#     logger.info(f"User {user_kinde_id} attempting to read assignment ID: {assignment_id}")
#
#     assignment = await crud.get_assignment_by_id(assignment_id=assignment_id) # Assuming include_deleted=False by default if implemented
#     if assignment is None:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=f"Assignment with ID {assignment_id} not found."
#         )
#
#     # TODO: Add fine-grained authorization check:
#     # Can user 'user_kinde_id' view this assignment?
#     # (e.g., are they the teacher of the assignment's class_group_id? Or an admin?)
#     # Example: await _authorize_assignment_action(assignment.class_group_id, current_user_payload, action="read")
#     # For now, any authenticated user can read any assignment they know the ID of.
#
#     return assignment

# @router.get(
#     "/",
#     response_model=List[Assignment],
#     status_code=status.HTTP_200_OK,
#     summary="Get a list of assignments (Protected)", # Updated summary
#     description="Retrieves a list of assignments, with optional filtering by class group and pagination. Requires authentication." # Updated description
# )
# async def read_assignments(
#     class_group_id: Optional[uuid.UUID] = Query(None, description="Filter assignments by ClassGroup UUID"),
#     skip: int = Query(0, ge=0, description="Records to skip"),
#     limit: int = Query(100, ge=1, le=500, description="Max records to return"),
#     # === Add Authentication Dependency ===
#     current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
# ):
#     """
#     Protected endpoint to retrieve a list of assignments. Supports filtering and pagination.
#     - **class_group_id**: Optional ClassGroup UUID filter.
#     - **skip**: Number of records to skip.
#     - **limit**: Maximum number of records per page.
#     """
#     user_kinde_id = current_user_payload.get("sub")
#     logger.info(f"User {user_kinde_id} attempting to read list of assignments with filter: class_group_id={class_group_id}")
#
#     # --- Authorization Check ---
#     # TODO: Add authorization logic.
#     # If class_group_id is provided, verify user can access that class group.
#     # Example: if class_group_id: await _authorize_assignment_action(class_group_id, current_user_payload, action="list assignments for")
#     # If class_group_id is NOT provided, should probably only return assignments
#     # from class groups the user teaches, or require admin rights to list all.
#     # For now, allows any authenticated user to use the filter as provided.
#     # --- End Authorization Check ---
#
#     # Assuming get_all_assignments respects soft delete if implemented
#     assignments = await crud.get_all_assignments(
#         class_group_id=class_group_id,
#         skip=skip,
#         limit=limit
#         # include_deleted=False # Pass if needed
#     )
#     return assignments

# @router.put(
#     "/{assignment_id}",
#     response_model=Assignment,
#     status_code=status.HTTP_200_OK,
#     summary="Update an existing assignment (Protected)", # Updated summary
#     description="Updates details (name, due date) of an existing assignment. Requires authentication. Only the assigned teacher can update." # Updated description
# )
# async def update_existing_assignment(
#     assignment_id: uuid.UUID,
#     assignment_in: AssignmentUpdate, # Uses AssignmentUpdate model (excludes class_group_id)
#     # === Add Authentication Dependency ===
#     current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
# ):
#     """
#     Protected endpoint to update an existing assignment.
#     Ensures the updater is the teacher of the associated class group.
#     - **assignment_id**: The UUID of the assignment to update.
#     - **assignment_in**: The assignment data fields to update (AssignmentUpdate model).
#     """
#     user_kinde_id_str = current_user_payload.get("sub")
#     logger.info(f"User {user_kinde_id_str} attempting to update assignment ID: {assignment_id}")
#
#     # --- Authorization Check ---
#     # Get the existing assignment first to find its class_group_id
#     # Assuming get_assignment_by_id respects soft delete by default
#     existing_assignment = await crud.get_assignment_by_id(assignment_id=assignment_id)
#     if existing_assignment is None:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=f"Assignment with ID {assignment_id} not found."
#         )
#     # Check if the current user is the teacher for the associated class group
#     await _authorize_assignment_action(existing_assignment.class_group_id, current_user_payload, action="update")
#     # --- End Authorization Check ---
#
#     # CRUD function assumes assignment exists and is not soft-deleted (if applicable)
#     updated_assignment = await crud.update_assignment(assignment_id=assignment_id, assignment_in=assignment_in)
#     if updated_assignment is None:
#         # Should only happen if assignment deleted between check and update, or DB error
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, # Or 404 if not found during update
#             detail=f"Failed to update assignment with ID {assignment_id}."
#         )
#     logger.info(f"Assignment ID {assignment_id} updated successfully by user {user_kinde_id_str}.")
#     return updated_assignment

# @router.delete(
#     "/{assignment_id}",
#     status_code=status.HTTP_204_NO_CONTENT,
#     summary="Delete an assignment (Protected)", # Updated summary
#     description="Deletes an assignment record. Requires authentication. Only the assigned teacher can delete." # Updated description
# )
# async def delete_existing_assignment(
#     assignment_id: uuid.UUID,
#     # === Add Authentication Dependency ===
#     current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
# ):
#     """
#     Protected endpoint to delete a specific assignment by its ID.
#     Ensures the deleter is the teacher of the associated class group.
#     - **assignment_id**: The UUID of the assignment to delete.
#     """
#     user_kinde_id_str = current_user_payload.get("sub")
#     logger.info(f"User {user_kinde_id_str} attempting to delete assignment ID: {assignment_id}")
#
#     # --- Authorization Check ---
#     # Get the existing assignment first to find its class_group_id
#     # Assuming get_assignment_by_id respects soft delete by default
#     existing_assignment = await crud.get_assignment_by_id(assignment_id=assignment_id)
#     if existing_assignment is None:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=f"Assignment with ID {assignment_id} not found."
#         )
#     # Check if the current user is the teacher for the associated class group
#     await _authorize_assignment_action(existing_assignment.class_group_id, current_user_payload, action="delete")
#     # --- End Authorization Check ---
#
#     # Assuming delete_assignment respects soft delete if implemented
#     deleted_successfully = await crud.delete_assignment(assignment_id=assignment_id) # Add hard_delete=False/True if needed
#     if not deleted_successfully:
#          # Should not happen if existence check passed, implies other error during delete
#          raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=f"Failed to delete assignment with ID {assignment_id}."
#         )
#     logger.info(f"Assignment ID {assignment_id} deleted successfully by user {user_kinde_id_str}.")
#     # No content returned on successful delete
#     return None

