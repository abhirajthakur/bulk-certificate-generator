import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from .celery_app import celery_app
from .certificates import generate_certificate
from .database import SessionLocal
from .models import GenerationJob, JobRecipient

logger = logging.getLogger(__name__)

STORAGE_DIR = Path(__file__).resolve().parents[2] / "storage" / "certificates"

TERMINAL_JOB_STATUSES = {
    "completed",
    "failed",
    "completed_with_errors",
}


@celery_app.task(name="bulk_certificate_generator.ping")
def ping() -> str:
    """Verify that the Celery worker can execute a task."""
    return "pong"


@celery_app.task(
    bind=True,
    name="bulk_certificate_generator.process_job",
    max_retries=3,
)
def process_job(self, job_id: str) -> dict[str, str | int]:
    """Generate certificates and persist individual recipient outcomes."""
    try:
        parsed_job_id = UUID(job_id)
    except ValueError:
        logger.error("Invalid job ID received: %s", job_id)
        raise

    # Claim the job before processing its recipients.
    with SessionLocal() as db:
        job = db.get(GenerationJob, parsed_job_id)

        if job is None:
            logger.warning("Job %s was not found.", job_id)
            return {"job_id": job_id, "result": "not_found"}

        if job.status in TERMINAL_JOB_STATUSES:
            logger.info("Job %s is already finished.", job_id)
            return {"job_id": job_id, "result": "already_finished"}

        if job.status == "processing":
            logger.warning("Job %s is already processing.", job_id)
            return {"job_id": job_id, "result": "already_processing"}

        job.status = "processing"
        job.started_at = datetime.now(UTC)
        db.commit()

    # Process each recipient independently.
    with SessionLocal() as db:
        recipient_ids = [
            recipient.id
            for recipient in db.query(JobRecipient.id)
            .filter(JobRecipient.job_id == parsed_job_id)
            .all()
        ]

    for recipient_id in recipient_ids:
        with SessionLocal() as db:
            recipient = db.get(JobRecipient, recipient_id)

            if recipient is None or recipient.status == "completed":
                continue

            recipient.status = "processing"
            recipient.error_message = None
            db.commit()

            recipient_name = recipient.name
            recipient_email = recipient.email
            recipient_job_id = recipient.job_id

        try:
            with SessionLocal() as db:
                job = db.get(GenerationJob, recipient_job_id)
                if job is None:
                    raise RuntimeError("Parent job no longer exists")

                event_name = job.event_name
                completion_date = job.completion_date

            certificate_id = recipient_id
            output_path = STORAGE_DIR / str(parsed_job_id) / f"{certificate_id}.pdf"

            generate_certificate(
                recipient_name=recipient_name,
                event_name=event_name,
                completion_date=completion_date,
                output_path=output_path,
                certificate_id=certificate_id,
            )

            with SessionLocal() as db:
                recipient = db.get(JobRecipient, recipient_id)
                if recipient is not None:
                    recipient.certificate_path = str(output_path)
                    recipient.status = "completed"
                    recipient.error_message = None
                    recipient.completed_at = datetime.now(UTC)
                    db.commit()

            logger.info(
                "Generated certificate for recipient %s (%s)",
                recipient_name,
                recipient_email,
            )

        except Exception as exc:
            logger.exception(
                "Certificate generation failed for recipient %s",
                recipient_id,
            )

            with SessionLocal() as db:
                recipient = db.get(JobRecipient, recipient_id)
                if recipient is not None:
                    recipient.status = "failed"
                    recipient.error_message = str(exc)[:2000]
                    recipient.completed_at = datetime.now(UTC)
                    db.commit()

    # Recalculate final counts from persisted recipient records.
    with SessionLocal() as db:
        job = db.get(GenerationJob, parsed_job_id)
        if job is None:
            return {"job_id": job_id, "result": "job_disappeared"}

        recipients = (
            db.query(JobRecipient).filter(JobRecipient.job_id == parsed_job_id).all()
        )

        success_count = sum(recipient.status == "completed" for recipient in recipients)
        failure_count = sum(recipient.status == "failed" for recipient in recipients)

        job.success_count = success_count
        job.failure_count = failure_count
        job.completed_at = datetime.now(UTC)

        if success_count == len(recipients):
            job.status = "completed"
        elif failure_count == len(recipients):
            job.status = "failed"
        else:
            job.status = "completed_with_errors"

        db.commit()

        logger.info(
            "Job %s finished: %s successful, %s failed",
            job_id,
            success_count,
            failure_count,
        )

        return {
            "job_id": job_id,
            "result": job.status,
            "success_count": success_count,
            "failure_count": failure_count,
        }
