# backend/app/api/v1/endpoints/analytics.py

import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from datetime import date
from typing import Dict, Any
from enum import Enum

from app.core.security import get_current_user_payload
from app.db import crud
from app.models.analytics import UsageStatsResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/analytics",
    tags=["Analytics"]
)

class PeriodOption(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"

@router.get(
    "/usage/{period}",
    response_model=UsageStatsResponse,
    summary="Get usage statistics for a specific period (Protected)",
    description="Retrieves aggregated document counts, character counts, and word counts for the authenticated teacher "
                "within a specified daily, weekly, or monthly period based on a target date."
)
async def get_usage_statistics(
    period: PeriodOption = Path(..., description="The time period to aggregate usage for (daily, weekly, monthly)."),
    target_date: date = Query(..., description="The target date to calculate the period around (e.g., YYYY-MM-DD)."),
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    if not user_kinde_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User Kinde ID not found in token.")

    logger.info(f"User {user_kinde_id} requesting usage stats for period '{period.value}' around target date '{target_date}'")

    try:
        # Call the CRUD function
        usage_data = await crud.get_usage_stats_for_period(
            teacher_id=user_kinde_id,
            period=period.value,
            target_date=target_date
        )

        if usage_data is None:
            # If CRUD returns None (e.g., on DB error), raise a 500
            # The CRUD function itself handles returning zero counts if no documents are found
            logger.error(f"CRUD function get_usage_stats_for_period returned None for user {user_kinde_id}, period {period.value}, date {target_date}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve usage statistics due to an internal error.")

        # Validate response against Pydantic model implicitly via FastAPI
        # Ensure the returned dict matches UsageStatsResponse structure
        return usage_data

    except ValueError as ve:
        # Catch potential errors from date calculations in CRUD
        logger.error(f"Value error getting usage stats for {user_kinde_id}: {ve}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Unexpected error getting usage stats for {user_kinde_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal error occurred while fetching usage statistics.") 