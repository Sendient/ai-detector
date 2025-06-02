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
from ..queue import dequeue_assessment_task
from ..models.task import AssessmentTask
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

# Custom Exceptions for AssessmentWorker
class WorkerProcessingError(Exception):
    """Base exception for worker processing issues."""
    pass

class DocumentPreparationError(WorkerProcessingError):
    """Error during document/result fetching or initial status updates."""
    pass

class TextExtractionError(WorkerProcessingError):
    """Base for text extraction issues."""
    pass

class FileDownloadError(TextExtractionError):
    """Error downloading file from blob storage."""
    pass

class UnsupportedFileTypeError(TextExtractionError):
    """File type is not supported for extraction."""
    pass

class TextProcessingError(TextExtractionError):
    """Generic error during text processing or counting."""
    pass

class UsageLimitError(WorkerProcessingError):
    """Base for usage limit issues."""
    pass

class UserNotFoundForLimitCheckError(UsageLimitError):
    """Teacher record not found when checking usage limits."""
    pass

class PlanLimitExceededError(UsageLimitError):
    """Teacher's plan usage limits exceeded."""
    def __init__(self, message="Plan limit exceeded", limit_type="word/character"):
        super().__init__(message)
        self.limit_type = limit_type

class MlApiError(WorkerProcessingError):
    """Base for ML API call or processing issues."""
    pass

class MlApiConfigError(MlApiError):
    """ML API URL not configured."""
    pass

class MlApiHttpError(MlApiError):
    """HTTP error when calling the ML API."""
    def __init__(self, status_code: int, detail: Optional[str] = None):
        super().__init__(f"ML API returned HTTP {status_code}. Detail: {detail or 'N/A'}")
        self.status_code = status_code
        self.detail = detail

class MlApiConnectionError(MlApiError):
    """Network or connection error when calling the ML API."""
    pass

class MlApiReportedError(MlApiError):
    """ML API returned a response indicating an error in its own processing."""
    def __init__(self, api_error_message: str, api_error_detail: Optional[str] = None):
        super().__init__(f"ML API reported error: {api_error_message}. Detail: {api_error_detail or 'N/A'}")
        self.api_error_message = api_error_message
        self.api_error_detail = api_error_detail

class MlApiResponseParseError(MlApiError):
    """Error parsing the response from the ML API."""
    pass

class TaskFinalizationError(WorkerProcessingError):
    """Error during final updates to document/result or teacher usage."""
    pass

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

    async def _prepare_document_and_result(self, task: AssessmentTask) -> tuple[Any, Any]:
        """
        Fetches/creates Document and Result, and updates their statuses to PROCESSING.
        Raises DocumentPreparationError on failure after attempting task retry.
        """
        document_id = task.document_id
        teacher_id = task.user_id
        document = None # Initialize to ensure it's defined for potential error logging

        # Get the associated Document
        document = await crud.get_document_by_id(document_id=document_id, teacher_id=teacher_id)
        if not document:
            logger.error(f"[AssessmentWorker__prepare] Document {document_id} not found for task {task.id}.")
            # Current logic in _process_task for 'document not found' (line 96) is to return and let task be picked up again.
            # To maintain this, we raise an error that _process_task can catch and then decide to return without retry.
            # Or, if retry is desired for this specific case, call _update_task_for_retry here.
            # For now, let's make it a distinct error that signals _process_task to just stop for this task attempt.
            raise DocumentPreparationError(f"Document {document_id} not found.")

        # Update Document status to PROCESSING
        doc_status_updated = await crud.update_document_status(document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.PROCESSING)
        if not doc_status_updated:
            error_msg = f"Failed to update document {document_id} to PROCESSING."
            logger.critical(f"[AssessmentWorker__prepare] {error_msg} for task {task.id}.")
            await self._update_task_for_retry(task, "PREPARE_DOC_UPDATE_PROCESSING_FAILED")
            raise DocumentPreparationError(error_msg)
        
        # Get or create Result
        result = await crud.get_result_by_document_id(document_id=document_id, teacher_id=teacher_id)
        if not result:
            logger.warning(f"[AssessmentWorker__prepare] Result not found for doc {document_id} (task {task.id}). Creating.")
            try:
                result_in_create = ResultCreate(document_id=document_id, teacher_id=teacher_id)
                result = await crud.create_result(result_in=result_in_create)
                if not result: # create_result itself might return None on failure
                    error_msg = f"Failed to create result for doc {document_id}."
                    logger.error(f"[AssessmentWorker__prepare] {error_msg} Aborting task {task.id}.")
                    # Attempt to set document status back to ERROR
                    await crud.update_document_status(document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.ERROR)
                    await self._update_task_for_retry(task, "PREPARE_RESULT_CREATION_FAILED")
                    raise DocumentPreparationError(error_msg)
            except Exception as e_create_res: # Catch any exception during result creation
                error_msg = f"Exception during result creation for doc {document_id}: {e_create_res}"
                logger.error(f"[AssessmentWorker__prepare] {error_msg}", exc_info=True)
                await crud.update_document_status(document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.ERROR)
                await self._update_task_for_retry(task, "PREPARE_RESULT_CREATION_EXCEPTION")
                raise DocumentPreparationError(error_msg)

        # Update Result status to PROCESSING
        result_status_updated = await crud.update_result_status(
            result_id=result.id,
            status=ResultStatus.PROCESSING,
            teacher_id=teacher_id
        )
        if not result_status_updated:
            error_msg = f"Failed to update result {result.id} to PROCESSING."
            logger.critical(f"[AssessmentWorker__prepare] {error_msg} for task {task.id} (doc {document_id}).")
            # Document is already PROCESSING, if result update fails, retry the whole task.
            await self._update_task_for_retry(task, "PREPARE_RESULT_UPDATE_PROCESSING_FAILED")
            raise DocumentPreparationError(error_msg)
        
        logger.info(f"[AssessmentWorker__prepare] Document {document.id} and Result {result.id} prepared and set to PROCESSING for task {task.id}.")
        return document, result

    async def _extract_text_and_counts(self, document: Any, teacher_id: str) -> tuple[str, int, int]:
        """
        Extracts text from the document, calculates counts, and updates the document record.
        Raises TextExtractionError or its subclasses on failure.
        """
        logger.info(f"[AssessmentWorker__extract] Starting text extraction for doc {document.id}")
        
        file_type_enum_member: Optional[FileType] = None
        if isinstance(document.file_type, str):
            try:
                file_type_enum_member = FileType(document.file_type.lower())
            except ValueError:
                logger.error(f"[AssessmentWorker__extract] Unknown file_type string '{document.file_type}' for doc {document.id}.")
                raise UnsupportedFileTypeError(f"Could not map document.file_type '{document.file_type}' to FileType enum.")
        elif isinstance(document.file_type, FileType):
            file_type_enum_member = document.file_type
        
        if not file_type_enum_member:
            # This case should ideally be caught by the above checks, but as a safeguard:
            logger.error(f"[AssessmentWorker__extract] file_type '{document.file_type}' is not a valid FileType enum member for doc {document.id}.")
            raise UnsupportedFileTypeError(f"Invalid file_type '{document.file_type}'.")

        try:
            file_bytes = await download_blob_as_bytes(document.storage_blob_path)
        except Exception as e_download: # Broad catch for download issues
            logger.error(f"[AssessmentWorker__extract] Failed to download blob {document.storage_blob_path} for doc {document.id}: {e_download}", exc_info=True)
            raise FileDownloadError(f"Failed to download blob {document.storage_blob_path}: {e_download}")

        if file_bytes is None: # download_blob_as_bytes might return None on some failures
            logger.error(f"[AssessmentWorker__extract] Downloaded file_bytes is None for blob {document.storage_blob_path} (doc {document.id}).")
            raise FileDownloadError(f"Downloaded file_bytes is None for blob {document.storage_blob_path}")

        try:
            extracted_text = await asyncio.to_thread(extract_text_from_bytes, file_bytes, file_type_enum_member)
            if extracted_text is None: extracted_text = "" # Ensure string type for len()
        except Exception as e_extract: # Broad catch for text_extraction service errors
            logger.error(f"[AssessmentWorker__extract] Error during extract_text_from_bytes for doc {document.id}: {e_extract}", exc_info=True)
            raise TextProcessingError(f"Error extracting text from bytes for doc {document.id}: {e_extract}")
            
        character_count = len(extracted_text)
        
        # Revised word count logic (from original _process_task)
        raw_tokens = re.split(r'\s+', extracted_text.strip())
        cleaned_tokens = [token.strip(string.punctuation) for token in raw_tokens]
        words = [token for token in cleaned_tokens if token]
        word_count = len(words)
        
        logger.info(f"[AssessmentWorker__extract] Text extraction complete for doc {document.id}. Chars: {character_count}, Words: {word_count}")

        # Always update document with character and word counts, regardless of limit checks
        try:
            doc_counts_updated = await crud.update_document_counts(
                document_id=document.id, 
                teacher_id=teacher_id, 
                character_count=character_count, 
                word_count=word_count
            )
            if not doc_counts_updated:
                # Log error but proceed as per original logic (line 176-178)
                logger.error(f"[AssessmentWorker__extract] Failed to update char/word counts for doc {document.id}. Proceeding, but counts may be stale.")
        except Exception as e_update_counts:
            logger.error(f"[AssessmentWorker__extract] Exception updating char/word counts for doc {document.id}: {e_update_counts}. Proceeding.", exc_info=True)
            
        return extracted_text, character_count, word_count

    async def _check_usage_limits(self, task: AssessmentTask, result: Any, document_id: uuid.UUID, teacher_id: str, word_count: int) -> Any:
        """
        Checks teacher usage limits. 
        Deletes task if limits exceeded or user not found (after updating statuses).
        Retries task if DB updates for limit exceeded status fail.
        Returns teacher_db object if usage is within limits.
        Raises UserNotFoundForLimitCheckError or PlanLimitExceededError.
        """
        logger.info(f"[AssessmentWorker__limits] Checking usage limits for task {task.id}, teacher {teacher_id}, doc {document_id}.")
        
        teacher_db = await crud.get_teacher_by_kinde_id(kinde_id=teacher_id)
        if not teacher_db:
            error_message = "User not found, cannot verify usage limits."
            logger.error(f"[AssessmentWorker__limits] Teacher {teacher_id} not found for task {task.id}. {error_message}")
            doc_limit_err_update = await crud.update_document_status(document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.ERROR)
            res_limit_err_update = await crud.update_result_status(
                result_id=result.id, 
                status=ResultStatus.FAILED,
                teacher_id=teacher_id,
                error_message=error_message
            )
            if not doc_limit_err_update or not res_limit_err_update:
                logger.error(f"[AssessmentWorker__limits] Failed to update doc/result to ERROR after teacher not found for task {task.id}. Retrying task.")
                await self._update_task_for_retry(task, "DB_UPDATE_TEACHER_NOT_FOUND_FAILED_LIMIT_CHECK")
                # Still raise, as the core issue (user not found) for this path is critical for limit check
                raise UserNotFoundForLimitCheckError(f"Teacher {teacher_id} not found, and DB status update failed.")
            
            await self._delete_assessment_task(task.id) # Delete task as user not found
            raise UserNotFoundForLimitCheckError(f"Teacher {teacher_id} not found. Task deleted.")

        current_plan = teacher_db.current_plan
        logger.info(f"[AssessmentWorker__limits] Teacher {teacher_id} is on plan: {current_plan} for doc {document_id}.")

        if current_plan == SubscriptionPlan.SCHOOLS:
            logger.info(f"[AssessmentWorker__limits] Teacher {teacher_id} on SCHOOLS plan. Bypassing usage limit check for doc {document_id}.")
            return teacher_db # Proceed with processing

        # Logic for non-SCHOOLS plans
        current_cycle_words = teacher_db.words_used_current_cycle if teacher_db.words_used_current_cycle is not None else 0
        doc_actual_word_count = word_count if word_count is not None else 0

        limit_exceeded_flag = False
        exceeded_by_reason = ""
        plan_limit = 0

        if current_plan == SubscriptionPlan.FREE:
            plan_limit = settings.FREE_PLAN_MONTHLY_WORD_LIMIT
            if (current_cycle_words + doc_actual_word_count) > plan_limit:
                limit_exceeded_flag = True
                exceeded_by_reason = "word"
        elif current_plan == SubscriptionPlan.PRO:
            plan_limit = settings.PRO_PLAN_MONTHLY_WORD_LIMIT
            if (current_cycle_words + doc_actual_word_count) > plan_limit:
                limit_exceeded_flag = True
                exceeded_by_reason = "word"
        else: # Fallback for unknown non-SCHOOLS plan
            plan_limit = settings.FREE_PLAN_MONTHLY_WORD_LIMIT # Default to free limit
            logger.warning(f"[AssessmentWorker__limits] Unknown plan {current_plan} for teacher {teacher_id}. Applying free word limit ({plan_limit}).")
            if (current_cycle_words + doc_actual_word_count) > plan_limit:
                limit_exceeded_flag = True
                exceeded_by_reason = "word (fallback)"
        
        if limit_exceeded_flag:
            log_msg = f"Document {document_id} (words: {doc_actual_word_count}) for teacher {teacher_id} (Plan: {current_plan}) would exceed cycle {exceeded_by_reason} limit of {plan_limit} (current usage: {current_cycle_words})."
            logger.warning(f"[AssessmentWorker__limits] {log_msg}")
            error_message_db = f"Cycle {exceeded_by_reason} limit exceeded."
            
            doc_limit_update_success = await crud.update_document_status(document_id=document_id, teacher_id=teacher_id, status=DocumentStatus.LIMIT_EXCEEDED)
            res_limit_update_success = await crud.update_result_status(
                result_id=result.id,
                status=ResultStatus.FAILED,
                teacher_id=teacher_id,
                error_message=error_message_db
            )

            if not doc_limit_update_success or not res_limit_update_success:
                logger.error(f"[AssessmentWorker__limits] Failed to update doc/result to LIMIT_EXCEEDED/FAILED for task {task.id}. Retrying task.")
                await self._update_task_for_retry(task, "DB_UPDATE_LIMIT_EXCEEDED_FAILED")
                raise PlanLimitExceededError(message=f"Limit exceeded and DB status update failed for task {task.id}.", limit_type=exceeded_by_reason)
            
            await self._delete_assessment_task(task.id)
            logger.info(f"[AssessmentWorker__limits] Task {task.id} deleted due to {exceeded_by_reason} limit exceeded.")
            raise PlanLimitExceededError(message=log_msg, limit_type=exceeded_by_reason)

        logger.info(f"[AssessmentWorker__limits] Usage limits check passed for teacher {teacher_id}, doc {document_id}.")
        return teacher_db # Usage is within limits

    async def _execute_ml_call_and_parse_response(self, extracted_text: str, document_id: uuid.UUID) -> tuple[Optional[str], Optional[float], List[ParagraphResult], Optional[bool], Optional[bool]]:
        """
        Executes the ML API call via _call_ml_api and processes its response.
        Returns a tuple: (ml_api_error_for_result_update, overall_ai_score, paragraph_results, api_ai_flag, api_human_flag)
        The first element (error message) is populated if _call_ml_api indicated an issue, allowing FAILED status recording.
        Raises specific MlApiError subclasses for critical/unrecoverable API issues.
        """
        logger.info(f"[AssessmentWorker__ml_execute] Preparing ML API call for doc {document_id}.")

        if not extracted_text:
            logger.warning(f"[AssessmentWorker__ml_execute] Extracted text is empty for doc {document_id}. Skipping ML API call, treating as human.")
            return None, 0.0, [], False, True # No error msg, 0.0 score, no paragraphs, not AI, is Human

        # Call the internal _call_ml_api method which handles actual HTTP call and its direct errors
        ml_api_response_dict = await self._call_ml_api(extracted_text)

        # Check if _call_ml_api itself caught an error and returned an error structure
        # (e.g., ML_AIDETECTOR_URL not configured, HTTP error, Request error)
        if "error" in ml_api_response_dict:
            error_val = ml_api_response_dict["error"]
            detail_val = ml_api_response_dict.get("detail")
            logger.error(f"[AssessmentWorker__ml_execute] _call_ml_api reported an error for doc {document_id}: {error_val} - Detail: {detail_val}")
            
            if "ML_AIDETECTOR_URL not configured" in error_val:
                raise MlApiConfigError(str(error_val))
            elif "HTTP error" in str(error_val): # Error string from _call_ml_api's except httpx.HTTPStatusError
                status_code_match = re.search(r'HTTP error (\d+)', str(error_val))
                status_code = int(status_code_match.group(1)) if status_code_match else 500 # Default if parse fails
                raise MlApiHttpError(status_code=status_code, detail=str(detail_val))
            elif "Request error" in str(error_val): # Error string from _call_ml_api's except httpx.RequestError
                raise MlApiConnectionError(f"Request error during ML API call: {detail_val or error_val}")
            else: # Other unexpected errors reported by _call_ml_api
                # This will be the error message stored in the Result object if we proceed to FAILED status
                ml_api_error_for_result = f"ML API Error: {error_val} - {detail_val or ''}"
                # Return structure indicates failure but allows Result update to FAILED
                return ml_api_error_for_result, None, [], False, False # Error msg, No score, No paragraphs, flags false

        # If no "error" key, proceed to parse the successful response content
        try:
            api_ai_flag = ml_api_response_dict.get("ai_generated")
            api_human_flag = ml_api_response_dict.get("human_generated")
            overall_ai_score: Optional[float] = None

            if api_ai_flag is True:
                overall_ai_score = 1.0
            elif api_human_flag is True and api_ai_flag is False:
                overall_ai_score = 0.0
            elif "results" in ml_api_response_dict and not ml_api_response_dict["results"] and api_ai_flag is False:
                overall_ai_score = 0.0
            else:
                logger.warning(f"[AssessmentWorker__ml_execute] ML API response for doc {document_id} had ambiguous flags: ai_generated={api_ai_flag}, human_generated={api_human_flag}. Score defaults to None.")
                overall_ai_score = None # Undetermined

            paragraph_results_from_api: List[ParagraphResult] = []
            if "results" in ml_api_response_dict and isinstance(ml_api_response_dict["results"], list):
                for para_data in ml_api_response_dict["results"]:
                    paragraph_results_from_api.append(
                        ParagraphResult(
                            paragraph=para_data.get("paragraph"),
                            label=para_data.get("label"),
                            probability=para_data.get("probability")
                        )
                    )
            else:
                # If "results" key is missing or not a list, and it wasn't an empty text scenario
                if extracted_text: # Only raise if we expected results
                    logger.error(f"[AssessmentWorker__ml_execute] 'results' key missing or not a list in ML API response for doc {document_id}. Response: {str(ml_api_response_dict)[:200]}")
                    raise MlApiResponseParseError("ML API response missing 'results' list or invalid format.")
            
            logger.info(f"[AssessmentWorker__ml_execute] ML API response parsed successfully for doc {document_id}.")
            return None, overall_ai_score, paragraph_results_from_api, api_ai_flag, api_human_flag # No error message for result update

        except KeyError as ke:
            logger.error(f"[AssessmentWorker__ml_execute] KeyError parsing ML API response for doc {document_id}: {ke}. Response: {str(ml_api_response_dict)[:200]}", exc_info=True)
            raise MlApiResponseParseError(f"Missing expected key '{ke}' in ML API response.")
        except Exception as e_parse: # Catch any other parsing errors
            logger.error(f"[AssessmentWorker__ml_execute] Unexpected error parsing ML API response for doc {document_id}: {e_parse}. Response: {str(ml_api_response_dict)[:200]}", exc_info=True)
            raise MlApiResponseParseError(f"Unexpected error parsing ML API response: {e_parse}")

    async def _finalize_processing_and_update_db(
        self, 
        task: AssessmentTask, 
        document: Any, 
        result: Any, 
        teacher_db: Any, 
        word_count: int, 
        # char_count: int, # char_count is not directly used in this finalization block
        ml_output: tuple[Optional[str], Optional[float], List[ParagraphResult], Optional[bool], Optional[bool]]
    ) -> None:
        """
        Finalizes task processing by updating database records (Result, Document, Teacher usage)
        and deleting the task if successful. 
        Retries task if critical DB updates fail.
        Raises TaskFinalizationError on such DB update failures.
        """
        document_id = document.id
        teacher_id = task.user_id # Or from document.teacher_id / result.teacher_id for consistency

        logger.info(f"[AssessmentWorker__finalize] Finalizing processing for task {task.id}, doc {document_id}.")

        ml_api_error_message_for_result_update, overall_ai_score_from_api, paragraph_results_from_api, api_ai_flag, api_human_flag = ml_output

        # Determine final result status
        current_result_status = ResultStatus.COMPLETED if not ml_api_error_message_for_result_update else ResultStatus.FAILED
        
        overall_label_for_result: Optional[str]
        if ml_api_error_message_for_result_update:
            overall_label_for_result = "Error"
        elif api_ai_flag is True:
            overall_label_for_result = "AI Generated"
        elif api_human_flag is True and api_ai_flag is False:
            overall_label_for_result = "Human Written"
        else:
            overall_label_for_result = "Undetermined"

        # Update Result object
        try:
            updated_result_obj = await crud.update_result_status(
                result_id=result.id, 
                teacher_id=teacher_id,
                status=current_result_status,
                score=overall_ai_score_from_api, 
                label=overall_label_for_result,
                ai_generated=api_ai_flag, 
                human_generated=api_human_flag, 
                paragraph_results=paragraph_results_from_api, 
                error_message=ml_api_error_message_for_result_update
            )
            if not updated_result_obj:
                err_msg = f"Failed to update result {result.id} with ML data for doc {document_id}."
                logger.error(f"[AssessmentWorker__finalize] {err_msg}")
                final_error_for_task_retry = ml_api_error_message_for_result_update or "FINALIZE_RESULT_UPDATE_ML_DATA_FAILED"
                await self._update_task_for_retry(task, final_error_for_task_retry)
                raise TaskFinalizationError(err_msg)
        except Exception as e_res_update:
            err_msg = f"Exception updating result {result.id} for doc {document_id}: {e_res_update}"
            logger.error(f"[AssessmentWorker__finalize] {err_msg}", exc_info=True)
            await self._update_task_for_retry(task, "FINALIZE_RESULT_UPDATE_EXCEPTION")
            raise TaskFinalizationError(err_msg)
            
        logger.info(f"[AssessmentWorker__finalize] Successfully updated result {result.id} for doc {document_id}. Status: {current_result_status}")

        # Update Document status
        final_doc_status = DocumentStatus.COMPLETED if current_result_status == ResultStatus.COMPLETED else DocumentStatus.ERROR
        score_to_update_doc = overall_ai_score_from_api if final_doc_status == DocumentStatus.COMPLETED else None
        
        try:
            doc_status_updated_success = await crud.update_document_status(
                document_id=document.id, 
                teacher_id=teacher_id, 
                status=final_doc_status,
                score=score_to_update_doc
            )
            if not doc_status_updated_success:
                err_msg = f"Failed to update document {document.id} to {final_doc_status} after ML processing."
                logger.error(f"[AssessmentWorker__finalize] {err_msg}")
                await self._update_task_for_retry(task, f"FINALIZE_DOC_UPDATE_{final_doc_status.value}_FAILED")
                raise TaskFinalizationError(err_msg)
        except Exception as e_doc_update:
            err_msg = f"Exception updating document {document.id} to {final_doc_status}: {e_doc_update}"
            logger.error(f"[AssessmentWorker__finalize] {err_msg}", exc_info=True)
            await self._update_task_for_retry(task, f"FINALIZE_DOC_UPDATE_{final_doc_status.value}_EXCEPTION")
            raise TaskFinalizationError(err_msg)

        # Increment teacher's processed counts if successful and not SCHOOLS plan
        if final_doc_status == DocumentStatus.COMPLETED and teacher_db.current_plan != SubscriptionPlan.SCHOOLS:
            try:
                increment_words = word_count if word_count is not None else 0
                await crud.increment_teacher_usage_cycle_counts(
                    kinde_id=teacher_id,
                    words_to_add=increment_words,
                    documents_to_add=1
                )
                logger.info(f"[AssessmentWorker__finalize] Incremented usage for teacher {teacher_id}: {increment_words} words, 1 document.")
            except Exception as e_usage_inc:
                # Log error but don't fail the entire task processing for this, as main analysis is done.
                logger.error(f"[AssessmentWorker__finalize] Failed to increment usage for teacher {teacher_id}, doc {document.id}: {e_usage_inc}", exc_info=True)

        logger.info(f"[AssessmentWorker__finalize] Successfully finalized processing for task {task.id}, doc {document.id}. Final doc status: {final_doc_status}. Deleting task.")
        await self._delete_assessment_task(task.id) # Task completed successfully (or terminally failed due to ML error recorded)

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

        document: Optional[Any] = None
        result: Optional[Any] = None

        try:
            # Step 1: Prepare document and result
            document, result = await self._prepare_document_and_result(task)
        except DocumentPreparationError as e:
            if "Document" in str(e) and "not found" in str(e):
                logger.warning(f"[AssessmentWorker_PROCESS_TASK] Halting task {task.id} because document {document_id} not found. Task not retried by this path.")
                return 
            else:
                logger.error(f"[AssessmentWorker_PROCESS_TASK] Document/Result preparation failed for task {task.id}: {e}. Retry handled by helper.")
                return 
        
        # Initialize for the try-except block, in case _extract_text_and_counts fails early
        extracted_text: Optional[str] = None
        character_count: Optional[int] = None
        word_count: Optional[int] = None
        # Define teacher_db here as it's used in broader scope now
        teacher_db: Optional[Any] = None
        ml_api_error_message: Optional[str] = None # Retain this from original for ML error message storage

        try:
            # Step 2: Extract text and counts
            extracted_text, character_count, word_count = await self._extract_text_and_counts(document, teacher_id)

            # Step 3: Check usage limits
            # This helper returns teacher_db if successful, or raises an exception (handled below).
            # It internally handles task deletion or retry for certain failure modes.
            teacher_db = await self._check_usage_limits(task, result, document.id, teacher_id, word_count)

            # Initialize ml_output_tuple for use in potential ML error finalization path
            ml_output_tuple: tuple[Optional[str], Optional[float], List[ParagraphResult], Optional[bool], Optional[bool]]
            ml_output_tuple = (None, None, [], False, False) # Default error-like state

            try:
                # Step 4: Call ML API and parse response
                ml_output_tuple = await self._execute_ml_call_and_parse_response(extracted_text, document.id)
            except (MlApiConfigError, MlApiHttpError, MlApiConnectionError, MlApiReportedError, MlApiResponseParseError) as ml_err_e:
                logger.error(f"[AssessmentWorker_PROCESS_TASK] ML API call or parsing error for task {task.id}: {ml_err_e}")
                ml_api_error_for_result = f"ML_API_ERROR: {type(ml_err_e).__name__}: {str(ml_err_e)[:150]}" # Truncate
                ml_output_tuple = (ml_api_error_for_result, None, [], False, False) 
                # Proceed to finalization which will record a FAILED result.
            
            # Step 5: Finalize processing and update database
            await self._finalize_processing_and_update_db(
                task, document, result, teacher_db, 
                word_count, # char_count is not passed as it's not used by finalize
                ml_output_tuple
            )

        except DocumentPreparationError as e: # This was the first try-except block
            if "Document" in str(e) and "not found" in str(e):
                logger.warning(f"[AssessmentWorker_PROCESS_TASK] Halting task {task.id} because document {document_id} not found. Task not retried by this path.")
                return 
            else:
                logger.error(f"[AssessmentWorker_PROCESS_TASK] Document/Result preparation failed for task {task.id}: {e}. Retry handled by helper.")
                return 
        except (FileDownloadError, UnsupportedFileTypeError, TextProcessingError) as e: # From the second (main) try-except
            logger.error(f"[AssessmentWorker_PROCESS_TASK] Text extraction or processing failed for task {task.id}: {e}")
            await self._handle_generic_processing_failure(task, document, result, f"TEXT_EXTRACTION_ERROR:{type(e).__name__}")
        except UserNotFoundForLimitCheckError as e:
            logger.error(f"[AssessmentWorker_PROCESS_TASK] User not found for limit check, task {task.id}: {e}. Task state (deleted/retried) handled by helper.")
            return 
        except PlanLimitExceededError as e:
            logger.warning(f"[AssessmentWorker_PROCESS_TASK] Plan limit exceeded for task {task.id}: {e.message}. Task state (deleted/retried) handled by helper.")
            return
        # Note: MlApi... errors are caught inside the main try, then ml_output_tuple is set with error info, 
        # and _finalize_processing_and_update_db is called which will record the FAILED state.
        # If _finalize_processing_and_update_db then fails its own DB updates, it raises TaskFinalizationError.
        except TaskFinalizationError as e:
            logger.error(f"[AssessmentWorker_PROCESS_TASK] Task finalization failed for task {task.id}: {e}. Retry handled by helper.")
            return
        except Exception as e: # Catch-all for truly unexpected errors in the orchestration
            logger.error(f"[AssessmentWorker_PROCESS_TASK] Unhandled orchestration error for task {task.id} (doc id: {document_id if document else 'N/A'}): {e}", exc_info=True)
            await self._handle_generic_processing_failure(task, document, result, f"UNHANDLED_ORCHESTRATION_ERROR:{type(e).__name__}")
    
    async def _handle_generic_processing_failure(self, task: AssessmentTask, document: Optional[Any], result: Optional[Any], error_reason_key: str):
        """
        Helper to update document/result to ERROR/FAILED and requeue the task.
        """
        logger.warning(f"[AssessmentWorker__handle_failure] Handling generic failure for task {task.id}. Reason: {error_reason_key}")
        error_message_for_db = str(error_reason_key)[:500] # Truncate for DB
        
        # Ensure document_id and teacher_id are available for crud operations
        doc_id_for_crud = document.id if document else task.document_id
        teacher_id_for_crud = task.user_id # Assuming task.user_id is the teacher_id

        if document: # If document object exists, use its id
            try:
                await crud.update_document_status(document_id=doc_id_for_crud, teacher_id=teacher_id_for_crud, status=DocumentStatus.ERROR)
            except Exception as db_e:
                logger.error(f"[AssessmentWorker__handle_failure] Failed to update document status to ERROR for doc {doc_id_for_crud}: {db_e}")
        elif doc_id_for_crud and teacher_id_for_crud : # Fallback if document object doesn't exist but we have IDs
            logger.info(f"[AssessmentWorker__handle_failure] Document object not available for task {task.id}, attempting to update status by ID {doc_id_for_crud}.")
            try:
                await crud.update_document_status(document_id=doc_id_for_crud, teacher_id=teacher_id_for_crud, status=DocumentStatus.ERROR)
            except Exception as db_e:
                logger.error(f"[AssessmentWorker__handle_failure] Failed to update document status by ID to ERROR for doc {doc_id_for_crud}: {db_e}")

        if result: # If result object exists, use its id
            try:
                await crud.update_result_status(
                    result_id=result.id,
                    status=ResultStatus.FAILED,
                    teacher_id=teacher_id_for_crud,
                    error_message=error_message_for_db
                )
            except Exception as db_e:
                logger.error(f"[AssessmentWorker__handle_failure] Failed to update result status to FAILED for result {result.id}: {db_e}")
        elif doc_id_for_crud and teacher_id_for_crud: # Fallback if result object doesn't exist but we can try to find/update by doc_id
            logger.info(f"[AssessmentWorker__handle_failure] Result object not available for task {task.id}. Attempting to find and update result by doc ID {doc_id_for_crud}.")
            # This might be complex if result doesn't exist; the original code had specific result creation logic.
            # For a generic handler, simplest is to log. If result creation is essential, _prepare_document_and_result should handle it.
            # Here, we assume if result object isn't passed, we might not have its ID directly to update.
            # A more robust solution might involve trying to fetch result by doc_id then update.
            # For now, logging the limitation.
            pass # Or attempt to fetch result then update if critical
                
        await self._update_task_for_retry(task, error_reason_key)

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
            "status": "PENDING", # Changed from "RETRYING"
            "retry_count": retry_count,
            "available_at": available_at,
            "last_error": f"{error_reason} at {datetime.now(timezone.utc).isoformat()}"
        }

        try:
            logger.info(f"[AssessmentWorker] Updating task {task.id} for retry (status PENDING). Error: {error_reason}. Retry count: {retry_count}. Available at: {available_at.isoformat()}")
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