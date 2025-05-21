import asyncio
import logging

from ..db import crud
from ..db.database import get_database
from ..models.enums import BatchStatus, DocumentStatus
from ..models.batch import Batch, BatchUpdate

logger = logging.getLogger(__name__)

class BatchProcessor:
    """Periodically update batch records based on document statuses."""

    def __init__(self, interval: int = 10):
        self.is_running = False
        self.interval = interval

    async def process_batches(self):
        """Main loop that periodically recalculates batch status."""
        self.is_running = True
        while self.is_running:
            try:
                await self._update_active_batches()
            except Exception as e:
                logger.error(f"Batch processor error: {e}", exc_info=True)
            await asyncio.sleep(self.interval)

    async def _update_active_batches(self):
        db = get_database()
        if db is None:
            logger.error("Database connection not available for batch updates.")
            return

        active_statuses = [
            BatchStatus.QUEUED.value,
            BatchStatus.PROCESSING.value,
            BatchStatus.PARTIAL.value,
            BatchStatus.UPLOADING.value,
            BatchStatus.VALIDATING.value,
        ]

        cursor = db.batches.find({"status": {"$in": active_statuses}})
        async for batch_doc in cursor:
            batch = Batch(**batch_doc)
            await self._compute_and_update_batch(batch)

    async def _compute_and_update_batch(self, batch: Batch) -> None:
        status_counts = await crud.get_batch_status_summary(batch_id=batch.id)
        completed = status_counts.get(DocumentStatus.COMPLETED.value, 0)
        failed = status_counts.get(DocumentStatus.ERROR.value, 0)
        processing = status_counts.get(DocumentStatus.PROCESSING.value, 0)

        if completed + failed >= batch.total_files:
            new_status = (BatchStatus.COMPLETED if failed == 0 else BatchStatus.PARTIAL)
        elif processing > 0 or completed > 0 or failed > 0:
            new_status = BatchStatus.PROCESSING
        else:
            new_status = BatchStatus.QUEUED

        await crud.update_batch(
            batch_id=batch.id,
            batch_in=BatchUpdate(
                completed_files=completed,
                failed_files=failed,
                status=new_status,
            ),
        )

    def stop(self):
        """Stop the batch processor loop."""
        self.is_running = False
