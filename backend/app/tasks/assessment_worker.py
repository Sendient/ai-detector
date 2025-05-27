# backend/app/tasks/assessment_worker.py
import asyncio
import logging
import time # For a simple delay in the loop
import random # For dummy score
from typing import Optional, List, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
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
            # Consider updating task to a FAILED state here if this repeats. For now, just return.
            # No task deletion here as the task might be picked up again if the document appears.
            return

        # Update Document status to PROCESSING
        doc_status_updated_to_processing = await crud.update_document_status(document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.PROCESSING)
        if not doc_status_updated_to_processing:
            logger.critical(f"[AssessmentWorker] CRITICAL: Failed to update document {document_id} status to PROCESSING for task {task.id}. Re-queueing task for retry.")
            await self._update_task_for_retry(task, "DB_UPDATE_PROCESSING_FAILED")
            return # Do not delete the task
        
        result = await crud.get_result_by_document_id(document_id=document_id, teacher_id=teacher_id)
        if not result:
            logger.warning(f"[AssessmentWorker] Result record not found for document {document_id} (task {task.id}). Creating one.")
            result = await crud.create_result(
                document_id=document_id, 
                teacher_id=teacher_id
            )
            if not result:
                logger.error(f"[AssessmentWorker] Failed to create result record for document {document_id}. Aborting task {task.id}.")
                # Attempt to set document status back to ERROR
                error_update_doc = await crud.update_document_status(document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.ERROR)
                if not error_update_doc:
                    logger.error(f"[AssessmentWorker] Also failed to update doc {document_id} to ERROR after result creation failure.")
                # Task should be retried or handled, not deleted immediately if result creation fails
                await self._update_task_for_retry(task, "RESULT_CREATION_FAILED")
                return
        
        # Update Result status to PROCESSING
        result_status_updated = await crud.update_result_status(
            result_id=result.id,
            status=ResultStatus.PROCESSING,
            teacher_id=teacher_id
        )
        if not result_status_updated:
            logger.critical(f"[AssessmentWorker] CRITICAL: Failed to update result {result.id} status to PROCESSING for task {task.id} (doc {document_id}). Re-queueing task for retry.")
            await self._update_task_for_retry(task, "RESULT_UPDATE_PROCESSING_FAILED")
            return # Do not delete the task

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
            doc_counts_updated = await crud.update_document_counts(document_id=document.id, teacher_id=teacher_id, character_count=character_count, word_count=word_count)
            if not doc_counts_updated:
                logger.error(f"[AssessmentWorker] Failed to update char/word counts for doc {document.id} (task {task.id}). Proceeding with ML, but counts are stale.")
                # Not re-queueing here as ML call is more critical, but this is a data integrity issue.

            # --- Usage Limit Check ---
            teacher_db = await crud.get_teacher_by_kinde_id(kinde_id=teacher_id)
            if not teacher_db:
                logger.error(f"[AssessmentWorker] Teacher {teacher_id} not found. Cannot check usage limits. Aborting task {task.id} for doc {document.id}")
                doc_limit_err_update = await crud.update_document_status(document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.ERROR)
                res_limit_err_update = await crud.update_result_status(
                    result_id=result.id, 
                    status=ResultStatus.FAILED,
                    teacher_id=teacher_id,
                    error_message="User not found, cannot verify usage limits."
                )
                if not doc_limit_err_update or not res_limit_err_update:
                    logger.error(f"[AssessmentWorker] Failed to update doc/result to ERROR after teacher not found for limit check (doc: {document_id}). Re-queueing task.")
                    await self._update_task_for_retry(task, "DB_UPDATE_TEACHER_NOT_FOUND_FAILED")
                    return # Do not delete task
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
                    doc_limit_update_success = await crud.update_document_status(document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.LIMIT_EXCEEDED)
                    res_limit_update_success = await crud.update_result_status(
                        result_id=result.id,
                        status=ResultStatus.FAILED,
                        teacher_id=teacher_id,
                        error_message=error_message
                    )

                    if not doc_limit_update_success or not res_limit_update_success:
                        logger.error(f"[AssessmentWorker] Failed to update doc/result to LIMIT_EXCEEDED/FAILED after limit check (doc: {document_id}). Re-queueing task.")
                        await self._update_task_for_retry(task, "DB_UPDATE_LIMIT_EXCEEDED_FAILED")
                        return # Do not delete the task
                    
                    await self._delete_assessment_task(task.id)
                    logger.info(f"[AssessmentWorker] Task {task.id} for document {document.id} deleted due to {exceeded_by} limit exceeded.")
                    return # Stop processing this task further
            
            # --- End Usage Limit Check ---

            # --- ML API Call & Response Processing ---
            # TODO: Replace with actual ML API call logic using self._call_ml_api(extracted_text)
            
            # --- NEW Enhanced Dummy ML API Response Simulation ---
            overall_score = random.uniform(0.0, 1.0)
            overall_label = "AI-Generated" if overall_score > 0.6 else ("Human-Written" if overall_score < 0.4 else "Mixed/Uncertain")
            overall_ai_generated = overall_label == "AI-Generated"
            overall_human_generated = overall_label == "Human-Written"

            generated_paragraph_results: List[ParagraphResult] = []
            parsed_paragraphs_list = extracted_text.split('\n\n') if extracted_text else []

            if parsed_paragraphs_list:
                for i, para_text in enumerate(parsed_paragraphs_list):
                    if not para_text.strip(): # Skip empty paragraphs
                        continue
                    
                    para_score = random.uniform(0.0, 1.0)
                    para_label = "AI-Generated" if para_score > 0.7 else ("Human-Written" if para_score < 0.3 else "Undetermined")
                    
                    segments_data = []
                    if para_label == "AI-Generated":
                        # Simulate some segments being marked
                        # Make a few segments, some AI, some not, for variety
                        words_in_para = para_text.split()
                        if len(words_in_para) > 5: # Only segment if there are enough words
                            cut1 = len(words_in_para) // 3
                            cut2 = (len(words_in_para) // 3) * 2
                            
                            segments_data.append({
                                "text": " ".join(words_in_para[:cut1]),
                                "label": "POSSIBLY_HUMAN_IN_AI_PARA",
                                "color_hint": "lightgray" # Less prominent
                            })
                            segments_data.append({
                                "text": " ".join(words_in_para[cut1:cut2]),
                                "label": "AI_HIGH_CONFIDENCE",
                                "color_hint": "red" 
                            })
                            segments_data.append({
                                "text": " ".join(words_in_para[cut2:]),
                                "label": "AI_MEDIUM_CONFIDENCE",
                                "color_hint": "orange"
                            })
                        else: # Short AI paragraph, mark all of it
                             segments_data.append({
                                "text": para_text,
                                "label": "AI_HIGH_CONFIDENCE",
                                "color_hint": "red"
                            })
                    elif para_label == "Human-Written":
                        segments_data.append({
                            "text": para_text,
                            "label": "HUMAN_LIKELY",
                            "color_hint": "green" 
                        })
                    else: # Undetermined
                        segments_data.append({
                            "text": para_text,
                            "label": "UNDETERMINED_SEGMENT",
                            "color_hint": "blue" # Or some neutral color
                        })

                    generated_paragraph_results.append(
                        ParagraphResult(
                            paragraph=para_text,
                            label=para_label,
                            probability=para_score,
                            segments=segments_data,
                            paragraph_explanation=f"This paragraph was classified as '{para_label}' with a confidence of {para_score:.2f}. Highlighting indicates specific segments."
                        )
                    )
            
            if not generated_paragraph_results: # Fallback if no paragraphs were parsed or all were empty
                 generated_paragraph_results.append(
                    ParagraphResult(
                        paragraph="Document content could not be parsed into processable paragraphs or was empty.",
                        label="ERROR_PARSING",
                        probability=0.0,
                        segments=[{"text": "N/A", "label": "ERROR_CONTENT", "color_hint": "grey"}],
                        paragraph_explanation="Content parsing failed, document was empty, or paragraphs were empty."
                    )
                )
                 # Update overall assessment if parsing failed
                 overall_label = "ERROR_PARSING"
                 overall_score = 0.0
                 overall_ai_generated = False
                 overall_human_generated = False


            # --- End of NEW Enhanced Dummy ML API Response ---
            
            # Update Document status to COMPLETED and include the score
            doc_update_completed = await crud.update_document_status(
                document_id=document_id, 
                teacher_id=teacher_id, 
                status=DocumentStatus.COMPLETED,
                score=overall_score 
            )
            # REMOVED: dummy_ml_response = {} - No longer needed in this old form

            # Update Result with score and status
            # Ensure paragraph_results uses the list of ParagraphResult model instances
            final_res_update = await crud.update_result_status(
                result_id=result.id,
                teacher_id=teacher_id,
                status=ResultStatus.COMPLETED,
                score=overall_score,
                label=overall_label, # Use overall_label
                ai_generated=overall_ai_generated, # Use overall_ai_generated
                human_generated=overall_human_generated, # Use overall_human_generated
                paragraph_results=generated_paragraph_results, # Pass the list of ParagraphResult objects
                # raw_response can be added here if/when _call_ml_api is implemented and returns a raw dict
            )
            
            if not doc_update_completed or not final_res_update:
                logger.error(f"[AssessmentWorker] Failed to update doc/result to COMPLETED/FAILED after ML processing for task {task.id}. Re-queueing task.")
                await self._update_task_for_retry(task, "RESULT_UPDATE_ML_DATA_FAILED")
                return

            logger.info(f"[AssessmentWorker] Successfully processed task {task.id} for document {document_id}. Final score: {overall_score}")
            await self._delete_assessment_task(task.id) # Delete task after successful processing

        except FileNotFoundError as fnf_error:
            logger.error(f"[AssessmentWorker] File not found error for task {task.id} (document {document_id}): {fnf_error}. Setting doc/result to ERROR. Task will be retried.")
            doc_err_update = await crud.update_document_status(document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.ERROR)
            res_err_update = await crud.update_result_status(
                result_id=result.id,
                status=ResultStatus.FAILED,
                teacher_id=teacher_id,
                error_message=f"File processing error: {str(fnf_error)[:500]}" # Truncated for safety
            )

            if not doc_err_update or not res_err_update:
                 logger.error(f"[AssessmentWorker] Also failed to update doc/result to ERROR after FileNotFoundError for task {task.id}. Re-queueing task.")
            await self._update_task_for_retry(task, f"FILE_NOT_FOUND: {fnf_error}")

        except ValueError as val_error: # Catch specific ValueError from file type mapping or text extraction
            logger.error(f"[AssessmentWorker] Value error during processing for task {task.id} (document {document_id}): {val_error}. Setting doc/result to ERROR. Task will be retried.")
            doc_err_update = await crud.update_document_status(document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.ERROR)
            res_err_update = await crud.update_result_status(
                result_id=result.id,
                status=ResultStatus.FAILED,
                teacher_id=teacher_id,
                error_message=f"Value error: {str(val_error)[:500]}" # Truncated for safety
            )
            
            if not doc_err_update or not res_err_update:
                 logger.error(f"[AssessmentWorker] Also failed to update doc/result to ERROR after ValueError for task {task.id}. Re-queueing task.")
            await self._update_task_for_retry(task, f"VALUE_ERROR: {val_error}")

        except httpx.HTTPStatusError as http_err:
            logger.error(f"[AssessmentWorker] HTTP error calling ML API for task {task.id} (document {document_id}): {http_err}. Response: {http_err.response.text}. Re-queueing task.")
            doc_ml_err_update = await crud.update_document_status(document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.ERROR)
            res_ml_err_update = await crud.update_result_status(
                result_id=result.id,
                status=ResultStatus.FAILED,
                teacher_id=teacher_id,
                error_message=f"ML API HTTP error: {http_err.response.status_code}"
            )
            
            if not doc_ml_err_update or not res_ml_err_update:
                 logger.error(f"[AssessmentWorker] Also failed to update doc/result to ERROR after ML API HTTPStatusError for task {task.id}. Re-queueing task.")
            await self._update_task_for_retry(task, f"ML_API_HTTP_ERROR: {http_err.response.status_code}")
        
        except httpx.RequestError as req_err: # More general network errors
            logger.error(f"[AssessmentWorker] Network error calling ML API for task {task.id} (document {document_id}): {req_err}. Re-queueing task.")
            doc_net_err_update = await crud.update_document_status(document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.ERROR)
            res_net_err_update = await crud.update_result_status(
                result_id=result.id,
                status=ResultStatus.FAILED,
                teacher_id=teacher_id,
                error_message=f"ML API Network error: {type(req_err).__name__}"
            )
            
            if not doc_net_err_update or not res_net_err_update:
                 logger.error(f"[AssessmentWorker] Also failed to update doc/result to ERROR after ML API RequestError for task {task.id}. Re-queueing task.")
            await self._update_task_for_retry(task, f"ML_API_REQUEST_ERROR: {type(req_err).__name__}")

        except Exception as e:
            logger.error(f"[AssessmentWorker] Unhandled error processing task {task.id} (document {document_id}): {e}", exc_info=True)
            doc_gen_err_update = await crud.update_document_status(document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.ERROR)
            res_gen_err_update = await crud.update_result_status(
                result_id=result.id,
                status=ResultStatus.FAILED,
                teacher_id=teacher_id,
                error_message=f"Unhandled worker error: {type(e).__name__}"
            )

            if not doc_gen_err_update or not res_gen_err_update:
                 logger.error(f"[AssessmentWorker] Also failed to update doc/result to ERROR after unhandled exception for task {task.id}. Re-queueing task.")
            await self._update_task_for_retry(task, f"UNHANDLED_EXCEPTION: {type(e).__name__}")
            # Do not delete the task, let it be retried after cool-down or manually inspected.
    
    async def _update_task_for_retry(self, task: AssessmentTask, error_reason: str):
        """
        Updates a task in the queue to mark it for retry after a failure.
        Increments retry_count and sets available_at to a future time.
        Args:
            task: The AssessmentTask object to update.
            error_reason: A string indicating the reason for the retry.
        """
        if self.db is None:
            logger.error(f"[AssessmentWorker] Database instance (self.db) not available, cannot update task {task.id} for retry.")
            return

        retry_count = task.retry_count + 1
        # Exponential backoff for retry, e.g., 10s, 20s, 40s, etc., max 1 hour
        delay_seconds = min(self.poll_interval * (2 ** retry_count), 3600) 
        available_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
        
        update_payload = {
            "status": "RETRYING", # Or a more specific error status if your queue handles it
            "retry_count": retry_count,
            "available_at": available_at,
            "last_error": f"{error_reason} at {datetime.now(timezone.utc).isoformat()}"
        }

        try:
            logger.info(f"[AssessmentWorker] Updating task {task.id} for retry. Error: {error_reason}. Retry count: {retry_count}. Available at: {available_at.isoformat()}")
            result = await self.db.assessment_tasks.update_one(
                {"_id": task.id},
                {"$set": update_payload}
            )
            if result.modified_count == 0:
                logger.error(f"[AssessmentWorker] Failed to update task {task.id} in queue for retry (modified_count was 0). Task might have been processed/deleted by another worker.")
            else:
                logger.info(f"[AssessmentWorker] Successfully updated task {task.id} for retry.")
        except Exception as e:
            logger.error(f"[AssessmentWorker] Error updating task {task.id} in queue for retry: {e}", exc_info=True)

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

    async def _call_ml_api(self, document_content: str) -> Dict[str, Any]:
        """
        Placeholder for calling the actual ML API.
        For now, this will simulate a delay and return a basic structure.
        It should eventually make an HTTP call to the ML service.
        """
        logger.info(f"[_call_ml_api] Simulating ML API call for document content (first 100 chars): {document_content[:100]}")
        await asyncio.sleep(2) # Simulate network latency

        # This is a VERY basic placeholder. The actual API call will be more complex
        # and will need to handle potential errors, retries, etc.
        # The response structure will depend on the actual ML API.
        # For now, let's imagine it returns something that needs to be transformed
        # into our ParagraphResult model structure.
        
        # Example of a raw response structure we might get:
        # {
        #     "overall_assessment": {
        #         "score": 0.75,
        #         "classification": "AI_GENERATED_HIGH_CONFIDENCE"
        #     },
        #     "paragraphs": [
        #         {
        #             "text": "This is the first paragraph.",
        #             "analysis": {
        #                 "score": 0.9,
        #                 "label": "AI_STRONG",
        #                 "explanation": "Strong indicators of AI generation found.",
        #                 "highlight_spans": [
        #                     {"start_char": 10, "end_char": 20, "suggestion": "Reword this phrase.", "color": "red"}
        #                 ]
        #             }
        #         },
        #         # ... more paragraphs
        #     ]
        # }
        # We would then need to parse this and map it to our ResultUpdate and ParagraphResult models.

        logger.warning("[_call_ml_api] ML API call is currently a placeholder and returns a static dummy response. Needs implementation.")
        
        # For now, let's return a structure that the calling code might expect
        # based on how we USED to do dummy data. The real implementation will
        # replace this entirely.
        # This method should return data that `_process_task` can then
        # use to build `ParagraphResult` objects and the `ResultUpdate` object.
        
        # Let's assume _process_task will now iterate through paragraphs itself
        # and call a sub-function or directly build ParagraphResult.
        # So, this API might just return the raw classifications.
        
        # For now, returning an empty dict as the main logic is dummied in _process_task
        return {}

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