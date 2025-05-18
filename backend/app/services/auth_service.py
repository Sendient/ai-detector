from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import uuid
from motor.motor_asyncio import AsyncIOMotorClient
from ..core.config import settings
from ..models.teacher import TeacherInDBBase, TeacherCreate
from ..core.security import verify_token

class AuthService:
    def __init__(self, db: AsyncIOMotorClient):
        self.db = db
        self.teachers_collection = db[settings.MONGODB_DB][settings.TEACHERS_COLLECTION]

    async def get_teacher_by_kinde_id(self, kinde_id: str) -> Optional[TeacherInDBBase]:
        """Get teacher by their Kinde ID."""
        teacher_data = await self.teachers_collection.find_one({"kinde_id": kinde_id})
        if teacher_data:
            return TeacherInDBBase(**teacher_data)
        return None

    async def get_teacher_by_uuid(self, teacher_uuid: str) -> Optional[TeacherInDBBase]:
        """Get teacher by their internal UUID."""
        teacher_data = await self.teachers_collection.find_one({"_id": teacher_uuid})
        if teacher_data:
            return TeacherInDBBase(**teacher_data)
        return None

    async def create_teacher(self, teacher_data: TeacherCreate, kinde_id: str, token_payload: Dict[str, Any]) -> TeacherInDBBase:
        """Create a new teacher with internal UUID and Kinde permissions."""
        teacher_dict = teacher_data.model_dump()
        
        # Extract permissions from Kinde token
        permissions = token_payload.get("permissions", [])
        org_code = token_payload.get("org_code")
        
        # Extract Kinde user details
        kinde_user_details = token_payload.get("user", {})
        
        teacher_dict.update({
            "_id": str(uuid.uuid4()),
            "kinde_id": kinde_id,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "is_deleted": False,
            "is_admin": "admin:all" in permissions,  # Use Kinde permission for admin status
            "kinde_permissions": permissions,
            "kinde_org_code": org_code,
            # Add Kinde user details
            "kinde_picture": kinde_user_details.get("picture"),
            "kinde_given_name": kinde_user_details.get("given_name"),
            "kinde_family_name": kinde_user_details.get("family_name")
        })
        
        await self.teachers_collection.insert_one(teacher_dict)
        return TeacherInDBBase(**teacher_dict)

    async def verify_teacher_access(self, teacher_uuid: str, resource_teacher_id: str, required_permission: Optional[str] = None) -> bool:
        """Verify if a teacher has access to a resource with optional permission check."""
        teacher = await self.get_teacher_by_uuid(teacher_uuid)
        if not teacher:
            return False
        
        # Check Kinde permissions if required
        if required_permission:
            if required_permission not in teacher.kinde_permissions:
                return False
        
        # Admin teachers have access to all resources
        if teacher.is_admin:
            return True
        
        # Regular teachers can only access their own resources
        return teacher_uuid == resource_teacher_id

    async def verify_token_and_get_teacher(self, token: str) -> Optional[TeacherInDBBase]:
        """Verify token and return associated teacher."""
        payload = verify_token(token)
        if not payload:
            return None
        
        kinde_id = payload.get("sub")
        if not kinde_id:
            return None
        
        teacher = await self.get_teacher_by_kinde_id(kinde_id)
        if teacher:
            # Update teacher's permissions and details from token
            teacher.kinde_permissions = payload.get("permissions", [])
            teacher.kinde_org_code = payload.get("org_code")
            
            # Update Kinde user details
            kinde_user_details = payload.get("user", {})
            teacher.kinde_picture = kinde_user_details.get("picture")
            teacher.kinde_given_name = kinde_user_details.get("given_name")
            teacher.kinde_family_name = kinde_user_details.get("family_name")
            
            # Update in database
            await self.teachers_collection.update_one(
                {"_id": teacher.id},
                {"$set": {
                    "kinde_permissions": teacher.kinde_permissions,
                    "kinde_org_code": teacher.kinde_org_code,
                    "kinde_picture": teacher.kinde_picture,
                    "kinde_given_name": teacher.kinde_given_name,
                    "kinde_family_name": teacher.kinde_family_name,
                    "updated_at": datetime.now(timezone.utc)
                }}
            )
        return teacher

    async def is_admin(self, teacher_uuid: str) -> bool:
        """Check if a teacher has admin privileges."""
        teacher = await self.get_teacher_by_uuid(teacher_uuid)
        return teacher.is_admin if teacher else False

    async def get_teacher_permissions(self, teacher_uuid: str) -> List[str]:
        """Get all permissions for a teacher."""
        teacher = await self.get_teacher_by_uuid(teacher_uuid)
        return teacher.kinde_permissions if teacher else []

    async def has_permission(self, teacher_uuid: str, permission: str) -> bool:
        """Check if a teacher has a specific permission."""
        permissions = await self.get_teacher_permissions(teacher_uuid)
        return permission in permissions 