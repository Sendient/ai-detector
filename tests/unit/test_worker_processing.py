import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.app.workers import process_next_task
from backend.app.models.enums import DocumentStatus, ResultStatus

@pytest.mark.asyncio
async def test_worker_success(mocker):
    task = MagicMock(document_id=uuid.uuid4(), user_id='u1', priority_level=0)
    mocker.patch('backend.app.workers.dequeue_assessment_task', return_value=task)

    document = MagicMock(id=task.document_id, storage_blob_path='path', file_type='txt')
    mocker.patch('backend.app.workers.crud.get_document_by_id', return_value=document)
    update_status = mocker.patch('backend.app.workers.crud.update_document_status', new_callable=AsyncMock)
    mocker.patch('backend.app.workers.download_blob_as_bytes', return_value=b'data')
    mocker.patch('backend.app.workers.extract_text_from_bytes', return_value='text')
    ai_mock = AsyncMock(return_value=0.5)
    result = MagicMock(id=uuid.uuid4())
    mocker.patch('backend.app.workers.crud.get_result_by_document_id', return_value=result)
    update_result = mocker.patch('backend.app.workers.crud.update_result', new_callable=AsyncMock)

    success = await process_next_task(ai_mock)

    assert success is True
    update_status.assert_any_call(document_id=document.id, teacher_id=task.user_id, status=DocumentStatus.PROCESSING)
    update_status.assert_any_call(document_id=document.id, teacher_id=task.user_id, status=DocumentStatus.COMPLETED)
    update_result.assert_awaited_once()
    ai_mock.assert_awaited_once()

@pytest.mark.asyncio
async def test_worker_retry(mocker):
    task = MagicMock(document_id=uuid.uuid4(), user_id='u1', priority_level=1)
    mocker.patch('backend.app.workers.dequeue_assessment_task', return_value=task)
    document = MagicMock(id=task.document_id, storage_blob_path='path', file_type='txt')
    mocker.patch('backend.app.workers.crud.get_document_by_id', return_value=document)
    update_status = mocker.patch('backend.app.workers.crud.update_document_status', new_callable=AsyncMock)
    mocker.patch('backend.app.workers.download_blob_as_bytes', return_value=b'data')
    mocker.patch('backend.app.workers.extract_text_from_bytes', return_value='text')
    ai_mock = AsyncMock(side_effect=Exception('fail'))
    mocker.patch('backend.app.workers.crud.get_result_by_document_id', return_value=None)
    enqueue = mocker.patch('backend.app.workers.enqueue_assessment_task', new_callable=AsyncMock)

    success = await process_next_task(ai_mock)

    assert success is False
    enqueue.assert_awaited_once_with(task.document_id, task.user_id, task.priority_level)
    update_status.assert_any_call(document_id=document.id, teacher_id=task.user_id, status=DocumentStatus.PROCESSING)
    update_status.assert_any_call(document_id=document.id, teacher_id=task.user_id, status=DocumentStatus.QUEUED)
