from pymongo import MongoClient
import time

# Connect to your Cosmos DB with your provided connection string
connection_string = "mongodb://mongo-sdt-uks-aid-dev1:PK8WirVV8QcSuchgUAy1HPMqo6bS3bTe8ae2JLooGDh4AfWFB9sTuhiYrKDjT7g9CsFkp2m2HABtACDbcGSvTA==@mongo-sdt-uks-aid-dev1.mongo.cosmos.azure.com:10255/?ssl=true&replicaSet=globaldb&retrywrites=false&maxIdleTimeMS=120000&appName=@mongo-sdt-uks-aid-dev1@"
client = MongoClient(connection_string)
db = client.aidetector_dev1

# 1. Drop the collection if it exists
try:
    db.drop_collection("teachers")
    print("Existing 'teachers' collection dropped.")
except Exception as e:
    print(f"No collection to drop or error: {e}")

# 2. Create the new collection (it might be automatically created)
try:
    db.create_collection("teachers")
    print("New 'teachers' collection created.")
except Exception as e:
    print(f"Collection creation error (might already exist): {e}")
    # Continue anyway as the collection might be created automatically

# 3. Create the unique index
try:
    result = db.teachers.create_index("kinde_id", unique=True)
    print(f"Unique index on 'kinde_id' created successfully: {result}")
except Exception as e:
    print(f"Error creating index: {e}")

# 4. Verify the index was created
try:
    indexes = db.teachers.index_information()
    print(f"Current indexes on teachers collection: {indexes}")
    
    # Check if our unique index exists
    has_unique_index = any(
        'kinde_id' in str(idx['key']) and idx.get('unique', False) 
        for name, idx in indexes.items()
    )
    
    if has_unique_index:
        print("SUCCESS: Unique index on 'kinde_id' verified.")
    else:
        print("WARNING: Unique index not found after creation attempt.")
except Exception as e:
    print(f"Error verifying indexes: {e}")