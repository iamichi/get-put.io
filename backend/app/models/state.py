from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PutioToken(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int | None = None
    expiry: str | None = None
    refresh_token: str | None = None
    scope: str | None = None


class PutioSettings(BaseModel):
    app_id: str = ""
    client_secret: str = ""
    redirect_uri: str = "http://localhost:8000/api/auth/putio/callback"
    token: PutioToken | None = None
    oauth_state: str | None = None
    account_username: str | None = None
    account_user_id: int | None = None
    connected_at: str | None = None


class JellyfinSettings(BaseModel):
    enabled: bool = False
    base_url: str = ""
    api_key: str = ""
    refresh_after_sync: bool = True
    refresh_only_on_change: bool = True
    selected_library_ids: list[str] = Field(default_factory=list)


class SyncDefaults(BaseModel):
    destination_path: str = "/media/staging"


class AppSettings(BaseModel):
    putio: PutioSettings = Field(default_factory=PutioSettings)
    jellyfin: JellyfinSettings = Field(default_factory=JellyfinSettings)
    sync_defaults: SyncDefaults = Field(default_factory=SyncDefaults)


class SyncJobRecord(BaseModel):
    id: str
    label: str
    mode: Literal["all", "folder"]
    folder_path: str | None = None
    destination_path: str
    command_preview: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    created_at: str = Field(default_factory=utc_now)
    started_at: str | None = None
    finished_at: str | None = None
    warnings: list[str] = Field(default_factory=list)
    log_lines: list[str] = Field(default_factory=list)
    refresh_requested: bool = False
    refresh_triggered: bool = False
    files_changed: bool = False
    error_message: str | None = None
    schedule_id: str | None = None
    triggered_by: Literal["manual", "schedule"] = "manual"


class RecurringSchedule(BaseModel):
    id: str
    name: str
    enabled: bool = True
    mode: Literal["all", "folder"]
    folder_path: str | None = None
    destination_path: str
    schedule_type: Literal["interval", "daily"] = "interval"
    interval_hours: int = 6
    daily_time: str = "03:00"
    next_run_at: str | None = None
    last_run_at: str | None = None
    last_job_id: str | None = None
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


class AppState(BaseModel):
    settings: AppSettings = Field(default_factory=AppSettings)
    jobs: list[SyncJobRecord] = Field(default_factory=list)
    schedules: list[RecurringSchedule] = Field(default_factory=list)
    updated_at: str = Field(default_factory=utc_now)

    @classmethod
    def create_default(cls, destination_path: str) -> "AppState":
        state = cls()
        state.settings.sync_defaults.destination_path = destination_path
        return state

    def touch(self) -> None:
        self.updated_at = utc_now()

    def latest_jobs(self, limit: int = 10) -> list[SyncJobRecord]:
        return list(reversed(self.jobs[-limit:]))

    def get_job(self, job_id: str) -> SyncJobRecord | None:
        for job in self.jobs:
            if job.id == job_id:
                return job
        return None

    def append_job(self, job: SyncJobRecord) -> None:
        self.jobs.append(job)
        self.touch()

    def update_job(self, job_id: str, **changes: Any) -> SyncJobRecord:
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        for key, value in changes.items():
            setattr(job, key, value)
        self.touch()
        return job

    def get_schedule(self, schedule_id: str) -> RecurringSchedule | None:
        for schedule in self.schedules:
            if schedule.id == schedule_id:
                return schedule
        return None

    def upsert_schedule(self, schedule: RecurringSchedule) -> RecurringSchedule:
        existing = self.get_schedule(schedule.id)
        if existing is None:
            self.schedules.append(schedule)
        else:
            index = self.schedules.index(existing)
            self.schedules[index] = schedule
        self.touch()
        return schedule

    def delete_schedule(self, schedule_id: str) -> None:
        self.schedules = [schedule for schedule in self.schedules if schedule.id != schedule_id]
        self.touch()
