from sqlalchemy.exc import OperationalError

from ..services.job_processor import process_job as process_job_service
from .celery_app import celery_app


@celery_app.task(name="bulk_certificate_generator.ping")
def ping() -> str:
    """Verify that the Celery worker can execute a task."""
    return "pong"


@celery_app.task(
    bind=True,
    name="bulk_certificate_generator.process_job",
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
)
def process_job(self, job_id: str) -> dict[str, str | int]:
    """Process a job, retrying transient database errors."""
    return process_job_service(
        job_id,
        resume_processing=self.request.retries > 0,
    )
