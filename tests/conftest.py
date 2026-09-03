"""Shared pytest fixtures for the test suite."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Provide a TestClient bound to the application."""
    with TestClient(app) as test_client:
        yield test_client
