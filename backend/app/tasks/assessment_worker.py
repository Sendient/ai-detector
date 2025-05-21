"""Background worker to process assessment tasks."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import httpx

from ..queue import dequeue_assessment_task, AssessmentTask
from ..services.blob_storage import download_blob_as_bytes
from ..services.text_extraction import extract_text_from_bytes
from ..db import crud
from ..db.database import get_database
from ..models.enums import DocumentStatus, ResultStatus, FileType

# Temporary: same ML API URL used in documents endpoint
ML_API_URL = "https://fa-sdt-uks-aitextdet-prod.azurewebsites.net/api/ai-text-detection?code=PZrMzMk1VBBCyCminwvgUfzv_YGhVU-5E1JIs2if7zqiAzFuMhUC-g%3D%3D"

logger = logging.getLogger(__name__)


class AssessmentWorker:
    """Worker that continuously polls the assessment queue and processes documents."""

    def __init__(self) -> None:
        self.is_running = False

    async def run(self) -> None:
        self.is_running = True
        while self.is_running:
            try:
                task = await dequeue_assessment_task()
                if not task:
                    await asyncio.sleep(5)
                    continue

                await self._process_task(task)
            except Exception as e:
                logger.error(f"Assessment worker encountered error: {e}", exc_info=True)
                await asyncio.sleep(5)

    def stop(self) -> None:
        self.is_running = False

    async def _process_task(self, task: AssessmentTask) -> None:
        logger.info(f"Processing assessment task {task.id} attempt {task.attempts}")

        document = await crud.get_document_by_id(task.document_id, task.user_id)
        if not document:
            logger.error(f"Document {task.document_id} not found for task {task.id}")
            await self._dead_letter(task, reason="Document not found")
            return

        # Update processing attempts on the document
        await self._update_document_attempts(task.document_id, task.user_id, task.attempts)

        try:
            await crud.update_document_status(
                document_id=document.id,
                teacher_id=document.teacher_id,
                status=DocumentStatus.PROCESSING,
            )

            file_bytes = await download_blob_as_bytes(document.storage_blob_path)
            if not file_bytes:
                raise RuntimeError("Failed to download blob")

            # ensure FileType enum
            file_type = document.file_type
            if isinstance(file_type, str):
                try:
                    file_type = FileType(file_type)
                except ValueError:
                    raise RuntimeError(f"Unsupported file type: {document.file_type}")

            text_content = await asyncio.to_thread(extract_text_from_bytes, file_bytes, file_type)
            if text_content is None:
                raise RuntimeError("Text extraction returned None")

            character_count = len(text_content)
            word_count = len([w for w in text_content.split() if w])

            ai_score, label, ai_generated, human_generated, paragraph_results = await self._call_ai(text_content)

            result = await crud.get_result_by_document_id(document_id=document.id, teacher_id=document.teacher_id)
            if result:
                update_payload: Dict[str, Any] = {
                    "status": ResultStatus.COMPLETED.value,
                    "result_timestamp": datetime.now(timezone.utc),
                }
                if ai_score is not None:
                    update_payload["score"] = ai_score
                if label is not None:
                    update_payload["label"] = label
                if ai_generated is not None:
                    update_payload["ai_generated"] = ai_generated
                if human_generated is not None:
                    update_payload["human_generated"] = human_generated
                if paragraph_results is not None:
                    update_payload["paragraph_results"] = paragraph_results

                await crud.update_result(result_id=result.id, update_data=update_payload, teacher_id=document.teacher_id)

            await crud.update_document_status(
                document_id=document.id,
                teacher_id=document.teacher_id,
                status=DocumentStatus.COMPLETED,
                character_count=character_count,
                word_count=word_count,
            )

            await self._complete_task(task)

        except Exception as e:
            logger.error(f"Error processing assessment task {task.id}: {e}", exc_info=True)
            await crud.update_document_status(
                document_id=document.id,
                teacher_id=document.teacher_id,
                status=DocumentStatus.ERROR,
            )
            if task.attempts >= 5:
                await self._dead_letter(task, reason=str(e))
            # Otherwise task will reappear after visibility timeout

    async def _update_document_attempts(self, document_id, teacher_id, attempts: int) -> None:
        db = get_database()
        if not db:
            return
        await db.documents.update_one(
            {"_id": document_id, "teacher_id": teacher_id},
            {"$set": {"processing_attempts": attempts, "updated_at": datetime.now(timezone.utc)}},
        )

    async def _complete_task(self, task: AssessmentTask) -> None:
        db = get_database()
        if not db:
            return
        await db.assessment_tasks.delete_one({"_id": task.id})

    async def _dead_letter(self, task: AssessmentTask, reason: str) -> None:
        logger.warning(f"Moving task {task.id} to dead letter queue: {reason}")
        db = get_database()
        if not db:
            return
        await db.assessment_tasks.delete_one({"_id": task.id})
        task_dict = task.model_dump(by_alias=True)
        task_dict["status"] = "FAILED"
        task_dict["error"] = reason
        await db.assessment_deadletter.insert_one(task_dict)

    async def _call_ai(self, text: str) -> tuple[Optional[float], Optional[str], Optional[bool], Optional[bool], Optional[list]]:
        headers = {"Content-Type": "application/json"}
        payload = {"text": text}
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(ML_API_URL, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        ai_generated = data.get("ai_generated") if isinstance(data.get("ai_generated"), bool) else None
        human_generated = data.get("human_generated") if isinstance(data.get("human_generated"), bool) else None
        label = None
        score = None
        paragraph_results = None
        if isinstance(data, dict):
            if isinstance(data.get("results"), list) and data["results"]:
                paragraph_results = data["results"] if all(isinstance(i, dict) for i in data["results"]) else None
                first = data["results"][0]
                label = first.get("label") if isinstance(first.get("label"), str) else None
                prob = first.get("probability")
                if isinstance(prob, (int, float)):
                    score = max(0.0, min(1.0, float(prob)))
        return score, label, ai_generated, human_generated, paragraph_results
