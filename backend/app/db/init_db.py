from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import IndexModel, ASCENDING, DESCENDING
from .database import get_database

async def init_db_indexes():
    """
    Initialize MongoDB indexes for collections.
    This should be called during application startup.
    """
    db = get_database()
    if not db:
        return False

    try:
        # Student Collection Indexes
        student_indexes = [
            # Index for internal ID (should be created automatically by MongoDB)
            IndexModel([("_id", ASCENDING)], name="internal_id_index"),
            
            # Sparse unique index for external_student_id
            # Only indexes documents where external_student_id exists
            IndexModel(
                [("external_student_id", ASCENDING)],
                name="external_student_id_unique",
                unique=True,
                sparse=True
            ),
            
            # Compound index for efficient filtering and sorting
            IndexModel(
                [
                    ("last_name", ASCENDING),
                    ("first_name", ASCENDING)
                ],
                name="name_lookup"
            )
        ]
        
        # Batch Collection Indexes
        batch_indexes = [
            # Index for internal ID
            IndexModel([("_id", ASCENDING)], name="batch_id_index"),
            
            # Index for user_id for quick lookup of user's batches
            IndexModel([("user_id", ASCENDING)], name="batch_user_index"),
            
            # Compound index for status and creation time
            IndexModel(
                [
                    ("status", ASCENDING),
                    ("created_at", DESCENDING)
                ],
                name="batch_status_time_index"
            ),
            
            # Index for batch priority
            IndexModel([("priority", ASCENDING)], name="batch_priority_index")
        ]

        # Document Collection Indexes
        document_indexes = [
            # Index for internal ID
            IndexModel([("_id", ASCENDING)], name="document_id_index"),
            
            # Index for batch_id for quick lookup of documents in a batch
            IndexModel([("batch_id", ASCENDING)], name="document_batch_index"),
            
            # Compound index for queue position within a batch
            IndexModel(
                [
                    ("batch_id", ASCENDING),
                    ("queue_position", ASCENDING)
                ],
                name="batch_queue_position_index"
            ),
            
            # Compound index for processing priority and status
            IndexModel(
                [
                    ("processing_priority", DESCENDING),
                    ("status", ASCENDING)
                ],
                name="document_processing_index"
            )
        ]
        
        # Create indexes
        await db["students"].create_indexes(student_indexes)
        await db["batches"].create_indexes(batch_indexes)
        await db["documents"].create_indexes(document_indexes)
        
        return True
    except Exception as e:
        print(f"Error creating indexes: {e}")
        return False 