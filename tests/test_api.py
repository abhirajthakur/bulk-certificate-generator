from datetime import date
from uuid import UUID, uuid4

from bulk_certificate_generator.api import routes
from bulk_certificate_generator.db.models import GenerationJob, JobRecipient


def valid_job_payload():
    return {
        "event_name": "Python Workshop",
        "completion_date": "2026-10-01",
        "recipients": [
            {"name": "Ada Lovelace", "email": "ada@example.com"},
            {"name": "Grace Hopper", "email": "grace@example.com"},
        ],
    }


def test_health_check(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_job_persists_job_and_recipients(
    client, db_session, mock_celery_dispatch
):
    response = client.post("/api/v1/jobs", json=valid_job_payload())

    assert response.status_code == 201
    data = response.json()

    assert data["event_name"] == "Python Workshop"
    assert data["status"] == "queued"
    assert data["total_count"] == 2

    job = db_session.get(GenerationJob, UUID(data["id"]))
    assert job is not None
    assert job.total_count == 2
    assert len(job.recipients) == 2

    mock_celery_dispatch.assert_called_once_with(
        "bulk_certificate_generator.process_job",
        args=[data["id"]],
    )


def test_create_job_rejects_empty_recipients(client, mock_celery_dispatch):
    payload = valid_job_payload()
    payload["recipients"] = []

    response = client.post("/api/v1/jobs", json=payload)

    assert response.status_code == 422
    mock_celery_dispatch.assert_not_called()


def test_create_job_rejects_invalid_email(client, mock_celery_dispatch):
    payload = valid_job_payload()
    payload["recipients"][0]["email"] = "not-an-email"

    response = client.post("/api/v1/jobs", json=payload)

    assert response.status_code == 422
    mock_celery_dispatch.assert_not_called()


def test_get_job_returns_status(client, mock_celery_dispatch):
    create_response = client.post("/api/v1/jobs", json=valid_job_payload())
    job_id = create_response.json()["id"]

    response = client.get(f"/api/v1/jobs/{job_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == job_id
    assert data["status"] == "queued"
    assert data["total_count"] == 2
    assert data["success_count"] == 0
    assert data["failure_count"] == 0


def test_get_unknown_job_returns_404(client):
    response = client.get(f"/api/v1/jobs/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_list_job_recipients(client, mock_celery_dispatch):
    create_response = client.post("/api/v1/jobs", json=valid_job_payload())
    job_id = create_response.json()["id"]

    response = client.get(f"/api/v1/jobs/{job_id}/recipients")

    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job_id
    assert data["total_count"] == 2
    assert {recipient["name"] for recipient in data["recipients"]} == {
        "Ada Lovelace",
        "Grace Hopper",
    }


def test_list_recipients_for_unknown_job_returns_404(client):
    response = client.get(f"/api/v1/jobs/{uuid4()}/recipients")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_download_unknown_certificate_returns_404(client):
    response = client.get(f"/api/v1/certificates/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Certificate not found"


def test_download_pending_certificate_returns_404(
    client, db_session, monkeypatch, tmp_path
):
    monkeypatch.setattr(routes, "CERTIFICATE_STORAGE_DIR", tmp_path)

    job = GenerationJob(
        event_name="Python Workshop",
        completion_date=date(2026, 10, 1),
        status="queued",
        total_count=1,
        success_count=0,
        failure_count=0,
    )
    db_session.add(job)
    db_session.flush()

    recipient = JobRecipient(
        job_id=job.id,
        name="Ada Lovelace",
        email="ada@example.com",
        status="pending",
    )
    db_session.add(recipient)
    db_session.commit()

    response = client.get(f"/api/v1/certificates/{recipient.id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Certificate is not available"


def test_download_completed_certificate(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(routes, "CERTIFICATE_STORAGE_DIR", tmp_path)

    certificate_path = tmp_path / "certificate.pdf"
    certificate_path.write_bytes(b"%PDF-1.4 test certificate")

    job = GenerationJob(
        event_name="Python Workshop",
        completion_date=date(2026, 10, 1),
        status="completed",
        total_count=1,
        success_count=1,
        failure_count=0,
    )
    db_session.add(job)
    db_session.flush()

    recipient = JobRecipient(
        job_id=job.id,
        name="Ada Lovelace",
        email="ada@example.com",
        status="completed",
        certificate_path=str(certificate_path),
    )
    db_session.add(recipient)
    db_session.commit()

    response = client.get(f"/api/v1/certificates/{recipient.id}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-1.4")


def test_get_job_with_malformed_id_returns_validation_error(client):
    response = client.get("/api/v1/jobs/not-a-uuid")

    assert response.status_code == 422


def test_list_recipients_with_malformed_job_id_returns_validation_error(client):
    response = client.get("/api/v1/jobs/not-a-uuid/recipients")

    assert response.status_code == 422


def test_create_job_rejects_blank_event_name(client, mock_celery_dispatch):
    payload = valid_job_payload()
    payload["event_name"] = "   "

    response = client.post("/api/v1/jobs", json=payload)

    assert response.status_code == 422
    mock_celery_dispatch.assert_not_called()


def test_create_job_rejects_blank_recipient_name(client, mock_celery_dispatch):
    payload = valid_job_payload()
    payload["recipients"][0]["name"] = "   "

    response = client.post("/api/v1/jobs", json=payload)

    assert response.status_code == 422
    mock_celery_dispatch.assert_not_called()


def test_create_job_rejects_more_than_1000_recipients(client, mock_celery_dispatch):
    payload = valid_job_payload()
    payload["recipients"] = [
        {"name": f"Recipient {i}", "email": f"user{i}@example.com"} for i in range(1001)
    ]

    response = client.post("/api/v1/jobs", json=payload)

    assert response.status_code == 422
    mock_celery_dispatch.assert_not_called()


def test_download_completed_certificate_when_file_is_missing_returns_404(
    client, db_session, monkeypatch, tmp_path
):
    monkeypatch.setattr(routes, "CERTIFICATE_STORAGE_DIR", tmp_path)

    job = GenerationJob(
        event_name="Python Workshop",
        completion_date=date(2026, 10, 1),
        status="completed",
        total_count=1,
        success_count=1,
        failure_count=0,
    )
    db_session.add(job)
    db_session.flush()

    recipient = JobRecipient(
        job_id=job.id,
        name="Ada Lovelace",
        email="ada@example.com",
        status="completed",
        certificate_path=str(tmp_path / "missing.pdf"),
    )
    db_session.add(recipient)
    db_session.commit()

    response = client.get(f"/api/v1/certificates/{recipient.id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Certificate file not found"
