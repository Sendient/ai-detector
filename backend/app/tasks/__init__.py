# app/tasks/__init__.py

from .batch_processor import BatchProcessor
from .assessment_worker import AssessmentWorker

batch_processor = BatchProcessor()
assessment_worker = AssessmentWorker()
