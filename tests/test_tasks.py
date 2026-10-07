from unittest.mock import Mock

import pytest
from celery.exceptions import Retry
from sqlalchemy.exc import OperationalError

from bulk_certificate_generator.workers import tasks


def test_ping_task_returns_pong():
    assert tasks.ping() == "pong"


def test_ping_task_has_expected_registered_name():
    assert tasks.ping.name == "bulk_certificate_generator.ping"


def test_process_job_task_has_expected_registered_name():
    assert tasks.process_job.name == "bulk_certificate_generator.process_job"


def test_process_job_task_delegates_to_service(monkeypatch):
    service_mock = Mock(
        return_value={
            "job_id": "test-job-id",
            "result": "completed",
            "success_count": 2,
            "failure_count": 0,
        }
    )
    monkeypatch.setattr(tasks, "process_job_service", service_mock)

    result = tasks.process_job("test-job-id")

    assert result == {
        "job_id": "test-job-id",
        "result": "completed",
        "success_count": 2,
        "failure_count": 0,
    }
    service_mock.assert_called_once_with(
        "test-job-id",
        resume_processing=False,
    )


def test_process_job_task_propagates_unexpected_service_errors(monkeypatch):
    service_mock = Mock(side_effect=RuntimeError("Unexpected worker error"))
    monkeypatch.setattr(tasks, "process_job_service", service_mock)

    with pytest.raises(RuntimeError, match="Unexpected worker error"):
        tasks.process_job("test-job-id")

    service_mock.assert_called_once_with(
        "test-job-id",
        resume_processing=False,
    )


def test_process_job_retries_transient_database_error(monkeypatch):
    database_error = OperationalError(
        "SELECT 1",
        {},
        ConnectionError("database temporarily unavailable"),
    )
    service_mock = Mock(side_effect=database_error)
    retry_mock = Mock(return_value=Retry("Task can be retried"))

    monkeypatch.setattr(tasks, "process_job_service", service_mock)
    monkeypatch.setattr(tasks.process_job, "retry", retry_mock)

    with pytest.raises(Retry):
        tasks.process_job.run("test-job-id")

    service_mock.assert_called_once_with(
        "test-job-id",
        resume_processing=False,
    )
    retry_mock.assert_called_once()
    assert retry_mock.call_args.kwargs["exc"] is database_error


def test_process_job_marks_retry_attempt_as_resumption(monkeypatch):
    service_mock = Mock(
        return_value={
            "job_id": "test-job-id",
            "result": "completed",
            "success_count": 1,
            "failure_count": 0,
        }
    )
    monkeypatch.setattr(tasks, "process_job_service", service_mock)

    result = tasks.process_job.apply(
        args=["test-job-id"],
        retries=1,
        throw=True,
    ).get()

    assert result["result"] == "completed"
    service_mock.assert_called_once_with(
        "test-job-id",
        resume_processing=True,
    )
