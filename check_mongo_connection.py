import os
import pymongo
from dotenv import load_dotenv

# Load environment variables from .env and backend/.env.test
# This mimics pytest-dotenv behavior for a standalone script
load_dotenv()
load_dotenv("backend/.env.test", override=True) # backend/.env.test values will take precedence

MONGO_URL = os.getenv("MONGO_URL_TEST")
DB_NAME = os.getenv("MONGO_TEST_DB_NAME")

if not MONGO_URL or not DB_NAME:
    print("Error: MONGO_URL_TEST or MONGO_TEST_DB_NAME environment variables not set.")
    print("Please ensure backend/.env.test is populated and accessible or variables are set in your environment.")
    exit(1)

print(f"Attempting to connect to MongoDB...\nURL: {MONGO_URL}\nDatabase: {DB_NAME}")

try:
    # Connect to the MongoDB server
    client = pymongo.MongoClient(MONGO_URL)

    # The ismaster command is cheap and does not require auth.
    client.admin.command('ismaster')
    print("Successfully connected to MongoDB server!")

    # Get the database
    db = client[DB_NAME]
    print(f"Successfully accessed database: {DB_NAME}")

    # List collections as a basic check
    collections = db.list_collection_names()
    print(f"Collections in '{DB_NAME}': {collections if collections else 'None'}")
    print("MongoDB connectivity test successful!")

except pymongo.errors.ConfigurationError as ce:
    print(f"MongoDB Configuration Error: {ce}")
    print("This often means there's an issue with the connection string format or SSL settings.")
except pymongo.errors.ServerSelectionTimeoutError as sste:
    print(f"MongoDB Server Selection Timeout Error: {sste}")
    print("This usually means the MongoDB server is not reachable. Check:")
    print("  1. MongoDB server is running.")
    print("  2. Network/firewall rules allow connection from your IP to the MongoDB server.")
    print("  3. The hostname and port in MONGO_URL_TEST are correct.")
except pymongo.errors.ConnectionFailure as cf:
    print(f"MongoDB Connection Failure: {cf}")
    print("Could not connect to MongoDB. See details above.")
except Exception as e:
    print(f"An unexpected error occurred: {e}")

finally:
    if 'client' in locals() and client:
        client.close()
        print("MongoDB connection closed.") 