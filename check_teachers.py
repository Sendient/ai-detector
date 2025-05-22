import os
import sys
import json # Added for pretty printing
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import logging

# Add backend directory to sys.path to find settings
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__) # Use __name__ for logger

# Load environment variables
load_dotenv()
logger.info(f"Loaded environment variables from: {os.path.abspath('.env')}")

MONGO_DETAILS = os.getenv("MONGO_DETAILS")
DATABASE_NAME = os.getenv("MONGO_INITDB_DATABASE", "aidetector_dev1") # Use default if not set

if not MONGO_DETAILS:
    logger.error("MONGO_DETAILS environment variable not set.")
    sys.exit(1)
if not DATABASE_NAME:
    logger.error("MONGO_INITDB_DATABASE environment variable not set.")
    sys.exit(1)

logger.info(f"Attempting to connect to MongoDB/Cosmos DB: {DATABASE_NAME}")

client = None
try:
    # Increase server selection timeout
    client = MongoClient(MONGO_DETAILS, serverSelectionTimeoutMS=10000)

    # The ismaster command is cheap and does not require auth.
    logger.info("Pinging MongoDB/Cosmos DB server...")
    client.admin.command('ping')
    logger.info("MongoDB/Cosmos DB server ping successful.")

    db = client[DATABASE_NAME]
    logger.info(f"Successfully connected to database: '{DATABASE_NAME}'")

    # Change collection to 'documents'
    documents_collection = db["documents"]
    logger.info(f"Accessing collection: '{documents_collection.name}'")

    logger.info("Attempting to get index information for the collection...")
    # Get index information directly using pymongo
    index_info = documents_collection.index_information()

    if index_info:
        logger.info("Found the following index information:")
        # Pretty print the index information
        logger.info(json.dumps(index_info, indent=2))
    else:
        logger.info("No index information found for the 'documents' collection.")

except ServerSelectionTimeoutError as err:
    logger.error(f"MongoDB/Cosmos DB connection failed: Server selection timeout: {err}")
except ConnectionFailure as err:
    logger.error(f"MongoDB/Cosmos DB connection failed: {err}")
except Exception as e:
    logger.error(f"An unexpected error occurred: {e}")
    import traceback
    logger.error(traceback.format_exc())
finally:
    if client:
        client.close()
        logger.info("MongoDB/Cosmos DB connection closed.") 