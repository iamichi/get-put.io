from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.services.scheduler import get_scheduler_service
from app.services.state import get_state_store


def test_health_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_settings_round_trip_and_preview(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GET_PUTIO_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("GET_PUTIO_SCHEDULE_TIMEZONE", "UTC")
    monkeypatch.setenv("GET_PUTIO_SCHEDULER_POLL_SECONDS", "1")
    get_settings.cache_clear()
    get_state_store.cache_clear()
    get_scheduler_service.cache_clear()
    client = TestClient(app)

    save_response = client.put(
        "/api/settings",
        json={
            "settings": {
                "putio": {
                    "app_id": "1234",
                    "client_secret": "secret",
                    "redirect_uri": "http://localhost:8000/api/auth/putio/callback",
                    "token": None,
                    "oauth_state": None,
                    "account_username": None,
                    "account_user_id": None,
                    "connected_at": None,
                },
                "jellyfin": {
                    "enabled": True,
                    "base_url": "http://localhost:8096",
                    "api_key": "abc123",
                    "refresh_after_sync": True,
                    "refresh_only_on_change": True,
                    "selected_library_ids": [],
                },
                "sync_defaults": {
                    "destination_path": "/media/staging",
                },
            }
        },
    )
    assert save_response.status_code == 200
    assert save_response.json()["settings"]["putio"]["app_id"] == "1234"

    preview_response = client.post(
        "/api/jobs/preview",
        json={
            "mode": "folder",
            "folder_path": "/Movies",
            "destination_path": "/media/staging",
        },
    )
    assert preview_response.status_code == 200
    payload = preview_response.json()
    assert payload["command_preview"].startswith("rclone copy putio:Movies")
    assert "Put.io is not connected yet." in payload["warnings"]

    schedule_response = client.post(
        "/api/schedules",
        json={
            "name": "Nightly Movies",
            "enabled": True,
            "mode": "folder",
            "folder_path": "/Movies",
            "destination_path": "/media/staging",
            "schedule_type": "daily",
            "interval_hours": 6,
            "daily_time": "02:30",
        },
    )
    assert schedule_response.status_code == 200
    schedule_payload = schedule_response.json()
    assert schedule_payload["name"] == "Nightly Movies"
    assert schedule_payload["next_run_at"] is not None

    list_response = client.get("/api/schedules")
    assert list_response.status_code == 200
    assert len(list_response.json()["schedules"]) == 1
