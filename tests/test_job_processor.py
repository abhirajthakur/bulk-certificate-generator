from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session, sessionmaker

from bulk_certificate_generator.db.models import GenerationJob, JobRecipient
from bulk_certificate_generator.services import job_processor


@pytest.fixture
def worker_db(test_engine, monkeypatch, tmp_path):
    """Use the isolated test database for worker processing."""
    test_session_local = sessionmaker(
        bind=test_engine,
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )
    monkeypatch.setattr(job_processor, "SessionLocal", test_session_local)
    monkeypatch.setattr(job_processor, "STORAGE_DIR", tmp_path / "certificates")
    return test_session_local


def seed_job(session_local, recipient_specs):
    """Create a job and recipients, then close the setup session."""
    with session_local() as session:
        job = GenerationJob(
            event_name="Python Workshop",
            completion_date=date(2026, 10, 1),
            status="queued",
            total_count=len(recipient_specs),
            success_count=0,
            failure_count=0,
        )
        session.add(job)
        session.flush()

        recipients = []
        for name, email in recipient_specs:
            recipient = JobRecipient(
                job_id=job.id,
                name=name,
                email=email,
                status="pending",
            )
            session.add(recipient)
            recipients.append(recipient)

        session.commit()
        job_id = job.id
        recipient_ids = [recipient.id for recipient in recipients]

    return job_id, recipient_ids


def fake_generate_certificate(
    *,
    recipient_name,
    event_name,
    completion_date,
    output_path: Path,
    certificate_id,
):
    """Write a small placeholder file instead of rendering a real PDF."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"%PDF-1.4 test certificate")
    return output_path


def test_process_job_completes_all_recipients(worker_db, monkeypatch):
    monkeypatch.setattr(
        job_processor, "generate_certificate", fake_generate_certificate
    )
    job_id, recipient_ids = seed_job(
        worker_db,
        [
            ("Ada Lovelace", "ada@example.com"),
            ("Grace Hopper", "grace@example.com"),
        ],
    )

    result = job_processor.process_job(str(job_id))

    assert result["result"] == "completed"
    assert result["success_count"] == 2
    assert result["failure_count"] == 0

    with worker_db() as session:
        job = session.get(GenerationJob, job_id)
        recipients = [
            session.get(JobRecipient, recipient_id) for recipient_id in recipient_ids
        ]

        assert job is not None
        assert job.status == "completed"
        assert job.started_at is not None
        assert job.completed_at is not None
        assert job.success_count == 2
        assert job.failure_count == 0

        for recipient in recipients:
            assert recipient is not None
            assert recipient.status == "completed"
            assert recipient.completed_at is not None
            assert recipient.certificate_path is not None
            assert Path(recipient.certificate_path).is_file()


def test_process_job_records_partial_failure(worker_db, monkeypatch):
    def generate_with_one_failure(**kwargs):
        if kwargs["recipient_name"] == "Grace Hopper":
            raise RuntimeError("Simulated PDF generation failure")
        return fake_generate_certificate(**kwargs)

    monkeypatch.setattr(
        job_processor, "generate_certificate", generate_with_one_failure
    )
    job_id, recipient_ids = seed_job(
        worker_db,
        [
            ("Ada Lovelace", "ada@example.com"),
            ("Grace Hopper", "grace@example.com"),
        ],
    )

    result = job_processor.process_job(str(job_id))

    assert result["result"] == "completed_with_errors"
    assert result["success_count"] == 1
    assert result["failure_count"] == 1

    with worker_db() as session:
        job = session.get(GenerationJob, job_id)
        ada = session.get(JobRecipient, recipient_ids[0])
        grace = session.get(JobRecipient, recipient_ids[1])

        assert job is not None
        assert job.status == "completed_with_errors"
        assert ada is not None
        assert ada.status == "completed"
        assert grace is not None
        assert grace.status == "failed"
        assert "Simulated PDF generation failure" in grace.error_message


def test_process_job_marks_job_failed_when_all_recipients_fail(worker_db, monkeypatch):
    def always_fail(**kwargs):
        raise RuntimeError("PDF generation failed")

    monkeypatch.setattr(job_processor, "generate_certificate", always_fail)
    job_id, recipient_ids = seed_job(
        worker_db,
        [("Ada Lovelace", "ada@example.com")],
    )

    result = job_processor.process_job(str(job_id))

    assert result["result"] == "failed"
    assert result["success_count"] == 0
    assert result["failure_count"] == 1

    with worker_db() as session:
        job = session.get(GenerationJob, job_id)
        recipient = session.get(JobRecipient, recipient_ids[0])

        assert job is not None
        assert job.status == "failed"
        assert recipient is not None
        assert recipient.status == "failed"
        assert recipient.error_message == "PDF generation failed"


def test_process_job_returns_not_found_for_unknown_job(worker_db):
    result = job_processor.process_job(str(uuid4()))

    assert result == {
        "job_id": result["job_id"],
        "result": "not_found",
    }


def test_process_job_rejects_invalid_uuid():
    with pytest.raises(ValueError):
        job_processor.process_job("not-a-uuid")


@pytest.mark.parametrize(
    ("initial_status", "expected_result"),
    [
        ("completed", "already_finished"),
        ("failed", "already_finished"),
        ("completed_with_errors", "already_finished"),
        ("processing", "already_processing"),
    ],
)
def test_process_job_skips_jobs_that_are_not_queued(
    worker_db,
    monkeypatch,
    initial_status,
    expected_result,
):
    monkeypatch.setattr(
        job_processor,
        "generate_certificate",
        lambda **kwargs: pytest.fail("Certificate generation should not run"),
    )
    job_id, _ = seed_job(
        worker_db,
        [("Ada Lovelace", "ada@example.com")],
    )

    with worker_db() as session:
        job = session.get(GenerationJob, job_id)
        assert job is not None
        job.status = initial_status
        session.commit()

    result = job_processor.process_job(str(job_id))

    assert result["result"] == expected_result

    with worker_db() as session:
        job = session.get(GenerationJob, job_id)
        assert job is not None
        assert job.status == initial_status


def test_process_job_resumes_processing_job(
    worker_db,
    monkeypatch,
):
    monkeypatch.setattr(
        job_processor,
        "generate_certificate",
        fake_generate_certificate,
    )
    job_id, recipient_ids = seed_job(
        worker_db,
        [("Ada Lovelace", "ada@example.com")],
    )

    with worker_db() as session:
        job = session.get(GenerationJob, job_id)
        assert job is not None
        job.status = "processing"
        session.commit()

    result = job_processor.process_job(
        str(job_id),
        resume_processing=True,
    )

    assert result["result"] == "completed"
    assert result["success_count"] == 1

    with worker_db() as session:
        job = session.get(GenerationJob, job_id)
        recipient = session.get(JobRecipient, recipient_ids[0])
        assert job is not None
        assert job.status == "completed"
        assert recipient is not None
        assert recipient.status == "completed"
