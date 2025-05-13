# inspect_results.py
import asyncio
import os
import motor.motor_asyncio
from dotenv import load_dotenv # To load variables from .env file

# --- Configuration ---
# Read from environment variables specified in the .env file
DB_NAME_ENV_VAR = "DB_NAME"
CONNECTION_STRING_ENV_VAR = "MONGODB_URL"
COLLECTION_NAME = "results"
TEACHER_KINDE_ID_TO_CHECK = "kp_788807885ec6418f8116df5e65561b41"
# -------------------

async def inspect_data():
    """Connects to MongoDB and inspects results data for a specific teacher."""

    load_dotenv() # Load variables from .env file into environment

    # Read connection string and DB name from environment variables
    connection_string = os.getenv(CONNECTION_STRING_ENV_VAR)
    database_name = os.getenv(DB_NAME_ENV_VAR)

    if not connection_string:
        print(f"ERROR: {CONNECTION_STRING_ENV_VAR} environment variable not set.")
        print("Ensure it is defined in your .env file or system environment.")
        return
    if not database_name:
        print(f"ERROR: {DB_NAME_ENV_VAR} environment variable not set.")
        print("Ensure it is defined in your .env file or system environment.")
        return

    print(f"Connecting to MongoDB using {CONNECTION_STRING_ENV_VAR}...")
    try:
        # Increase timeout settings for Cosmos DB
        client = motor.motor_asyncio.AsyncIOMotorClient(
            connection_string,
            serverSelectionTimeoutMS=10000, # Increase server selection timeout to 10s
            connectTimeoutMS=10000         # Increase connection timeout to 10s
        )
        # Select database using the name from the environment variable
        db = client[database_name]
        collection = db[COLLECTION_NAME]
        print(f"Connected to database '{database_name}', collection '{COLLECTION_NAME}'")

        print(f"\n--- Finding results for teacher_id: {TEACHER_KINDE_ID_TO_CHECK} ---")

        count = 0
        # Find documents matching the teacher_id
        cursor = collection.find({"teacher_id": TEACHER_KINDE_ID_TO_CHECK})

        async for doc in cursor:
            count += 1
            doc_id = doc.get("_id", "N/A")
            status = doc.get("status", "N/A")
            score = doc.get("score", "N/A")
            score_type = type(score).__name__ # Get the type of the score field

            print(f"\nResult {count}:")
            print(f"  _id:    {doc_id}")
            print(f"  status: {status}")
            print(f"  score:  {score}")
            print(f"  score_type: {score_type}") # Check if score is a number

        if count == 0:
            print("\nNo results found for this teacher_id.")
        else:
            print(f"\n--- Found {count} total results for this teacher_id ---")

    except Exception as e:
        print(f"\nAn error occurred: {e}")
        # Log the full traceback for connection errors
        import traceback
        traceback.print_exc()
    finally:
        if 'client' in locals() and client:
            client.close()
            print("\nConnection closed.")

if __name__ == "__main__":
    # On Windows, default asyncio event loop policy might cause issues
    # If you get errors running, uncomment the line below
    # asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(inspect_data())