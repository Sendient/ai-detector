import uuid
from datetime import datetime, timezone

import pytest
from pytest_mock import MockerFixture
from unittest.mock import AsyncMock

from backend.app.queue import enqueue_assessment_task, dequeue_assessment_task, AssessmentTask

@pytest.mark.asyncio
async def test_enqueue_assessment_task(mocker: MockerFixture):
    mock_db = mocker.Mock()
    mock_insert = AsyncMock(return_value=mocker.Mock(acknowledged=True))
    mock_db.assessment_tasks.insert_one = mock_insert
    mocker.patch('backend.app.queue.get_database', return_value=mock_db)

    doc_id = uuid.uuid4()
    result = await enqueue_assessment_task(doc_id, 'user1', 2)

    assert result is True
    mock_insert.assert_called_once()
    inserted_doc = mock_insert.call_args.args[0]
    assert inserted_doc['document_id'] == doc_id
    assert inserted_doc['user_id'] == 'user1'
    assert inserted_doc['priority_level'] == 2

@pytest.mark.asyncio
async def test_dequeue_assessment_task_returns_task(mocker: MockerFixture):
    task_dict = {
        '_id': uuid.uuid4(),
        'document_id': uuid.uuid4(),
        'user_id': 'user',
        'priority_level': 1,
        'attempts': 1,
        'status': 'PENDING',
        'available_at': datetime.now(timezone.utc),
        'created_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc),
    }

    mock_db = mocker.Mock()
    mock_db.assessment_tasks.find_one_and_update = AsyncMock(return_value=task_dict)
    mocker.patch('backend.app.queue.get_database', return_value=mock_db)

    result = await dequeue_assessment_task()

    assert isinstance(result, AssessmentTask)
    assert result.document_id == task_dict['document_id']

@pytest.mark.asyncio
async def test_dequeue_assessment_task_dead_letter(mocker: MockerFixture):
    task_dict = {
        '_id': uuid.uuid4(),
        'document_id': uuid.uuid4(),
        'user_id': 'user',
        'priority_level': 1,
        'attempts': 6,  # already over limit
        'status': 'PENDING',
        'available_at': datetime.now(timezone.utc),
        'created_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc),
    }

    mock_db = mocker.Mock()
    mock_db.assessment_tasks.find_one_and_update = AsyncMock(side_effect=[task_dict, None])
    mock_db.assessment_tasks.delete_one = AsyncMock()
    mock_db.assessment_deadletter.insert_one = AsyncMock()
    mocker.patch('backend.app.queue.get_database', return_value=mock_db)

    result = await dequeue_assessment_task(max_attempts=5)

    assert result is None
    mock_db.assessment_tasks.delete_one.assert_called_once_with({'_id': task_dict['_id']})
    mock_db.assessment_deadletter.insert_one.assert_called_once()
