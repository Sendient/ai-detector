@description('Name of the existing Cosmos DB account.')
param cosmosDbAccountName string

@description('Name of the MongoDB database to create or use.')
param databaseName string = 'aidetector_dev1' // Default from your logs

@description('Location of the Cosmos DB account. Should match the account\'s location.')
param location string = resourceGroup().location

@description('Default throughput settings for collections.')
param autoscaleMaxThroughput int = 4000 // Default for autoscale, adjust as needed

// Define collection names as an array for easier management if you prefer
var collectionNames = {
  schools: 'schools'
  teachers: 'teachers'
  classgroups: 'classgroups'
  students: 'students'
  assignments: 'assignments'
  documents: 'documents'
  results: 'results'
  batches: 'batches'
}

resource cosmosDbAccount 'Microsoft.DocumentDB/databaseAccounts@2023-11-15' existing = {
  name: cosmosDbAccountName
}

resource mongoDb 'Microsoft.DocumentDB/databaseAccounts/mongodbDatabases@2023-11-15' = {
  parent: cosmosDbAccount
  name: databaseName
  location: location
  properties: {
    resource: {
      id: databaseName
    }
    options: {
      autoscaleSettings: {
        maxThroughput: autoscaleMaxThroughput // Throughput can also be set at DB level if not using shared collection throughput
      }
    }
  }
}

// --- Collections Definition ---

resource schoolsCollection 'Microsoft.DocumentDB/databaseAccounts/mongodbDatabases/collections@2023-11-15' = {
  parent: mongoDb
  name: collectionNames.schools
  location: location
  properties: {
    resource: {
      id: collectionNames.schools
      shardKey: {
        _id: 'Hashed' // Assuming _id is a GUID/UUID for good distribution
      }
      indexes: [
        {
          key: {
            keys: [ '_id' ]
          }
        }
        {
          key: {
            keys: [ 'is_deleted' ] // For soft_delete_filter
          }
        }
        // Add other specific indexes for schools if needed based on common queries
      ]
    }
    options: {
      autoscaleSettings: {
        maxThroughput: autoscaleMaxThroughput
      }
    }
  }
}

resource teachersCollection 'Microsoft.DocumentDB/databaseAccounts/mongodbDatabases/collections@2023-11-15' = {
  parent: mongoDb
  name: collectionNames.teachers
  location: location
  properties: {
    resource: {
      id: collectionNames.teachers
      shardKey: {
        _id: 'Hashed'
      }
      indexes: [
        {
          key: {
            keys: [ '_id' ]
          }
        }
        {
          key: {
            keys: [ 'kinde_id' ]
          }
          options: {
            unique: true // As per code comment "assumes you have a unique index on 'kinde_id'"
          }
        }
        {
          key: {
            keys: [ 'is_deleted' ]
          }
        }
        {
          key: {
            keys: [ 'kinde_id', 'is_deleted' ] // For get_teacher_by_kinde_id with soft delete
          }
        }
        {
          key: {
            keys: [ 'school_id', 'is_deleted' ] // For get_teachers_by_school
          }
        }
      ]
    }
    options: {
      autoscaleSettings: {
        maxThroughput: autoscaleMaxThroughput
      }
    }
  }
}

resource classgroupsCollection 'Microsoft.DocumentDB/databaseAccounts/mongodbDatabases/collections@2023-11-15' = {
  parent: mongoDb
  name: collectionNames.classgroups
  location: location
  properties: {
    resource: {
      id: collectionNames.classgroups
      shardKey: {
        _id: 'Hashed'
      }
      indexes: [
        {
          key: {
            keys: [ '_id' ]
          }
        }
        {
          key: {
            keys: [ 'is_deleted' ]
          }
        }
        {
          key: {
            keys: [ 'teacher_id', 'is_deleted' ] // For get_all_class_groups by teacher
          }
        }
        {
          key: {
            keys: [ 'student_ids' ] // For $addToSet/$pull operations
          }
        }
      ]
    }
    options: {
      autoscaleSettings: {
        maxThroughput: autoscaleMaxThroughput
      }
    }
  }
}

resource studentsCollection 'Microsoft.DocumentDB/databaseAccounts/mongodbDatabases/collections@2023-11-15' = {
  parent: mongoDb
  name: collectionNames.students
  location: location
  properties: {
    resource: {
      id: collectionNames.students
      // Consider if teacher_id is a good shard key if high cardinality and frequent teacher-scoped queries.
      // For now, _id is safer for general distribution.
      shardKey: {
        _id: 'Hashed'
      }
      indexes: [
        {
          key: {
            keys: [ '_id' ]
          }
        }
        {
          key: {
            keys: [ 'is_deleted' ]
          }
        }
        {
          key: {
            keys: [ 'teacher_id', 'is_deleted' ] // For get_all_students, get_student_by_id
          }
        }
        {
          key: {
            keys: [ 'teacher_id', '_id', 'is_deleted' ] // Specifically for get_student_by_id
          }
        }
        {
          key: {
            keys: [ 'teacher_id', 'external_student_id' ] // Potentially unique as per DuplicateKeyError handling.
          }
          // If it MUST be unique for a teacher:
          // options: {
          //   unique: true
          // }
          // Note: Cosmos DB unique indexes apply globally. For per-teacher uniqueness,
          // you often handle it at the application layer or use a compound unique key that includes teacher_id.
          // The unique option here would make external_student_id globally unique if not combined with teacher_id in a specific unique index syntax.
          // For compound unique index: keys: [ 'teacher_id', 'external_student_id' ], options: { unique: true }
        }
        {
          key: {
            keys: [ 'teacher_id', 'year_group', 'is_deleted' ] // For get_all_students
          }
        }
        // Regex queries on first_name, last_name are harder to optimize with standard indexes.
        // Consider text indexes if full-text search is needed, or ensure queries are anchored (^).
      ]
    }
    options: {
      autoscaleSettings: {
        maxThroughput: autoscaleMaxThroughput
      }
    }
  }
  // Example of a compound unique index (if needed for students)
  // Make sure to check exact syntax for unique compound keys in Cosmos MongoDB Bicep
  // This is a conceptual representation, the 'indexes' array takes individual index definitions.
  // You would define ONE index object with multiple keys for a compound index.
  // Example for unique (teacher_id, external_student_id):
  // {
  //   key: { keys: [ 'teacher_id', 'external_student_id' ] },
  //   options: { unique: true }
  // }
}

resource assignmentsCollection 'Microsoft.DocumentDB/databaseAccounts/mongodbDatabases/collections@2023-11-15' = {
  parent: mongoDb
  name: collectionNames.assignments
  location: location
  properties: {
    resource: {
      id: collectionNames.assignments
      shardKey: {
        _id: 'Hashed'
      }
      indexes: [
        {
          key: {
            keys: [ '_id' ]
          }
        }
        {
          key: {
            keys: [ 'is_deleted' ]
          }
        }
        {
          key: {
            keys: [ 'class_group_id', 'is_deleted' ] // For get_all_assignments
          }
        }
      ]
    }
    options: {
      autoscaleSettings: {
        maxThroughput: autoscaleMaxThroughput
      }
    }
  }
}

resource documentsCollection 'Microsoft.DocumentDB/databaseAccounts/mongodbDatabases/collections@2023-11-15' = {
  parent: mongoDb
  name: collectionNames.documents
  location: location
  properties: {
    resource: {
      id: collectionNames.documents
      // Consider teacher_id as shard key if it offers good cardinality and distribution for document data.
      // Defaulting to _id for general safety.
      shardKey: {
        _id: 'Hashed' // or teacher_id: 'Hashed' if appropriate
      }
      indexes: [
        {
          key: {
            keys: [ '_id' ]
          }
        }
        {
          key: {
            keys: [ 'is_deleted' ]
          }
        }
        {
          key: {
            keys: [ 'teacher_id', 'is_deleted' ] // Base for many document queries
          }
        }
        {
          key: {
            keys: [ 'teacher_id', '_id', 'is_deleted' ] // For get_document_by_id
          }
        }
        {
          key: {
            keys: [ 'teacher_id', 'student_id', 'is_deleted' ]
          }
        }
        {
          key: {
            keys: [ 'teacher_id', 'assignment_id', 'is_deleted' ]
          }
        }
        {
          key: {
            keys: [ 'teacher_id', 'status', 'is_deleted' ]
          }
        }
        {
          key: {
            keys: [ 'teacher_id', 'upload_timestamp' ] // For get_recent_documents (sorts by upload_timestamp desc)
            // If sort is always desc: keys: [ 'teacher_id', 'upload_timestamp:-1' ]
            // Bicep uses string 'ascending'/'descending' or integer 1/-1. Let's use string for clarity.
            // The API actually expects `keys: [ 'field1', 'field2:-1']` or for Bicep `[{key:'field1'}, {key:'field2', order:'descending'}]`
            // For CosmosDB, standard index definition doesn't specify order in the `keys` array for compound,
            // but queries utilize it. The Bicep definition here creates the fields for indexing.
            // Sorting is handled by the query engine using the available indexed fields.
            // A specific sort order index like { 'teacher_id': 1, 'upload_timestamp': -1 } is standard.
          }
        }
        { // Specific index for sorting recent documents
          key: {
            keys: [ 'teacher_id', 'upload_timestamp' ] // Query will specify direction
          }
        }
        {
          key: {
            keys: [ 'batch_id' ] // For get_documents_by_batch_id
          }
        }
        {
          key: {
            keys: [ 'batch_id', 'status' ] // For get_batch_status_summary
          }
        }
      ]
    }
    options: {
      autoscaleSettings: {
        maxThroughput: autoscaleMaxThroughput
      }
    }
  }
}

resource resultsCollection 'Microsoft.DocumentDB/databaseAccounts/mongodbDatabases/collections@2023-11-15' = {
  parent: mongoDb
  name: collectionNames.results
  location: location
  properties: {
    resource: {
      id: collectionNames.results
      shardKey: {
        _id: 'Hashed' // or document_id: 'Hashed' or teacher_id: 'Hashed'
      }
      indexes: [
        {
          key: {
            keys: [ '_id' ]
          }
        }
        {
          key: {
            keys: [ 'is_deleted' ]
          }
        }
        {
          key: {
            keys: [ 'document_id', 'is_deleted' ] // For get_result_by_document_id
          }
        }
        {
          key: {
            // For dashboard/stats queries (equality on teacher_id, status, then ranges/sorts on score/updated_at)
            keys: [ 'teacher_id', 'status', 'score', 'updated_at' ]
          }
        }
        // You might not need all permutations if the above compound index is used effectively by queries.
        // For example, (teacher_id, status, score) is a prefix of the above.
      ]
    }
    options: {
      autoscaleSettings: {
        maxThroughput: autoscaleMaxThroughput
      }
    }
  }
}

resource batchesCollection 'Microsoft.DocumentDB/databaseAccounts/mongodbDatabases/collections@2023-11-15' = {
  parent: mongoDb
  name: collectionNames.batches
  location: location
  properties: {
    resource: {
      id: collectionNames.batches
      shardKey: {
        _id: 'Hashed'
      }
      indexes: [
        {
          key: {
            keys: [ '_id' ]
          }
        }
        // Add other indexes if common query patterns for batches emerge
      ]
    }
    options: {
      autoscaleSettings: {
        maxThroughput: autoscaleMaxThroughput
      }
    }
  }
}
