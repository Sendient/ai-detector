import os
import sys
import json
import argparse # Import argparse
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import logging
from bson import ObjectId # For handling ObjectId if necessary, though not directly used for stripe_customer_id query

# Add backend directory to sys.path to find settings (if your script needs other modules from backend)
# For a standalone script like this, it might not be strictly necessary if only .env is needed.
# sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables from .env in the current directory or project root
dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if not os.path.exists(dotenv_path):
    # Try project root if script is in a subdirectory (e.g. ./scripts)
    dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')

if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
    logger.info(f"Loaded environment variables from: {os.path.abspath(dotenv_path)}")
else:
    # Fallback to trying to load .env from current working directory if not found relative to script
    load_dotenv() 
    logger.info(f"Attempted to load environment variables from default .env path (current dir or parent): {os.path.abspath('.env')}")


MONGO_DETAILS = os.getenv("MONGODB_URL") or os.getenv("MONGO_DETAILS")
DATABASE_NAME = os.getenv("DB_NAME") or os.getenv("MONGO_INITDB_DATABASE", "aidetector_dev1")

# --- Argument Parsing ---
parser = argparse.ArgumentParser(description="Check teacher records in MongoDB.")
parser.add_argument("--stripe_customer_id", type=str, help="Stripe Customer ID to search for.")
parser.add_argument("--kinde_id", type=str, help="Kinde ID to search for.")
parser.add_argument("--email", type=str, help="Email to search for.")
args = parser.parse_args()

if not MONGO_DETAILS:
    logger.error("MONGODB_URL or MONGO_DETAILS environment variable not set or loaded.")
    sys.exit(1)
if not DATABASE_NAME:
    logger.error("DB_NAME or MONGO_INITDB_DATABASE environment variable not set or loaded (or using default 'aidetector_dev1').")
    # Allow default, but log it.

logger.info(f"Using Database: {DATABASE_NAME}")
logger.info(f"Attempting to connect to MongoDB/Cosmos DB...") # MONGO_DETAILS can be long, so not logging its full value unless debugging is needed

client = None
try:
    client = MongoClient(MONGO_DETAILS, serverSelectionTimeoutMS=10000)
    logger.info("Pinging MongoDB/Cosmos DB server...")
    client.admin.command('ping')
    logger.info("MongoDB/Cosmos DB server ping successful.")

    db = client[DATABASE_NAME]
    logger.info(f"Successfully connected to database: '{DATABASE_NAME}'")

    teachers_collection = db["teachers"]
    logger.info(f"Accessing collection: '{teachers_collection.name}'")

    query = {}
    if args.stripe_customer_id:
        query["stripe_customer_id"] = args.stripe_customer_id
        logger.info(f"Querying for teacher with stripe_customer_id: {args.stripe_customer_id}")
    elif args.kinde_id:
        query["kinde_id"] = args.kinde_id
        logger.info(f"Querying for teacher with kinde_id: {args.kinde_id}")
    elif args.email:
        query["email"] = args.email
        logger.info(f"Querying for teacher with email: {args.email}")
    else:
        logger.info("No query parameters provided. Listing up to 5 teachers instead.")
        # If no specific ID is given, maybe list a few or just schema
        teacher_records = list(teachers_collection.find().limit(5))
        if teacher_records:
            logger.info(f"Found {len(teacher_records)} teacher(s):")
            for record in teacher_records:
                record['_id'] = str(record['_id']) # Convert ObjectId to string for JSON serialization
                logger.info(json.dumps(record, indent=2, default=str)) # Use default=str for other non-serializable types like datetime
        else:
            logger.info("No teachers found with the general query.")
        sys.exit(0)


    teacher_record = teachers_collection.find_one(query)

    if teacher_record:
        logger.info("Found the following teacher record:")
        # Convert ObjectId to string for JSON serialization
        teacher_record['_id'] = str(teacher_record['_id'])
        logger.info(json.dumps(teacher_record, indent=2, default=str)) # Use default=str for datetime etc.
    else:
        logger.info(f"No teacher found with the specified criteria: {query}")

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