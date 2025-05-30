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
                result_in=ResultCreate(document_id=document_id, teacher_id=teacher_id)
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
        ml_api_error_message: Optional[str] = None # To store errors from ML API call for result

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
                # Use direct cycle counts from the teacher model
                current_cycle_words = teacher_db.words_used_current_cycle if teacher_db.words_used_current_cycle is not None else 0
                # current_cycle_docs = teacher_db.documents_processed_current_cycle if teacher_db.documents_processed_current_cycle is not None else 0
                # Character count limit check is not strictly enforced by teacher model fields yet,
                # but word count is the primary metric.
                # For character limits, if they become primary, we might need a teacher_db.chars_used_current_cycle
                
                # Fallback to settings for char limit if needed, but primary check is words
                # For this change, we will focus on word limits as per the teacher model.
                # The monthly aggregation for characters was a secondary check.

                doc_word_count = word_count if word_count is not None else 0
                # doc_char_count = character_count if character_count is not None else 0 # Not used with teacher_db fields directly

                limit_exceeded = False
                exceeded_by = ""

                if current_plan == SubscriptionPlan.FREE:
                    plan_word_limit_free = settings.FREE_PLAN_MONTHLY_WORD_LIMIT
                    # plan_char_limit_free = settings.FREE_PLAN_MONTHLY_CHAR_LIMIT # Secondary
                    logger.info(f"[AssessmentWorker] FREE Plan: Current cycle words: {current_cycle_words}, Doc words: {doc_word_count}, Word Limit: {plan_word_limit_free}")

                    if (current_cycle_words + doc_word_count) > plan_word_limit_free:
                        limit_exceeded = True
                        exceeded_by = "word"
                        logger.warning(f"[AssessmentWorker] Document {document.id} (words: {doc_word_count}) for teacher {teacher_id} would exceed FREE plan current cycle word limit of {plan_word_limit_free} (current usage: {current_cycle_words}). Projected total: {current_cycle_words + doc_word_count}")
                    
                    # Character limit check can remain secondary or be removed if words_used_current_cycle is the single source of truth for quota
                    # For now, let's keep it simple and rely on word count primarily.
                    # if not limit_exceeded and (current_monthly_chars + doc_char_count) > plan_char_limit_free:
                    #     limit_exceeded = True
                    #     exceeded_by = "character"
                    #     logger.warning(f"[AssessmentWorker] Document {document.id} (chars: {doc_char_count}) for teacher {teacher_id} would exceed FREE plan monthly char limit of {plan_char_limit_free} (current usage: {current_monthly_chars}). Projected total: {current_monthly_chars + doc_char_count}")
                
                elif current_plan == SubscriptionPlan.PRO:
                    plan_word_limit_pro = settings.PRO_PLAN_MONTHLY_WORD_LIMIT
                    # plan_char_limit_pro = settings.PRO_PLAN_MONTHLY_CHAR_LIMIT # Secondary
                    logger.info(f"[AssessmentWorker] PRO Plan: Current cycle words: {current_cycle_words}, Doc words: {doc_word_count}, Word Limit: {plan_word_limit_pro}")

                    if (current_cycle_words + doc_word_count) > plan_word_limit_pro:
                        limit_exceeded = True
                        exceeded_by = "word"
                        logger.warning(f"[AssessmentWorker] Document {document.id} (words: {doc_word_count}) for teacher {teacher_id} would exceed PRO plan current cycle word limit of {plan_word_limit_pro} (current usage: {current_cycle_words}). Projected total: {current_cycle_words + doc_word_count}")
                    
                    # Similar to FREE, character limit is secondary
                    # if not limit_exceeded and (current_monthly_chars + doc_char_count) > plan_char_limit_pro:
                    #     limit_exceeded = True
                    #     exceeded_by = "character"
                    #     logger.warning(f"[AssessmentWorker] Document {document.id} (chars: {doc_char_count}) for teacher {teacher_id} would exceed PRO plan monthly char limit of {plan_char_limit_pro} (current usage: {current_monthly_chars}). Projected total: {current_monthly_chars + doc_char_count}")

                else: # Fallback for any other unknown non-SCHOOLS plan - use FREE plan limits based on words
                    plan_word_limit_fallback = settings.FREE_PLAN_MONTHLY_WORD_LIMIT
                    logger.warning(f"[AssessmentWorker] Unknown plan {current_plan} for teacher {teacher_id}. Applying default free word limit ({plan_word_limit_fallback}) as a fallback.")
                    logger.info(f"[AssessmentWorker] FALLBACK Plan: Cycle words: {current_cycle_words}, Doc words: {doc_word_count}, Limit: {plan_word_limit_fallback}")
                    if (current_cycle_words + doc_word_count) > plan_word_limit_fallback:
                        limit_exceeded = True
                        exceeded_by = "word (fallback)"
                        logger.warning(f"[AssessmentWorker] Document {document.id} (words: {doc_word_count}) for teacher {teacher_id} would exceed FALLBACK (free) cycle word limit of {plan_word_limit_fallback} (current usage: {current_cycle_words}).")

                if limit_exceeded:
                    error_message = f"Cycle {exceeded_by} limit exceeded."
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

            # --- Real ML API Call ---
            ml_api_response: Dict[str, Any]
            if not extracted_text: # Handle empty text case
                logger.warning(f"[AssessmentWorker] Extracted text is empty for doc {document.id}. Skipping ML API call, treating as human.")
                ml_api_response = {
                    "ai_generated": False,
                    "human_generated": True, # Treat empty as human
                    "results": [] 
                }
            else:
                ml_api_response = await self._call_ml_api(extracted_text)
            
            if ml_api_response.get("error"): # Check if _call_ml_api returned an error structure
                ml_api_error_message = f"ML API Error: {ml_api_response.get('error')} - {ml_api_response.get('detail', '')}"
                logger.error(f"[AssessmentWorker] {ml_api_error_message} for doc {document.id}")
                # Proceed to update result as FAILED, but don't raise to hit the finally block for cleanup
            # --- End of Real ML API Call ---

            # --- Process ML API Response ---
            overall_ai_score_from_api: Optional[float] = None
            api_ai_flag = ml_api_response.get("ai_generated")
            api_human_flag = ml_api_response.get("human_generated")

            if ml_api_error_message: # If API call failed, treat as undetermined
                 overall_ai_score_from_api = None 
            elif api_ai_flag is True:
                overall_ai_score_from_api = 1.0
            elif api_human_flag is True and api_ai_flag is False: # Explicitly human and not AI
                overall_ai_score_from_api = 0.0
            elif "results" in ml_api_response and not ml_api_response["results"] and api_ai_flag is False : # Empty results, not AI
                 overall_ai_score_from_api = 0.0 
            else: # Undetermined or flags not present as expected
                 logger.warning(f"[AssessmentWorker] ML API response for doc {document.id} had ai_generated={api_ai_flag}, human_generated={api_human_flag}. Overall score defaults to None.")
                 overall_ai_score_from_api = None # Default for ambiguous cases without clear AI/Human flags

            paragraph_results_from_api: List[ParagraphResult] = []
            if "results" in ml_api_response and isinstance(ml_api_response["results"], list):
                for para_data in ml_api_response["results"]:
                    paragraph_results_from_api.append(
                        ParagraphResult(
                            paragraph=para_data.get("paragraph"),
                            label=para_data.get("label"),
                            probability=para_data.get("probability")
                            # segments will be None as the provided API structure doesn't include sub-paragraph segments
                        )
                    )
            # --- End of Process ML API Response ---
            
            # Determine final result status based on whether an ML API error occurred
            current_result_status = ResultStatus.COMPLETED if not ml_api_error_message else ResultStatus.FAILED
            
            # Determine overall label based on API flags and error status
            overall_label_for_result: Optional[str] = None
            if ml_api_error_message:
                overall_label_for_result = "Error"
            elif api_ai_flag is True: # Parsed from ml_api_response.get("ai_generated")
                overall_label_for_result = "AI Generated"
            elif api_human_flag is True and api_ai_flag is False: # Parsed from ml_api_response.get("human_generated")
                overall_label_for_result = "Human Written"
            else:
                overall_label_for_result = "Undetermined"

            # Update the Result object using crud.update_result_status
            updated_result = await crud.update_result_status(
                result_id=result.id, 
                teacher_id=teacher_id,
                status=current_result_status,
                score=overall_ai_score_from_api, 
                label=overall_label_for_result,
                ai_generated=api_ai_flag, 
                human_generated=api_human_flag, 
                paragraph_results=paragraph_results_from_api, 
                error_message=ml_api_error_message
            )

            if not updated_result:
                logger.error(f"[AssessmentWorker] Failed to update result {result.id} with ML API data for doc {document.id}. Re-queueing task.")
                final_error_msg_for_task_retry = ml_api_error_message or "RESULT_UPDATE_ML_DATA_FAILED"
                await self._update_task_for_retry(task, final_error_msg_for_task_retry)
                return 
            
            logger.info(f"[AssessmentWorker] Successfully updated result {result.id} with ML data for doc {document.id}. Status: {current_result_status}")

            # Update Document status based on the outcome of result processing
            final_doc_status = DocumentStatus.COMPLETED if current_result_status == ResultStatus.COMPLETED else DocumentStatus.ERROR
            # Update document score only if successfully completed and score is available
            score_to_update = overall_ai_score_from_api if final_doc_status == DocumentStatus.COMPLETED else None
            doc_status_updated = await crud.update_document_status(
                document_id=document.id, 
                teacher_id=teacher_id, 
                status=final_doc_status,
                score=score_to_update
            )
            if not doc_status_updated:
                 logger.error(f"[AssessmentWorker] Failed to update document {document.id} to {final_doc_status} after ML processing. Re-queueing task.")
                 await self._update_task_for_retry(task, f"DOC_UPDATE_{final_doc_status.value}_FAILED")
                 return 
            
            # Increment teacher's processed counts if successful and not SCHOOLS plan
            if final_doc_status == DocumentStatus.COMPLETED and teacher_db.current_plan != SubscriptionPlan.SCHOOLS: # Check teacher_db again
                increment_words = word_count if word_count is not None else 0
                await crud.increment_teacher_usage_cycle_counts(
                    kinde_id=teacher_id,
                    words_to_add=increment_words,
                    documents_to_add=1
                )
                logger.info(f"[AssessmentWorker] Incremented usage for teacher {teacher_id}: {increment_words} words, 1 document.")

            logger.info(f"[AssessmentWorker] Successfully processed task {task.id} for document {document.id}. Final doc status: {final_doc_status}")
            await self._delete_assessment_task(task.id) # Task completed successfully or failed terminally (API error)

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
        Calls the actual ML API with the provided document content.
        Handles potential errors and returns the API's JSON response.
        """
        # MODIFIED: Use settings.ML_AIDETECTOR_URL
        if not settings.ML_AIDETECTOR_URL:
            logger.error("ML_AIDETECTOR_URL is not configured in settings. Cannot make API call.")
            return {"error": "ML_AIDETECTOR_URL not configured", "detail": "Service unavailable.", "ai_generated": False, "human_generated": False, "results": []}

        # MODIFIED: Use settings.ML_AIDETECTOR_URL
        logger.info(f"[_call_ml_api] Calling ML API at {settings.ML_AIDETECTOR_URL} for document content (first 100 chars): {document_content[:100]}...")
        
        payload = {"text": document_content} 

        try:
            # MODIFIED: Use settings.ML_AIDETECTOR_URL
            async with httpx.AsyncClient(timeout=settings.ML_API_TIMEOUT_SECONDS) as client:
                response = await client.post(settings.ML_AIDETECTOR_URL, json=payload)
                response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
                
                api_response_data = response.json()
                logger.info(f"[_call_ml_api] Successfully received response from ML API.")
                # logger.debug(f"[_call_ml_api] ML API Response data: {api_response_data}") # Can be very verbose
                return api_response_data

        except httpx.HTTPStatusError as e:
            response_text = ""
            try:
                response_text = e.response.text # Try to get error text from response
            except Exception: # Handle cases where .text might not be available or fails
                response_text = "Could not retrieve error response body."
            logger.error(f"[_call_ml_api] HTTP error calling ML API: {e.response.status_code} - {response_text}", exc_info=True)
            # Return a structured error that _process_task can understand
            return {"error": f"HTTP error {e.response.status_code}", "detail": response_text, "ai_generated": False, "human_generated": False, "results": []}
        except httpx.RequestError as e: # Covers network errors, timeouts, etc.
            logger.error(f"[_call_ml_api] Request error calling ML API: {e}", exc_info=True)
            return {"error": f"Request error: {str(e)}", "ai_generated": False, "human_generated": False, "results": []}
        except Exception as e: # Catch-all for other unexpected errors (e.g., JSON decoding if API returns malformed JSON)
            logger.error(f"[_call_ml_api] Unexpected error calling ML API: {e}", exc_info=True)
            return {"error": f"Unexpected error: {str(e)}", "ai_generated": False, "human_generated": False, "results": []}

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