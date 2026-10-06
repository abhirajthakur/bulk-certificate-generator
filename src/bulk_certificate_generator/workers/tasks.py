from ..services.job_processor import process_job as process_job_service
from .celery_app import celery_app


@celery_app.task(name="bulk_certificate_generator.ping")
def ping() -> str:
    """Verify that the Celery worker can execute a task."""
    return "pong"


@celery_app.task(
    name="bulk_certificate_generator.process_job",
    max_retries=3,
)
def process_job(job_id: str) -> dict[str, str | int]:
    """Celery entry point for certificate job processing."""
    return process_job_service(job_id)
