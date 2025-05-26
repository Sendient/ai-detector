# app/api/v1/endpoints/dashboard.py

import logging
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, status, Depends, Query
from datetime import datetime, timezone
from pydantic import BaseModel
import uuid # Added for potential future use

# Import authentication dependency
from ....core.security import get_current_user_payload

# Import CRUD functions
from ....db import crud
# Import Document model for response type
from ....models.document import Document
from ....models.teacher import Teacher  # Import Teacher model

# Setup logger
logger = logging.getLogger(__name__)

# Create router instance
router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)

# Define response models
class ScoreDistributionItem(BaseModel):
    range: str
    count: int

class ScoreDistributionResponse(BaseModel):
    distribution: List[ScoreDistributionItem]
    total_documents: int

@router.get(
    "/stats",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Get dashboard statistics (User specific)",
    description="Retrieves various statistics for the current authenticated teacher's dashboard."
)
async def get_dashboard_stats_endpoint(
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """Protected endpoint to get dashboard statistics for the current user."""
    logger.info(f"Endpoint /dashboard/stats called. Payload sub: {current_user_payload.get('sub')}")
    try:
        stats = await crud.get_dashboard_stats(current_user_payload)
        logger.info(f"Endpoint /dashboard/stats returning stats.")
        return stats
    except Exception as e:
        logger.error(f"!!! EXCEPTION IN /dashboard/stats ENDPOINT: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error fetching dashboard stats.")

@router.get(
    "/score-distribution",
    response_model=ScoreDistributionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get score distribution (User specific)",
    description="Retrieves the distribution of AI scores across different ranges for the current authenticated teacher."
)
async def get_score_distribution_endpoint(
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """Protected endpoint to get score distribution data for the current user."""
    logger.info(f"Endpoint /dashboard/score-distribution called. Payload sub: {current_user_payload.get('sub')}")
    try:
        result = await crud.get_score_distribution(current_user_payload)
        if result is None or not result.get("distribution"):
            logger.warning(f"Score distribution data not found or empty for user {current_user_payload.get('sub')}. Returning empty.")
            return ScoreDistributionResponse(distribution=[], total_documents=0)

        logger.info(f"Endpoint /dashboard/score-distribution returning distribution.")
        return ScoreDistributionResponse(
            distribution=[ScoreDistributionItem(**item) for item in result["distribution"]],
            total_documents=result.get("total_documents", 0)
        )
    except Exception as e:
        logger.error(f"!!! EXCEPTION IN /dashboard/score-distribution ENDPOINT: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error fetching score distribution.")

@router.get("/recent")
async def get_recent_documents_endpoint(
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Retrieves the 5 most recent documents for the logged-in teacher.
    """
    teacher_id = None # Initialize for logging in case of early error
    try:
        teacher_id = current_user_payload.get("sub") # Kinde user ID is in 'sub' claim
        if not teacher_id:
            # Log the payload for debugging if teacher_id is missing
            logger.warning(f"Teacher ID ('sub') missing in token payload: {current_user_payload}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Could not validate credentials or user ID missing")

        logger.info(f"Endpoint /dashboard/recent called for teacher {teacher_id}")

        # Get recent documents using the CRUD function
        # crud.get_recent_documents returns a List[Document]
        documents: List[Document] = await crud.get_recent_documents(teacher_id=teacher_id, limit=5) # Explicit limit
        logger.info(f"Endpoint /dashboard/recent - CRUD returned {len(documents)} documents.")

        # <<< START EDIT: Explicitly serialize response >>>
        response_data = []
        for doc in documents:
            # Manually construct the dictionary for the response
            # Accessing the attributes of the Pydantic model instance
            doc_dict = {
                # Ensure id is explicitly included using the model attribute
                "id": doc.id,
                "teacher_id": doc.teacher_id,
                "original_filename": doc.original_filename,
                "status": doc.status, # Will use enum value due to model config
                "created_at": doc.created_at,
                "updated_at": doc.updated_at,
                "score": doc.score, # ADDED: Include the score
                # The frontend AnalyticsPage table needs the AI score, but it's not here.
                # needs modification later to fetch/include score if required here. <- This comment is now outdated
            }
            # Add optional fields only if they exist and needed by frontend
            # <<< START EDIT: Add counts if they exist >>>
            if hasattr(doc, 'character_count') and doc.character_count is not None:
                 doc_dict["character_count"] = doc.character_count
            if hasattr(doc, 'word_count') and doc.word_count is not None:
                 doc_dict["word_count"] = doc.word_count
            # <<< END EDIT >>>

            response_data.append(doc_dict)
        # <<< END EDIT: Explicitly serialize response >>>

        # Log the exact data being returned
        logger.info(f"Returning response data for /dashboard/recent: {response_data}")
        return response_data # Return the list of dictionaries

    except HTTPException as http_exc:
        # Re-raise HTTPExceptions directly
        raise http_exc
    except Exception as e:
        logger.error(f"Error in /dashboard/recent endpoint for teacher {teacher_id}: {e}", exc_info=True)
        # Raise a generic 500 error for unexpected issues
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error fetching recent documents.")