from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RecipientInput(BaseModel):
    """Validate one certificate recipient."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    email: EmailStr


class CreateJobRequest(BaseModel):
    """Validate a bulk certificate generation request."""

    model_config = ConfigDict(str_strip_whitespace=True)

    event_name: str = Field(min_length=1, max_length=200)
    completion_date: date
    recipients: list[RecipientInput] = Field(
        min_length=1,
        max_length=1000,
    )


class CreateJobResponse(BaseModel):
    """Response returned after a job is accepted."""

    id: UUID
    event_name: str
    completion_date: date
    status: str
    total_count: int
    created_at: datetime


class JobStatusResponse(BaseModel):
    """Return the current state and progress of a job."""

    id: UUID
    event_name: str
    completion_date: date
    status: str
    total_count: int
    success_count: int
    failure_count: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class RecipientStatusResponse(BaseModel):
    """Return the processing result for one recipient."""

    id: UUID
    name: str
    email: EmailStr
    status: str
    certificate_path: str | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


class JobRecipientsResponse(BaseModel):
    """Return recipients belonging to a specific job."""

    job_id: UUID
    total_count: int
    recipients: list[RecipientStatusResponse]
