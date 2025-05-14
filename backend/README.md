# AI Detector Backend

**IMPORTANT DEPLOYMENT PREREQUISITES:**
1. **Azure Credentials Setup:**
   - Before any deployment, you MUST set up the following GitHub secrets:
     - `AZURE_CLIENT_ID`: The client ID of your Azure service principal
     - `AZURE_TENANT_ID`: Your Azure tenant ID
     - `AZURE_SUBSCRIPTION_ID`: Your Azure subscription ID
   - These credentials are required for GitHub Actions to authenticate with Azure and deploy resources
   - The service principal must have appropriate permissions to deploy and manage resources in your Azure subscription

This is the backend service for the AI Detector application, built with FastAPI and designed to run in Azure Container Apps.

## Project Structure

```
backend/
├── app/                    # Main application package
│   ├── api/               # API routes and endpoints
│   ├── core/              # Core application configuration
│   ├── db/                # Database connection and utilities
│   ├── migrations/        # Database migrations
│   ├── models/            # Data models and schemas
│   ├── services/          # Business logic and services
│   ├── tasks/             # Background tasks and workers
│   └── main.py           # Application entry point
├── tests/                 # Test suite
├── scripts/               # Utility scripts
├── documents/            # Documentation and reference materials
├── Dockerfile            # Container definition
├── requirements.txt      # Production dependencies
└── requirements-dev.txt  # Development dependencies
```

## Local Development Setup

1. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install development dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```

3. Set up environment variables:
   Create a `.env` file in the backend directory with the following variables:
   ```
   MONGODB_URL=your_mongodb_connection_string
   STORAGE_CONNECTION_STRING=your_storage_connection_string
   KINDLE_DOMAIN=your_kindle_domain
   KINDLE_AUDIENCE=your_kindle_audience
   KINDLE_CLIENT_SECRET=your_kindle_client_secret
   STRIPE_SECRET_KEY=your_stripe_secret_key
   ```

4. Run the development server:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

The API will be available at `http://localhost:8000`

## Container Deployment

The application is containerized using Docker and deployed to Azure Container Apps. The `Dockerfile` defines the container environment:

- Base image: Python 3.13 slim-bookworm
- Working directory: `/app`
- Environment optimizations:
  - Disabled Python bytecode writing
  - Unbuffered Python output
  - Optimized pip settings
- Exposed port: 8000
- Entry point: Uvicorn server running the FastAPI application

### Container Configuration

The container is configured with:
- Single worker process (can be scaled horizontally in Azure Container Apps)
- Host binding to `0.0.0.0` for external access
- Port 8000 exposed for HTTP traffic

## Key Components

### 1. API Layer (`app/api/`)
- RESTful endpoints for the application
- Request/response handling
- Input validation
- Authentication middleware

### 2. Core Configuration (`app/core/`)
- Application settings
- Environment configuration
- Security settings
- Constants and shared utilities

### 3. Database Layer (`app/db/`)
- MongoDB connection management
- Database utilities
- Connection pooling
- Error handling

### 4. Models (`app/models/`)
- Pydantic models for data validation
- Database models
- Request/response schemas

### 5. Services (`app/services/`)
- Business logic implementation
- External service integrations
- Data processing
- File handling

### 6. Tasks (`app/tasks/`)
- Background task processing
- Async operations
- Scheduled jobs

## Dependencies

### Core Dependencies
- FastAPI: Web framework
- Uvicorn: ASGI server
- Motor: MongoDB async driver
- Pydantic: Data validation
- Azure Storage Blob: File storage
- Python-jose: JWT handling
- Stripe: Payment processing

### Development Dependencies
- Pytest: Testing framework
- Black: Code formatting
- Flake8: Linting
- MyPy: Type checking

## Testing

Run the test suite:
```bash
pytest
```

For test coverage:
```bash
pytest --cov=app tests/
```

## Important Files

- `main.py`: Application entry point and FastAPI app configuration
- `Dockerfile`: Container definition for deployment
- `requirements.txt`: Production dependencies
- `requirements-dev.txt`: Development dependencies
- `pytest.ini`: Test configuration
- `fix_cosmos_index.py`: Database index management utility
- `indexes.json`: Database index definitions

## Environment Variables

The application requires the following environment variables:

- `MONGODB_URL`: MongoDB connection string
- `STORAGE_CONNECTION_STRING`: Azure Storage connection string
- `KINDLE_DOMAIN`: Kindle authentication domain
- `KINDLE_AUDIENCE`: Kindle authentication audience
- `KINDLE_CLIENT_SECRET`: Kindle client secret
- `STRIPE_SECRET_KEY`: Stripe API secret key

## API Documentation

When running the application, API documentation is available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc` 