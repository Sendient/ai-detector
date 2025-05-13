// MongoDB script to initialize collections and indexes to match the working database
// Run this script using: mongosh "your_connection_string" init_collections.js

// Read database name from environment variable, default to 'aidetector_dev1'
const dbName = process.env.MONGO_DB_NAME || 'aidetector_dev1';
db = db.getSiblingDB(dbName);

const collections = {
  documents: [
    { key: { _id: 1 } },
    { key: { teacher_id: 1, upload_timestamp: -1 }, name: 'teacher_timestamp_compound' }
  ],
  batches: [
    { key: { _id: 1 } },
    { key: { priority: -1, created_at: 1 }, name: 'priority_-1_created_at_1' }
  ],
  classgroups: [
    { key: { _id: 1 } }
  ],
  users: [
    { key: { _id: 1 } }
  ],
  students: [
    { key: { _id: 1 } }
  ],
  teachers: [
    { key: { _id: 1 } }
  ],
  results: [
    { key: { _id: 1 } }
  ]
};

function createCollectionWithIndexes(collectionName, indexes) {
  print(`\nProcessing collection: ${collectionName}`);
  if (!db.getCollectionNames().includes(collectionName)) {
    db.createCollection(collectionName);
    print(`✅ Created collection: ${collectionName}`);
  } else {
    print(`ℹ️ Collection already exists: ${collectionName}`);
  }
  const collection = db[collectionName];
  indexes.forEach(index => {
    try {
      const options = {};
      if (index.name) options.name = index.name;
      collection.createIndex(index.key, options);
      print(`✅ Created index on ${collectionName}: ${JSON.stringify(index)}`);
    } catch (error) {
      print(`❌ Error creating index on ${collectionName}: ${error.message}`);
    }
  });
}

Object.entries(collections).forEach(([collectionName, indexes]) => {
  createCollectionWithIndexes(collectionName, indexes);
});

print(`\nDatabase initialization completed for database: ${dbName}!`);
