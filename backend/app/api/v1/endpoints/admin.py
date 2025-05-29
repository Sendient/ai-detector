# backend/app/api/v1/endpoints/admin.py

import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, status

from ....core.security import require_kinde_admin_role # Adjusted import path

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(require_kinde_admin_role)] # Apply to all routes in this router
)

@router.get(
    "/overview",
    status_code=status.HTTP_200_OK,
    summary="Get Admin Dashboard Overview (Protected)",
    description="Provides a basic overview for the admin dashboard. Requires admin privileges."
)
async def get_admin_overview(
    # current_user_payload: Dict[str, Any] = Depends(require_kinde_admin_role) # Dependency already at router level
    # If you need the payload specifically in the function, you can still add it:
    payload: Dict[str, Any] = Depends(require_kinde_admin_role) # Or Depends(get_current_user_payload) if you want it without re-validating role here
) -> Dict[str, str]:
    logger.info(f"Admin user {payload.get('sub')} accessed admin overview.")
    return {"message": "Welcome to the Admin Dashboard! You have admin access."}

# Add other admin-specific endpoints here in the future 