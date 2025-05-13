# backend/app/migrations/add_unique_email_index.py

import asyncio
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def create_unique_email_index():
    """Create a unique index on the email field in the teachers collection."""
    try:
        # Connect to MongoDB
        client = AsyncIOMotorClient(settings.MONGODB_URL)
        db = client[settings.MONGODB_DB]
        collection = db[settings.TEACHERS_COLLECTION]

        # Create the unique index
        await collection.create_index(
            [("email", 1)],
            unique=True,
            name="unique_email_index"
        )
        logger.info("Successfully created unique index on 'email' field in teachers collection.")

    except Exception as e:
        logger.error(f"Error creating unique index: {e}", exc_info=True)
        raise
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(create_unique_email_index()) 