from datetime import datetime, timezone
import uuid
import logging
from typing import Dict, List
from pymongo import MongoClient
from pymongo.database import Database
from app.core.config import settings

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_mongo_client() -> MongoClient:
    """Create a MongoDB client with proper UUID handling."""
    return MongoClient(
        settings.MONGODB_URL,
        uuidRepresentation='standard'  # This enables proper UUID handling
    )

def migrate_teachers():
    # Connect to MongoDB
    client = get_mongo_client()
    db = client[settings.MONGODB_DB]
    teachers_collection = db[settings.TEACHERS_COLLECTION]

    # Get all teachers
    teachers = list(teachers_collection.find())
    logger.info(f"Found {len(teachers)} teachers to migrate")

    for teacher in teachers:
        # Skip if already has UUID _id
        if isinstance(teacher['_id'], uuid.UUID):
            logger.info(f"Skipping teacher {teacher['_id']} - already has UUID")
            continue

        # Create new UUID
        new_id = uuid.uuid4()
        kinde_id = teacher['_id']  # Store original Kinde ID
        logger.info(f"Processing teacher {kinde_id} -> {new_id}")

        # Create new document with updated fields
        new_doc = {
            '_id': new_id,
            'kinde_id': kinde_id,
            'is_deleted': teacher.get('is_deleted', False),
            'is_admin': False,  # Default to non-admin
            'updated_at': datetime.now(timezone.utc)
        }

        # Copy all other fields
        for key, value in teacher.items():
            if key not in ['_id', 'deleted_at']:  # Skip _id and deleted_at
                new_doc[key] = value

        try:
            # Insert new document
            logger.info(f"Inserting new document for teacher {kinde_id}")
            teachers_collection.insert_one(new_doc)
            # Delete old document
            logger.info(f"Deleting old document for teacher {kinde_id}")
            teachers_collection.delete_one({'_id': kinde_id})
            logger.info(f"Successfully migrated teacher {kinde_id} to {new_id}")
        except Exception as e:
            logger.error(f"Error migrating teacher {kinde_id}: {str(e)}")
            raise  # Re-raise the exception to see the full traceback

    logger.info("Migration completed")

def migrate_resources(db: Database, kinde_to_uuid_map: Dict[str, uuid.UUID]):
    """Migrate all resources to use internal teacher UUIDs."""
    collections = {
        'students': settings.STUDENTS_COLLECTION,
        'class_groups': settings.CLASS_GROUPS_COLLECTION,
        'assignments': settings.ASSIGNMENTS_COLLECTION,
        'documents': settings.DOCUMENTS_COLLECTION,
        'results': settings.RESULTS_COLLECTION
    }
    
    for resource_name, collection_name in collections.items():
        logger.info(f"Migrating {resource_name} collection")
        collection = db[collection_name]
        for resource in collection.find({}):
            old_teacher_id = resource.get('teacher_id')
            if old_teacher_id and old_teacher_id in kinde_to_uuid_map:
                new_teacher_id = kinde_to_uuid_map[old_teacher_id]
                collection.update_one(
                    {'_id': resource['_id']},
                    {
                        '$set': {
                            'teacher_id': new_teacher_id,
                            'updated_at': datetime.now(timezone.utc)
                        }
                    }
                )

def run_rbac_migration():
    """Main migration function."""
    logger.info("Starting RBAC migration")
    client = get_mongo_client()
    db = client[settings.MONGODB_DB]
    
    try:
        # Step 1: Migrate teachers and get mapping
        logger.info("Migrating teachers...")
        migrate_teachers()
        logger.info("Teacher migration completed")
        
        # Step 2: Migrate all resources
        logger.info("Migrating resources...")
        migrate_resources(db, {})
        logger.info("Resource migration completed")
        
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        raise
    finally:
        client.close()

if __name__ == "__main__":
    run_rbac_migration() 