from typing import Optional, Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, OAuth2PasswordBearer
from motor.motor_asyncio import AsyncIOMotorDatabase
from ..core.config import settings
from ..services.auth_service import AuthService
from ..models.teacher import TeacherInDBBase
import uuid
from ..db.database import get_database

security = HTTPBearer()

async def get_db_session() -> AsyncIOMotorDatabase:
    """Get database session from the global database setup."""
    db = get_database()
    if db is None:
        # This should ideally not happen if connect_to_mongo is called at startup
        # and handles errors robustly. Consider more specific error handling or logging.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is not available."
        )
    yield db # FastAPI handles this as a dependency; no try/finally/close needed here for yielded global instance

async def get_auth_service(db: Annotated[AsyncIOMotorDatabase, Depends(get_db_session)]) -> AuthService:
    """Get auth service instance."""
    return AuthService(db)

async def get_current_teacher(
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]
) -> TeacherInDBBase:
    """Get current authenticated teacher."""
    teacher = await auth_service.verify_token_and_get_teacher(credentials.credentials)
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if teacher.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated",
        )
    return teacher

async def verify_resource_access(
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    current_teacher: Annotated[TeacherInDBBase, Depends(get_current_teacher)],
    resource_teacher_id: uuid.UUID
) -> bool:
    """Verify if current teacher has access to a resource."""
    has_access = await auth_service.verify_teacher_access(current_teacher.id, resource_teacher_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions to access this resource"
        )
    return True

async def verify_admin_access(
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    current_teacher: Annotated[TeacherInDBBase, Depends(get_current_teacher)]
) -> bool:
    """Verify if current teacher has admin access."""
    is_admin = await auth_service.is_admin(current_teacher.id)
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return True 