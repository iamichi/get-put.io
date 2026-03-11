import stat
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app, resolve_static_asset
from app.models.state import PutioToken, SyncJobRecord, utc_now
from app.services.jobs import JobService
from app.services.putio import PutioService
from app.services.storage_cleanup import StorageCleanupService
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
                    "deletion_policy": "keep_local",
                },
                "storage_cleanup": {
                    "enabled": False,
                    "threshold_free_percent": 15,
                    "target_free_percent": 25,
                    "min_age_days": 30,
                    "exclude_paths": [],
                    "schedule_enabled": False,
                    "schedule_type": "daily",
                    "interval_hours": 24,
                    "daily_time": "04:00",
                },
            }
        },
    )
    assert save_response.status_code == 200
    assert save_response.json()["settings"]["putio"]["app_id"] == "1234"
    assert save_response.json()["settings"]["putio"]["client_secret"] == ""
    assert save_response.json()["settings"]["jellyfin"]["api_key"] == ""

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


def test_settings_save_preserves_putio_managed_fields(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GET_PUTIO_STATE_PATH", str(tmp_path / "state.json"))
    get_settings.cache_clear()
    get_state_store.cache_clear()
    get_scheduler_service.cache_clear()

    store = get_state_store()

    def seed_state(state) -> None:
        state.settings.putio.token = PutioToken(access_token="token", token_type="Bearer")
        state.settings.putio.oauth_state = "oauth-state"
        state.settings.putio.account_username = "ichi"
        state.settings.putio.account_user_id = 42
        state.settings.putio.connected_at = utc_now()

    store.mutate(seed_state)

    client = TestClient(app)
    response = client.put(
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
                    "enabled": False,
                    "base_url": "",
                    "api_key": "",
                    "refresh_after_sync": True,
                    "refresh_only_on_change": True,
                    "selected_library_ids": [],
                },
                "sync_defaults": {
                    "destination_path": "",
                    "deletion_policy": "keep_local",
                },
                "storage_cleanup": {
                    "enabled": False,
                    "threshold_free_percent": 15,
                    "target_free_percent": 25,
                    "min_age_days": 30,
                    "exclude_paths": [],
                    "schedule_enabled": False,
                    "schedule_type": "daily",
                    "interval_hours": 24,
                    "daily_time": "04:00",
                },
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()["settings"]["putio"]
    assert payload["token"] is None
    assert payload["oauth_state"] is None
    assert payload["account_username"] == "ichi"
    assert payload["account_user_id"] == 42

    saved_state = store.snapshot().settings.putio
    assert saved_state.token is not None
    assert saved_state.token.access_token == "token"
    assert saved_state.oauth_state == "oauth-state"


def test_putio_callback_escapes_error(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GET_PUTIO_STATE_PATH", str(tmp_path / "state.json"))
    get_settings.cache_clear()
    get_state_store.cache_clear()
    get_scheduler_service.cache_clear()

    client = TestClient(app)
    response = client.get("/api/auth/putio/callback?error=%3Cscript%3Ealert(1)%3C/script%3E")

    assert response.status_code == 400
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "<script>alert(1)</script>" not in response.text


def test_putio_callback_returns_to_frontend_url(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GET_PUTIO_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("FRONTEND_URL", "http://localhost:5173")
    get_settings.cache_clear()
    get_state_store.cache_clear()
    get_scheduler_service.cache_clear()

    def fake_exchange_code(self: PutioService, code: str) -> PutioToken:
        assert code == "oauth-code"
        return PutioToken(
            access_token="token",
            token_type="Bearer",
            expiry="0001-01-01T00:00:00Z",
        )

    def fake_fetch_account(self: PutioService, token: PutioToken) -> tuple[int | None, str | None]:
        assert token.access_token == "token"
        return 42, "ichi"

    monkeypatch.setattr(PutioService, "exchange_code", fake_exchange_code)
    monkeypatch.setattr(PutioService, "fetch_account", fake_fetch_account)

    store = get_state_store()

    def seed_oauth_state(state) -> None:
        state.settings.putio.oauth_state = "oauth-state"

    store.mutate(seed_oauth_state)

    client = TestClient(app)
    response = client.get("/api/auth/putio/callback?code=oauth-code&state=oauth-state")

    assert response.status_code == 200
    assert 'href="http://localhost:5173"' in response.text


def test_putio_callback_requires_non_empty_state(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GET_PUTIO_STATE_PATH", str(tmp_path / "state.json"))
    get_settings.cache_clear()
    get_state_store.cache_clear()
    get_scheduler_service.cache_clear()

    client = TestClient(app)
    response = client.get("/api/auth/putio/callback?code=oauth-code")

    assert response.status_code == 400
    assert "Invalid state token." in response.text


def test_settings_and_dashboard_redact_credentials(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GET_PUTIO_STATE_PATH", str(tmp_path / "state.json"))
    get_settings.cache_clear()
    get_state_store.cache_clear()
    get_scheduler_service.cache_clear()

    store = get_state_store()

    def seed_state(state) -> None:
        state.settings.putio.app_id = "1234"
        state.settings.putio.client_secret = "secret"
        state.settings.putio.token = PutioToken(access_token="token", token_type="Bearer")
        state.settings.jellyfin.enabled = True
        state.settings.jellyfin.base_url = "http://localhost:8096"
        state.settings.jellyfin.api_key = "abc123"

    store.mutate(seed_state)

    client = TestClient(app)
    settings_response = client.get("/api/settings")
    dashboard_response = client.get("/api/dashboard")

    assert settings_response.status_code == 200
    assert dashboard_response.status_code == 200
    assert settings_response.json()["settings"]["putio"]["client_secret"] == ""
    assert settings_response.json()["settings"]["putio"]["token"] is None
    assert settings_response.json()["settings"]["jellyfin"]["api_key"] == ""
    assert dashboard_response.json()["settings"]["putio"]["client_secret"] == ""
    assert dashboard_response.json()["settings"]["putio"]["token"] is None
    assert dashboard_response.json()["settings"]["jellyfin"]["api_key"] == ""


def test_run_job_rejects_destination_outside_storage_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GET_PUTIO_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("GET_PUTIO_STORAGE_PATH", str(tmp_path / "media"))
    get_settings.cache_clear()
    get_state_store.cache_clear()
    get_scheduler_service.cache_clear()

    client = TestClient(app)
    response = client.post(
        "/api/jobs/run",
        json={
            "mode": "folder",
            "folder_path": "/Movies",
            "destination_path": str(tmp_path / "escape"),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Destination must be inside the configured storage root."


def test_save_settings_rejects_unsafe_jellyfin_url(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GET_PUTIO_STATE_PATH", str(tmp_path / "state.json"))
    get_settings.cache_clear()
    get_state_store.cache_clear()
    get_scheduler_service.cache_clear()

    client = TestClient(app)
    response = client.put(
        "/api/settings",
        json={
            "settings": {
                "putio": {
                    "app_id": "",
                    "client_secret": "",
                    "redirect_uri": "http://localhost:8000/api/auth/putio/callback",
                    "token": None,
                    "oauth_state": None,
                    "account_username": None,
                    "account_user_id": None,
                    "connected_at": None,
                },
                "jellyfin": {
                    "enabled": True,
                    "base_url": "http://169.254.169.254/latest/meta-data",
                    "api_key": "abc123",
                    "refresh_after_sync": True,
                    "refresh_only_on_change": True,
                    "selected_library_ids": [],
                },
                "sync_defaults": {
                    "destination_path": "",
                    "deletion_policy": "keep_local",
                },
                "storage_cleanup": {
                    "enabled": False,
                    "threshold_free_percent": 15,
                    "target_free_percent": 25,
                    "min_age_days": 30,
                    "exclude_paths": [],
                    "schedule_enabled": False,
                    "schedule_type": "daily",
                    "interval_hours": 24,
                    "daily_time": "04:00",
                },
            }
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Jellyfin URL must point to a unicast host."


def test_settings_reject_cleanup_target_below_threshold(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GET_PUTIO_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("GET_PUTIO_STORAGE_PATH", str(tmp_path / "media"))
    get_settings.cache_clear()
    get_state_store.cache_clear()
    get_scheduler_service.cache_clear()

    client = TestClient(app)
    response = client.put(
        "/api/settings",
        json={
            "settings": {
                "putio": {
                    "app_id": "",
                    "client_secret": "",
                    "redirect_uri": "http://localhost:8000/api/auth/putio/callback",
                    "token": None,
                    "oauth_state": None,
                    "account_username": None,
                    "account_user_id": None,
                    "connected_at": None,
                },
                "jellyfin": {
                    "enabled": False,
                    "base_url": "",
                    "api_key": "",
                    "refresh_after_sync": True,
                    "refresh_only_on_change": True,
                    "selected_library_ids": [],
                },
                "sync_defaults": {
                    "destination_path": "",
                    "deletion_policy": "keep_local",
                },
                "storage_cleanup": {
                    "enabled": True,
                    "threshold_free_percent": 25,
                    "target_free_percent": 20,
                    "min_age_days": 30,
                    "exclude_paths": [],
                    "schedule_enabled": False,
                    "schedule_type": "daily",
                    "interval_hours": 24,
                    "daily_time": "04:00",
                },
            }
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Cleanup target free space must be greater than the cleanup threshold."


def test_cleanup_preview_respects_cleanup_policy(monkeypatch, tmp_path: Path) -> None:
    storage_root = tmp_path / "media"
    library = storage_root / "library"
    library.mkdir(parents=True)
    old_file = library / "old.mkv"
    old_file.write_bytes(b"x" * 32)

    monkeypatch.setenv("GET_PUTIO_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("GET_PUTIO_STORAGE_PATH", str(storage_root))
    get_settings.cache_clear()
    get_state_store.cache_clear()
    get_scheduler_service.cache_clear()

    def fake_disk_usage(_: Path) -> tuple[int, int, int]:
        return (100, 90, 10)

    monkeypatch.setattr(StorageCleanupService, "_disk_usage", staticmethod(fake_disk_usage))

    store = get_state_store()

    def seed_cleanup_settings(state) -> None:
        state.settings.storage_cleanup.enabled = True
        state.settings.storage_cleanup.threshold_free_percent = 15
        state.settings.storage_cleanup.target_free_percent = 25
        state.settings.storage_cleanup.min_age_days = 0
        state.settings.storage_cleanup.exclude_paths = []

    store.mutate(seed_cleanup_settings)

    client = TestClient(app)
    response = client.get("/api/storage/cleanup/preview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["would_run"] is True
    assert payload["estimated_files_to_delete"] == 1
    assert payload["candidate_count"] == 1
    assert payload["sample_paths"] == [str(old_file.resolve())]


def test_resolve_static_asset_rejects_traversal(tmp_path: Path) -> None:
    static_root = tmp_path / "static"
    static_root.mkdir()
    asset = static_root / "index.html"
    asset.write_text("<html>ok</html>")
    secret = tmp_path / "secret.txt"
    secret.write_text("secret")

    assert resolve_static_asset(static_root, "index.html") == asset.resolve()
    assert resolve_static_asset(static_root, "../secret.txt") is None


def test_state_store_writes_secret_file_permissions(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / "data" / "state.json"
    monkeypatch.setenv("GET_PUTIO_STATE_PATH", str(state_path))
    get_settings.cache_clear()
    get_state_store.cache_clear()
    get_scheduler_service.cache_clear()

    store = get_state_store()
    store.mutate(lambda state: setattr(state.settings.putio, "app_id", "1234"))

    assert stat.S_IMODE(state_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(state_path.parent.stat().st_mode) == 0o700


def test_putio_connection_status_handles_missing_username(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GET_PUTIO_STATE_PATH", str(tmp_path / "state.json"))
    get_settings.cache_clear()
    get_state_store.cache_clear()
    get_scheduler_service.cache_clear()

    snapshot = get_state_store().snapshot()
    snapshot.settings.putio.token = PutioToken(access_token="token", token_type="Bearer")

    status = PutioService(get_settings(), snapshot).connection_status()

    assert status.connected is True
    assert status.summary == "Connected as Put.io user."


def test_job_change_detector_ignores_zero_transfer_stats() -> None:
    assert JobService._line_indicates_file_change("movie.mkv: Copied (new)") is True
    assert JobService._line_indicates_file_change("Transferred: 0 B / 0 B, -, 0 B/s, ETA -") is False
    assert JobService._line_indicates_file_change("Checks: 3 / 3, 100%") is False


def test_cancel_running_job(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GET_PUTIO_STATE_PATH", str(tmp_path / "state.json"))
    get_settings.cache_clear()
    get_state_store.cache_clear()
    get_scheduler_service.cache_clear()

    store = get_state_store()

    def seed_job(state) -> None:
        state.append_job(
            SyncJobRecord(
                id="job-test-cancel",
                label="Sync /Movies",
                mode="folder",
                folder_path="/Movies",
                destination_path="/media/staging",
                command_preview="rclone copy putio:Movies /media/staging",
                status="running",
            )
        )

    store.mutate(seed_job)

    client = TestClient(app)
    response = client.post("/api/jobs/job-test-cancel/cancel")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "cancelled"
    assert payload["error_message"] == "Cancelled by user."


def test_scheduler_claim_does_not_advance_next_run(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GET_PUTIO_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("GET_PUTIO_SCHEDULE_TIMEZONE", "UTC")
    get_settings.cache_clear()
    get_state_store.cache_clear()
    get_scheduler_service.cache_clear()

    scheduler = get_scheduler_service()
    schedule = scheduler.create_schedule(
        name="Nightly Movies",
        enabled=True,
        mode="folder",
        folder_path="/Movies",
        destination_path="/media/staging",
        deletion_policy="keep_local",
        schedule_type="daily",
        interval_hours=6,
        daily_time="02:30",
    )

    store = get_state_store()

    def make_due(state) -> None:
        current = state.get_schedule(schedule.id)
        assert current is not None
        current.next_run_at = "2000-01-01T00:00:00+00:00"

    store.mutate(make_due)
    before = store.snapshot().get_schedule(schedule.id)
    assert before is not None

    claimed = scheduler._claim_due_schedules()

    after = store.snapshot().get_schedule(schedule.id)
    assert len(claimed) == 1
    assert after is not None
    assert after.next_run_at == before.next_run_at
