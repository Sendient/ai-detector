# Detector Backend

This is the backend service for the AI Detector application, built with FastAPI and designed to handle document processing, AI analysis, and data management.

## Architecture Overview

The backend is structured as a modern FastAPI application with the following key components:

### Core Components

1. **API Layer**
   - RESTful API endpoints for document management, user authentication, and data operations
   - Built with FastAPI for high performance and automatic OpenAPI documentation
   - Organized into versioned endpoints (v1) with clear separation of concerns

2. **Document Processing Pipeline**
   - Handles document uploads, storage, and processing
   - Supports multiple file types (PDF, DOCX, TXT, PNG, JPG)
   - Integrates with Azure Blob Storage for file management
   - Implements text extraction for supported document types

3. **Batch Processing System**
   - Asynchronous batch processing for multiple documents
   - Priority-based queue system
   - Progress tracking and status updates
   - Error handling and retry mechanisms

4. **Data Management**
   - MongoDB database integration using Motor for async operations
   - Structured data models for schools, teachers, students, and documents
   - Comprehensive CRUD operations with transaction support
   - Soft delete functionality for data preservation

### Key Features

- **Authentication & Authorization**
  - Integration with Kinde for user authentication
  - Role-based access control
  - Secure API endpoints

- **Document Analysis**
  - Text extraction from various document formats
  - Integration with AI detection service
  - Result storage and retrieval

- **Monitoring & Health Checks**
  - Comprehensive health check endpoints
  - System metrics monitoring
  - Detailed logging system

## Prerequisites

- Python 3.8+
- MongoDB (local or Azure Cosmos DB)
- Azure Blob Storage account
- Kinde authentication setup

## Environment Setup

Create a `.env` file in the backend directory with the following variables:

```env
# Database
MONGODB_URL=your_mongodb_connection_string
DB_NAME=aidetector_dev

# Authentication
KINDE_DOMAIN=your_kinde_domain
KINDE_AUDIENCE=your_kinde_audience

# Azure Blob Storage
AZURE_BLOB_CONNECTION_STRING=your_blob_storage_connection_string
AZURE_BLOB_CONTAINER_NAME=uploaded-documents

# Optional: Stripe Integration
STRIPE_SECRET_KEY=your_stripe_secret_key
STRIPE_WEBHOOK_SECRET=your_stripe_webhook_secret

# Logging
LOG_LEVEL=INFO
```

## Installation

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Running the Application

### Local Development

1. Start the development server:
```bash
uvicorn app.main:app --reload --port 8000
```

2. Access the API documentation:
- Swagger UI: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc

### Docker Deployment

1. Build the Docker image:
```bash
docker build -t ai-detector-backend .
```

2. Run the container:
```bash
docker run -p 8000:8000 --env-file .env ai-detector-backend
```

## API Endpoints

### Document Management
- `POST /api/v1/documents/upload` - Upload a new document
- `POST /api/v1/documents/{document_id}/assess` - Trigger AI assessment
- `GET /api/v1/documents/{document_id}` - Get document metadata
- `GET /api/v1/documents/{document_id}/text` - Get document text content

### Batch Processing
- `POST /api/v1/documents/batch` - Upload multiple documents
- `GET /api/v1/documents/batch/{batch_id}` - Get batch status

### Health & Monitoring
- `GET /health` - Comprehensive health check
- `GET /healthz` - Liveness probe
- `GET /readyz` - Readiness probe

## Development Guidelines

### Code Structure
```
backend/
├── app/
│   ├── api/
│   │   └── v1/
│   │       └── endpoints/
│   ├── core/
│   ├── db/
│   ├── models/
│   ├── services/
│   └── tasks/
├── tests/
└── requirements.txt
```

### Best Practices
1. Use type hints consistently
2. Follow FastAPI dependency injection patterns
3. Implement proper error handling
4. Write comprehensive logging
5. Use transactions for data consistency
6. Follow REST API design principles

## Testing

Run the test suite:
```bash
pytest
```

## Contributing

1. Follow the existing code style and structure
2. Add appropriate tests for new features
3. Update documentation as needed
4. Use meaningful commit messages

## License

[Your License Here] 