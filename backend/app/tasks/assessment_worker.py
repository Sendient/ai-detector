# backend/app/tasks/assessment_worker.py
import asyncio
import logging
import time # For a simple delay in the loop
import random # For dummy score
from typing import Optional

# Import database functions and models
from ..db import crud
from ..db.database import get_database # Added to allow worker to get DB instance
from ..models.enums import DocumentStatus, ResultStatus
from ..models.result import Result # To type hint the task
from ..models.document import Document # For type hinting

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

    async def _claim_next_task(self) -> Optional[Result]:
        """
        Claims the next available task (Result with status ASSESSING).
        Sorts by 'updated_at' to pick older tasks first.
        Returns:
            A Result object if one was successfully claimed and updated, None otherwise.
        """
        db = get_database()
        if db is None:
            logger.error("[AssessmentWorker] Database not available, cannot claim task.")
            return None

        results_collection = db.get_collection(crud.RESULT_COLLECTION)
        logger.debug("[AssessmentWorker] Attempting to find next task (Result with status ASSESSING)...")

        try:
            # Find one task with status ASSESSING, oldest first
            # In a multi-worker scenario, we'd need an atomic update here to "claim" it.
            # For a single worker, simply fetching and then processing is okay for now.
            # However, a more robust approach is find_one_and_update.
            # For simplicity in this step, we'll find, then update status in _process_task.
            # This is NOT robust for multiple workers.
            # TODO: Implement atomic claim if multiple workers are anticipated.

            assessing_task_doc = await results_collection.find_one(
                {"status": ResultStatus.ASSESSING.value},
                sort=[("updated_at", 1)] # Get the oldest updated task
            )

            if assessing_task_doc:
                logger.info(f"[AssessmentWorker] Found task: {assessing_task_doc['_id']} for document: {assessing_task_doc['document_id']}")
                return Result(**assessing_task_doc) # Convert to Pydantic model
            else:
                logger.debug("[AssessmentWorker] No ASSESSING tasks found.")
                return None
        except Exception as e:
            logger.error(f"[AssessmentWorker] Error claiming next task: {e}", exc_info=True)
            return None

    async def _process_task(self, result_doc: Result):
        """
        Processes a claimed task (Result object).
        Simulates ML processing and updates Document and Result statuses.
        Args:
            result_doc: The Result object to process.
        """
        document_id = result_doc.document_id
        teacher_id = result_doc.teacher_id # teacher_id is on the Result model
        logger.info(f"[AssessmentWorker] Starting processing for result {result_doc.id} (document_id: {document_id})")

        try:
            # --- Simulate work ---
            await asyncio.sleep(random.randint(3, 7)) # Simulate variable processing time
            simulated_score = round(random.uniform(0.1, 0.95), 2) # Simulate an ML score
            logger.info(f"[AssessmentWorker] Simulated ML processing complete for doc {document_id}. Score: {simulated_score}")

            # Update Result record to COMPLETED
            update_data_result = {
                "status": ResultStatus.COMPLETED,
                "score": simulated_score,
                # Potentially add other fields like 'label', 'ai_generated' etc.
            }
            updated_result = await crud.update_result(
                result_id=result_doc.id, 
                update_data=update_data_result,
                teacher_id=teacher_id # Pass teacher_id for auth if crud.update_result uses it
            )
            if not updated_result:
                logger.error(f"[AssessmentWorker] Failed to update result {result_doc.id} to COMPLETED for doc {document_id}")
                # If result update fails, set document to ERROR to avoid perpetual processing
                await crud.update_document_status(document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.ERROR)
                return
            
            logger.info(f"[AssessmentWorker] Successfully updated result {result_doc.id} for doc {document_id} to COMPLETED.")

            # Update Document record to COMPLETED
            # Assuming character/word counts are set during the initial /assess call or text extraction step.
            # If worker is responsible for these, it needs to calculate/fetch them.
            updated_document = await crud.update_document_status(
                document_id=document_id, 
                teacher_id=teacher_id, # crud.update_document_status requires teacher_id
                status=DocumentStatus.COMPLETED
                # character_count and word_count could be passed if available/calculated by worker
            )
            if not updated_document:
                logger.error(f"[AssessmentWorker] Failed to update document {document_id} to COMPLETED. Setting result back to ERROR for retry.")
                # Revert result status to allow for retry or manual intervention if doc update fails
                await crud.update_result(result_id=result_doc.id, update_data={"status": ResultStatus.ERROR}, teacher_id=teacher_id)
                return

            logger.info(f"[AssessmentWorker] Successfully updated document {document_id} to COMPLETED.")
            logger.info(f"[AssessmentWorker] Finished processing for result {result_doc.id} (document_id: {document_id})")

        except Exception as e:
            logger.error(f"[AssessmentWorker] Error processing result {result_doc.id} (doc: {document_id}): {e}", exc_info=True)
            # Set document and result to ERROR status if processing fails
            try:
                await crud.update_document_status(document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.ERROR)
                await crud.update_result(result_id=result_doc.id, update_data={"status": ResultStatus.ERROR}, teacher_id=teacher_id)
                logger.info(f"[AssessmentWorker] Set document {document_id} and result {result_doc.id} to ERROR due to processing exception.")
            except Exception as update_err:
                logger.error(f"[AssessmentWorker] Further error setting statuses to ERROR for doc {document_id}: {update_err}", exc_info=True)

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