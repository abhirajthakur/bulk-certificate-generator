# Bulk Certificate Generator

A backend service for generating PDF certificates in bulk. Submit a job containing an event name, completion date, and recipient list, then track its progress and download generated certificates through a REST API.

## Features

- Asynchronous certificate generation using Celery and Redis.
- REST API built with FastAPI.
- PostgreSQL persistence using SQLAlchemy.
- Database schema migrations with Alembic.
- PDF certificate generation using ReportLab.
- Job-level progress tracking and individual recipient outcomes.
- Certificate downloads through the API.
- Automatic retries for transient SQLAlchemy database operational errors, with up to three retries.
- Request validation using Pydantic.

## Tech Stack

- Python 3.12+
- FastAPI and Uvicorn
- PostgreSQL
- SQLAlchemy and Alembic
- Redis and Celery
- ReportLab
- uv for Python dependency management
- pytest, Ruff, and Pyright for testing and code quality

## Prerequisites

Install the following before starting:

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)
- Docker Engine and Docker Compose

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/abhirajthakur/bulk-certificate-generator
cd bulk-certificate-generator
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Configure environment variables

Create a local environment file from the example:

```bash
cp .env.example .env
```

The required settings are:

```dotenv
DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5432/certificate_db
REDIS_URL=redis://localhost:6379/0
```

These values match the development services in the included Docker Compose configuration. Change them if your local services use different credentials or addresses.

**Do not use the example database password in production.**

### 4. Start PostgreSQL and Redis

```bash
docker-compose up -d
```

Check service status:

```bash
docker-compose ps
```

### 5. Apply database migrations

```bash
uv run alembic upgrade head
```

### 6. Start the API

In one terminal:

```bash
uv run uvicorn bulk_certificate_generator.main:app --reload
```

The API is available at `http://localhost:8000`.

Interactive API documentation is available at `http://localhost:8000/docs`.

### 7. Start the Celery worker

In a second terminal, from the project root:

```bash
uv run celery -A bulk_certificate_generator.workers.celery_app:celery_app worker --loglevel=info
```

Keep the API and worker running while processing jobs. The API creates and stores jobs, while the Celery worker performs certificate generation.

## API Reference

### Health check

```http
GET /health
```

Example:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{
  "status": "ok"
}
```

### Create a certificate generation job

```http
POST /api/v1/jobs
Content-Type: application/json
```

Example:

```bash
curl -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "event_name": "Python Workshop",
    "completion_date": "2026-10-07",
    "recipients": [
      {
        "name": "Alice Johnson",
        "email": "alice@example.com"
      },
      {
        "name": "Bob Smith",
        "email": "bob@example.com"
      }
    ]
  }'
```

The API validates the request, stores the job and its recipients, and attempts to enqueue the background task. A successful response returns HTTP `201 Created` with the job ID and initial status.

Request constraints:

- Event name: 1–200 characters.
- Recipient name: 1–200 characters.
- Recipient email: must be a valid email address.
- Completion date: ISO date format (`YYYY-MM-DD`).
- Recipients: between 1 and 1,000 per request.

Save the returned `id`; you will use it to track the job.

### Get job status

```http
GET /api/v1/jobs/{job_id}
```

Example:

```bash
curl http://localhost:8000/api/v1/jobs/<job-id>
```

The response includes the job status, total recipient count, successful and failed counts, and timestamps.

### List recipient results

```http
GET /api/v1/jobs/{job_id}/recipients
```

Example:

```bash
curl http://localhost:8000/api/v1/jobs/<job-id>/recipients
```

Each recipient entry includes its ID, name, email, status, certificate path when available, error details when applicable, and timestamps.

### Download a certificate

```http
GET /api/v1/certificates/{certificate_id}
```

Use the recipient ID returned by the recipients endpoint as the `certificate_id`.

```bash
curl -f \
  http://localhost:8000/api/v1/certificates/<recipient-id> \
  -o certificate.pdf
```

The endpoint returns the PDF for a successfully completed recipient. A certificate that is missing or not yet available returns HTTP `404`.

## Job and Recipient Statuses

Jobs can have these statuses:

| Status | Meaning |
|---|---|
| `queued` | The job has been created and is awaiting processing. |
| `processing` | The worker is processing recipients. |
| `completed` | All recipients completed successfully. |
| `completed_with_errors` | The job finished with a mixture of successful and failed recipients. |
| `failed` | All recipients failed. |

Recipient statuses include `pending`, `processing`, `completed`, and `failed`.

## Certificate Storage

Generated PDFs are stored locally under:

```text
storage/certificates/<job-id>/<recipient-id>.pdf
```

Use the certificate download endpoint rather than relying on local filesystem paths. Generated certificate files are excluded from version control.

## Development

### Run tests

```bash
uv run pytest -v
```

### Check the current migration revision

```bash
uv run alembic current
```

## Stopping Services

Stop the local infrastructure:

```bash
docker-compose down
```

This stops the containers while preserving named volumes. To also remove the PostgreSQL and Redis volumes and their stored data, use `docker-compose down -v` only when you intend to delete that data.

## Notes

- The API and Celery worker must both be running for background processing to work.
- Celery uses Redis as its broker and result backend.
- Transient SQLAlchemy `OperationalError` exceptions are configured for automatic retries, with exponential backoff and up to three retries.
- The included Docker Compose configuration is intended for local development, not production deployment.
