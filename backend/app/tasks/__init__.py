# app/tasks/__init__.py

from .batch_processor import BatchProcessor
from .assessment_worker import AssessmentWorker

batch_processor = BatchProcessor()
# The line below was causing a TypeError and should be removed.
# assessment_worker = AssessmentWorker()
