# backend/app/tasks/assessment_worker.py
import asyncio
import logging
import time # For a simple delay in the loop
import random # For dummy score
from typing import Optional, List, Dict, Any
import uuid
from datetime import datetime, timezone
import re
import string # Added import

import httpx
# --- Database Access ---
from motor.motor_asyncio import AsyncIOMotorDatabase # Added for type hinting

from ..core.config import settings
from ..queue import dequeue_assessment_task, AssessmentTask
from ..services.blob_storage import download_blob_as_bytes
from ..services.text_extraction import extract_text_from_bytes
from ..db import crud
# get_database is still used by crud and queue functions, so it's not removed from here
# but AssessmentWorker itself will use the passed 'db' instance where possible.
from ..db.database import get_database 
from ..models.enums import DocumentStatus, ResultStatus, FileType, SubscriptionPlan
from ..models.result import ResultCreate, ParagraphResult

# Temporary: same ML API URL used in documents endpoint
# ML_API_URL = "https://fa-sdt-uks-aitextdet-prod.azurewebsites.net/api/ai-text-detection?code=PZrMzMk1VBBCyCminwvgUfzv_YGhVU-5E1JIs2if7zqiAzFuMhUC-g%3D%3D" # MODIFIED: Removed

logger = logging.getLogger(__name__)

class AssessmentWorker:
    def __init__(self, db: AsyncIOMotorDatabase, poll_interval: int = 10): # MODIFIED: Added db parameter
        """
        Initializes the AssessmentWorker.
        Args:
            db: The asynchronous MongoDB database instance.
            poll_interval: Time in seconds to wait between polling for new tasks.
        """
        self.db = db # MODIFIED: Store db instance
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
        if self.db is None:
            logger.warning("[AssessmentWorker] self.db is None immediately before calling dequeue_assessment_task!")
        else:
            logger.debug("[AssessmentWorker] self.db is NOT None before calling dequeue_assessment_task.")
        
        try:
            # MODIFIED: Pass self.db to dequeue_assessment_task
            task = await dequeue_assessment_task(db=self.db) 
            if task:
                logger.info(f"[AssessmentWorker] Dequeued task: {task.id} for document: {task.document_id}, status: {task.status}")
                return task
            else:
                logger.debug("[AssessmentWorker] No tasks found in assessment_tasks queue.")
                return None
        except Exception as e:
            logger.error(f"[AssessmentWorker] Error claiming next task from assessment_tasks queue: {e}", exc_info=True)
            return None

    async def _delete_assessment_task(self, task_id: uuid.UUID): # MODIFIED: Removed db parameter, will use self.db
        # MODIFIED: Use self.db instead of calling get_database()
        if self.db is None: # Should not happen if worker is initialized correctly
            logger.error(f"[AssessmentWorker] Database instance (self.db) not available, cannot delete task {task_id}.")
            return
        try:
            logger.debug(f"[AssessmentWorker] Deleting task {task_id} from assessment_tasks queue using self.db.")
            await self.db.assessment_tasks.delete_one({"_id": task_id})
            logger.info(f"[AssessmentWorker] Successfully deleted task {task_id} from assessment_tasks queue.")
        except Exception as e:
            logger.error(f"[AssessmentWorker] Error deleting task {task_id} from assessment_tasks queue: {e}", exc_info=True)

    async def _process_task(self, task: AssessmentTask): # MODIFIED: Removed db parameter
        """
        Processes a claimed AssessmentTask.
        Extracts text, calls ML API, updates Document and Result statuses.
        Args:
            task: The AssessmentTask object to process.
        """
        document_id = task.document_id
        teacher_id = task.user_id # Assuming task.user_id from AssessmentTask is the teacher_id for CRUD operations
        logger.info(f"[AssessmentWorker] Starting processing for task {task.id} (document_id: {document_id})")

        # Get the associated Document
        document = await crud.get_document_by_id(document_id=document_id, teacher_id=teacher_id)
        if not document:
            logger.error(f"[AssessmentWorker] Document {document_id} not found or not accessible by teacher {teacher_id} for task {task.id}. Marking task for potential dead-lettering if repeated.")
            return

        # Update Document status to PROCESSING
        await crud.update_document_status(document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.PROCESSING)
        
        result = await crud.get_result_by_document_id(document_id=document_id, teacher_id=teacher_id)
        if not result:
            logger.warning(f"[AssessmentWorker] Result record not found for document {document_id} (task {task.id}). Creating one.")
            result_data = ResultCreate(
                document_id=document_id, 
                teacher_id=teacher_id, 
                status=ResultStatus.PENDING
            )
            result = await crud.create_result(result_in=result_data)
            if not result:
                logger.error(f"[AssessmentWorker] Failed to create result record for document {document_id}. Aborting task {task.id}.")
                await crud.update_document_status(document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.ERROR)
                return
        
        await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.PROCESSING}, teacher_id=teacher_id)

        extracted_text: Optional[str] = None
        character_count: Optional[int] = None
        word_count: Optional[int] = None

        try:
            # --- Text Extraction (Copied from documents.py and adapted) ---
            logger.info(f"[AssessmentWorker] Starting text extraction for doc {document.id} (task {task.id})")
            file_type_enum_member: Optional[FileType] = None
            if isinstance(document.file_type, str):
                try: file_type_enum_member = FileType(document.file_type.lower())
                except ValueError: pass 
            elif isinstance(document.file_type, FileType):
                file_type_enum_member = document.file_type

            if not file_type_enum_member:
                raise ValueError(f"Could not map document.file_type \'{document.file_type}\' to FileType enum.")

            file_bytes = await download_blob_as_bytes(document.storage_blob_path)
            if file_bytes is None:
                raise FileNotFoundError(f"Failed to download blob {document.storage_blob_path}")

            extracted_text = await asyncio.to_thread(extract_text_from_bytes, file_bytes, file_type_enum_member)
            if extracted_text is None: extracted_text = "" 
            character_count = len(extracted_text)
            
            # Revised word count logic
            raw_tokens = re.split(r'\s+', extracted_text.strip())
            # Strip leading/trailing punctuation (e.g., '.', ',', '!', '?') from each token
            cleaned_tokens = [token.strip(string.punctuation) for token in raw_tokens]
            # Filter out any empty strings that might result (e.g., if a token was purely punctuation)
            words = [token for token in cleaned_tokens if token]
            word_count = len(words)
            
            logger.info(f"[AssessmentWorker] Text extraction complete for doc {document.id}. Chars: {character_count}, Words: {word_count}")

            # Always update document with character and word counts, regardless of limit checks
            await crud.update_document_counts(document_id=document.id, teacher_id=teacher_id, character_count=character_count, word_count=word_count)
            logger.info(f"[AssessmentWorker] Updated char/word counts for doc {document.id}")

            # --- Usage Limit Check ---
            teacher_db = await crud.get_teacher_by_kinde_id(kinde_id=teacher_id)
            if not teacher_db:
                logger.error(f"[AssessmentWorker] Teacher {teacher_id} not found. Cannot check usage limits. Aborting task {task.id} for doc {document.id}")
                await crud.update_document_status(document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.ERROR)
                await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.FAILED, "error_message": "User not found, cannot verify usage limits."}, teacher_id=teacher_id)
                await self._delete_assessment_task(task.id)
                return

            current_plan = teacher_db.current_plan
            logger.info(f"[AssessmentWorker] Teacher {teacher_id} is on plan: {current_plan}")

            if current_plan == SubscriptionPlan.SCHOOLS:
                logger.info(f"[AssessmentWorker] Teacher {teacher_id} on SCHOOLS plan. Bypassing usage limit check for doc {document.id}.")
            else:
                usage_stats = await crud.get_usage_stats_for_period(
                    teacher_id=teacher_id,
                    period='monthly',
                    target_date=datetime.now(timezone.utc).date()
                )
                current_monthly_words = usage_stats.get("total_words", 0) if usage_stats else 0
                current_monthly_chars = usage_stats.get("total_characters", 0) if usage_stats else 0
                
                doc_word_count = word_count if word_count is not None else 0
                doc_char_count = character_count if character_count is not None else 0

                limit_exceeded = False
                exceeded_by = ""

                if current_plan == SubscriptionPlan.FREE:
                    plan_word_limit_free = settings.FREE_PLAN_MONTHLY_WORD_LIMIT
                    plan_char_limit_free = settings.FREE_PLAN_MONTHLY_CHAR_LIMIT
                    logger.info(f"[AssessmentWorker] FREE Plan: Monthly words: {current_monthly_words}, Doc words: {doc_word_count}, Word Limit: {plan_word_limit_free}")
                    logger.info(f"[AssessmentWorker] FREE Plan: Monthly chars: {current_monthly_chars}, Doc chars: {doc_char_count}, Char Limit: {plan_char_limit_free}")

                    if current_monthly_words > plan_word_limit_free:
                        limit_exceeded = True
                        exceeded_by = "word"
                        logger.warning(f"[AssessmentWorker] Document {document.id} (words: {doc_word_count}) for teacher {teacher_id} would exceed FREE plan monthly word limit of {plan_word_limit_free} (current usage: {current_monthly_words}).")
                    
                    if not limit_exceeded and current_monthly_chars > plan_char_limit_free:
                        limit_exceeded = True
                        exceeded_by = "character"
                        logger.warning(f"[AssessmentWorker] Document {document.id} (chars: {doc_char_count}) for teacher {teacher_id} would exceed FREE plan monthly char limit of {plan_char_limit_free} (current usage: {current_monthly_chars}).")
                
                elif current_plan == SubscriptionPlan.PRO:
                    plan_word_limit_pro = settings.PRO_PLAN_MONTHLY_WORD_LIMIT
                    plan_char_limit_pro = settings.PRO_PLAN_MONTHLY_CHAR_LIMIT
                    logger.info(f"[AssessmentWorker] PRO Plan: Monthly words: {current_monthly_words}, Doc words: {doc_word_count}, Word Limit: {plan_word_limit_pro}")
                    logger.info(f"[AssessmentWorker] PRO Plan: Monthly chars: {current_monthly_chars}, Doc chars: {doc_char_count}, Char Limit: {plan_char_limit_pro}")

                    if current_monthly_words > plan_word_limit_pro:
                        limit_exceeded = True
                        exceeded_by = "word"
                        logger.warning(f"[AssessmentWorker] Document {document.id} (words: {doc_word_count}) for teacher {teacher_id} would exceed PRO plan monthly word limit of {plan_word_limit_pro} (current usage: {current_monthly_words}).")
                    
                    if not limit_exceeded and current_monthly_chars > plan_char_limit_pro:
                        limit_exceeded = True
                        exceeded_by = "character"
                        logger.warning(f"[AssessmentWorker] Document {document.id} (chars: {doc_char_count}) for teacher {teacher_id} would exceed PRO plan monthly char limit of {plan_char_limit_pro} (current usage: {current_monthly_chars}).")

                else: # Fallback for any other unknown non-SCHOOLS plan - use FREE plan char limits
                    plan_char_limit_fallback = settings.FREE_PLAN_MONTHLY_CHAR_LIMIT
                    logger.warning(f"[AssessmentWorker] Unknown plan {current_plan} for teacher {teacher_id}. Applying default free character limit ({plan_char_limit_fallback}) as a fallback.")
                    logger.info(f"[AssessmentWorker] FALLBACK Plan: Monthly chars: {current_monthly_chars}, Doc chars: {doc_char_count}, Limit: {plan_char_limit_fallback}")
                    if current_monthly_chars > plan_char_limit_fallback:
                        limit_exceeded = True
                        exceeded_by = "character (fallback)"
                        logger.warning(f"[AssessmentWorker] Document {document.id} (chars: {doc_char_count}) for teacher {teacher_id} would exceed FALLBACK (free) monthly char limit of {plan_char_limit_fallback} (current usage: {current_monthly_chars}).")

                if limit_exceeded:
                    error_message = f"Monthly {exceeded_by} limit exceeded."
                    await crud.update_document_status(document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.LIMIT_EXCEEDED)
                    await crud.update_result(
                        result_id=result.id, 
                        update_data={
                            "status": ResultStatus.FAILED, 
                            "error_message": error_message
                        }, 
                        teacher_id=teacher_id
                    )
                    await self._delete_assessment_task(task.id)
                    logger.info(f"[AssessmentWorker] Task {task.id} for document {document.id} deleted due to {exceeded_by} limit exceeded.")
                    return # Stop processing this task further
            
            # --- End Usage Limit Check ---

            # --- ML API Call (Copied from documents.py and adapted) ---
            ml_api_url_worker = settings.ML_API_URL 
            if not ml_api_url_worker:
                logger.critical("[AssessmentWorker] ML_API_URL is not configured in settings. Cannot proceed with ML call.")
                raise ValueError("ML_API_URL not configured.")

            ai_score: Optional[float] = None
            error_message_ml: Optional[str] = None
            label: Optional[str] = None # Initialize label
            ai_generated_flag: Optional[bool] = None # Initialize
            human_generated_flag: Optional[bool] = None # Initialize
            paragraph_results_data: List[ParagraphResult] = [] # Initialize

            if not extracted_text:
                logger.warning(f"[AssessmentWorker] Document {document.id} (task {task.id}) has no extracted text. Skipping ML API call. Setting score to 0.")
                ai_score = 0.0 # Or None, depending on desired behavior for empty text
                label = "No text available"
                # paragraph_results_data will remain empty as initialized
            else:
                logger.info(f"[AssessmentWorker] Calling ML API for doc {document.id} (task {task.id})")
                async with httpx.AsyncClient(timeout=settings.ML_API_TIMEOUT_SECONDS) as client:
                    try:
                        response = await client.post(ml_api_url_worker, json={"text": extracted_text})
                        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
                        ml_response_data = response.json()
                        
                        # --- REMOVE DETAILED LOGGING OF THE RESPONSE (was for debugging) ---
                        # logger.info(f"[AssessmentWorker] RAW ML API Response for doc {document.id}: {ml_response_data}")
                        # --- END REMOVED LOGGING ---

                        # --- Corrected Score, Label, and Flags Extraction ---
                        ai_score: Optional[float] = None # Initialize
                        label: Optional[str] = None    # Initialize

                        ai_generated_flag = ml_response_data.get('ai_generated')
                        human_generated_flag = ml_response_data.get('human_generated')

                        # Derive overall label from boolean flags
                        if ai_generated_flag is True:
                            label = "AI-Generated"
                        elif human_generated_flag is True: # Only if not ai_generated
                            label = "Human-Written"
                        else:
                            label = "Undetermined" # Or "Mixed", or keep as None to show "Unknown" or "N/A"

                        logger.info(f"[AssessmentWorker] ML API call successful for doc {document.id}. Overall Flags: AI? {ai_generated_flag}, Human? {human_generated_flag}. Derived Label: {label}")

                        # --- Corrected Extraction and Processing Paragraph-Level Results ---
                        paragraph_results_data: List[ParagraphResult] = []
                        raw_paragraph_analysis = ml_response_data.get('results') # CORRECTED KEY
                        
                        if isinstance(raw_paragraph_analysis, list):
                            for idx, para_item in enumerate(raw_paragraph_analysis):
                                if isinstance(para_item, dict):
                                    try:
                                        p_text = para_item.get('paragraph')         # CORRECTED KEY
                                        p_label = para_item.get('label')           # CORRECTED KEY
                                        p_score_raw = para_item.get('probability') # CORRECTED KEY
                                        p_score_val = float(p_score_raw) if p_score_raw is not None else None

                                        p_result = ParagraphResult(
                                            paragraph=p_text,
                                            label=p_label,
                                            probability=p_score_val
                                        )
                                        paragraph_results_data.append(p_result)

                                        # Derive overall ai_score from the first paragraph's probability, as per Result model hint
                                        if idx == 0 and p_score_val is not None:
                                            ai_score = p_score_val
                                            logger.info(f"[AssessmentWorker] Set overall ai_score to {ai_score} from first paragraph for doc {document.id}")

                                    except (ValueError, TypeError) as e:
                                        logger.warning(f"[AssessmentWorker] Error processing a paragraph result for doc {document.id}: {para_item}. Error: {e}. Skipping this paragraph.")
                                else:
                                    logger.warning(f"[AssessmentWorker] Expected a dict for paragraph item, got {type(para_item)} for doc {document.id}. Skipping item.")
                            logger.info(f"[AssessmentWorker] Extracted {len(paragraph_results_data)} paragraph results for doc {document.id}. Overall Score derived: {ai_score}")
                        elif raw_paragraph_analysis is not None:
                            logger.warning(f"[AssessmentWorker] Expected 'results' to be a list, got {type(raw_paragraph_analysis)} for doc {document.id}. No paragraph results will be stored.")
                        else:
                            logger.warning(f"[AssessmentWorker] ML API response did not contain a 'results' key for doc {document.id}. No paragraph results will be stored.")
                        # --- END Corrected Extraction ---

                    except httpx.ReadTimeout:
                        logger.error(f"[AssessmentWorker] ML API call timed out for doc {document.id} (task {task.id})")
                        error_message_ml = "ML API request timed out."
                    except httpx.HTTPStatusError as e:
                        logger.error(f"[AssessmentWorker] ML API call failed for doc {document.id} (task {task.id}): HTTP {e.response.status_code} - {e.response.text}")
                        error_message_ml = f"ML API request failed: {e.response.status_code}"
                    except Exception as e:
                        logger.error(f"[AssessmentWorker] Error during ML API call for doc {document.id} (task {task.id}): {e}", exc_info=True)
                        error_message_ml = f"Unexpected error during ML processing: {str(e)[:100]}"
            
            # --- Update Result and Document based on ML outcome --- 
            result_update_payload: Dict[str, Any] = {
                "score": ai_score,
                "label": label,
                "ai_generated": ai_generated_flag, # ADDED
                "human_generated": human_generated_flag, # ADDED
                "paragraph_results": [p.model_dump() for p in paragraph_results_data] if paragraph_results_data else None # MODIFIED: Ensure model_dump for DB
            }
            new_doc_status = DocumentStatus.COMPLETED # Default to COMPLETED

            if error_message_ml is None: # ML API call was successful and response processed (score might be None)
                result_update_payload["status"] = ResultStatus.COMPLETED
                # Document status remains COMPLETED
            else: # Error during ML call (timeout, HTTP error, etc.) or score processing issue that generated an error_message_ml
                result_update_payload["status"] = ResultStatus.FAILED
                result_update_payload["error_message"] = error_message_ml # This was already set if there was an ML error
                new_doc_status = DocumentStatus.ERROR
            
            await crud.update_result(result_id=result.id, update_data=result_update_payload, teacher_id=teacher_id)
            logger.info(f"[AssessmentWorker] Result {result.id} for doc {document.id} updated with status: {result_update_payload['status']}")

            # MODIFIED: Call update_document_status to include the score and final status
            logger.info(f"[AssessmentWorker] Preparing to update document {document.id} with status: {new_doc_status} and score: {ai_score}")
            await crud.update_document_status(
                document_id=document.id, 
                teacher_id=teacher_id, 
                status=new_doc_status, 
                score=ai_score # Persist the score on the document record
            )
            logger.info(f"[AssessmentWorker] Document {document.id} status updated to {new_doc_status} and score to {ai_score}.")
            # --- End ML API Call ---

        except FileNotFoundError as e:
            logger.error(f"[AssessmentWorker] File not found for doc {document.id} (task {task.id}): {e}", exc_info=True)
            await crud.update_document_status(document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.ERROR)
            await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.FAILED, "error_message": f"File processing error: {e}"}, teacher_id=teacher_id)
        except ValueError as e: # Catch config errors or text extraction mapping errors
            logger.error(f"[AssessmentWorker] Value error processing doc {document.id} (task {task.id}): {e}", exc_info=True)
            await crud.update_document_status(document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.ERROR)
            await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.FAILED, "error_message": f"Configuration or data error: {e}"}, teacher_id=teacher_id)
        except Exception as e:
            logger.error(f"[AssessmentWorker] Unhandled error processing doc {document.id} (task {task.id}): {e}", exc_info=True)
            # Generic error status
            await crud.update_document_status(document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.ERROR)
            await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.FAILED, "error_message": f"Unexpected worker error: {str(e)[:100]}"}, teacher_id=teacher_id)
        finally:
            # Delete the task from the queue after processing
            await self._delete_assessment_task(task.id)
            logger.info(f"[AssessmentWorker] Task {task.id} processing finished for document {document_id}. Task deleted.")

    async def run(self):
        """
        Main loop for the assessment worker.
        Periodically polls for tasks and processes them.
        """
        if self.db is None: # Add check for db initialization
            logger.critical("[AssessmentWorker] Database instance (self.db) is None. Worker cannot run.")
            self._running = False # Ensure it doesn't attempt to run
            return

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
                    processed_task_in_iteration = True 
                else:
                    logger.debug("[AssessmentWorker] No pending tasks found this cycle.")
                
            except asyncio.CancelledError:
                logger.info("AssessmentWorker run loop cancelled.")
                self._running = False
                break 
            except Exception as e:
                logger.error(f"Unhandled error in AssessmentWorker run loop: {e}", exc_info=True)
            
            if self._running: # Only sleep if still supposed to be running
                if processed_task_in_iteration:
                    await asyncio.sleep(0.1) # Short sleep if a task was processed
                else:
                    await asyncio.sleep(self.poll_interval) # Longer sleep if no task was found

    def stop(self):
        """
        Stops the worker's run loop.
        """
        logger.info("AssessmentWorker stop called.")
        self._running = False

# Example usage (for testing, typically managed by main application)
async def worker_main_test(): # Renamed to avoid conflict
    from ..db.database import connect_to_mongo, close_mongo_connection, get_database

    logger.info("Starting AssessmentWorker test...")
    await connect_to_mongo()
    db_instance = get_database()
    if db_instance is None:
        logger.error("Failed to get database instance for worker_main_test. Aborting.")
        return

    worker = AssessmentWorker(db=db_instance, poll_interval=5) # Pass db instance
    try:
        await worker.run()
    except KeyboardInterrupt:
        logger.info("AssessmentWorker test interrupted by user.")
    finally:
        worker.stop()
        # Give it a moment to finish current iteration if any
        await asyncio.sleep(1) 
        await close_mongo_connection()
        logger.info("AssessmentWorker test finished and MongoDB connection closed.")

if __name__ == "__main__":
    # Configure logging for standalone test
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    asyncio.run(worker_main_test()) 