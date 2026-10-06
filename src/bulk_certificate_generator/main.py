import logging
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.orm import Session

from .database import get_db
from .models import GenerationJob, JobRecipient
from .schemas import (
    CreateJobRequest,
    CreateJobResponse,
    JobRecipientsResponse,
    JobStatusResponse,
    RecipientStatusResponse,
)
from .tasks import process_job

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Bulk Certificate Generator",
    description="Generate and retrieve certificates for bulk recipient jobs.",
    version="0.1.0",
)


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    """Return the API health status."""
    return {"status": "ok"}


@app.post(
    "/api/v1/jobs",
    response_model=CreateJobResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Jobs"],
)
def create_job(
    request: CreateJobRequest,
    db: Session = Depends(get_db),
) -> CreateJobResponse:
    """Create a certificate generation job and its recipients."""

    job = GenerationJob(
        event_name=request.event_name,
        completion_date=request.completion_date,
        status="queued",
        total_count=len(request.recipients),
        success_count=0,
        failure_count=0,
    )

    try:
        db.add(job)
        db.flush()

        recipients = [
            JobRecipient(
                job_id=job.id,
                name=recipient.name,
                email=str(recipient.email),
                status="pending",
            )
            for recipient in request.recipients
        ]

        db.add_all(recipients)
        db.commit()
        db.refresh(job)
        try:
            process_job.delay(str(job.id))
        except Exception:
            logger.exception(
                "Failed to enqueue certificate job %s",
                job.id,
            )

    except Exception:
        db.rollback()
        raise

    return CreateJobResponse(
        id=job.id,
        event_name=job.event_name,
        completion_date=job.completion_date,
        status=job.status,
        total_count=job.total_count,
        created_at=job.created_at,
    )


@app.get(
    "/api/v1/jobs/{job_id}",
    response_model=JobStatusResponse,
    tags=["Jobs"],
)
def get_job(
    job_id: UUID,
    db: Session = Depends(get_db),
) -> JobStatusResponse:
    """Return a job's current status and progress."""

    job = db.get(GenerationJob, job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    return JobStatusResponse(
        id=job.id,
        event_name=job.event_name,
        completion_date=job.completion_date,
        status=job.status,
        total_count=job.total_count,
        success_count=job.success_count,
        failure_count=job.failure_count,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


@app.get(
    "/api/v1/jobs/{job_id}/recipients",
    response_model=JobRecipientsResponse,
    tags=["Jobs"],
)
def get_job_recipients(
    job_id: UUID,
    db: Session = Depends(get_db),
) -> JobRecipientsResponse:
    """List the recipients associated with a job."""

    job = db.get(GenerationJob, job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    recipients = [
        RecipientStatusResponse(
            id=recipient.id,
            name=recipient.name,
            email=recipient.email,
            status=recipient.status,
            certificate_path=recipient.certificate_path,
            error_message=recipient.error_message,
            created_at=recipient.created_at,
            completed_at=recipient.completed_at,
        )
        for recipient in job.recipients
    ]

    return JobRecipientsResponse(
        job_id=job.id,
        total_count=len(recipients),
        recipients=recipients,
    )
