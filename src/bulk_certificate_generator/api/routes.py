import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..db.models import GenerationJob, JobRecipient
from ..db.session import get_db
from ..schemas.jobs import (
    CreateJobRequest,
    CreateJobResponse,
    JobRecipientsResponse,
    JobStatusResponse,
    RecipientStatusResponse,
)
from ..workers.celery_app import celery_app

logger = logging.getLogger(__name__)

CERTIFICATE_STORAGE_DIR = (
    Path(__file__).resolve().parents[3] / "storage" / "certificates"
)

router = APIRouter()


@router.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    """Return the API health status."""
    return {"status": "ok"}


@router.post(
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

    except Exception:
        db.rollback()
        raise

    # Dispatch only after the database transaction commits.
    try:
        celery_app.send_task(
            "bulk_certificate_generator.process_job",
            args=[str(job.id)],
        )
    except Exception:
        logger.exception("Failed to enqueue certificate job %s", job.id)

    return CreateJobResponse(
        id=job.id,
        event_name=job.event_name,
        completion_date=job.completion_date,
        status=job.status,
        total_count=job.total_count,
        created_at=job.created_at,
    )


@router.get(
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
        raise HTTPException(status_code=404, detail="Job not found")

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


@router.get(
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
        raise HTTPException(status_code=404, detail="Job not found")

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


@router.get(
    "/api/v1/certificates/{certificate_id}",
    response_class=FileResponse,
    tags=["Certificates"],
)
def download_certificate(
    certificate_id: UUID,
    db: Session = Depends(get_db),
) -> FileResponse:
    """Download a successfully generated certificate PDF."""
    recipient = db.get(JobRecipient, certificate_id)

    if recipient is None:
        raise HTTPException(
            status_code=404,
            detail="Certificate not found",
        )

    if recipient.status != "completed" or not recipient.certificate_path:
        raise HTTPException(
            status_code=404,
            detail="Certificate is not available",
        )

    storage_root = CERTIFICATE_STORAGE_DIR.resolve()
    certificate_path = Path(recipient.certificate_path).resolve()

    if not certificate_path.is_relative_to(storage_root):
        logger.error(
            "Certificate path for recipient %s is outside storage",
            certificate_id,
        )
        raise HTTPException(
            status_code=404,
            detail="Certificate file not found",
        )

    if not certificate_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Certificate file not found",
        )

    return FileResponse(
        path=certificate_path,
        media_type="application/pdf",
        filename=f"certificate-{recipient.id}.pdf",
    )
