import logging
from typing import Callable, Awaitable
import uuid

from app.queue import dequeue_assessment_task, enqueue_assessment_task
from app.db import crud
from app.models.enums import DocumentStatus, ResultStatus
from app.services.blob_storage import download_blob_as_bytes
from app.services.text_extraction import extract_text_from_bytes

logger = logging.getLogger(__name__)

AIServiceCallable = Callable[[str], Awaitable[float]]

async def process_next_task(ai_service: AIServiceCallable) -> bool:
    """Process a single assessment task from the queue."""
    task = await dequeue_assessment_task()
    if not task:
        return False

    document = await crud.get_document_by_id(task.document_id, teacher_id=task.user_id)
    if not document:
        return False

    await crud.update_document_status(
        document_id=document.id,
        teacher_id=task.user_id,
        status=DocumentStatus.PROCESSING,
    )

    try:
        blob = await download_blob_as_bytes(document.storage_blob_path)
        text = extract_text_from_bytes(blob or b"", document.file_type)
        score = await ai_service(text or "")
        result = await crud.get_result_by_document_id(document.id, teacher_id=task.user_id)
        if result:
            await crud.update_result(
                result_id=result.id,
                update_data={"status": ResultStatus.COMPLETED, "score": score},
                teacher_id=task.user_id,
            )
        await crud.update_document_status(
            document_id=document.id,
            teacher_id=task.user_id,
            status=DocumentStatus.COMPLETED,
        )
        return True
    except Exception:
        await enqueue_assessment_task(task.document_id, task.user_id, task.priority_level)
        await crud.update_document_status(
            document_id=document.id,
            teacher_id=task.user_id,
            status=DocumentStatus.QUEUED,
        )
        return False


