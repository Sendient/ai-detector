# backend/app/tasks/assessment_worker.py
import asyncio
import logging
import time # For a simple delay in the loop
import random # For dummy score
from typing import Optional, List, Dict, Any
import uuid
from datetime import datetime, timezone
import os

# Import database functions and models
from ..db import crud
from ..db.database import get_database # Added to allow worker to get DB instance
from ..models.enums import DocumentStatus, ResultStatus
from ..models.result import Result, ResultCreate # To type hint the task and create initial result
from ..models.document import Document # For type hinting
from ..queue import AssessmentTask, dequeue_assessment_task, DEFAULT_VISIBILITY_TIMEOUT, MAX_ATTEMPTS # MODIFIED: Import new items
import httpx # For ML API call
from ..services.blob_storage import download_blob_as_bytes
from ..services.text_extraction import extract_text_from_bytes, FileType # Assuming FileType is in text_extraction or models.enums
import re # For word count
from ..core.config import settings # MODIFIED: Import settings

logger = logging.getLogger(__name__)

class AssessmentWorker:
    def __init__(self, poll_interval: int = 10):
        """
        Initializes the AssessmentWorker.
        Args:
            poll_interval: Time in seconds to wait between polling for new tasks.
        """
        self.poll_interval = poll_interval
        self._running = False
        logger.info(f"AssessmentWorker initialized with poll_interval: {self.poll_interval}s")

    async def _claim_next_task(self) -> Optional[AssessmentTask]:
        """
        Claims the next available task from the assessment_tasks queue.
        Returns:
            An AssessmentTask object if one was successfully claimed, None otherwise.
        """
        logger.debug("[AssessmentWorker] Attempting to dequeue next task from assessment_tasks queue...")
        try:
            task = await dequeue_assessment_task()
            if task:
                logger.info(f"[AssessmentWorker] Dequeued task: {task.id} for document: {task.document_id}, status: {task.status}")
                return task
            else:
                logger.debug("[AssessmentWorker] No tasks found in assessment_tasks queue.")
                return None
        except Exception as e:
            logger.error(f"[AssessmentWorker] Error claiming next task from assessment_tasks queue: {e}", exc_info=True)
            return None

    async def _delete_assessment_task(self, task_id: uuid.UUID):
        db = get_database()
        if db is None:
            logger.error(f"[AssessmentWorker] Database not available, cannot delete task {task_id}.")
            return
        try:
            logger.debug(f"[AssessmentWorker] Deleting task {task_id} from assessment_tasks queue.")
            await db.assessment_tasks.delete_one({"_id": task_id})
            logger.info(f"[AssessmentWorker] Successfully deleted task {task_id} from assessment_tasks queue.")
        except Exception as e:
            logger.error(f"[AssessmentWorker] Error deleting task {task_id} from assessment_tasks queue: {e}", exc_info=True)

    async def _process_task(self, task: AssessmentTask):
        """
        Processes a claimed AssessmentTask.
        Extracts text, calls ML API, updates Document and Result statuses.
        Args:
            task: The AssessmentTask object to process.
        """
        document_id = task.document_id
        teacher_id = task.user_id # Assuming task.user_id from AssessmentTask is the teacher_id for CRUD operations
        logger.info(f"[AssessmentWorker] Starting processing for task {task.id} (document_id: {document_id})")

        # Get the database instance
        db = get_database()
        if db is None:
            logger.error(f"[AssessmentWorker] Database not available, cannot process task {task.id}. Attempt: {task.attempts}")
            # This task will become available again after visibility timeout.
            # If it consistently fails to get DB, it will eventually be dead-lettered by dequeue_assessment_task.
            return

        # Get the associated Document
        document = await crud.get_document_by_id(document_id=document_id, teacher_id=teacher_id)
        if not document:
            logger.error(f"[AssessmentWorker] Document {document_id} not found or not accessible by teacher {teacher_id} for task {task.id}. Marking task for potential dead-lettering if repeated.")
            # Update task status to ERROR in assessment_tasks if possible, or let it be re-queued and eventually dead-lettered
            # For now, we'll let dequeue_assessment_task handle retries/dead-lettering based on attempts.
            # No explicit delete here as the task might be recoverable if doc appears later.
            return

        # Update Document status to PROCESSING
        await crud.update_document_status(document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.PROCESSING)
        
        # Get or Create Result record
        # The Result record should typically be created during upload with PENDING status.
        # The worker's job is to move it to ASSESSING (momentarily, then to COMPLETED/ERROR)
        result = await crud.get_result_by_document_id(document_id=document_id, teacher_id=teacher_id)
        if not result:
            logger.warning(f"[AssessmentWorker] Result record not found for document {document_id} (task {task.id}). Creating one.")
            result_data = ResultCreate(
                document_id=document_id, 
                teacher_id=teacher_id, 
                status=ResultStatus.PENDING # Start as PENDING, will be updated shortly
            )
            result = await crud.create_result(result_in=result_data)
            if not result:
                logger.error(f"[AssessmentWorker] Failed to create result record for document {document_id}. Aborting task {task.id}.")
                await crud.update_document_status(document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.ERROR)
                # Let dequeue_assessment_task handle retries/dead-lettering for the AssessmentTask.
                return
        
        # Update Result status to ASSESSING (briefly, before actual ML call)
        await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ASSESSING}, teacher_id=teacher_id)

        extracted_text: Optional[str] = None
        character_count: Optional[int] = None
        word_count: Optional[int] = None

        try:
            # --- Text Extraction (Copied from documents.py and adapted) ---
            logger.info(f"[AssessmentWorker] Starting text extraction for doc {document.id} (task {task.id})")
            file_type_enum_member: Optional[FileType] = None
            if isinstance(document.file_type, str):
                try: file_type_enum_member = FileType(document.file_type.lower())
                except ValueError: pass # Handled below
            elif isinstance(document.file_type, FileType):
                file_type_enum_member = document.file_type

            if not file_type_enum_member:
                raise ValueError(f"Could not map document.file_type '{document.file_type}' to FileType enum.")

            file_bytes = await download_blob_as_bytes(document.storage_blob_path)
            if file_bytes is None:
                raise FileNotFoundError(f"Failed to download blob {document.storage_blob_path}")

            extracted_text = await asyncio.to_thread(extract_text_from_bytes, file_bytes, file_type_enum_member)
            if extracted_text is None: extracted_text = "" # Ensure string
            character_count = len(extracted_text)
            words = re.split(r'\s+', extracted_text.strip())
            word_count = len([w for w in words if w])
            logger.info(f"[AssessmentWorker] Text extraction complete for doc {document.id}. Chars: {character_count}, Words: {word_count}")
            # --- End Text Extraction ---

            # --- ML API Call (Copied from documents.py and adapted) ---
            ml_api_url_worker = settings.ML_API_URL # MODIFIED: Use settings.ML_API_URL
            if not ml_api_url_worker:
                logger.critical("[AssessmentWorker] ML_API_URL is not configured in settings. Cannot proceed with ML call.")
                raise ValueError("ML_API_URL not configured.")

            ai_score: Optional[float] = None
            ml_label: Optional[str] = None
            ml_ai_generated: Optional[bool] = None
            ml_human_generated: Optional[bool] = None
            ml_paragraph_results_raw: Optional[List[Dict[str, Any]]] = None

            ml_payload = {"text": extracted_text}
            headers = {'Content-Type': 'application/json'}
            logger.info(f"[AssessmentWorker] Calling ML API for doc {document.id} at {ml_api_url_worker}")
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(ml_api_url_worker, json=ml_payload, headers=headers)
                response.raise_for_status() # Raises HTTPStatusError for 4xx/5xx
                ml_response_data = response.json()
            logger.info(f"[AssessmentWorker] ML API response for doc {document.id}: {ml_response_data}")

            if isinstance(ml_response_data, dict):
                ml_ai_generated = ml_response_data.get("ai_generated")
                ml_human_generated = ml_response_data.get("human_generated")
                # ... (rest of ML response parsing copied from documents.py) ...
                if ("results" in ml_response_data and isinstance(ml_response_data["results"], list)):
                    ml_paragraph_results_raw = ml_response_data["results"]
                    if len(ml_paragraph_results_raw) > 0 and isinstance(ml_paragraph_results_raw[0], dict):
                        first_result_data = ml_paragraph_results_raw[0]
                        ml_label = first_result_data.get("label")
                        score_value = first_result_data.get("probability")
                        if isinstance(score_value, (int, float)):
                            ai_score = float(score_value)
                            ai_score = max(0.0, min(1.0, ai_score))
            else: raise ValueError("ML API response format unexpected.")
            # --- End ML API Call ---

            # --- Update DB with Result (Copied and adapted) ---
            update_payload_dict = {
                "status": ResultStatus.COMPLETED.value,
                "result_timestamp": datetime.now(timezone.utc)
            }
            if ai_score is not None: update_payload_dict["score"] = ai_score
            if ml_label is not None: update_payload_dict["label"] = ml_label
            if ml_ai_generated is not None: update_payload_dict["ai_generated"] = ml_ai_generated
            if ml_human_generated is not None: update_payload_dict["human_generated"] = ml_human_generated
            if ml_paragraph_results_raw is not None: update_payload_dict["paragraph_results"] = ml_paragraph_results_raw
            
            final_result_obj = await crud.update_result(result_id=result.id, update_data=update_payload_dict, teacher_id=teacher_id)
            if final_result_obj:
                logger.info(f"[AssessmentWorker] Successfully updated result {result.id} for doc {document.id} to COMPLETED.")
                await crud.update_document_status(
                    document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.COMPLETED,
                    character_count=character_count, word_count=word_count
                )
                logger.info(f"[AssessmentWorker] Successfully updated document {document.id} to COMPLETED.")
                await self._delete_assessment_task(task.id) # Delete task from queue on full success
            else:
                logger.error(f"[AssessmentWorker] Failed to update result record for doc {document.id}. Status will remain ASSESSING. Task {task.id} will be retried.")
                await crud.update_document_status(document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.ERROR, character_count=character_count, word_count=word_count)
                # Do not delete task, let it be retried by dequeue logic

        except Exception as e:
            logger.error(f"[AssessmentWorker] Error processing task {task.id} (doc: {document.id}): {e}", exc_info=True)
            try:
                await crud.update_document_status(document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.ERROR, character_count=character_count, word_count=word_count)
                if result: # Ensure result object exists
                    await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR}, teacher_id=teacher_id)
                logger.info(f"[AssessmentWorker] Set document {document.id} and result {result.id if result else 'N/A'} to ERROR due to processing exception for task {task.id}.")
                # Do not delete the task here. If it's a persistent issue, 
                # dequeue_assessment_task's max_attempts will eventually move it to dead-letter.
            except Exception as update_err:
                logger.error(f"[AssessmentWorker] Further error setting statuses to ERROR for doc {document_id} (task {task.id}): {update_err}", exc_info=True)
        
        logger.info(f"[AssessmentWorker] Finished processing attempt for task {task.id} (document_id: {document.id})")

    async def run(self):
        """
        Main loop for the assessment worker.
        Periodically polls for tasks and processes them.
        """
        logger.info("AssessmentWorker run loop started.")
        self._running = True
        while self._running:
            processed_task_in_iteration = False
            try:
                logger.debug("[AssessmentWorker] Checking for new assessment tasks...")
                task_to_process = await self._claim_next_task()
                
                if task_to_process:
                    logger.info(f"[AssessmentWorker] Claimed task: Result ID {task_to_process.id} for document: {task_to_process.document_id}")
                    await self._process_task(task_to_process)
                    processed_task_in_iteration = True # A task was processed
                else:
                    logger.debug("[AssessmentWorker] No pending tasks found this cycle.")
                
            except asyncio.CancelledError:
                logger.info("AssessmentWorker run loop cancelled.")
                self._running = False
                break # Exit loop immediately on cancellation
            except Exception as e:
                logger.error(f"[AssessmentWorker] Unhandled error in run loop's main try block: {e}", exc_info=True)
            
            # Sleep only if no task was processed, otherwise try to pick another one quickly
            if self._running and not processed_task_in_iteration:
                await asyncio.sleep(self.poll_interval)
            elif self._running and processed_task_in_iteration:
                await asyncio.sleep(1) # Short sleep if a task was just processed, to check again soon

        logger.info("AssessmentWorker run loop finished.")

    def stop(self):
        """
        Signals the worker to stop processing.
        """
        logger.info("AssessmentWorker stop requested.")
        self._running = False

if __name__ == '__main__':
    # Example of how to run the worker directly for testing (optional)
    async def main_test(): # Renamed to avoid conflict with main module's main
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        # Ensure DB is connected for this test to work if crud operations are called
        # from backend.app.db.database import connect_to_mongo, close_mongo_connection
        # await connect_to_mongo()
        
        worker = AssessmentWorker(poll_interval=5)
        try:
            await worker.run()
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received, stopping worker...")
        finally:
            worker.stop()
            # Allow time for the loop to finish if it's in an await
            await asyncio.sleep(worker.poll_interval + 1) 
            logger.info("AssessmentWorker stopped by KeyboardInterrupt in test.")
            # await close_mongo_connection()

    # To run this test worker: 
    # Ensure your .env file is loaded or MONGODB_URL is available if it hits DB
    # Then uncomment the line below:
    # asyncio.run(main_test()) 