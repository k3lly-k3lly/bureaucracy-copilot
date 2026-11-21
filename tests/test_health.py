import os

import pytest
from fastapi.testclient import TestClient

from copilot.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.db
@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
def test_database_has_pgvector():
    response = client.get("/health/db")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pgvector_version"] is not None
