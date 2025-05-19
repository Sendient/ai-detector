from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import IndexModel, ASCENDING, DESCENDING
from .database import get_database
import logging

logger = logging.getLogger(__name__)

async def init_db_indexes():
    """
    Initialize MongoDB indexes for all collections used by the app.
    This should be called during application startup.
    NOTE: Cosmos DB requires unique indexes to be defined at collection creation. If you need to change a unique index, you must drop and recreate the collection.
    """
    db = get_database()
    if not db:
        logger.error("Database connection is not available. Cannot create indexes.")
        return False

    try:
        # Students
        logger.info("Ensuring indexes for students collection...")
        student_indexes = [
            IndexModel([("_id", ASCENDING)], name="internal_id_index"),
            IndexModel([("external_student_id", ASCENDING)], name="external_student_id_unique", unique=True, sparse=True),
            IndexModel([("last_name", ASCENDING), ("first_name", ASCENDING)], name="name_lookup")
        ]
        await db["students"].create_indexes(student_indexes)

        # Batches
        logger.info("Ensuring indexes for batches collection...")
        batch_indexes = [
            IndexModel([("_id", ASCENDING)], name="batch_id_index"),
            IndexModel([("user_id", ASCENDING)], name="batch_user_index"),
            IndexModel([("status", ASCENDING), ("created_at", DESCENDING)], name="batch_status_time_index"),
            IndexModel([("priority", ASCENDING)], name="batch_priority_index"),
            IndexModel([("status", ASCENDING), ("created_at", DESCENDING)], name="status_1_created_at_-1")
        ]
        await db["batches"].create_indexes(batch_indexes)

        # Documents
        logger.info("Ensuring indexes for documents collection...")
        document_indexes = [
            IndexModel([("_id", ASCENDING)], name="document_id_index"),
            IndexModel([("batch_id", ASCENDING)], name="document_batch_index"),
            IndexModel([("batch_id", ASCENDING), ("queue_position", ASCENDING)], name="batch_queue_position_index"),
            IndexModel([("processing_priority", DESCENDING), ("status", ASCENDING)], name="document_processing_index"),
            IndexModel([("teacher_id", ASCENDING), ("upload_timestamp", DESCENDING)], name="teacher_upload_index")
        ]
        await db["documents"].create_indexes(document_indexes)

        # Teachers
        logger.info("Ensuring indexes for teachers collection...")
        teacher_indexes = [
            IndexModel([("_id", ASCENDING)], name="teacher_id_index"),
            IndexModel([("kinde_id", ASCENDING)], name="unique_kinde_id", unique=True),
            IndexModel([("email", ASCENDING)], name="unique_email", unique=True),
            IndexModel([("is_deleted", ASCENDING)], name="is_deleted_index"),
            IndexModel([("kinde_id", ASCENDING), ("is_deleted", ASCENDING)], name="kinde_id_is_deleted_index"),
            IndexModel([("school_id", ASCENDING), ("is_deleted", ASCENDING)], name="school_id_is_deleted_index")
        ]
        await db["teachers"].create_indexes(teacher_indexes)

        # Results
        logger.info("Ensuring indexes for results collection...")
        result_indexes = [
            IndexModel([("_id", ASCENDING)], name="result_id_index"),
            IndexModel([("is_deleted", ASCENDING)], name="result_is_deleted_index"),
            IndexModel([("document_id", ASCENDING), ("is_deleted", ASCENDING)], name="document_id_is_deleted_index"),
            IndexModel([("teacher_id", ASCENDING), ("status", ASCENDING), ("score", ASCENDING), ("updated_at", ASCENDING)], name="dashboard_stats_index")
        ]
        await db["results"].create_indexes(result_indexes)

        # Schools
        logger.info("Ensuring indexes for schools collection...")
        school_indexes = [IndexModel([("_id", ASCENDING)], name="school_id_index")]
        await db["schools"].create_indexes(school_indexes)

        # Classgroups
        logger.info("Ensuring indexes for classgroups collection...")
        classgroup_indexes = [IndexModel([("_id", ASCENDING)], name="classgroup_id_index")]
        await db["classgroups"].create_indexes(classgroup_indexes)

        logger.info("All collections and indexes ensured.")
        return True
    except Exception as e:
        logger.error(f"Error creating indexes: {e}")
        return False 