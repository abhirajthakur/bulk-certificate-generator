from collections.abc import Generator
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from bulk_certificate_generator.api import routes
from bulk_certificate_generator.db.models import (  # noqa: F401
    GenerationJob,
    JobRecipient,
)
from bulk_certificate_generator.db.session import Base, get_db
from bulk_certificate_generator.main import app


@pytest.fixture()
def test_engine():
    """Create an isolated in-memory SQLite database for a test."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(bind=engine)

    yield engine

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db_session(test_engine) -> Generator[Session, None, None]:
    """Provide a database session for test setup and assertions."""
    testing_session_local = sessionmaker(
        bind=test_engine,
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )

    with testing_session_local() as session:
        yield session


@pytest.fixture()
def mock_celery_dispatch(monkeypatch) -> Mock:
    """Prevent tests from enqueueing real background jobs."""
    send_task = Mock()
    monkeypatch.setattr(routes.celery_app, "send_task", send_task)
    return send_task


@pytest.fixture()
def client(test_engine, mock_celery_dispatch) -> Generator[TestClient, None, None]:
    """Provide a test client connected to the isolated test database."""
    testing_session_local = sessionmaker(
        bind=test_engine,
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )

    def override_get_db() -> Generator[Session, None, None]:
        with testing_session_local() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
