# backend/app/api/v1/endpoints/analytics.py

import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from datetime import date
from typing import Dict, Any
from enum import Enum

from ....core.security import get_current_user_payload
from ....db import crud
from ....models.analytics import UsageStatsResponse

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

@router.get(
    "/all-time-stats",
    response_model=UsageStatsResponse, # We can reuse this if it fits, or create a new one
    summary="Get all-time usage statistics (Protected)",
    description="Retrieves aggregated document counts, character counts, and word counts for the authenticated teacher across all time."
)
async def get_all_time_usage_statistics(
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    if not user_kinde_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User Kinde ID not found in token.")

    logger.info(f"User {user_kinde_id} requesting all-time usage stats.")

    try:
        usage_data = await crud.get_usage_stats_for_period(
            teacher_id=user_kinde_id
            # period and target_date are omitted to get all-time stats
        )

        if usage_data is None:
            logger.error(f"CRUD function get_usage_stats_for_period returned None for all-time stats for user {user_kinde_id}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve all-time usage statistics due to an internal error.")

        # Ensure the response includes period and target_date as null or a specific string if the model expects them
        # The `UsageStatsResponse` model has `period`, `target_date`, `start_date`, `end_date` as optional.
        # The crud function, when fetching all-time, should set these appropriately (e.g. to None or a specific marker).
        # For now, let's assume the crud function returns them as None for all-time.
        # If UsageStatsResponse requires these to be non-None, this might need adjustment or a new response model.
        # From the previous step, period_start_str and period_end_str were set to None in crud for all-time.
        # The crud.get_usage_stats_for_period returns: 
        # {"teacher_id": ..., "document_count": ..., etc., "period_start_date": None, "period_end_date": None }
        # This should be compatible with UsageStatsResponse if period_start_date/end_date are Optional[date].
        # The `UsageStatsResponse` model in `models/analytics.py` has: 
        # period: Optional[str] = None
        # target_date: Optional[date] = None
        # start_date: Optional[date] = None
        # end_date: Optional[date] = None
        # So this is fine. The crud function will return these as None for all-time stats.

        return usage_data

    except Exception as e:
        logger.error(f"Unexpected error getting all-time usage stats for {user_kinde_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal error occurred while fetching all-time usage statistics.") 