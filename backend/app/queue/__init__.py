from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from pydantic import BaseModel, Field
from pymongo import ReturnDocument
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..db.database import get_database

# Default configuration values
DEFAULT_VISIBILITY_TIMEOUT = 60  # seconds
MAX_ATTEMPTS = 5

logger = logging.getLogger(__name__)

class AssessmentTask(BaseModel):
    """Model representing a queued assessment task."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, alias="_id")
    document_id: uuid.UUID
    user_id: str
    priority_level: int = 0
    attempts: int = 0
    status: str = "PENDING"
    available_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    retry_count: int = Field(default=0)
    last_error: Optional[str] = Field(default=None)

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True

async def enqueue_assessment_task(document_id: uuid.UUID, user_id: str, priority_level: int, db: Optional[AsyncIOMotorDatabase] = None, session=None) -> bool:
    """Add a new assessment task to the queue."""
    if db is None:
        db = get_database()
    
    if db is None:
        logger.error("Failed to get database for enqueue_assessment_task.")
        return False
    task = AssessmentTask(document_id=document_id, user_id=user_id, priority_level=priority_level)
    result = await db.assessment_tasks.insert_one(task.model_dump(by_alias=True), session=session)
    if not result.acknowledged:
        logger.error(f"Failed to insert assessment task for document {document_id}. Insert not acknowledged.")
        return False
    logger.info(f"Successfully enqueued assessment task for document {document_id} with task ID {task.id}.")
    return True

async def _claim_next_task(db: AsyncIOMotorDatabase, visibility_timeout: int) -> Optional[dict]:
    now = datetime.now(timezone.utc)
    filter_query = {
        "available_at": {"$lt": now},  # Ensure task is available
        "$or": [
            {"status": "PENDING"},
            {"status": "IN_PROGRESS"},
        ]
    }
    update_doc = {
        "$set": {
            "status": "IN_PROGRESS",
            "available_at": now + timedelta(seconds=visibility_timeout),
            "updated_at": now,
        },
        "$inc": {"attempts": 1},
    }
    sort = [("priority_level", -1), ("created_at", 1)]
    logger.debug(f"_claim_next_task: Executing find_one_and_update with filter: {filter_query}, sort: {sort}")
    task_doc = await db.assessment_tasks.find_one_and_update(
        filter=filter_query,
        update=update_doc,
        sort=sort,
        return_document=ReturnDocument.AFTER,
    )
    logger.debug(f"_claim_next_task: find_one_and_update returned: {task_doc}")
    return task_doc

async def dequeue_assessment_task(
    visibility_timeout: int = DEFAULT_VISIBILITY_TIMEOUT, 
    max_attempts: int = MAX_ATTEMPTS,
    db: Optional[AsyncIOMotorDatabase] = None
) -> Optional[AssessmentTask]:
    """Retrieve the highest priority task, handling dead letters and at-least-once delivery."""
    if db is None:
        current_db = get_database()
    else:
        current_db = db
        
    if current_db is None:
        return None

    while True:
        task_dict = await _claim_next_task(current_db, visibility_timeout)
        if task_dict is None:
            return None
        if task_dict.get("attempts", 0) > max_attempts:
            await current_db.assessment_tasks.delete_one({"_id": task_dict["_id"]})
            task_dict["status"] = "DEAD_LETTER"
            await current_db.assessment_deadletter.insert_one(task_dict)
            # try to get another task
            continue
        return AssessmentTask(**task_dict)
