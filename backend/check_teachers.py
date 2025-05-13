# check_teachers.py (Index Checking Version - Manual Copy)
import os
import sys
import json # Added for pretty printing
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import logging

# Add backend directory to sys.path to find settings
# sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))) # Not needed if run directly from backend/

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("IndexCheckScript") # Use specific name

# Load environment variables
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=env_path)
logger.info(f"Loaded environment variables from: {os.path.abspath(env_path)}")

MONGO_DETAILS = os.getenv("MONGODB_URL")
DATABASE_NAME = os.getenv("DB_NAME", "aidetector_dev")

if not MONGO_DETAILS:
    logger.error("MONGODB_URL environment variable not set.")
    sys.exit(1)
if not DATABASE_NAME:
    logger.error("DB_NAME environment variable not set or is empty.")
    sys.exit(1)

logger.info(f"Attempting to connect to MongoDB/Cosmos DB using database: {DATABASE_NAME}")

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
    # index_info = documents_collection.index_information() # Moved after index creation attempt

    # --- Attempt to create the required compound index --- 
    required_index_key = [('teacher_id', 1), ('upload_timestamp', -1)]
    required_index_name = "teacher_timestamp_compound"
    logger.info(f"Attempting to ensure compound index '{required_index_name}' exists on fields: {required_index_key}")
    try:
        # create_index is idempotent - it won't error if the index already exists with the same definition
        created_index_name = documents_collection.create_index(required_index_key, name=required_index_name)
        logger.info(f"Successfully ensured index '{created_index_name}' exists.")
    except Exception as index_err:
        logger.error(f"Error attempting to create index '{required_index_name}': {index_err}")
    # -----------------------------------------------------

    logger.info("Fetching current index information...")
    index_info = documents_collection.index_information()

    if index_info:
        logger.info("Found the following index information:")
        # Pretty print the index information
        logger.info(json.dumps(index_info, indent=2, default=str)) # Added default=str for non-serializable types
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
