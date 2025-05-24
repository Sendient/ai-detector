from datetime import datetime, timezone
import logging
from pymongo import MongoClient
from ..core.config import settings
from ..db.crud import TEACHER_COLLECTION, STUDENT_COLLECTION, CLASSGROUP_COLLECTION, ASSIGNMENT_COLLECTION, DOCUMENT_COLLECTION, RESULT_COLLECTION
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_mongo_client() -> MongoClient:
    """Create a MongoDB client with proper UUID handling."""
    return MongoClient(
        settings.MONGODB_URL,
        uuidRepresentation='standard'  # This enables proper UUID handling
    )

async def cleanup_database():
    """Clean up all collections in the database."""
    logger.info("Starting database cleanup")
    client = get_mongo_client()
    db = client[settings.DB_NAME]
    
    try:
        # List of collections to clean up
        collections = [
            TEACHER_COLLECTION,
            STUDENT_COLLECTION,
            CLASSGROUP_COLLECTION,
            ASSIGNMENT_COLLECTION,
            DOCUMENT_COLLECTION,
            RESULT_COLLECTION
        ]
        
        for collection_name in collections:
            logger.info(f"Cleaning up collection: {collection_name}")
            collection = db[collection_name]
            result = collection.delete_many({})
            logger.info(f"Deleted {result.deleted_count} documents from {collection_name}")
            
        logger.info("Database cleanup completed successfully")
        
    except Exception as e:
        logger.error(f"Error during database cleanup: {str(e)}")
        raise
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(cleanup_database()) 