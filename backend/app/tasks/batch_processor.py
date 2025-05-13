# app/tasks/batch_processor.py

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, List
import uuid
from pymongo import ReturnDocument

from ..db import crud
from ..db.database import get_database
from ..models.enums import BatchStatus, DocumentStatus, ResultStatus
from ..models.document import Document
from ..models.batch import Batch, BatchUpdate
from ..services.text_extraction import extract_text_from_bytes
from ..services.blob_storage import download_blob_as_bytes

# Configure logging
logger = logging.getLogger(__name__)

class BatchProcessor:
    def __init__(self):
        self.is_running = False
        self.current_batch: Optional[Batch] = None
        self.current_documents: List[Document] = []

    async def process_batches(self):
        """Main loop for processing batches."""
        self.is_running = True
        try:
            while self.is_running:
                # Get next batch to process (now atomically claims it)
                batch = await self._get_next_batch()
                if not batch:
                    # No batches to process, wait before checking again
                    await asyncio.sleep(10)
                    continue

                self.current_batch = batch
                logger.info(f"Processing batch {batch.id} (claimed atomically)")

                try:
                    # Get all documents in the batch
                    self.current_documents = await crud.get_documents_by_batch_id(batch_id=batch.id)
                    
                    # Sort documents by queue position
                    self.current_documents.sort(key=lambda x: x.queue_position or float('inf'))
                    
                    # Process each document
                    completed = 0
                    failed = 0
                    for doc in self.current_documents:
                        try:
                            success = await self._process_document(doc)
                            if success:
                                completed += 1
                            else:
                                failed += 1
                        except Exception as e:
                            logger.error(f"Error processing document {doc.id} in batch {batch.id}: {e}")
                            failed += 1
                            continue

                    # Update batch status
                    final_status = BatchStatus.COMPLETED if failed == 0 else BatchStatus.PARTIAL
                    await crud.update_batch(
                        batch_id=batch.id,
                        batch_in=BatchUpdate(
                            status=final_status,
                            completed_files=completed,
                            failed_files=failed,
                            error_message=f"Failed to process {failed} files" if failed > 0 else None
                        )
                    )

                except Exception as e:
                    logger.error(f"Error processing batch {batch.id}: {e}")
                    await crud.update_batch(
                        batch_id=batch.id,
                        batch_in=BatchUpdate(
                            status=BatchStatus.ERROR,
                            error_message=str(e)
                        )
                    )
                finally:
                    self.current_batch = None
                    self.current_documents = []

        except Exception as e:
            logger.error(f"Batch processor error: {e}")
            self.is_running = False

    async def _get_next_batch(self) -> Optional[Batch]:
        """
        Atomically find the next batch in QUEUED status, update its status
        to PROCESSING, and return it. Ordered by priority and creation time.
        """
        try:
            db = get_database()
            if db is None:
                logger.error("Database connection not available for getting next batch.")
                return None

            collection = db.batches
            
            # Define the query filter for finding a queued batch
            query_filter = {"status": BatchStatus.QUEUED.value}

            # Define the update to set status to PROCESSING and update timestamp
            # Use timezone.utc for consistency
            update_doc = {
                "$set": {
                    "status": BatchStatus.PROCESSING.value,
                    "updated_at": datetime.now(timezone.utc) 
                }
            }

            # Define the sort order
            sort_order = [("priority", -1), ("created_at", 1)]

            logger.debug(f"Attempting to find and claim next batch with filter: {query_filter}, sort: {sort_order}")

            # Atomically find one document, update it, and return the updated document
            updated_batch_dict = await collection.find_one_and_update(
                filter=query_filter,
                update=update_doc,
                sort=sort_order,
                return_document=ReturnDocument.AFTER
            )

            if updated_batch_dict:
                logger.info(f"Atomically claimed batch {updated_batch_dict['_id']} for processing.")
                return Batch(**updated_batch_dict) 
            else:
                logger.debug("No QUEUED batches found to process.")
                return None

        except Exception as e:
            logger.error(f"Error getting next batch atomically: {e}", exc_info=True)
            return None

    async def _process_document(self, document: Document) -> bool:
        """Process a single document in the batch."""
        if not document.teacher_id:
            logger.error(f"Document {document.id} is missing teacher_id. Cannot process.")
            # Optionally, update the document's status to ERROR here if desired,
            # but that would also require teacher_id.
            # For now, just log and return, preventing further processing.
            return False

        character_count: Optional[int] = None
        word_count: Optional[int] = None

        try:
            logger.info(f"Processing document {document.id} for teacher {document.teacher_id}")
            # Update document status to PROCESSING
            await crud.update_document_status(
                document_id=document.id,
                teacher_id=document.teacher_id,
                status=DocumentStatus.PROCESSING
            )

            # Download file from blob storage
            file_bytes = await download_blob_as_bytes(document.storage_blob_path)
            if not file_bytes:
                logger.error(f"Failed to download file from storage for document {document.id}")
                raise Exception("Failed to download file from storage")

            # Extract text from document
            text_content = await extract_text_from_bytes(
                file_bytes=file_bytes,
                file_type=document.file_type
            )
            if not text_content: # Assuming empty string means failure or no text
                logger.warning(f"Failed to extract text or no text content for document {document.id}")
                # Depending on requirements, this might be an error or just a doc with no content
                # For now, we'll allow it to proceed to COMPLETED but with no counts.
                # If it should be an error, raise Exception("Failed to extract text from document")
            else:
                character_count = len(text_content)
                word_count = len(text_content.split())


            # TODO: Call AI assessment service
            # For now, just update status to COMPLETED
            logger.info(f"Updating document {document.id} to COMPLETED for teacher {document.teacher_id} with char_count: {character_count}, word_count: {word_count}")
            await crud.update_document_status(
                document_id=document.id,
                teacher_id=document.teacher_id,
                status=DocumentStatus.COMPLETED,
                character_count=character_count,
                word_count=word_count
            )

            # Update result status
            # Assuming document.id is also the result_id, which might be a simplification.
            # If result is a separate entity, it should be fetched or created with its own ID.
            # The crud.update_result function also needs to be checked if it requires teacher_id.
            # For now, focusing on update_document_status.
            result_to_update = await crud.get_result_by_document_id(document_id=document.id, teacher_id=document.teacher_id)
            if result_to_update:
                await crud.update_result(
                    result_id=result_to_update.id, # Use the actual result_id
                    # Ensure teacher_id is handled correctly in update_result if needed by that function
                    update_data={"status": ResultStatus.COMPLETED.value}
                )
            else:
                logger.warning(f"No result found for document {document.id} to update to COMPLETED status.")


            return True

        except Exception as e:
            logger.error(f"Error processing document {document.id} for teacher {document.teacher_id}: {e}", exc_info=True)
            # Update document status to ERROR
            await crud.update_document_status(
                document_id=document.id,
                teacher_id=document.teacher_id,
                status=DocumentStatus.ERROR,
                character_count=character_count, # Pass counts if available
                word_count=word_count
            )
            # Update result status to ERROR
            result_to_update_on_error = await crud.get_result_by_document_id(document_id=document.id, teacher_id=document.teacher_id, include_deleted=True) # include_deleted in case it was soft-deleted
            if result_to_update_on_error:
                await crud.update_result(
                    result_id=result_to_update_on_error.id,
                     # Ensure teacher_id is handled correctly in update_result if needed
                    update_data={"status": ResultStatus.ERROR.value}
                )
            else:
                logger.warning(f"No result found for document {document.id} to update to ERROR status.")
            return False

    def stop(self):
        """Stop the batch processor."""
        self.is_running = False 