# app/db/crud.py

# --- Core Imports ---
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError
from pymongo.collation import Collation, CollationStrength # Add for case-insensitive aggregation if needed
import uuid
from typing import List, Optional, Dict, Any, TypeVar, Type, Tuple
from datetime import datetime, timezone, timedelta, date as date_type # Avoid naming conflict with datetime module
import logging
import re
from contextlib import asynccontextmanager
from functools import wraps
import asyncio
from pydantic import ValidationError
# FIX: Import ResourceNotFoundError from azure.core.exceptions
from azure.core.exceptions import ResourceNotFoundError 
import os
import calendar
from fastapi import HTTPException # Import HTTPException

# --- Database Access ---
from .database import get_database # Changed to relative import

# --- Pydantic Models ---
from ..models.school import SchoolCreate, SchoolUpdate, School
# --- CORRECTED Teacher model imports ---
# Import TeacherCreate as defined in your teacher.py
from ..models.teacher import Teacher, TeacherCreate, TeacherUpdate, TeacherRole
# ------------------------------------
from ..models.class_group import ClassGroup, ClassGroupCreate, ClassGroupUpdate
from ..models.student import Student, StudentCreate, StudentUpdate
from ..models.document import Document, DocumentCreate, DocumentUpdate
from ..models.result import Result, ResultCreate, ResultUpdate, ResultStatus
# --- Import Enums used in Teacher model ---
from ..models.enums import DocumentStatus, ResultStatus, FileType, MarketingSource
from ..models.batch import Batch, BatchCreate, BatchUpdate, BatchWithDocuments
# --- Import for reprocess ---
from ..queue import enqueue_assessment_task

# --- Service Imports --- ADD THIS SECTION IF IT DOESN'T EXIST
from ..services.blob_storage import delete_blob as service_delete_blob # ADD THIS IMPORT

# --- Logging Setup ---
logger = logging.getLogger(__name__)

# --- MongoDB Collection Names ---
SCHOOL_COLLECTION = "schools"
TEACHER_COLLECTION = "teachers"
CLASSGROUP_COLLECTION = "classgroups"
STUDENT_COLLECTION = "students"
# ASSIGNMENT_COLLECTION = "assignments" # COMMENTED OUT
DOCUMENT_COLLECTION = "documents"
RESULT_COLLECTION = "results"

# --- Transaction and Helper Functions ---
# --- Database Transaction Utilities ---
# Ensure this is imported correctly
# from backend.app.db.database import get_database # REMOVED - Redundant and problematic absolute import

# Global variable for database instance, primarily for the transaction context
# This will be set by get_database() during app startup or when first called
# db_instance_for_crud: Optional[AsyncIOMotorDatabase] = None # Not strictly needed if get_database() is always used

# Async context manager for database transactions
@asynccontextmanager
async def transaction():
    """
    Provides a database transaction context using the MongoDB session.
    Ensures that the session is started and properly committed or aborted.
    """
    current_db = get_database()

    if current_db is None:
        logger.error("Transaction cannot proceed: Database not initialized (get_database() returned None).")
        raise RuntimeError("Database connection not available for transaction (get_database() returned None)")

    # Using the client from the database instance
    async with await current_db.client.start_session() as session: # 'session' is the motor session object
        async with session.start_transaction(): # MODIFIED: Use async with for the transaction context
            logger.debug(f"Transaction started with session ID: {session.session_id}")
            try:
                yield session # Yield the session for operations to use
                # If yield completes without exception, commit.
                if session.in_transaction: # Check if still in transaction before committing
                    await session.commit_transaction()
                    logger.debug(f"Transaction committed for session ID: {session.session_id}")
            except Exception as e:
                logger.error(f"Transaction aborted due to error: {e} for session ID: {session.session_id}", exc_info=True)
                if session.in_transaction: # Check if still in transaction before aborting
                    await session.abort_transaction()
                raise # Re-raise the exception after aborting

def with_transaction(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Check if a session is already provided (nested transaction)
        session = kwargs.get('session')
        if session is not None:
            # If called within an existing transaction, just execute the function
            logger.debug(f"Function {func.__name__} called within existing session.")
            return await func(*args, **kwargs)
        else:
            # If no session provided, start a new one (or proceed without if not supported)
            try:
                async with transaction() as new_session:
                    # Pass the new session (or None if transactions not supported) to the function
                    kwargs['session'] = new_session
                    logger.debug(f"Function {func.__name__} starting with new/no session.")
                    result = await func(*args, **kwargs)
                    logger.debug(f"Function {func.__name__} completed within new/no session.")
                    return result
            except Exception as e:
                # Log error from transaction context or the function itself
                logger.error(f"Operation failed for function {func.__name__}: {e}", exc_info=True)
                # Decide what to return on failure. None is common.
                return None
    return wrapper

def soft_delete_filter(include_deleted: bool = False) -> Dict[str, Any]:
    if include_deleted: return {}
    # return {"is_deleted": False} # Previous implementation
    # NEW: Filter for documents where is_deleted is NOT True (includes missing or False)
    return {"is_deleted": {"$ne": True}} 

def _get_collection(collection_name: str) -> Optional[AsyncIOMotorCollection]:
    db = get_database()
    if db is not None: return db[collection_name]
    logger.error("Database connection is not available (db object is None). Cannot get collection.")
    return None

# --- School CRUD Functions ---
@with_transaction
async def create_school(school_in: SchoolCreate, session=None) -> Optional[School]:
    collection = _get_collection(SCHOOL_COLLECTION); now = datetime.now(timezone.utc)
    if collection is None: return None
    new_school_id = uuid.uuid4()
    school_doc = school_in.model_dump(); school_doc["_id"] = new_school_id
    school_doc["created_at"] = now; school_doc["updated_at"] = now; school_doc["is_deleted"] = False
    logger.info(f"Inserting school: {school_doc['_id']}")
    try:
        inserted_result = await collection.insert_one(school_doc, session=session)
        if inserted_result.acknowledged: created_doc = await collection.find_one({"_id": new_school_id}, session=session)
        else: logger.error(f"Insert not acknowledged for school ID: {new_school_id}"); return None
        if created_doc: return School(**created_doc) # Assumes schema handles alias
        else: logger.error(f"Failed to retrieve school after insert: {new_school_id}"); return None
    except Exception as e: logger.error(f"Error inserting school: {e}", exc_info=True); return None

async def get_school_by_id(school_id: uuid.UUID, include_deleted: bool = False, session=None) -> Optional[School]:
    collection = _get_collection(SCHOOL_COLLECTION);
    if collection is None: return None
    logger.info(f"Getting school ID: {school_id}")
    query = {"_id": school_id}; query.update(soft_delete_filter(include_deleted))
    try: school_doc = await collection.find_one(query, session=session)
    except Exception as e: logger.error(f"Error getting school: {e}", exc_info=True); return None
    if school_doc: return School(**school_doc) # Assumes schema handles alias
    else: logger.warning(f"School {school_id} not found."); return None

async def get_all_schools(skip: int = 0, limit: int = 100, include_deleted: bool = False, session=None) -> List[School]:
    collection = _get_collection(SCHOOL_COLLECTION); schools_list: List[School] = []
    if collection is None: return schools_list
    query = soft_delete_filter(include_deleted)
    logger.info(f"Getting all schools (deleted={include_deleted}) skip={skip} limit={limit}")
    try:
        cursor = collection.find(query, session=session).skip(skip).limit(limit)
        async for doc in cursor:
            try:
                mapped_data = {**doc}
                if "_id" in mapped_data: mapped_data["id"] = mapped_data.pop("_id")
                else: logger.warning(f"School doc missing '_id': {doc}"); continue
                schools_list.append(School(**mapped_data))
            except Exception as validation_err: logger.error(f"Pydantic validation failed for school doc {doc.get('_id', 'UNKNOWN')}: {validation_err}")
    except Exception as e: logger.error(f"Error getting all schools: {e}", exc_info=True)
    return schools_list

@with_transaction
async def update_school(school_id: uuid.UUID, school_in: SchoolUpdate, session=None) -> Optional[School]:
    collection = _get_collection(SCHOOL_COLLECTION); now = datetime.now(timezone.utc)
    if collection is None: return None
    update_data = school_in.model_dump(exclude_unset=True)
    update_data.pop("_id", None); update_data.pop("id", None); update_data.pop("created_at", None)
    if not update_data: logger.warning(f"No update data for school {school_id}"); return await get_school_by_id(school_id, include_deleted=False, session=session)
    update_data["updated_at"] = now; logger.info(f"Updating school {school_id}")
    query_filter = {"_id": school_id, "is_deleted": {"$ne": True}}
    try:
        updated_doc = await collection.find_one_and_update(query_filter, {"$set": update_data}, return_document=ReturnDocument.AFTER, session=session)
        if updated_doc: return School(**updated_doc) # Assumes schema handles alias
        else: logger.warning(f"School {school_id} not found or deleted for update."); return None
    except Exception as e: logger.error(f"Error updating school: {e}", exc_info=True); return None

@with_transaction
async def delete_school(school_id: uuid.UUID, hard_delete: bool = False, session=None) -> bool:
    collection = _get_collection(SCHOOL_COLLECTION); now = datetime.now(timezone.utc)
    if collection is None: return False
    logger.info(f"{'Hard' if hard_delete else 'Soft'} deleting school {school_id}")
    count = 0
    try:
        if hard_delete: result = await collection.delete_one({"_id": school_id}, session=session); count = result.deleted_count
        else:
            now = datetime.now(timezone.utc)
            update_payload = {"is_deleted": True, "updated_at": now}
            result = await collection.update_one(
                {"_id": school_id, "is_deleted": {"$ne": True}},
                {"$set": update_payload},
                session=session
            )
            count = result.modified_count
    except Exception as e: logger.error(f"Error deleting school: {e}", exc_info=True); return False
    if count == 1: logger.info(f"Successfully deleted school {school_id}"); return True
    else: logger.warning(f"School {school_id} not found or already deleted."); return False


# --- Teacher CRUD Functions ---
# @with_transaction # Keep commented out if transactions cause issues
async def create_teacher(
    teacher_in: TeacherCreate, # Use TeacherCreate as defined in teacher.py
    kinde_id: str,             # Pass kinde_id separately
    session=None
) -> Optional[Teacher]:
    """
    Creates a teacher record, linking it to a Kinde ID.
    Uses data from TeacherCreate model (typically called by webhook/backend process).
    """
    # If not using transaction, session will be None here
    if session:
        logger.debug("create_teacher called within an existing session.")
    else:
        # This log appeared in user's logs, so keeping it.
        logger.warning("create_teacher called WITHOUT an active session (transaction decorator removed/disabled).")

    collection = _get_collection(TEACHER_COLLECTION)
    now = datetime.now(timezone.utc) # Define now here as it's used multiple times
    if collection is None: 
        logger.error("Teacher collection not found.")
        return None

    # --- Application-level uniqueness check for kinde_id --- 
    # This check is reinstated as kinde_id is a separate field and needs uniqueness.
    existing_teacher_count = await collection.count_documents({"kinde_id": kinde_id, "is_deleted": {"$ne": True}}, session=session)
    if existing_teacher_count > 0:
        logger.warning(f"Attempted to create a teacher with an existing kinde_id: {kinde_id}")
        # Consider raising HTTPException(status_code=409, detail="Teacher with this Kinde ID already exists.")
        return None 
    # --- End uniqueness check ---

    # Generate a new internal UUID for the teacher record (_id)
    internal_id = uuid.uuid4() # This will be the MongoDB _id

    # Prepare the document for insertion
    teacher_doc = teacher_in.model_dump() # Converts Pydantic model to dict
    
    teacher_doc["_id"] = internal_id      # Set MongoDB's _id to our new UUID
    teacher_doc["kinde_id"] = kinde_id    # Store the Kinde ID string as a separate field

    # Add timestamps
    teacher_doc["created_at"] = now
    teacher_doc["updated_at"] = now
    if 'is_deleted' not in teacher_doc:
         teacher_doc['is_deleted'] = False

    logger.info(f"Attempting to insert new teacher with _id: {internal_id} and kinde_id: {kinde_id}")
    
    try:
        result = await collection.insert_one(teacher_doc, session=session)
        if result.inserted_id: # This will be the internal_id (UUID)
            logger.info(f"Successfully created teacher with _id: {result.inserted_id}, kinde_id: {kinde_id}")
            # Retrieve the fully created document from DB
            created_doc = await collection.find_one({"_id": result.inserted_id}, session=session)
            if created_doc:
                # MongoDB returns _id as UUID if it was inserted as UUID.
                # The Pydantic model Teacher.id (aliased to _id) is uuid.UUID.
                # No explicit str conversion for _id is needed here.
                return Teacher(**created_doc) # Convert DB doc back to Pydantic model
            else:
                logger.error(f"Failed to retrieve teacher after insert, _id: {result.inserted_id}")
                return None 
        else:
            logger.error(f"Teacher insertion failed for kinde_id {kinde_id}, no inserted_id returned.")
            return None
    except DuplicateKeyError: # This would catch duplicate _id, which is unlikely for UUIDs.
        logger.error(f"Duplicate key error (likely on _id) creating teacher. This should be rare with UUIDs for _id.")
        return None
    except Exception as e:
        logger.error(f"Unexpected error creating teacher with kinde_id {kinde_id}: {e}", exc_info=True)
        return None

async def get_teacher_by_id(teacher_id: uuid.UUID, session=None) -> Optional[Teacher]: # Changed teacher_id type to uuid.UUID
    """Get a single teacher by their internal database ID (UUID)."""
    collection = _get_collection(TEACHER_COLLECTION)
    if collection is None: return None
    logger.info(f"Getting teacher by internal _id: {teacher_id}")
    try:
        teacher_doc = await collection.find_one({"_id": teacher_id, "is_deleted": {"$ne": True}}, session=session)
        if teacher_doc:
            # _id from DB is UUID, Teacher model id field is uuid.UUID.
            return Teacher(**teacher_doc)
        return None
    except Exception as e:
        logger.error(f"Error getting teacher by _id: {e}", exc_info=True)
        return None

async def get_teacher_by_kinde_id(kinde_id: str, session=None) -> Optional[Teacher]:
    """Retrieves a teacher by their Kinde ID."""
    collection = _get_collection(TEACHER_COLLECTION)
    if collection is None: return None
    
    query = {"kinde_id": kinde_id} # Query by the kinde_id field
    query.update(soft_delete_filter(False)) # Ensure we don't fetch soft-deleted

    logger.info(f"Getting teacher by kinde_id: {kinde_id}")
    try:
        teacher_doc = await collection.find_one(query, session=session)
    except Exception as e:
        logger.error(f"Error finding teacher by kinde_id {kinde_id}: {e}", exc_info=True)
        return None
        
    if teacher_doc:
        # _id from DB is UUID, Teacher model id field is uuid.UUID.
        return Teacher(**teacher_doc)
    else:
        logger.debug(f"Teacher with kinde_id {kinde_id} not found or is marked as deleted.")
        return None

async def get_all_teachers(skip: int = 0, limit: int = 100, include_deleted: bool = False, session=None) -> List[Teacher]:
    collection = _get_collection(TEACHER_COLLECTION); teachers_list: List[Teacher] = []
    if collection is None: return teachers_list
    query = soft_delete_filter(include_deleted)
    logger.info(f"Getting all teachers skip={skip} limit={limit}")
    try:
        # Fetch without session
        cursor = collection.find(query).skip(skip).limit(limit)
        async for doc in cursor:
            try:
                 teachers_list.append(Teacher(**doc))
            except Exception as validation_err:
                logger.error(f"Pydantic validation failed for teacher doc {doc.get('_id', 'UNKNOWN')}: {validation_err}")
    except Exception as e:
        logger.error(f"Error getting all teachers: {e}", exc_info=True)
    return teachers_list

@with_transaction # Keep transaction for update as it modifies existing data
async def update_teacher(kinde_id: str, teacher_in: TeacherUpdate, session=None) -> Optional[Teacher]:
    """Updates a teacher's profile information identified by their Kinde ID."""
    collection = _get_collection(TEACHER_COLLECTION); now = datetime.now(timezone.utc)
    if collection is None: return None

    update_data = teacher_in.model_dump(exclude_unset=True)

    if 'role' in update_data and isinstance(update_data.get('role'), TeacherRole):
        update_data['role'] = update_data['role'].value

    # Remove fields that should not be updated directly or are identifiers
    update_data.pop("_id", None) # Should not be in TeacherUpdate anyway
    update_data.pop("id", None)   # Should not be in TeacherUpdate anyway
    update_data.pop("kinde_id", None) # kinde_id is the query key, not part of $set
    update_data.pop("created_at", None)
    update_data.pop("how_did_you_hear", None)
    update_data.pop("email", None) # Email not updatable via profile PUT /me

    if not update_data:
        logger.warning(f"No valid update data provided for teacher with Kinde ID {kinde_id}")
        return await get_teacher_by_kinde_id(kinde_id=kinde_id, session=session)

    update_data["updated_at"] = now
    logger.info(f"Updating teacher with Kinde ID {kinde_id} with data: {update_data}")

    query_filter = {"kinde_id": kinde_id, "is_deleted": {"$ne": True}} # Query by kinde_id field

    try:
        updated_doc = await collection.find_one_and_update(
            query_filter,
            {"$set": update_data},
            return_document=ReturnDocument.AFTER,
            session=session
        )

        if updated_doc:
            # _id from DB is UUID, Teacher model id field is uuid.UUID.
            return Teacher(**updated_doc)
        else:
            logger.warning(f"Teacher with Kinde ID {kinde_id} not found or already deleted during update attempt.")
            return None
    except Exception as e:
        logger.error(f"Error during teacher update operation for Kinde ID {kinde_id}: {e}", exc_info=True)
        return None

@with_transaction # Keep transaction for delete
async def delete_teacher(kinde_id: str, hard_delete: bool = False, session=None) -> bool:
    """Deletes a teacher record identified by their Kinde ID."""
    collection = _get_collection(TEACHER_COLLECTION)
    if collection is None: return False
    logger.info(f"{'Hard' if hard_delete else 'Soft'} deleting teacher with Kinde ID {kinde_id}")
    count = 0
    query_filter = {"kinde_id": kinde_id}
    try:
        if hard_delete:
            result = await collection.delete_one(query_filter, session=session);
            count = result.deleted_count
        else:
            now = datetime.now(timezone.utc)
            update_payload = {"is_deleted": True, "updated_at": now}
            result = await collection.update_one(
                {"kinde_id": kinde_id, "is_deleted": {"$ne": True}},
                {"$set": update_payload},
                session=session
            );
            count = result.modified_count
    except Exception as e:
        logger.error(f"Error deleting teacher with Kinde ID {kinde_id}: {e}", exc_info=True); return False

    if count == 1:
        logger.info(f"Successfully {'hard' if hard_delete else 'soft'} deleted teacher with Kinde ID {kinde_id}")
        return True
    else:
        logger.warning(f"Teacher with Kinde ID {kinde_id} not found or already deleted."); return False

# Add this function within your app/db/crud.py, under "Teacher CRUD Functions"

async def update_teacher_by_stripe_customer_id(
    db: AsyncIOMotorDatabase, # Not strictly needed as _get_collection uses get_database internally
    stripe_customer_id: str,
    data_to_update: TeacherUpdate # Assuming TeacherUpdate is your app.models.teacher.TeacherUpdate
) -> Optional[Teacher]: # Changed TeacherModel to Teacher based on existing code
    """
    Updates a teacher's record identified by their Stripe Customer ID.
    """
    collection = _get_collection(TEACHER_COLLECTION)
    if collection is None:
        logger.error(f"Teacher collection not found for update by stripe_customer_id: {stripe_customer_id}")
        return None

    # Prepare the update document from the Pydantic model
    # exclude_unset=True ensures only provided fields are updated
    update_data_dict = data_to_update.model_dump(exclude_unset=True)

    # Ensure critical identifiers are not part of the $set payload if they shouldn't be changed
    update_data_dict.pop("_id", None)
    update_data_dict.pop("id", None)
    update_data_dict.pop("kinde_id", None) # Kinde ID should not be changed by Stripe webhooks
    update_data_dict.pop("stripe_customer_id", None) # This is the query key, not part of $set
    # Ensure 'role' is handled if present, converting Enum to value
    if 'role' in update_data_dict and isinstance(update_data_dict.get('role'), TeacherRole):
        update_data_dict['role'] = update_data_dict['role'].value


    if not update_data_dict:
        logger.warning(f"No valid update data provided for teacher with stripe_customer_id {stripe_customer_id}")
        # Optionally, fetch and return the current teacher document if no updates are to be made
        current_teacher_doc = await collection.find_one({"stripe_customer_id": stripe_customer_id, "is_deleted": {"$ne": True}})
        if current_teacher_doc:
            return Teacher(**current_teacher_doc) # Use Teacher model
        return None

    # Always set/update the 'updated_at' timestamp
    update_data_dict["updated_at"] = datetime.now(timezone.utc)

    logger.info(f"Attempting to update teacher with stripe_customer_id {stripe_customer_id} with data: {update_data_dict}")

    query_filter = {"stripe_customer_id": stripe_customer_id, "is_deleted": {"$ne": True}}

    try:
        updated_doc = await collection.find_one_and_update(
            query_filter,
            {"$set": update_data_dict},
            return_document=ReturnDocument.AFTER # Return the document after update
        )

        if updated_doc:
            logger.info(f"Successfully updated teacher (Kinde ID: {updated_doc.get('kinde_id')}) via stripe_customer_id {stripe_customer_id}")
            return Teacher(**updated_doc) # Use Teacher model
        else:
            logger.warning(f"Teacher with stripe_customer_id {stripe_customer_id} not found or already deleted during update attempt.")
            return None
    except Exception as e:
        logger.error(f"Error during teacher update by stripe_customer_id {stripe_customer_id}: {e}", exc_info=True)
        return None

# --- ClassGroup CRUD Functions ---
# --- REMOVED @with_transaction from create_class_group --- NO, it was already removed.
async def create_class_group(
    class_group_in: ClassGroupCreate, # teacher_id (UUID) is now correctly in this model
    # teacher_id: str, # MODIFIED: REMOVED - No longer needed as it's in class_group_in as UUID
    session=None
) -> Optional[ClassGroup]:
    """Creates a class group record using data. teacher_id (internal UUID) is in class_group_in."""
    collection = _get_collection(CLASSGROUP_COLLECTION); now = datetime.now(timezone.utc)
    if collection is None: return None
    new_id = uuid.uuid4()
    doc = class_group_in.model_dump(); # teacher_id (UUID) from class_group_in will be used
    doc["_id"] = new_id;
    # doc["teacher_id"] = teacher_id # REMOVED - No longer needed, taken from class_group_in.teacher_id
    doc.setdefault("student_ids", [])
    doc["created_at"] = now; doc["updated_at"] = now; doc["is_deleted"] = False
    logger.info(f"Inserting class group: {doc['_id']} for teacher (internal UUID): {doc['teacher_id']}") # Updated log message
    try: inserted_result = await collection.insert_one(doc, session=session) # Pass session if provided
    except Exception as e: logger.error(f"Error inserting class group: {e}", exc_info=True); return None
    if inserted_result.acknowledged: created_doc = await collection.find_one({"_id": new_id}, session=session)
    else: logger.error(f"Insert class group not acknowledged: {new_id}"); return None
    if created_doc: return ClassGroup(**created_doc) # Assumes schema handles alias
    else: logger.error(f"Failed retrieve class group post-insert: {new_id}"); return None

async def get_class_group_by_id(class_group_id: uuid.UUID, include_deleted: bool = False, session=None) -> Optional[ClassGroup]:
    collection = _get_collection(CLASSGROUP_COLLECTION);
    if collection is None: return None
    logger.info(f"Getting class group: {class_group_id}")
    query = {"_id": class_group_id}; query.update(soft_delete_filter(include_deleted))
    try: doc = await collection.find_one(query, session=session)
    except Exception as e: logger.error(f"Error getting class group: {e}", exc_info=True); return None
    if doc: return ClassGroup(**doc) # Assumes schema handles alias
    else: logger.warning(f"Class group {class_group_id} not found."); return None

async def get_all_class_groups( teacher_id: Optional[uuid.UUID] = None, school_id: Optional[uuid.UUID] = None, skip: int = 0, limit: int = 100, include_deleted: bool = False, session=None) -> List[ClassGroup]:
    collection = _get_collection(CLASSGROUP_COLLECTION); items_list: List[ClassGroup] = []
    if collection is None: return items_list
    filter_query = soft_delete_filter(include_deleted)
    if teacher_id: filter_query["teacher_id"] = teacher_id # Assuming ClassGroup stores teacher's internal UUID (_id/id)
    # if school_id: filter_query["school_id"] = school_id # Assuming ClassGroup stores school's internal UUID (_id/id)
    logger.info(f"Getting all class groups filter={filter_query} skip={skip} limit={limit}")
    try:
        cursor = collection.find(filter_query, session=session).skip(skip).limit(limit)
        async for doc in cursor:
            try:
                mapped_data = {**doc}
                if "_id" in mapped_data: mapped_data["id"] = mapped_data.pop("_id")
                else: logger.warning(f"ClassGroup doc missing '_id': {doc}"); continue
                items_list.append(ClassGroup(**mapped_data))
            except Exception as validation_err: logger.error(f"Pydantic validation failed for class group doc {doc.get('_id', 'UNKNOWN')}: {validation_err}")
    except Exception as e: logger.error(f"Error getting all class groups: {e}", exc_info=True)
    return items_list

async def get_class_group_by_name_year_and_teacher(
    class_name: str, 
    teacher_id: uuid.UUID, # MODIFIED: Changed from teacher_kinde_id: str to teacher_id: uuid.UUID
    academic_year: Optional[str], 
    session=None
) -> Optional[ClassGroup]:
    """
    Retrieves a class group by its name, academic year (optional), and the teacher's internal UUID.
    If academic_year is None, it specifically looks for class groups where academic_year is not set.
    """
    collection = _get_collection(CLASSGROUP_COLLECTION)
    if collection is None: 
        logger.error("Classgroup collection not available for get_class_group_by_name_year_and_teacher")
        return None

    # The teacher_id provided is now the internal UUID, so no further lookup is needed here.
    # If teacher_id were still Kinde ID, we'd do:
    # teacher_record = await get_teacher_by_kinde_id(kinde_id=teacher_kinde_id, session=session)
    # if not teacher_record or not teacher_record.id:
    #     logger.warning(f"Teacher not found for Kinde ID {teacher_kinde_id} when searching for class group.")
    #     return None
    # internal_teacher_uuid = teacher_record.id

    query = {
        "class_name": class_name,
        "teacher_id": teacher_id, # Use the direct internal UUID
        # "academic_year": academic_year # Original simple query for academic_year
    }
    # Handle academic_year: if None is passed, explicitly query for null or not exists.
    # If a string is passed, query for that string.
    if academic_year is None:
        query["academic_year"] = None # or query["academic_year"] = {"$exists": False} if that's preferred for unset fields
    else:
        query["academic_year"] = academic_year

    query.update(soft_delete_filter(include_deleted=False)) # Always exclude deleted for this check

    logger.debug(f"Querying for class group: {query}")
    try:
        class_group_doc = await collection.find_one(query, session=session)
        if class_group_doc:
            return ClassGroup(**class_group_doc)
        return None
    except Exception as e:
        logger.error(f"Error in get_class_group_by_name_year_and_teacher: {e}", exc_info=True)
        return None

@with_transaction
async def update_class_group(class_group_id: uuid.UUID, teacher_id: uuid.UUID, class_group_in: ClassGroupUpdate, session=None) -> Optional[ClassGroup]:
    collection = _get_collection(CLASSGROUP_COLLECTION); now = datetime.now(timezone.utc)
    if collection is None: return None
    update_data = class_group_in.model_dump(exclude_unset=True)
    update_data.pop("_id", None); update_data.pop("id", None); # Pop internal 'id' if present
    update_data.pop("created_at", None)
    # Prevent changing teacher/school association via this update if needed
    # update_data.pop("teacher_id", None) # Teacher ID should not be changed here
    # update_data.pop("school_id", None)
    if not update_data: 
        logger.warning(f"No update data for class group {class_group_id}")
        # Need to fetch class_group by id and teacher_id if we are to implement RBAC here
        # For now, just getting by id, assuming teacher_id check is for the update operation itself.
        # The get_class_group_by_id doesn't perform RBAC by teacher_id, so this path might need review
        # if called with a teacher_id that doesn't own the class_group_id.
        # However, the query_filter below *does* check ownership.
        cg = await get_class_group_by_id(class_group_id, include_deleted=False, session=session)
        if cg and cg.teacher_id == teacher_id: # Add check here
             return cg
        return None # If not owned or not found

    update_data["updated_at"] = now; logger.info(f"Updating class group {class_group_id} for teacher (internal UUID): {teacher_id}")
    query_filter = {"_id": class_group_id, "teacher_id": teacher_id, "is_deleted": {"$ne": True}} # teacher_id is now UUID
    try:
        updated_doc = await collection.find_one_and_update( query_filter, {"$set": update_data}, return_document=ReturnDocument.AFTER, session=session)
        if updated_doc: return ClassGroup(**updated_doc) # Assumes schema handles alias
        else: logger.warning(f"Class group {class_group_id} not found or already deleted for update, or not owned by teacher {teacher_id}."); return None
    except Exception as e: logger.error(f"Error during class group update operation: {e}", exc_info=True); return None

@with_transaction
async def delete_class_group(class_group_id: uuid.UUID, teacher_id: uuid.UUID, hard_delete: bool = False, session=None) -> bool:
    collection = _get_collection(CLASSGROUP_COLLECTION)
    if collection is None: return False
    logger.info(f"{'Hard' if hard_delete else 'Soft'} deleting class group {class_group_id} for teacher (internal UUID): {teacher_id}")
    count = 0
    query_base = {"_id": class_group_id, "teacher_id": teacher_id} # teacher_id is now UUID
    try:
        if hard_delete: 
            result = await collection.delete_one(query_base, session=session)
            count = result.deleted_count
        else:
            now = datetime.now(timezone.utc)
            # For soft delete, also ensure it's not already deleted
            soft_delete_query = {**query_base, "is_deleted": {"$ne": True}}
            result = await collection.update_one(
                soft_delete_query,
                {"$set": {"is_deleted": True, "updated_at": now}}, session=session
            )
            count = result.modified_count
    except Exception as e: 
        logger.error(f"Error deleting class group {class_group_id} for teacher {teacher_id}: {e}", exc_info=True)
        return False
    if count == 1: 
        logger.info(f"Successfully deleted class group {class_group_id} for teacher {teacher_id}")
        return True
    else: 
        logger.warning(f"Class group {class_group_id} not found for teacher {teacher_id} or already deleted.")
        return False

# --- START: NEW CRUD FUNCTIONS for ClassGroup <-> Student Relationship ---
@with_transaction
async def add_student_to_class_group(
    class_group_id: uuid.UUID, student_id: uuid.UUID, session=None
) -> bool:
    """Adds a student ID to the student_ids array of a specific class group.

    Uses $addToSet to prevent duplicates.

    Returns:
        bool: True if the student was added or already existed, False on error or if class not found.
    """
    collection = _get_collection(CLASSGROUP_COLLECTION)
    if collection is None:
        return False
    now = datetime.now(timezone.utc)
    logger.info(f"Attempting to add student {student_id} to class group {class_group_id}")
    # RBAC check for add_student_to_class_group: 
    # The calling layer should ensure teacher_id from token owns the class_group_id.
    # This function currently trusts class_group_id is valid for the context.
    # If direct RBAC needed here, add teacher_id to signature and query.
    query_filter = {"_id": class_group_id, "is_deleted": {"$ne": True}}
    update_operation = {
        "$addToSet": {"student_ids": student_id},  # Use $addToSet to avoid duplicates
        "$set": {"updated_at": now},
    }
    try:
        result = await collection.update_one(
            query_filter, update_operation, session=session
        )
        # update_one returns matched_count and modified_count.
        # If matched_count is 1, the class group was found.
        # modified_count will be 1 if added, 0 if student already existed. Both are success cases here.
        if result.matched_count == 1:
            logger.info(
                f"Student {student_id} added to (or already in) class group {class_group_id}. Modified count: {result.modified_count}"
            )
            return True
        else:
            logger.warning(
                f"Class group {class_group_id} not found or already deleted when trying to add student {student_id}."
            )
            return False
    except Exception as e:
        logger.error(
            f"Error adding student {student_id} to class group {class_group_id}: {e}",
            exc_info=True,
        )
        return False


@with_transaction
async def remove_student_from_class_group(
    class_group_id: uuid.UUID, student_id: uuid.UUID, session=None
) -> bool:
    """Removes a student ID from the student_ids array of a specific class group.

    Uses $pull operator.

    Returns:
        bool: True if the student was successfully removed, False otherwise (e.g., class not found, student not in class).
    """
    collection = _get_collection(CLASSGROUP_COLLECTION)
    if collection is None:
        return False
    now = datetime.now(timezone.utc)
    logger.info(f"Attempting to remove student {student_id} from class group {class_group_id}")
    # RBAC check for remove_student_from_class_group: Similar to add_student_to_class_group
    query_filter = {"_id": class_group_id, "is_deleted": {"$ne": True}}
    update_operation = {
        "$pull": {"student_ids": student_id},  # Use $pull to remove the specific student ID
        "$set": {"updated_at": now},
    }
    try:
        result = await collection.update_one(
            query_filter, update_operation, session=session
        )
        # We need modified_count to be 1 for a successful removal.
        # If matched_count is 1 but modified_count is 0, the student wasn't in the list.
        if result.modified_count == 1:
            logger.info(
                f"Successfully removed student {student_id} from class group {class_group_id}."
            )
            return True
        elif result.matched_count == 1:
            logger.warning(
                f"Student {student_id} was not found in class group {class_group_id} for removal."
            )
            return False
        else:
            logger.warning(
                f"Class group {class_group_id} not found or already deleted when trying to remove student {student_id}."
            )
            return False
    except Exception as e:
        logger.error(
            f"Error removing student {student_id} from class group {class_group_id}: {e}",
            exc_info=True,
        )
        return False
# --- END: NEW CRUD FUNCTIONS for ClassGroup <-> Student Relationship ---

# --- Student CRUD Functions (Keep existing) ---
@with_transaction
async def create_student(student_in: StudentCreate, teacher_id: str, session=None) -> Optional[Student]:
    collection = _get_collection(STUDENT_COLLECTION)
    if collection is None:
        logger.error(f"Failed to get collection {STUDENT_COLLECTION}")
        return None

    # Ensure the collection exists before starting a transaction for insert
    # by performing a lightweight, non-transactional read operation.
    # This is to prevent "OperationNotSupportedInTransaction" error in Cosmos DB
    # when a collection is auto-created during a transaction.
    # try:
    #     await collection.count_documents({}, limit=1) # No session here
    # except Exception as e:
    #     logger.error(f"Error ensuring collection {STUDENT_COLLECTION} exists: {e}", exc_info=True)
    #     # Depending on the desired behavior, you might want to return None or raise
    #     return None

    now = datetime.now(timezone.utc)
    if collection is None:
        return None

    new_student_id = uuid.uuid4()
    # Dump the Pydantic model, explicitly including 'teacher_id' if it's added to StudentCreate
    # If teacher_id is NOT part of StudentCreate yet, it needs to be added here.
    student_doc = student_in.model_dump(exclude_unset=True) # Using exclude_unset might be safer
    student_doc["_id"] = new_student_id
    student_doc["teacher_id"] = teacher_id # Add teacher_id to the document
    student_doc["created_at"] = now
    student_doc["updated_at"] = now
    student_doc["is_deleted"] = False
    # We might need to explicitly add teacher_id here if it's not in student_in
    # Example: student_doc["teacher_id"] = teacher_id_passed_to_function

    logger.info(f"Attempting to insert student with internal ID: {new_student_id} for teacher: {teacher_id}") # Update log
    try:
        inserted_result = await collection.insert_one(student_doc, session=session)
        if inserted_result.acknowledged:
            created_doc = await collection.find_one({"_id": new_student_id}, session=session)
            if created_doc:
                mapped_data = {**created_doc}
                if "_id" in mapped_data: mapped_data["id"] = mapped_data.pop("_id")
                return Student(**mapped_data)
            else:
                logger.error(f"Failed retrieve student post-insert: {new_student_id}"); return None
        else:
            logger.error(f"Insert student not acknowledged: {new_student_id}"); return None
    except DuplicateKeyError:
        ext_id = student_doc.get('external_student_id')
        logger.warning(f"Duplicate external_student_id: '{ext_id}' on create.")
        return None
    except Exception as e:
        logger.error(f"Error inserting student: {e}", exc_info=True); return None

async def get_student_by_id(
    student_internal_id: uuid.UUID,
    teacher_id: str, # <<< ADDED: Make teacher_id mandatory
    include_deleted: bool = False,
    session=None
) -> Optional[Student]:
    collection = _get_collection(STUDENT_COLLECTION);
    if collection is None: return None
    logger.info(f"Getting student: {student_internal_id} for teacher: {teacher_id}") # Update log
    query = {"_id": student_internal_id, "teacher_id": teacher_id}
    query.update(soft_delete_filter(include_deleted))
    
    logger.debug(f"[crud.get_student_by_id] Executing find_one with query: {query}") # DETAIL LOG 1

    try:
        student_doc = await collection.find_one(query, session=session)
        
        logger.debug(f"[crud.get_student_by_id] Raw student_doc from find_one: {student_doc}") # DETAIL LOG 2
        
        if student_doc:
            mapped_data = {**student_doc}
            if "_id" in mapped_data: mapped_data["id"] = mapped_data.pop("_id")
            return Student(**mapped_data)
        else:
            logger.warning(f"Student {student_internal_id} not found for teacher {teacher_id}."); return None # Modified log
    except Exception as e:
        logger.error(f"Error getting student: {e}", exc_info=True); return None

async def get_all_students(
    teacher_id: str, 
    external_student_id: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    year_group: Optional[str] = None,
    class_id: Optional[uuid.UUID] = None, # ADDED class_id
    skip: int = 0,
    limit: int = 100,
    include_deleted: bool = False,
    session=None
) -> List[Student]:
    collection = _get_collection(STUDENT_COLLECTION)
    students_list: List[Student] = []
    if collection is None:
        return students_list

    query: Dict[str, Any] = {}
    query.update(soft_delete_filter(include_deleted))

    # Apply teacher_id filter - assuming students are scoped to a teacher.
    # This might need adjustment based on your exact multi-tenancy model.
    # For now, we assume a teacher can only see students they are associated with
    # or students in a class they own.
    # If class_id is provided, the teacher_id check should ideally be on the class group.
    
    # If class_id is provided, prioritize fetching students from that class
    if class_id:
        logger.info(f"Filtering students by class_id: {class_id} for teacher_kinde_id: {teacher_id}")
        # Fetch the class group to get its student_ids
        # Note: get_class_group_by_id does not directly take teacher_id for auth,
        # Auth should happen at the API layer before calling this.
        # However, we need to ensure the requesting teacher CAN see these students.
        # The API layer already fetched the class group and authorized the teacher for it.
        class_group_doc = await get_class_group_by_id(class_group_id=class_id, session=session) # Renamed to avoid conflict
        if not class_group_doc or not class_group_doc.student_ids:
            logger.info(f"Class group {class_id} not found or has no students.")
            return [] # Return empty list if class not found or no students in it
        
        # Filter students whose _id is in the class_group's student_ids list
        query["_id"] = {"$in": class_group_doc.student_ids}
        # When filtering by class_id, the teacher_id constraint is implicitly handled 
        # by the API layer ensuring the teacher owns the class. We are fetching students
        # based on the class's student list.
        # We also need to ensure these students actually belong to the teacher if student_ids can be manipulated
        # or if a student can be in a class but not belong to the teacher who owns the class.
        # However, Student.teacher_id is Kinde ID. The current teacher_id param is Kinde ID.
        # So adding this ensures students are from the class AND directly tied to this teacher.
        query["teacher_id"] = teacher_id

        logger.debug(f"Query for students by class_id {class_id}: {query}")

    else:
        # Original filters if no class_id is provided
        # This part needs careful consideration of how students are linked to teachers
        # if not through a class. If students always belong to a teacher via their classes,
        # listing students without a class_id might require iterating all teacher's classes.
        # For now, let's assume a direct 'teacher_id' field on student for non-class specific queries
        # or that the current 'teacher_id' param is a Kinde ID and students need to be linked.
        # This part is complex and depends on your data model.
        # THE PREVIOUS IMPLEMENTATION OF get_all_students ADDED teacher_id as a MANDATORY PARAM
        # but it was used as `teacher_kinde_id`. We need to be clear on how students are
        # associated with teachers if not directly by class_id.
        # For now, if no class_id, we fall back to other filters.
        # A direct `students.teacher_id == teacher_kinde_id` might not exist.

        logger.info(f"Filtering students for teacher_kinde_id: {teacher_id} (no class_id provided)")
        # ADD THIS LINE TO FILTER BY THE TEACHER'S KINDE ID
        query["teacher_id"] = teacher_id

        # Fallback to existing filters if no class_id
        if external_student_id:
            query["external_student_id"] = external_student_id
        if first_name:
            # Using regex for case-insensitive partial match
            query["first_name"] = {"$regex": f"^{re.escape(first_name)}", "$options": "i"}
        if last_name:
            query["last_name"] = {"$regex": f"^{re.escape(last_name)}", "$options": "i"}
        if year_group: # Assuming year_group is stored directly on the student
            query["year_group"] = year_group
        
        # If querying without class_id, we need a way to scope to the teacher.
        # This is a placeholder, as the 'teacher_id' field might not exist directly on the Student model
        # or might mean something else (like the Kinde ID of the teacher who created them).
        # This needs to be resolved based on how students are associated with teachers.
        # For now, if no other filters narrow it down, this query might be too broad or incorrect.
        # query["created_by_teacher_kinde_id"] = teacher_id # Example, if such a field exists


    logger.debug(f"Final student query: {query}")
    
    student_docs_from_db = []
    try:
        cursor = collection.find(query, session=session).skip(skip).limit(limit)
        async for doc in cursor:
            student_docs_from_db.append(doc)
    except Exception as e:
        logger.error(f"Error fetching student documents: {e}", exc_info=True)
        return [] # Return empty if fetch fails

    # Fetch all class groups for the current teacher to cross-reference
    # This requires teacher_id (Kinde ID) to be resolved to an internal teacher UUID first
    # then use that internal UUID to fetch class groups.
    teacher_record = await get_teacher_by_kinde_id(kinde_id=teacher_id, session=session)
    teachers_class_groups: List[ClassGroup] = []
    if teacher_record and teacher_record.id:
        teachers_class_groups = await get_all_class_groups(
            teacher_id=teacher_record.id, # Pass internal teacher UUID
            include_deleted=False, 
            limit=1000, # Assuming a teacher won't have more than 1000 active classes
            session=session
        )
    else:
        logger.warning(f"Could not find teacher record for Kinde ID {teacher_id} when trying to populate student class_group_ids.")

    for doc in student_docs_from_db:
        try:
            mapped_doc = doc.copy()
            if "_id" in mapped_doc and "id" not in mapped_doc:
                mapped_doc["id"] = mapped_doc["_id"]
            
            student_actual_id = mapped_doc.get("id") # Should be UUID
            assigned_class_group_ids = []
            if student_actual_id and teachers_class_groups: # student_actual_id needs to be UUID
                for cg in teachers_class_groups:
                    if cg.student_ids and student_actual_id in cg.student_ids: # cg.student_ids contains UUIDs
                        if cg.id: # cg.id is also UUID
                            assigned_class_group_ids.append(cg.id)
            
            mapped_doc["class_group_ids"] = assigned_class_group_ids
            
            students_list.append(Student(**mapped_doc))
        except ValidationError as e:
            logger.error(f"Pydantic validation error for student document {doc.get('_id')}: {e.errors()}", exc_info=True)
        except Exception as e:
            logger.error(f"Error processing student document {doc.get('_id')} after fetch: {e}", exc_info=True)
            
    logger.info(f"Processed {len(students_list)} students with class group ID population.")
    
    return students_list

@with_transaction
async def update_student(student_internal_id: uuid.UUID, teacher_id: str, student_in: StudentUpdate, session=None) -> Optional[Student]:
    collection = _get_collection(STUDENT_COLLECTION); now = datetime.now(timezone.utc)
    if collection is None: return None
    update_data = student_in.model_dump(exclude_unset=True)
    update_data.pop("_id", None); update_data.pop("id", None); update_data.pop("created_at", None); update_data.pop("is_deleted", None)
    if "external_student_id" in update_data and update_data["external_student_id"] == "": update_data["external_student_id"] = None
    if not update_data: 
        logger.warning(f"No update data provided for student {student_internal_id}")
        return await get_student_by_id(student_internal_id, teacher_id=teacher_id, include_deleted=False, session=session)
    update_data["updated_at"] = now; logger.info(f"Updating student {student_internal_id} for teacher {teacher_id}")
    query_filter = {"_id": student_internal_id, "teacher_id": teacher_id, "is_deleted": {"$ne": True}}
    try:
        updated_doc = await collection.find_one_and_update( query_filter, {"$set": update_data}, return_document=ReturnDocument.AFTER, session=session)
        if updated_doc:
            mapped_data = {**updated_doc}
            if "_id" in mapped_data: mapped_data["id"] = mapped_data.pop("_id")
            return Student(**mapped_data)
        else:
            logger.warning(f"Student {student_internal_id} not found or already deleted for update."); return None
    except DuplicateKeyError:
        ext_id = update_data.get('external_student_id')
        logger.warning(f"Duplicate external_student_id on update: '{ext_id}' for student {student_internal_id}")
        return None # Or raise a specific exception
    except Exception as e:
        logger.error(f"Error during student update operation for {student_internal_id}: {e}", exc_info=True); return None

@with_transaction
async def delete_student(student_internal_id: uuid.UUID, teacher_id: str, hard_delete: bool = False, session=None) -> bool:
    collection = _get_collection(STUDENT_COLLECTION)
    if collection is None: return False
    logger.info(f"{'Hard' if hard_delete else 'Soft'} deleting student {student_internal_id} for teacher {teacher_id}")
    count = 0
    query_base = {"_id": student_internal_id, "teacher_id": teacher_id}
    try:
        if hard_delete: 
            result = await collection.delete_one(query_base, session=session)
            count = result.deleted_count
        else:
            now = datetime.now(timezone.utc)
            # For soft delete, also ensure it's not already deleted
            soft_delete_query = {**query_base, "is_deleted": {"$ne": True}}
            result = await collection.update_one(
                soft_delete_query, 
                {"$set": {"is_deleted": True, "updated_at": now}}, session=session
            )
            count = result.modified_count
    except Exception as e: 
        logger.error(f"Error deleting student {student_internal_id} for teacher {teacher_id}: {e}", exc_info=True)
        return False
    if count == 1: 
        logger.info(f"Successfully deleted student {student_internal_id} for teacher {teacher_id}")
        return True
    else: 
        logger.warning(f"Student {student_internal_id} not found for teacher {teacher_id} or already deleted.")
        return False


# --- Document CRUD Functions (Keep existing) ---
# @with_transaction # Keep transaction commented out if needed for collection creation
async def create_document(document_in: DocumentCreate, session=None) -> Optional[Document]:
    collection = _get_collection(DOCUMENT_COLLECTION)
    if collection is None: return None
    document_id = uuid.uuid4()
    now = datetime.now(timezone.utc); doc_dict = document_in.model_dump()
    if isinstance(doc_dict.get("status"), DocumentStatus): doc_dict["status"] = doc_dict["status"].value
    if isinstance(doc_dict.get("file_type"), FileType): doc_dict["file_type"] = doc_dict["file_type"].value
    doc = doc_dict
    # Explicitly add teacher_id from the input model
    if hasattr(document_in, 'teacher_id') and document_in.teacher_id:
        doc["teacher_id"] = document_in.teacher_id
    doc["_id"] = document_id; doc["created_at"] = now; doc["updated_at"] = now; doc["is_deleted"] = False
    logger.info(f"Inserting document metadata: {doc['_id']}")
    try:
        inserted_result = await collection.insert_one(doc, session=session)
        if inserted_result.acknowledged: created_doc = await collection.find_one({"_id": document_id}, session=session)
        else: logger.error(f"Insert document not acknowledged: {document_id}"); return None
        if created_doc: return Document(**created_doc) # Assumes schema handles alias
        else: logger.error(f"Failed retrieve document post-insert: {document_id}"); return None
    except Exception as e: logger.error(f"Error during document insertion: {e}", exc_info=True); return None

async def get_document_by_id(
    document_id: uuid.UUID,
    teacher_id: str, # <<< ADDED: Make teacher_id mandatory
    include_deleted: bool = False,
    session=None
) -> Optional[Document]:
    collection = _get_collection(DOCUMENT_COLLECTION)
    if collection is None: return None
    logger.info(f"Getting document: {document_id} for teacher: {teacher_id}") # Update log
    query = {"_id": document_id, "teacher_id": teacher_id}
    query.update(soft_delete_filter(include_deleted))
    try: doc = await collection.find_one(query, session=session)
    except Exception as e: logger.error(f"Error getting document: {e}", exc_info=True); return None
    if doc: return Document(**doc) # Assumes schema handles alias
    else: logger.warning(f"Document {document_id} not found."); return None

async def get_all_documents(
    teacher_id: str, # <<< This is the Kinde ID
    student_id: Optional[uuid.UUID] = None,
    assignment_id: Optional[uuid.UUID] = None,
    status: Optional[DocumentStatus] = None,
    skip: int = 0,
    limit: int = 100,
    include_deleted: bool = False,
    sort_by: Optional[str] = None, # NEW: Field to sort by (e.g., "upload_timestamp")
    sort_order: int = -1,        # NEW: 1 for asc, -1 for desc (default desc)
    session=None
) -> List[Document]:
    collection = _get_collection(DOCUMENT_COLLECTION)
    student_collection = _get_collection(STUDENT_COLLECTION) # Added for student details
    # teacher_collection = _get_collection(TEACHER_COLLECTION) # For fetching teacher's internal ID

    documents_list: List[Document] = []
    if collection is None or student_collection is None: # Check both collections
        logger.error("Document or Student collection not found for get_all_documents.")
        return documents_list

    # Get the teacher's internal UUID from their Kinde ID
    teacher_internal_uuid: Optional[uuid.UUID] = None
    teacher_record = await get_teacher_by_kinde_id(kinde_id=teacher_id, session=session) # session might be None
    if teacher_record:
        teacher_internal_uuid = teacher_record.id
    else:
        logger.warning(f"Teacher with Kinde ID {teacher_id} not found. Cannot reliably fetch student details by teacher ownership.")
        # Decide if we should return empty or proceed without teacher-based student filtering.
        # For now, proceed, but student_details might be inaccurate if student's teacher_id isn't the Kinde ID.


    query: Dict[str, Any] = {"teacher_id": teacher_id} # Document's teacher_id is Kinde ID
    query.update(soft_delete_filter(include_deleted))

    if student_id: query["student_id"] = student_id
    if assignment_id: query["assignment_id"] = assignment_id
    if status: query["status"] = status.value # Use .value for Enum comparison

    logger.info(f"Getting all documents for teacher {teacher_id} with filters: student_id={student_id}, assignment_id={assignment_id}, status={status}, deleted={include_deleted}, skip={skip}, limit={limit}, sort_by={sort_by}, sort_order={sort_order}")
    
    try:
        cursor = collection.find(query, session=session)
        if sort_by:
            cursor = cursor.sort(sort_by, sort_order)
        cursor = cursor.skip(skip).limit(limit)
        
        async for doc_data in cursor:
            try:
                # --- Populate student_details ---
                student_details_data = None
                if doc_data.get("student_id"):
                    # Student.teacher_id is Kinde ID (based on create_student)
                    # So, we query student_collection using the teacher_id (Kinde ID) from the function arguments.
                    student_query: Dict[str, Any] = {
                        "_id": doc_data["student_id"], 
                        "teacher_id": teacher_id, # Use the Kinde ID of the current teacher
                        "is_deleted": {"$ne": True}
                    }
                    
                    # logger.warning(f"Cannot verify student ownership for student_id {doc_data['student_id']} as teacher internal UUID is unknown.") # No longer relevant with direct Kinde ID usage

                    student_doc = await student_collection.find_one(
                        student_query,
                        session=session
                    )
                    if student_doc:
                        try:
                            # Map _id to id for StudentBasicInfo
                            student_details_data = {"id": student_doc["_id"], "first_name": student_doc["first_name"], "last_name": student_doc["last_name"]}
                        except KeyError as ke:
                            logger.error(f"Missing expected field in student_doc for student_id {doc_data['student_id']}: {ke}")
                            student_details_data = None # Reset if mapping fails
                    else:
                        logger.warning(f"Student details not found for student_id {doc_data['student_id']} linked to doc {doc_data.get('_id')} (queried with teacher Kinde ID: {teacher_id}).")
                
                # --- End Populate student_details ---

                # Prepare document data for Pydantic model, including student_details
                # Ensure Document model is instantiated with student_details
                # doc_data is a dict from MongoDB. We need to pass student_details to the Document constructor.
                
                # Manually construct the dictionary for the Document model
                final_doc_dict_for_model = {**doc_data}
                if student_details_data:
                    final_doc_dict_for_model["student_details"] = student_details_data
                
                documents_list.append(Document(**final_doc_dict_for_model))
            except ValidationError as e_val:
                logger.error(f"Pydantic validation error for document {doc_data.get('_id', 'N/A')}: {e_val}", exc_info=True)
            except Exception as e_doc:
                logger.error(f"Error processing individual document {doc_data.get('_id', 'N/A')} in get_all_documents: {e_doc}", exc_info=True)
    except Exception as e:
        logger.error(f"Error querying documents in get_all_documents: {e}", exc_info=True)
    
    logger.debug(f"get_all_documents returning {len(documents_list)} documents.")
    return documents_list

@with_transaction
async def update_document_status(
    document_id: uuid.UUID,
    teacher_id: str, # ADDED teacher_id for RBAC
    status: DocumentStatus,
    character_count: Optional[int] = None, # New optional parameter
    word_count: Optional[int] = None,      # New optional parameter
    score: Optional[float] = None,         # ADDED: Optional score parameter
    session=None
) -> Optional[Document]:
    collection = _get_collection(DOCUMENT_COLLECTION)
    if collection is None: return None
    now = datetime.now(timezone.utc)
    # <<< START EDIT: Build update_data dictionary >>>
    update_data = {
        "status": status.value, # Store enum value
        "updated_at": now
    }
    if character_count is not None:
        update_data["character_count"] = character_count
        logger.info(f"Including character_count={character_count} in update for document {document_id}")
    if word_count is not None:
        update_data["word_count"] = word_count
        logger.info(f"Including word_count={word_count} in update for document {document_id}")
    
    # ADDED: Log the received score value
    logger.info(f"[crud.update_document_status] Received score: {score} for document {document_id}")

    # ADDED: Detailed log for type and value of score before the 'if score is not None' check
    logger.info(f"[crud.update_document_status] DETAILED CHECK - score value: {repr(score)}, score type: {type(score)} for document {document_id}")

    if score is not None: # ADDED: Include score if provided
        update_data["score"] = score
        logger.info(f"Including score={score} in update for document {document_id}")
    # <<< END EDIT >>>

    logger.info(f"Updating document {document_id} for teacher {teacher_id} status to {status.value} and counts/score if provided. Update payload: {update_data}") # MODIFIED log & added payload
    query_filter = {"_id": document_id, "teacher_id": teacher_id, "is_deleted": {"$ne": True}}

    # <<< START EDIT: Add logging before DB call >>>
    logger.debug(f"Attempting find_one_and_update for doc {document_id} with $set payload: {update_data}")
    # <<< END EDIT >>>

    try:
        # <<< START EDIT: Use update_data dictionary in $set >>> # This comment is from previous edits
        updated_doc = await collection.find_one_and_update(
            query_filter,
            {"$set": update_data}, # Use the built dictionary
            return_document=ReturnDocument.AFTER,
            session=session
        )
        # <<< END EDIT >>>
        if updated_doc: return Document(**updated_doc) # Assumes schema handles alias
        else: logger.warning(f"Document {document_id} not found or already deleted for status/count update."); return None
    except Exception as e: logger.error(f"Error updating document status/counts for ID {document_id}: {e}", exc_info=True); return None

@with_transaction
async def update_document_counts(
    document_id: uuid.UUID,
    teacher_id: str,
    character_count: int,
    word_count: int,
    session=None
) -> Optional[Document]:
    collection = _get_collection(DOCUMENT_COLLECTION)
    if collection is None: return None
    now = datetime.now(timezone.utc)
    update_data = {
        "character_count": character_count,
        "word_count": word_count,
        "updated_at": now
    }
    logger.info(f"Updating document {document_id} for teacher {teacher_id} with char_count={character_count}, word_count={word_count}")
    query_filter = {"_id": document_id, "teacher_id": teacher_id, "is_deleted": {"$ne": True}}
    try:
        updated_doc = await collection.find_one_and_update(
            query_filter,
            {"$set": update_data},
            return_document=ReturnDocument.AFTER,
            session=session
        )
        if updated_doc: return Document(**updated_doc)
        else: logger.warning(f"Document {document_id} not found or already deleted for count update."); return None
    except Exception as e: logger.error(f"Error updating document counts for ID {document_id}: {e}", exc_info=True); return None

@with_transaction # Add decorator back
async def delete_document(document_id: uuid.UUID, teacher_id: str, session=None) -> Tuple[bool, Optional[str]]: # Add session back, change return type
    doc_collection = _get_collection(DOCUMENT_COLLECTION)
    if doc_collection is None:
        logger.error(f"Document collection not found when trying to delete document {document_id}")
        return False, None

    logger.info(f"Attempting to soft-delete document {document_id} by teacher {teacher_id} (session: {'provided' if session else 'None'})")

    # 1. Fetch the document to get blob_path and verify ownership, ensuring it's not already deleted.
    # Uses the session from the decorator.
    doc_to_delete = await doc_collection.find_one(
        {"_id": document_id, "teacher_id": teacher_id, "is_deleted": {"$ne": True}},
        session=session
    )

    if not doc_to_delete:
        logger.warning(f"Document {document_id} not found for teacher {teacher_id}, or already soft-deleted.")
        # To check if it was not found vs already deleted, one could do another query without is_deleted filter.
        # For now, if it's not an active document we can operate on, we indicate failure to perform a *new* delete.
        return False, None

    blob_path_to_delete = doc_to_delete.get("storage_blob_path")

    # 2. Soft-delete the Document record using the session from the decorator.
    now = datetime.now(timezone.utc)
    try:
        update_doc_result = await doc_collection.update_one(
            {"_id": document_id, "teacher_id": teacher_id, "is_deleted": {"$ne": True}}, # Ensure it's still active
            {"$set": {"is_deleted": True, "updated_at": now, "status": DocumentStatus.DELETED.value}},
            session=session
        )

        if update_doc_result.modified_count == 0:
            # This could happen if the document was deleted by another process between the find_one and update_one.
            logger.warning(f"Soft-delete failed for document {document_id} (modified_count is 0). It might have been deleted by another process. Blob path if found: {blob_path_to_delete}")
            # Return False, but still provide blob_path for potential cleanup by caller if doc was initially found.
            return False, blob_path_to_delete
        
        logger.info(f"Successfully soft-deleted document {document_id}. Blob path: {blob_path_to_delete}")
        return True, blob_path_to_delete

    except PyMongoError as e:
        logger.error(f"PyMongoError during document soft-deletion for {document_id} within transaction: {e}", exc_info=True)
        return False, blob_path_to_delete # Return blob_path if known, even on DB error
    except Exception as e:
        logger.error(f"Unexpected error during document soft-deletion for {document_id} within transaction: {e}", exc_info=True)
        return False, blob_path_to_delete # Return blob_path if known, even on DB error

@with_transaction
async def update_document_student_id(
    document_id: uuid.UUID,
    student_id: uuid.UUID,
    teacher_id: str, # For RBAC, ensuring the teacher owns the document
    session=None
) -> Optional[Document]:
    collection = _get_collection(DOCUMENT_COLLECTION)
    if collection is None:
        logger.error(f"Document collection not found while trying to update student_id for doc {document_id}")
        return None

    now = datetime.now(timezone.utc)
    update_data = {
        "student_id": student_id,
        "updated_at": now
    }

    logger.info(f"Attempting to update student_id to {student_id} for document {document_id} by teacher {teacher_id}")

    # Ensure the document exists, is not deleted, and belongs to the teacher
    query_filter = {
        "_id": document_id,
        "teacher_id": teacher_id,
        "is_deleted": {"$ne": True}
    }

    try:
        updated_doc = await collection.find_one_and_update(
            query_filter,
            {"$set": update_data},
            return_document=ReturnDocument.AFTER,
            session=session
        )
        if updated_doc:
            logger.info(f"Successfully updated student_id for document {document_id} to {student_id}.")
            return Document(**updated_doc)
        else:
            logger.warning(f"Document {document_id} not found, not owned by teacher {teacher_id}, or already deleted. Could not update student_id.")
            return None
    except Exception as e:
        logger.error(f"Error updating student_id for document {document_id}: {e}", exc_info=True)
        return None


# --- Result CRUD Functions ---
async def get_result_by_document_id(document_id: uuid.UUID, teacher_id: Optional[str] = None, include_deleted: bool = False, session=None) -> Optional[Result]:
    collection = _get_collection(RESULT_COLLECTION)
    if collection is None: return None

    query = {"document_id": document_id}
    if teacher_id:
        query["teacher_id"] = teacher_id
        logger.info(f"Getting result for document: {document_id} and teacher: {teacher_id}")
    else:
        logger.info(f"Getting result for document: {document_id}")
    
    query.update(soft_delete_filter(include_deleted))
    logger.debug(f"Executing find_one for result by document_id with query: {query}")
    try:
        result_doc = await collection.find_one(query, session=session)
        if result_doc:
            logger.debug(f"Raw result doc from DB by document_id: {result_doc}")
            return Result(**result_doc)
        else:
            logger.warning(f"Result not found for document: {document_id} with current filters.")
            return None
    except Exception as e:
        logger.error(f"Error getting result by document_id {document_id}: {e}", exc_info=True)
        return None

@with_transaction
async def update_result_status(
    result_id: uuid.UUID,
    status: ResultStatus,
    teacher_id: str, # Kinde ID for ownership check
    score: Optional[float] = None,
    label: Optional[str] = None, # MODIFIED: Changed from overall_assessment to label
    ai_generated: Optional[bool] = None,
    human_generated: Optional[bool] = None,
    paragraph_results: Optional[List[Any]] = None, # MODIFIED: Type hint to List[Any] to accept models or dicts initially
    error_message: Optional[str] = None,
    raw_response: Optional[Dict[str, Any]] = None, 
    session=None
) -> Optional[Result]:
    collection = _get_collection(RESULT_COLLECTION)
    if collection is None:
        logger.error(f"Result collection (\'{RESULT_COLLECTION}\') not found.")
        return None

    now = datetime.now(timezone.utc)
    update_payload: Dict[str, Any] = {"updated_at": now}

    # Explicitly add fields to update_payload if they are provided
    if status is not None: # Status is mandatory, but good practice
        update_payload["status"] = status.value # Ensure enum value is used
    
    if score is not None:
        update_payload["score"] = score
    
    # Use 'label' as per the Result model, not 'overall_assessment' for the main label
    if label is not None:
        update_payload["label"] = label
    
    if ai_generated is not None:
        update_payload["ai_generated"] = ai_generated
        
    if human_generated is not None:
        update_payload["human_generated"] = human_generated

    if paragraph_results is not None:
        # Convert list of ParagraphResult models to list of dicts
        # This uses .model_dump() available on Pydantic V2 models
        update_payload["paragraph_results"] = [
            p.model_dump(mode='json') if hasattr(p, 'model_dump') else p 
            for p in paragraph_results
        ]
        logger.debug(f"Paragraph results being prepared for DB: {update_payload['paragraph_results']}")


    if error_message is not None:
        update_payload["error_message"] = error_message
        # If there's an error, it's common to also clear fields that might be misleading
        update_payload["score"] = None 
        update_payload["label"] = "ERROR" # Or use the specific error status if appropriate
        update_payload["ai_generated"] = None
        update_payload["human_generated"] = None
        # update_payload["paragraph_results"] = [] # Optionally clear paragraph results on error

    if raw_response is not None:
        update_payload["raw_response"] = raw_response

    # Always update result_timestamp when this function is called
    update_payload["result_timestamp"] = now
    
    logger.info(f"[update_result_status] Attempting to update result {result_id} for teacher {teacher_id} to status {status.value if status else 'N/A'}. Payload: { {k: v for k, v in update_payload.items() if k != 'paragraph_results'} }") # Log payload excluding potentially large paragraph_results

    try:
        updated_doc = await collection.find_one_and_update(
            {"_id": result_id, "teacher_id": teacher_id, "is_deleted": {"$ne": True}}, # Ensure teacher owns the result and it's not deleted
            {"$set": update_payload},
            return_document=ReturnDocument.AFTER,
            session=session
        )
        if updated_doc:
            logger.info(f"[update_result_status] Successfully updated result {result_id} to status {status.value if status else 'N/A'}.")
            return Result(**updated_doc)
        else:
            logger.warning(f"[update_result_status] Result {result_id} not found or not owned by teacher {teacher_id}, or already deleted. No update performed.")
            return None
    except DuplicateKeyError as e: # Should not happen on update unless changing an indexed field to a duplicate
        logger.error(f"[update_result_status] Duplicate key error for result {result_id}: {e}", exc_info=True)
        return None
    except PyMongoError as e: # Catch other MongoDB-related errors
        logger.error(f"[update_result_status] MongoDB error updating result {result_id}: {e}", exc_info=True)
        # This will be caught by @with_transaction if it's a transactional error
        raise # Re-raise to be handled by transaction decorator or calling function
    except ValidationError as e: # Pydantic validation error on return
        logger.error(f"[update_result_status] Pydantic validation error for updated result {result_id}: {e}", exc_info=True)
        return None # Or raise, depending on desired error handling
    except Exception as e: # Catch any other unexpected errors
        logger.error(f"[update_result_status] Unexpected error updating result {result_id}: {e}", exc_info=True)
        raise # Re-raise to be handled by transaction decorator or calling function

async def get_dashboard_stats(current_user_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate dashboard statistics for the given teacher based on Kinde payload.
    Finds the internal teacher ID first.
    """
    teacher_kinde_id = current_user_payload.get("sub")
    # Restored default_stats to include all fields
    default_stats = {'current_documents': 0, 'deleted_documents': 0, 'total_processed_documents': 0, 'avgScore': None, 'flaggedRecent': 0, 'pending': 0}
    if not teacher_kinde_id:
        logger.warning("get_dashboard_stats called without teacher Kinde ID (sub) in payload.")
        return default_stats

    logger.info(f"Calculating dashboard stats for teacher kinde_id: {teacher_kinde_id}")

    try:
        teacher = await get_teacher_by_kinde_id(teacher_kinde_id)
        if not teacher:
            logger.warning(f"No teacher found in DB for kinde_id: {teacher_kinde_id}")
            return default_stats

        # teacher_internal_id = teacher.id # Not strictly needed if queries use teacher_kinde_id
        # logger.debug(f"Found internal teacher id: {teacher_internal_id} for kinde_id: {teacher_kinde_id}")

        docs_collection = _get_collection(DOCUMENT_COLLECTION)
        results_collection = _get_collection(RESULT_COLLECTION)
        
        if docs_collection is None or results_collection is None:
            logger.error("Could not get documents or results collection for dashboard stats.")
            return default_stats

        # RESTORED: Document count calculations
        active_documents_query = {"teacher_id": teacher_kinde_id, "is_deleted": {"$ne": True}}
        deleted_documents_query = {"teacher_id": teacher_kinde_id, "is_deleted": True}

        current_documents_count = await docs_collection.count_documents(active_documents_query)
        deleted_documents_count = await docs_collection.count_documents(deleted_documents_query)
        total_processed_documents_count = current_documents_count + deleted_documents_count

        logger.debug(f"[Stats] Current documents: {current_documents_count}")
        logger.debug(f"[Stats] Deleted documents: {deleted_documents_count}")
        logger.debug(f"[Stats] Total processed documents: {total_processed_documents_count}")

        # Get IDs of active documents for filtering results
        active_doc_ids_cursor = docs_collection.find(active_documents_query, {"_id": 1}) # Use pre-defined active_documents_query
        active_document_ids = [doc["_id"] async for doc in active_doc_ids_cursor]

        avg_score_pipeline = [
            {"$match": {
                "teacher_id": teacher_kinde_id, 
                "status": ResultStatus.COMPLETED.value, 
                "score": {"$ne": None},
                "document_id": {"$in": active_document_ids} 
            }},
            {"$group": {"_id": None, "avgScore": {"$avg": "$score"}}}
        ]
        avg_score_result = await results_collection.aggregate(avg_score_pipeline).to_list(length=1)
        avg_score = avg_score_result[0]['avgScore'] if avg_score_result else None
        logger.debug(f"[Stats] Avg score query result (for active docs): {avg_score}")

        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        flagged_recent_pipeline = [
            {"$match": {
                "teacher_id": teacher_kinde_id,
                "status": ResultStatus.COMPLETED.value,
                "score": {"$gte": 0.8},
                "updated_at": {"$gte": seven_days_ago},
                "document_id": {"$in": active_document_ids}
            }},
            {"$count": "count"}
        ]
        flagged_recent_result = await results_collection.aggregate(flagged_recent_pipeline).to_list(length=1)
        flagged_recent = flagged_recent_result[0]['count'] if flagged_recent_result else 0
        logger.debug(f"[Stats] Flagged recent query result (for active docs): {flagged_recent}")

        pending_statuses = [
            DocumentStatus.QUEUED.value,
            DocumentStatus.PROCESSING.value,
            DocumentStatus.RETRYING.value,
        ]
        pending = await docs_collection.count_documents({"teacher_id": teacher_kinde_id, "status": {"$in": pending_statuses}, "is_deleted": {"$ne": True}})
        logger.debug(f"[Stats] Pending query result: {pending}")

        stats = {
            # RESTORED: current_documents, deleted_documents, total_processed_documents
            'current_documents': current_documents_count,
            'deleted_documents': deleted_documents_count,
            'total_processed_documents': total_processed_documents_count,
            'avgScore': avg_score,
            'flaggedRecent': flagged_recent,
            'pending': pending
        }
        logger.info(f"Dashboard stats calculated for teacher {teacher_kinde_id}: {stats}")
        return stats

    except Exception as e:
        logger.error(f"Error calculating dashboard stats for teacher {teacher_kinde_id}: {str(e)}", exc_info=True)
        return default_stats

async def get_score_distribution(current_user_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate the distribution of document scores for the given teacher based on Kinde payload.
    Finds the internal teacher ID first.
    """
    teacher_kinde_id = current_user_payload.get("sub")
    if not teacher_kinde_id:
        logger.warning("get_score_distribution called without teacher Kinde ID (sub) in payload.")
        return {"distribution": []}

    # +++ ADDED Logging +++
    logger.info(f"Calculating score distribution for teacher kinde_id: {teacher_kinde_id}")
    # --- END Logging ---

    try:
        # 1. Find the internal teacher ObjectId using the Kinde ID (Optional - could query results directly)
        # teacher = await get_teacher_by_kinde_id(teacher_kinde_id)
        # if not teacher:
        #     logger.warning(f"No teacher found in DB for kinde_id: {teacher_kinde_id} for score distribution")
        #     return {"distribution": []}
        # teacher_internal_id = teacher.id
        # logger.debug(f"Found internal teacher id: {teacher_internal_id} for score distribution calculation")

        # 2. Get Results Collection
        results_collection = _get_collection(RESULT_COLLECTION)
        # FIX: Explicitly check against None
        if results_collection is None:
            logger.error("Could not get results collection for score distribution.")
            return {"distribution": []}

        # 3. Define Score Ranges and Aggregation Pipeline
        # Use teacher_kinde_id as it exists on the result document
        pipeline = [
            {
                "$match": {
                    "teacher_id": teacher_kinde_id,
                    "status": ResultStatus.COMPLETED.value,
                    "score": {"$ne": None} # Exclude documents without a score
                }
            },
            # --- START REPLACEMENT: Use $facet instead of $bucket ---
            {
                "$facet": {
                    "0-20": [
                        { "$match": { "score": { "$gte": 0, "$lte": 0.2 } } },
                        { "$count": "count" }
                    ],
                    "21-40": [
                        { "$match": { "score": { "$gt": 0.2, "$lte": 0.4 } } },
                        { "$count": "count" }
                    ],
                    "41-60": [
                        { "$match": { "score": { "$gt": 0.4, "$lte": 0.6 } } },
                        { "$count": "count" }
                    ],
                    "61-80": [
                        { "$match": { "score": { "$gt": 0.6, "$lte": 0.8 } } },
                        { "$count": "count" }
                    ],
                    "81-100": [
                        { "$match": { "score": { "$gt": 0.8, "$lte": 1.0 } } }, # Adjusted range slightly for edge cases
                        { "$count": "count" }
                    ]
                }
            },
            # Reshape the $facet output to the desired format [{range: "...", count: ...}]
            {
                "$project": {
                    "distribution": [
                        { "range": "0-20", "count": { "$ifNull": [ { "$arrayElemAt": ["$0-20.count", 0] }, 0 ] } },
                        { "range": "21-40", "count": { "$ifNull": [ { "$arrayElemAt": ["$21-40.count", 0] }, 0 ] } },
                        { "range": "41-60", "count": { "$ifNull": [ { "$arrayElemAt": ["$41-60.count", 0] }, 0 ] } },
                        { "range": "61-80", "count": { "$ifNull": [ { "$arrayElemAt": ["$61-80.count", 0] }, 0 ] } },
                        { "range": "81-100", "count": { "$ifNull": [ { "$arrayElemAt": ["$81-100.count", 0] }, 0 ] } }
                    ]
                }
            },
            # Extract the distribution array from the single document result
            {
                "$unwind": "$distribution"
            },
            {
                "$replaceRoot": { "newRoot": "$distribution" }
            }
            # --- END REPLACEMENT ---
        ]

        # +++ ADDED Logging +++
        logger.debug(f"Score distribution pipeline for {teacher_kinde_id}: {pipeline}")
        # --- END Logging ---

        aggregation_result = await results_collection.aggregate(pipeline).to_list(None)

        # +++ ADDED Logging +++
        logger.debug(f"Raw aggregation result for score distribution: {aggregation_result}")
        # --- END Logging ---

        # 4. Format results, ensuring all ranges are present
        # The new pipeline directly outputs the desired format, so mapping is simplified
        # If the aggregation returns nothing (e.g., no results found), aggregation_result will be empty
        final_distribution = aggregation_result if aggregation_result else [
            {"range": "0-20", "count": 0},
            {"range": "21-40", "count": 0},
            {"range": "41-60", "count": 0},
            {"range": "61-80", "count": 0},
            {"range": "81-100", "count": 0}
        ]

        # +++ ADDED Logging +++
        logger.info(f"Final score distribution for teacher {teacher_kinde_id}: {final_distribution}")
        # --- END Logging ---

        return {"distribution": final_distribution}

    except Exception as e:
        logger.error(f"Error calculating score distribution for teacher {teacher_kinde_id}: {str(e)}", exc_info=True)
        return {"distribution": []} # Return empty on error


async def get_recent_documents(teacher_id: str, limit: int = 4) -> List[Document]:
    """
    Get the most recent documents for a teacher using their Kinde ID.
    The 'score' attribute will be populated from the associated Result object.
    Args:
        teacher_id: The teacher's Kinde ID string.
        limit: Maximum number of documents to return.
    Returns:
        List of Document objects, with 'score' populated if available.
    """
    logger.info(f"Fetching recent documents for teacher_id: {teacher_id}, limit: {limit}")
    try:
        docs_collection = _get_collection(DOCUMENT_COLLECTION)
        if docs_collection is None:
            logger.error("Could not get documents collection for recent documents.")
            return []

        cursor = docs_collection.find(
            {
                "teacher_id": teacher_id,
                "is_deleted": {"$ne": True} 
            }
        ).sort([("upload_timestamp", -1)]).limit(limit)

        docs_data = await cursor.to_list(length=limit)
        logger.debug(f"Found {len(docs_data)} raw documents for teacher {teacher_id}.")
        if docs_data:
            logger.debug(f"First raw doc example: {docs_data[0]}")

        documents_list = []
        for doc_data in docs_data:
            try:
                doc_id = doc_data.get('_id')
                doc_data['id'] = doc_id # Ensure 'id' field is populated for the Document model

                # Create Document object first (it might not have a score initially)
                document_obj = Document(**doc_data)

                # Attempt to fetch the result and update the score
                if doc_id:
                    result = await get_result_by_document_id(document_id=doc_id, teacher_id=teacher_id)
                    if result and result.score is not None:
                        document_obj.score = result.score
                        logger.debug(f"Updated score for document {doc_id} to {result.score}")
                    elif result:
                        logger.debug(f"Result found for document {doc_id}, but score is None.")
                    else:
                        logger.debug(f"No result found for document {doc_id}.")
                
                documents_list.append(document_obj)
            except ValidationError as ve:
                logger.warning(f"Validation error converting document {doc_data.get('_id', 'N/A')} to model: {ve}")
            except Exception as model_ex:
                 logger.error(f"Error processing document {doc_data.get('_id', 'N/A')}: {model_ex}")
        
        logger.info(f"Returning {len(documents_list)} Document objects with scores (if available) for teacher {teacher_id}.")
        return documents_list
    except Exception as e:
        logger.error(f"Error fetching recent documents for teacher {teacher_id}: {str(e)}", exc_info=True)
        return []

# --- Bulk Operations (Keep existing) ---
@with_transaction
async def bulk_create_schools(schools_in: List[SchoolCreate], session=None) -> List[School]:
    collection = _get_collection(SCHOOL_COLLECTION)
    if collection is None: return []
    now = datetime.now(timezone.utc); school_docs = []; created_schools = []; inserted_ids = []
    for school_in in schools_in:
        school_id = uuid.uuid4(); school_doc = school_in.model_dump()
        school_doc["_id"] = school_id; school_doc["created_at"] = now; school_doc["updated_at"] = now; school_doc["is_deleted"] = False
        school_docs.append(school_doc)
    try:
        result = await collection.insert_many(school_docs, session=session)
        if result.acknowledged:
            inserted_ids = result.inserted_ids
            if inserted_ids:
                cursor = collection.find({"_id": {"$in": inserted_ids}}, session=session)
                async for doc in cursor: created_schools.append(School(**doc)) # Assumes schema handles alias
            logger.info(f"Successfully created {len(created_schools)} schools"); return created_schools
        else: logger.error("Bulk school creation insert_many not acknowledged."); return []
    except Exception as e: logger.error(f"Error during bulk school creation: {e}", exc_info=True); return []

@with_transaction
async def bulk_update_schools(updates: List[Dict[str, Any]], session=None) -> List[School]:
    collection = _get_collection(SCHOOL_COLLECTION)
    if collection is None: return []
    now = datetime.now(timezone.utc); updated_schools = []
    try:
        for update_item in updates:
            school_id = update_item.get("id"); update_model_data = update_item.get("data")
            if not isinstance(school_id, uuid.UUID) or not isinstance(update_model_data, dict):
                logger.warning(f"Skipping invalid item in bulk update: id={school_id}, data_type={type(update_model_data)}")
                continue
            try: update_model = SchoolUpdate.model_validate(update_model_data)
            except Exception as validation_err: logger.warning(f"Skipping item due to validation error for school {school_id}: {validation_err}"); continue

            update_doc = update_model.model_dump(exclude_unset=True)
            update_doc.pop("_id", None); update_doc.pop("id", None); update_doc.pop("created_at", None); update_doc.pop("is_deleted", None)
            if not update_doc: continue
            update_doc["updated_at"] = now
            result = await collection.find_one_and_update(
                {"_id": school_id, "is_deleted": {"$ne": True}}, {"$set": update_doc}, # Query by _id
                return_document=ReturnDocument.AFTER, session=session )
            if result: updated_schools.append(School(**result)) # Assumes schema handles alias
            else: logger.warning(f"School {school_id} not found/deleted during bulk update.")
        logger.info(f"Successfully updated {len(updated_schools)} schools"); return updated_schools
    except Exception as e: logger.error(f"Error during bulk school update: {e}", exc_info=True); return []

@with_transaction
async def bulk_delete_schools(school_ids: List[uuid.UUID], hard_delete: bool = False, session=None) -> int:
    collection = _get_collection(SCHOOL_COLLECTION)
    if collection is None or not school_ids: return 0
    deleted_count = 0
    try:
        if hard_delete: result = await collection.delete_many( {"_id": {"$in": school_ids}}, session=session); deleted_count = result.deleted_count # Query by _id
        else:
            result = await collection.update_many(
                {"_id": {"$in": school_ids}, "is_deleted": {"$ne": True}},
                {"$set": {"is_deleted": True, "updated_at": datetime.now(timezone.utc)}},
                session=session
            ); deleted_count = result.modified_count # Query by _id
        logger.info(f"Successfully {'hard' if hard_delete else 'soft'} deleted {deleted_count} schools"); return deleted_count
    except Exception as e: logger.error(f"Error during bulk school deletion: {e}", exc_info=True); return 0

# --- Advanced Filtering Support (Keep existing) ---
class FilterOperator:
    EQUALS = "$eq"; NOT_EQUALS = "$ne"; GREATER_THAN = "$gt"; LESS_THAN = "$lt"
    GREATER_THAN_EQUALS = "$gte"; LESS_THAN_EQUALS = "$lte"; IN = "$in"; NOT_IN = "$nin"
    EXISTS = "$exists"; REGEX = "$regex"; TEXT = "$text"; SEARCH = "$search" # Added $search for $text
    # Common operators used with $regex
    OPTIONS = "$options"
    # Geospatial operators (add if needed, for now an example)
    # NEAR = "$near"; GEO_WITHIN = "$geoWithin"
    # Array operators
    ALL = "$all"; ELEM_MATCH = "$elemMatch"; SIZE = "$size"

# Whitelist of allowed $-prefixed operators
ALLOWED_MONGO_OPERATORS = {
    FilterOperator.EQUALS, FilterOperator.NOT_EQUALS, FilterOperator.GREATER_THAN, 
    FilterOperator.LESS_THAN, FilterOperator.GREATER_THAN_EQUALS, FilterOperator.LESS_THAN_EQUALS,
    FilterOperator.IN, FilterOperator.NOT_IN, FilterOperator.EXISTS, FilterOperator.REGEX,
    FilterOperator.TEXT, FilterOperator.SEARCH, FilterOperator.OPTIONS,
    FilterOperator.ALL, FilterOperator.ELEM_MATCH, FilterOperator.SIZE,
    # Add any other specific, safe operators you intend to use.
    # Logical operators that combine expressions (their values will be recursively checked)
    "$and", "$or", "$not", "$nor"
}

def _validate_and_sanitize_filter_part(filter_part: Any) -> Any:
    """Recursively validates and sanitizes a part of the filter query."""
    if isinstance(filter_part, dict):
        sanitized_dict = {}
        for key, value in filter_part.items():
            if isinstance(key, str) and key.startswith('$'):
                if key not in ALLOWED_MONGO_OPERATORS:
                    logger.warning(f"Disallowed MongoDB operator '{key}' found in filter. Ignoring this part: {key}: {value}")
                    # Option 1: Skip this invalid operator
                    continue 
                    # Option 2: Raise an error
                    # raise ValueError(f"Disallowed MongoDB operator '{key}' found in filter.")
                # If the operator is allowed, sanitize its value recursively
                sanitized_dict[key] = _validate_and_sanitize_filter_part(value)
            else:
                # Regular field name, sanitize its value recursively
                sanitized_dict[key] = _validate_and_sanitize_filter_part(value)
        return sanitized_dict
    elif isinstance(filter_part, list):
        # For lists (e.g., in $and, $or, $in clauses), sanitize each item
        return [_validate_and_sanitize_filter_part(item) for item in filter_part]
    else:
        # Primitive value, return as is
        return filter_part

def build_filter_query(filters: Dict[str, Any], include_deleted: bool = False) -> Dict[str, Any]:
    """
    Builds a MongoDB filter query from a dictionary of filters, ensuring only whitelisted
    $-prefixed operators are used.
    Applies soft delete filtering unless include_deleted is True.
    """
    query = {}
    if filters:
        # Validate and sanitize the user-provided filters first
        sanitized_filters = _validate_and_sanitize_filter_part(filters.copy()) # Work on a copy
        query.update(sanitized_filters)
    
    # Apply soft delete filter - this is trusted internal logic, no need to sanitize its structure here
    # as it's constructed with known safe operators ($ne).
    soft_delete_part = soft_delete_filter(include_deleted)
    
    # Merge the sanitized filters with the soft delete part.
    # If there are overlapping keys (e.g., user tries to filter on 'is_deleted'),
    # the soft_delete_part should ideally take precedence for safety unless explicitly handled.
    # A simple update might be okay if client-side 'is_deleted' filters are not expected
    # or are also sanitized through _validate_and_sanitize_filter_part.
    
    # If sanitized_filters already contains 'is_deleted', we need to decide strategy.
    # For now, let's assume soft_delete_filter is paramount for non-deleted items.
    if not include_deleted:
        # Ensure our soft delete logic is applied correctly, possibly overriding user input for is_deleted
        if 'is_deleted' in query and query['is_deleted'] != soft_delete_part['is_deleted']:
            logger.warning(
                f"User filter for \'is_deleted\': {query['is_deleted']} conflicts with soft delete logic. "
                f"Prioritizing soft delete: {soft_delete_part['is_deleted']}"
            )
        query.update(soft_delete_part) # This will enforce is_deleted: {"$ne": True}
    elif 'is_deleted' not in query and include_deleted: # if explicitly asking for all and no filter on is_deleted
        pass # No specific is_deleted filter, so all documents (deleted or not) are implicitly included by query

    logger.debug(f"Constructed filter query: {query}")
    return query

# Example Usage (for testing):
# safe_filters = {"name": "test", "age": {"$gt": 20, "$lt": {"$numberInt": "30"} }, "tags": {"$in": ["A", "B"]}, "status": {"$exists": True}}
# unsafe_filters = {"name": {"$where": "this.credits == this.debits"}, "age": {"$gt": 20} }
# print(build_filter_query(safe_filters))
# try:
#     print(build_filter_query(unsafe_filters))
# except ValueError as e:
#     print(e)

async def validate_school_teacher_relationship( school_id: uuid.UUID, teacher_id: uuid.UUID, session=None) -> bool:
    teacher = await get_teacher_by_kinde_id(kinde_id=str(teacher_id), include_deleted=False, session=session) # Assuming teacher_id is Kinde ID string
    # Adjust based on how teacher ID is stored/passed
    return teacher is not None and teacher.school_id == school_id # Ensure teacher is not None

async def validate_class_group_relationships( class_group_id: uuid.UUID, teacher_id: uuid.UUID, school_id: uuid.UUID, session=None) -> bool:
    class_group = await get_class_group_by_id(class_group_id, include_deleted=False, session=session)
    if class_group is None: return False
    # Assuming teacher_id passed is the internal UUID (_id) stored in ClassGroup
    # If teacher_id passed is Kinde ID, fetch teacher by Kinde ID first
    # teacher = await get_teacher_by_kinde_id(kinde_id=str(teacher_id), session=session)
    # if teacher is None: return False
    # if not await validate_school_teacher_relationship(school_id, teacher.id, session=session): return False # Validate using internal teacher ID
    # For now, assume teacher_id is the internal UUID
    if not await validate_school_teacher_relationship(school_id, teacher_id, session=session): return False
    return (class_group.teacher_id == teacher_id and class_group.school_id == school_id)

async def validate_student_class_group_relationship( student_id: uuid.UUID, class_group_id: uuid.UUID, session=None) -> bool:
    class_group = await get_class_group_by_id(class_group_id, include_deleted=False, session=session)
    # Ensure class_group.student_ids exists and is a list before checking 'in'
    return class_group is not None and isinstance(class_group.student_ids, list) and student_id in class_group.student_ids

# --- Enhanced Query Functions (Keep existing) ---
async def get_schools_with_filters(
    filters: Dict[str, Any], include_deleted: bool = False, skip: int = 0,
    limit: int = 100, sort_by: Optional[str] = None, sort_order: int = 1, session=None
) -> List[School]:
    collection = _get_collection(SCHOOL_COLLECTION)
    if collection is None: return []
    query = build_filter_query(filters, include_deleted)
    sort_field = "_id" if sort_by == "id" else sort_by
    sort_criteria = [(sort_field, sort_order)] if sort_field else None; schools = []
    try:
        cursor = collection.find(query, session=session)
        if sort_criteria: cursor = cursor.sort(sort_criteria)
        cursor = cursor.skip(skip).limit(limit)
        async for doc in cursor:
            try:
                mapped_data = {**doc}
                if "_id" in mapped_data: mapped_data["id"] = mapped_data.pop("_id")
                schools.append(School(**mapped_data))
            except Exception as validation_err: logger.error(f"Pydantic validation failed for school doc {doc.get('_id', 'UNKNOWN')}: {validation_err}")
        logger.info(f"Retrieved {len(schools)} schools with filters")
        return schools
    except Exception as e: logger.error(f"Error retrieving schools with filters: {e}", exc_info=True); return []

async def get_teachers_by_school(
    school_id: uuid.UUID, include_deleted: bool = False, skip: int = 0,
    limit: int = 100, session=None
) -> List[Teacher]:
    collection = _get_collection(TEACHER_COLLECTION)
    if collection is None: return []
    query = {"school_id": school_id}; query.update(soft_delete_filter(include_deleted))
    teachers = []
    try:
        cursor = collection.find(query, session=session).skip(skip).limit(limit)
        async for doc in cursor:
            try:
                mapped_data = {**doc}
                if "_id" in mapped_data: mapped_data["id"] = mapped_data.pop("_id")
                teachers.append(Teacher(**mapped_data))
            except Exception as validation_err: logger.error(f"Pydantic validation failed for teacher doc {doc.get('_id', 'UNKNOWN')}: {validation_err}")
        logger.info(f"Retrieved {len(teachers)} teachers for school {school_id}")
        return teachers
    except Exception as e: logger.error(f"Error retrieving teachers by school: {e}", exc_info=True); return []

# --- Final Placeholder ---
# (All core entities now have basic CRUD with consistent pattern, applied explicit _id->id mapping for list returns)

# === Batch Operations ===

async def create_batch(*, batch_in: BatchCreate) -> Optional[Batch]:
    """Create a new batch record."""
    collection = _get_collection("batches")
    if collection is None:
        logger.error("Failed to get batches collection")
        return None

    try:
        batch_dict = batch_in.dict()
        batch_dict["_id"] = uuid.uuid4()  # Generate new UUID for the batch
        batch_dict["created_at"] = datetime.now(timezone.utc)
        batch_dict["updated_at"] = batch_dict["created_at"]
        
        result = await collection.insert_one(batch_dict)
        if result.inserted_id:
            return await get_batch_by_id(batch_id=batch_dict["_id"])
        return None
    except Exception as e:
        logger.error(f"Error creating batch: {e}")
        return None

async def get_batch_by_id(*, batch_id: uuid.UUID) -> Optional[Batch]:
    """Get a batch by its ID."""
    collection = _get_collection("batches")
    if collection is None:
        logger.error("Failed to get batches collection")
        return None

    try:
        batch_dict = await collection.find_one({"_id": batch_id})
        if batch_dict:
            return Batch(**batch_dict)
        return None
    except Exception as e:
        logger.error(f"Error getting batch {batch_id}: {e}")
        return None

async def update_batch(*, batch_id: uuid.UUID, batch_in: BatchUpdate) -> Optional[Batch]:
    """Update a batch record."""
    collection = _get_collection("batches")
    if collection is None:
        logger.error("Failed to get batches collection")
        return None

    try:
        update_data = batch_in.dict(exclude_unset=True)
        if not update_data:
            return await get_batch_by_id(batch_id=batch_id)
        
        update_data["updated_at"] = datetime.now(timezone.utc)
        
        result = await collection.update_one(
            {"_id": batch_id},
            {"$set": update_data}
        )
        
        if result.modified_count:
            return await get_batch_by_id(batch_id=batch_id)
        return None
    except Exception as e:
        logger.error(f"Error updating batch {batch_id}: {e}")
        return None

async def get_documents_by_batch_id(*, batch_id: uuid.UUID) -> List[Document]:
    """Get all documents in a batch."""
    collection = _get_collection(DOCUMENT_COLLECTION)
    if collection is None:
        logger.error("Failed to get documents collection")
        return []

    try:
        cursor = collection.find({"batch_id": batch_id})
        documents = []
        async for doc in cursor:
            documents.append(Document(**doc))
        return documents
    except Exception as e:
        logger.error(f"Error getting documents for batch {batch_id}: {e}")
        return []

async def get_batch_status_summary(*, batch_id: uuid.UUID) -> dict:
    """Get a summary of document statuses in a batch."""
    collection = _get_collection(DOCUMENT_COLLECTION)
    if collection is None:
        logger.error("Failed to get documents collection")
        return {}

    try:
        pipeline = [
            {"$match": {"batch_id": batch_id}},
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1}
                }
            }
        ]
        
        cursor = collection.aggregate(pipeline)
        status_counts = {}
        async for result in cursor:
            status_counts[result["_id"]] = result["count"]
        
        return status_counts
    except Exception as e:
        logger.error(f"Error getting status summary for batch {batch_id}: {e}")
        return {}

async def delete_batch(*, batch_id: uuid.UUID) -> bool:
    """Delete a batch and optionally its documents (metadata only)."""
    batch_collection = _get_collection("batches")
    doc_collection = _get_collection(DOCUMENT_COLLECTION)
    if batch_collection is None or doc_collection is None:
        logger.error("Failed to get required collections")
        return False

    try:
        # Delete the batch record
        result = await batch_collection.delete_one({"_id": batch_id})
        if result.deleted_count:
            # Update documents to remove batch_id reference
            await doc_collection.update_many(
                {"batch_id": batch_id},
                {"$unset": {"batch_id": "", "queue_position": ""}}
            )
            return True
        return False
    except Exception as e:
        logger.error(f"Error deleting batch {batch_id}: {e}")
        return False

async def delete_result(result_id: uuid.UUID, session=None) -> bool:
    collection = _get_collection(RESULT_COLLECTION)
    if collection is None: return False
    # Soft delete: find and update, setting is_deleted to True
    # Or hard delete: find and delete
    # For now, let's assume soft delete (or that Results are hard deleted)
    logger.info(f"Attempting to delete Result ID: {result_id}")
    try:
        # Simplistic hard delete for now, adjust as per actual requirements (soft/hard)
        result = await collection.delete_one({"_id": result_id}, session=session)
        if result.deleted_count == 1:
            logger.info(f"Successfully deleted result {result_id}.")
            return True
        else:
            logger.warning(f"Result {result_id} not found for deletion or already deleted.")
            return False # Or True if already deleted is considered success
    except Exception as e:
        logger.error(f"Error deleting result {result_id}: {e}", exc_info=True)
        return False

# NEW: Function to update document status for reprocessing (transactional)
@with_transaction
async def _update_document_for_reprocessing(document_id: uuid.UUID, teacher_id: str, session=None) -> bool:
    doc_collection = _get_collection(DOCUMENT_COLLECTION)
    if doc_collection is None:
        logger.error(f"[_update_document_for_reprocessing] Document collection not found for {document_id}")
        return False
    now = datetime.now(timezone.utc)
    doc_update_result = await doc_collection.update_one(
        {"_id": document_id, "teacher_id": teacher_id, "is_deleted": {"$ne": True}},
        {"$set": {"status": DocumentStatus.QUEUED.value, "updated_at": now, "score": None}},
        session=session
    )
    if doc_update_result.matched_count == 0:
        logger.warning(f"[_update_document_for_reprocessing] Document {document_id} not found for teacher {teacher_id}, or already deleted.")
        return False
    logger.info(f"[_update_document_for_reprocessing] Document {document_id} status updated to QUEUED (modified: {doc_update_result.modified_count}).")
    return True

# NEW: Function to update result(s) for reprocessing (transactional)
@with_transaction
async def _update_results_for_reprocessing(document_id: uuid.UUID, teacher_id: str, session=None) -> bool:
    res_collection = _get_collection(RESULT_COLLECTION)
    if res_collection is None:
        logger.error(f"[_update_results_for_reprocessing] Result collection not found for doc {document_id}")
        return False
    now = datetime.now(timezone.utc)
    result_update_payload = {
        "$set": {
            "status": ResultStatus.PENDING.value,
            "updated_at": now,
            "result_timestamp": now,
            "score": None,
            "overall_assessment": "Assessment pending reprocessing.",
            "label": None,
            "paragraph_results": [],
            "error_message": None,
            "raw_response": None
        }
    }
    res_update_result = await res_collection.update_many(
        {"document_id": document_id, "teacher_id": teacher_id, "is_deleted": {"$ne": True}},
        result_update_payload,
        session=session
    )
    logger.info(f"[_update_results_for_reprocessing] {res_update_result.modified_count} result(s) for document {document_id} updated to PENDING (matched: {res_update_result.matched_count}).")
    # This function returns True even if no results were modified, as long as the operation didn't fail.
    # The caller can decide if 0 modified results is an issue.
    return True


async def reprocess_document_and_result(
    document_id: uuid.UUID,
    teacher_id: str, # Kinde ID of the user requesting reprocessing
) -> bool:
    """
    Resets a document's status to QUEUED and its associated result to PENDING,
    then re-enqueues it for assessment.
    Each DB update step is now individually transactional.
    """
    # Step 1: Update document status (transactional)
    doc_updated = await _update_document_for_reprocessing(document_id, teacher_id)
    if not doc_updated:
        logger.error(f"[Reprocess] Failed to update document status for {document_id}. Reprocessing aborted.")
        return False

    # Step 2: Update result status (transactional)
    results_updated = await _update_results_for_reprocessing(document_id, teacher_id)
    if not results_updated:
        # Log this, but decide if it's a hard failure. For now, if the document was updated,
        # but results weren't (e.g., no result existed), we might still want to enqueue.
        # However, if _update_results_for_reprocessing itself errored (not just 0 modified),
        # then it's a problem. The current _update_results_for_reprocessing returns True unless an exception.
        logger.warning(f"[Reprocess] Call to update results for document {document_id} returned {results_updated}. This might be okay if no results existed or an error occurred.")
        # For now, let's consider a False return from _update_results_for_reprocessing as a failure to proceed.
        # This could be refined if "no results found to update" is an acceptable state.
        # Given the current error, any failure here is likely a transaction issue.
        return False


    # Step 3: Re-enqueue the assessment task
    logger.info(f"[Reprocess] Attempting to enqueue task for {document_id} after DB updates.")
    enqueue_success = await enqueue_assessment_task(
        document_id=document_id,
        user_id=teacher_id, 
        priority_level=0
    )

    if not enqueue_success:
        logger.error(f"[Reprocess] Document {document_id} statuses were reset, but FAILED to re-enqueue assessment task.")
        return False

    logger.info(f"[Reprocess] Document {document_id} successfully re-queued for assessment after DB updates.")
    return True

@with_transaction
async def soft_delete_result_by_document_id(document_id: uuid.UUID, teacher_id: str, session=None) -> bool:
    """
    Soft-deletes result records associated with a given document_id and teacher_id.
    This function is designed to be called in its own transaction.
    Returns True if the operation was successful (even if no records were modified),
    False if an error occurred.
    """
    res_collection = _get_collection(RESULT_COLLECTION)
    if res_collection is None:
        logger.error(f"[soft_delete_result] Result collection not found for document {document_id}")
        return False

    now = datetime.now(timezone.utc)
    try:
        update_result = await res_collection.update_many(
            {"document_id": document_id, "teacher_id": teacher_id, "is_deleted": {"$ne": True}},
            {"$set": {"is_deleted": True, "updated_at": now, "status": ResultStatus.DELETED.value}},
            session=session
        )
        logger.info(f"[soft_delete_result] Attempted to soft-delete results for document {document_id} by teacher {teacher_id}. Matched: {update_result.matched_count}, Modified: {update_result.modified_count}.")
        # Consider success if no error, regardless of modified count (e.g., results might have been already deleted or none existed)
        return True 
    except PyMongoError as e:
        logger.error(f"[soft_delete_result] PyMongoError soft-deleting results for document {document_id}: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"[soft_delete_result] Unexpected error soft-deleting results for document {document_id}: {e}", exc_info=True)
        return False

# <<< START EDIT: Add new analytics CRUD function >>>
async def get_usage_stats_for_period(
    teacher_id: str,
    period: Optional[str] = None,         # MODIFIED: Made optional
    target_date: Optional[date_type] = None # MODIFIED: Made optional
) -> Optional[Dict[str, Any]]: # Matches UsageStatsResponse structure
    """
    Calculates usage statistics (document count, total words, total characters)
    for a given teacher over a specified period or all time.

    If 'period' and 'target_date' are provided, stats are for that specific period.
    If 'period' and 'target_date' are None, stats are calculated for all time,
    and will include current_documents, deleted_documents, and total_processed_documents.
    """
    collection = _get_collection(DOCUMENT_COLLECTION)
    if collection is None:
        logger.error("Documents collection not found.")
        return None

    match_query: Dict[str, Any] = {
        "teacher_id": teacher_id,
        "is_deleted": {"$ne": True}
    }

    if period and target_date:
        start_datetime: Optional[datetime] = None
        end_datetime: Optional[datetime] = None
        
        if period == 'daily':
            start_datetime = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc)
            # Use combine with max.time() for end of day
            end_datetime = datetime.combine(target_date, datetime.max.time(), tzinfo=timezone.utc)
        elif period == 'weekly':
            # Calculate the start of the week (Monday)
            start_of_week = target_date - timedelta(days=target_date.weekday())
            # Calculate the end of the week (Sunday)
            end_of_week = start_of_week + timedelta(days=6)
            start_datetime = datetime.combine(start_of_week, datetime.min.time(), tzinfo=timezone.utc)
            end_datetime = datetime.combine(end_of_week, datetime.max.time(), tzinfo=timezone.utc)
        elif period == 'monthly':
            year = target_date.year
            month = target_date.month
            # Get the number of days in the given month and year
            num_days = calendar.monthrange(year, month)[1]
            # Create the first day of the month
            first_day_of_month = date_type(year, month, 1)
            # Create the last day of the month
            last_day_of_month = date_type(year, month, num_days)
            # Combine with min/max times for datetime objects
            start_datetime = datetime.combine(first_day_of_month, datetime.min.time(), tzinfo=timezone.utc)
            end_datetime = datetime.combine(last_day_of_month, datetime.max.time(), tzinfo=timezone.utc)
        else:
            logger.error(f"Unsupported period: {period} with target_date: {target_date}")
            # Consider raising ValueError or returning None if period is unsupported but provided
            # For now, if period is unrecognized but provided, we might fall through to all-time,
            # or we should explicitly handle it. Let's return None.
            return { # Return zeroed stats for unsupported period
                "teacher_id": teacher_id,
                "period_start_date": None, # Or some representation of the failed period
                "period_end_date": None,
                "document_count": 0,
                "total_words": 0,
                "total_characters": 0,
                "report_generated_at": datetime.now(timezone.utc)
            }

        if start_datetime and end_datetime:
            # Ensure end_datetime is inclusive for the query by going to the very end of the target day
            match_query["upload_timestamp"] = {
                "$gte": start_datetime,
                "$lte": end_datetime # up to 23:59:59.999999 of the end_datetime's day
            }
            period_start_str = start_datetime.strftime('%Y-%m-%d')
            period_end_str = end_datetime.strftime('%Y-%m-%d')
        else: # Should not happen if period and target_date are valid and lead to date calculation
            logger.warning(f"Could not determine date range for period '{period}' and target_date '{target_date}'. Returning all-time stats instead or error.")
            # Fallback to no date filter (all time) or handle as error
            # For now, let's assume this means all-time if dates weren't set.
            # However, the logic above should ensure start_datetime/end_datetime are set if period is valid.
            # This path is more of a safeguard.
            period_start_str = None # Indicates all-time
            period_end_str = None   # Indicates all-time
    else:
        # No period and target_date provided, so calculate for all time
        logger.info(f"Calculating all-time usage stats for teacher_id: {teacher_id}")
        period_start_str = None # Indicates all-time
        period_end_str = None   # Indicates all-time

        # For all-time, also get deleted documents count
        deleted_documents_count = await collection.count_documents({"teacher_id": teacher_id, "is_deleted": True})
        # The main match_query for the pipeline already targets current documents

    pipeline = [
        {
            "$match": match_query
        },
        {
            "$group": {
                "_id": "$teacher_id",  # Group by teacher_id
                "document_count": {"$sum": 1},
                "total_words": {"$sum": {"$ifNull": ["$word_count", 0]}},
                "total_characters": {"$sum": {"$ifNull": ["$character_count", 0]}}
            }
        },
        {
            "$project": {
                "_id": 0,  # Exclude the _id field from the output
                "teacher_id": "$_id",
                "document_count": 1,
                "total_words": 1,
                "total_characters": 1
            }
        }
    ]

    try:
        aggregation_result_list = await collection.aggregate(pipeline).to_list(length=1)
        logger.debug(f"Usage stats aggregation result for {teacher_id}, period={period or 'all-time'}: {aggregation_result_list}")

        response_payload: Dict[str, Any] = {}

        if aggregation_result_list:
            stats = aggregation_result_list[0]
            response_payload = {
                "teacher_id": stats.get("teacher_id", teacher_id), 
                # For all-time, document_count from pipeline is current_documents
                # For periodic, it's documents in that period
                "document_count": stats.get("document_count", 0),
                "total_words": stats.get("total_words", 0),
                "total_characters": stats.get("total_characters", 0),
                "report_generated_at": datetime.now(timezone.utc)
            }
            # If all-time, add specific breakdown
            if not period and not target_date:
                response_payload["current_documents"] = stats.get("document_count", 0) # current documents
                response_payload["deleted_documents"] = deleted_documents_count
                response_payload["total_processed_documents"] = stats.get("document_count", 0) + deleted_documents_count
                # document_count will still hold current_documents for backward compatibility / other uses of this field

        else: # No documents found matching the criteria
            logger.info(f"No documents found for usage stats (teacher: {teacher_id}, period: {period or 'all-time'}, target: {target_date})")
            response_payload = {
                "teacher_id": teacher_id,
                "document_count": 0,
                "total_words": 0,
                "total_characters": 0,
                "report_generated_at": datetime.now(timezone.utc)
            }
            # If all-time and no documents found, also set breakdown to 0
            if not period and not target_date:
                response_payload["current_documents"] = 0
                response_payload["deleted_documents"] = deleted_documents_count # could be > 0 if only deleted ones exist
                response_payload["total_processed_documents"] = deleted_documents_count

        # Add period-specific fields if they were used for the query
        if period and target_date and period_start_str and period_end_str: # period_start_str/end_str are set if period/target_date are valid
            response_payload["period"] = period
            response_payload["target_date"] = target_date.strftime('%Y-%m-%d') # Format date to string for response
            response_payload["start_date"] = period_start_str
            response_payload["end_date"] = period_end_str
        else: # For all-time, these can be None or omitted if the model allows
            response_payload["period"] = None
            response_payload["target_date"] = None
            response_payload["start_date"] = None
            response_payload["end_date"] = None
            
        logger.info(f"Successfully retrieved usage stats for {teacher_id}, period={period or 'all-time'}: {response_payload}")
        return response_payload

    except Exception as e:
        logger.error(f"Error during usage stats aggregation for teacher {teacher_id}: {e}", exc_info=True)
        return None

async def get_result_by_id(result_id: uuid.UUID, teacher_id: Optional[str] = None, include_deleted: bool = False, session=None) -> Optional[Result]:
    """Gets a single result by its own ID, optionally checking teacher_id."""
    collection = _get_collection(RESULT_COLLECTION)
    if collection is None: return None

    query = {"_id": result_id}
    if teacher_id:
        query["teacher_id"] = teacher_id
        logger.info(f"Getting result by ID: {result_id} for teacher: {teacher_id}")
    else:
        logger.info(f"Getting result by ID: {result_id}")
    
    query.update(soft_delete_filter(include_deleted))
    logger.debug(f"Executing find_one for result by ID with query: {query}")
    try:
        result_doc = await collection.find_one(query, session=session)
        if result_doc:
            logger.debug(f"Raw result doc from DB by ID: {result_doc}")
            return Result(**result_doc)
        else:
            logger.warning(f"Result {result_id} not found.")
            return None
    except Exception as e:
        logger.error(f"Error getting result by ID {result_id}: {e}", exc_info=True)
        return None

# If _get_collection is not globally available or needs specific import:
# from .database import _get_collection

# Initialize logger if not already done (though usually configured in main.py)
logger = logging.getLogger(__name__) # Or use your project's standard logger

# Define RESULT_COLLECTION if not imported (ensure this matches your actual collection name)
RESULT_COLLECTION = "results"

# If using a transaction decorator, apply it. Otherwise, remove @with_transaction.
# @with_transaction
async def create_result(
    result_in: ResultCreate, # MODIFIED: Accept ResultCreate schema
    session=None # For database transactions, if used
) -> Optional[Result]: # MODIFIED: Changed from Optional[models.Result] to Optional[Result]
    """Creates a new result record in the database from a ResultCreate schema."""
    collection = _get_collection(RESULT_COLLECTION)
    if collection is None:
        logger.error("Result collection not found.")
        return None

    now = datetime.now(timezone.utc)
    new_result_id = uuid.uuid4()

    # Create the dictionary for the new result document from result_in
    # and add auto-generated fields.
    result_doc_data = result_in.model_dump()
    result_doc_data["_id"] = new_result_id
    result_doc_data["id"] = new_result_id # Also set 'id' if your model uses it directly

    # Ensure essential fields that might not be in ResultCreate but are in Result model
    # are set with defaults if applicable, or are expected to be in result_in.
    # For example, created_at and updated_at are usually set by the CRUD.
    result_doc_data["created_at"] = now
    result_doc_data["updated_at"] = now
    
    # If status is part of ResultCreate and has a default, it will be used.
    # If not, and it's required by Result model, ensure it's provided or set here.
    # Example: if result_in doesn't guarantee status, set a default:
    if "status" not in result_doc_data or result_doc_data["status"] is None:
        result_doc_data["status"] = ResultStatus.PENDING.value # Default to PENDING

    logger.info(f"Attempting to insert new result with ID: {new_result_id} for document ID: {result_in.document_id}")

    try:
        # Use the result_doc_data dictionary for insertion
        inserted_result = await collection.insert_one(result_doc_data, session=session)
        if inserted_result.acknowledged:
            # Retrieve the document using the internal _id field
            created_doc = await collection.find_one({"_id": new_result_id}, session=session)
            if created_doc:
                # Ensure the Pydantic model can handle aliasing if _id is mapped to id
                return Result(**created_doc)
            else:
                logger.error(f"Failed to retrieve result after insert: {new_result_id}")
                return None
        else:
            logger.error(f"Insert not acknowledged for result ID: {new_result_id}")
            return None
    except DuplicateKeyError:
        logger.error(f"Attempted to insert a result with a duplicate ID: {new_result_id}")
        return None
    except Exception as e:
        logger.error(f"Error creating result: {e}", exc_info=True)
        return None

# --- Batch CRUD ---