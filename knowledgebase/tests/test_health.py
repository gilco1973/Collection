"""GET /api/health (liveness) and GET /api/health/ready (readiness)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kb_librarian.api import app as app_module
from kb_librarian.api.app import create_app, package_version
from kb_librarian.api.deps import AppState
from kb_librarian.api.observability import probe_writable
from kb_librarian.config import LibrarianSettings


@pytest.fixture
def client(kb_root: Path) -> TestClient:
    return TestClient(create_app(kb_root, LibrarianSettings()))


def test_health_reports_ok_version_and_checks(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok" and data["version"] == "0.1.0" and data["checks"] == {"process": True}
    assert response.headers["cache-control"] == "no-store"


def test_package_version_falls_back_when_the_distribution_is_missing(monkeypatch):
    def missing(name):
        raise app_module.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(app_module.metadata, "version", missing)
    assert package_version() == "0.1.0"


def test_ready_is_200_when_the_catalog_loads_and_the_state_dir_is_writable(client):
    response = client.get("/api/health/ready")
    assert response.status_code == 200
    expected = {"status": "ok", "version": "0.1.0", "checks": {"catalog": True, "state_writable": True}}
    assert response.json() == expected


def test_ready_is_503_when_the_state_dir_is_not_writable(client, monkeypatch):
    monkeypatch.setattr(app_module, "probe_writable", lambda directory: False)
    response = client.get("/api/health/ready")
    assert response.status_code == 503
    expected = {"status": "not_ready", "version": "0.1.0", "checks": {"catalog": True, "state_writable": False}}
    assert response.json() == expected and response.headers["cache-control"] == "no-store"


def test_ready_is_503_when_the_catalog_does_not_load_and_leaks_no_path(client, monkeypatch):
    def broken(self):
        raise ValueError("bad frontmatter at /srv/secret/path.md")

    monkeypatch.setattr(AppState, "catalog", broken)
    response = client.get("/api/health/ready")
    assert response.status_code == 503 and response.json()["checks"]["catalog"] is False
    assert "/srv/secret" not in response.text and "ValueError" not in response.text


def test_probe_writable_creates_and_removes_a_temp_file(tmp_path: Path):
    target = tmp_path / "state"
    assert probe_writable(target) is True and target.is_dir() and list(target.iterdir()) == []
    blocked = tmp_path / "file"
    blocked.write_text("x")
    assert probe_writable(blocked / "nested") is False  # a regular file where a directory is needed
