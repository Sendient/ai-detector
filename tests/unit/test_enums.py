import pytest
from backend.app.models.enums import DocumentStatus, ResultStatus


def test_document_status_additions():
    assert DocumentStatus.RETRYING.value == "RETRYING"
    assert DocumentStatus.FAILED.value == "FAILED"


def test_result_status_additions():
    assert ResultStatus.RETRYING.value == "RETRYING"
    assert ResultStatus.FAILED.value == "FAILED"

