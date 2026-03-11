from __future__ import annotations

import re
import shutil
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from app.api.schemas import SyncPreviewRequest, SyncPreviewResponse
from app.config import Settings
from app.models.state import AppState, SyncJobRecord
from app.services.jellyfin import JellyfinService
from app.services.paths import normalize_destination_path
from app.services.rclone import RcloneService
from app.services.state import StateStore


class JobService:
    _lock = threading.RLock()
    _processes: dict[str, subprocess.Popen[str]] = {}
    _changed_line_patterns = (
        re.compile(r":\s+Copied\s+\("),
        re.compile(r":\s+Copied\b"),
        re.compile(r":\s+Moved\b"),
        re.compile(r":\s+Updated\b"),
    )

    def __init__(self, settings: Settings, state_store: StateStore) -> None:
        self.settings = settings
        self.state_store = state_store

    def list_jobs(self) -> list[SyncJobRecord]:
        return self.state_store.snapshot().latest_jobs(limit=25)

    def get_job(self, job_id: str) -> SyncJobRecord | None:
        return self.state_store.snapshot().get_job(job_id)

    def cancel_job(self, job_id: str) -> SyncJobRecord:
        snapshot = self.state_store.snapshot()
        job = snapshot.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        if job.status not in {"queued", "running"}:
            raise ValueError("Only queued or running jobs can be cancelled.")

        with self._lock:
            process = self._processes.pop(job_id, None)

        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)

        def mutate(state: AppState) -> SyncJobRecord | None:
            current = state.get_job(job_id)
            if current is None:
                return None
            if current.status in {"completed", "failed", "cancelled"}:
                return current
            current.status = "cancelled"
            current.finished_at = datetime.now(timezone.utc).isoformat()
            current.error_message = "Cancelled by user."
            current.log_lines.append("Job cancelled by user.")
            current.log_lines = current.log_lines[-200:]
            state.touch()
            return current

        cancelled = self.state_store.mutate(mutate)
        if cancelled is None:
            raise KeyError(job_id)
        return cancelled

    def preview(self, payload: SyncPreviewRequest) -> SyncPreviewResponse:
        state = self.state_store.snapshot()
        normalized_destination = normalize_destination_path(self.settings, payload.destination_path)
        return RcloneService(self.settings, state).preview(
            payload.model_copy(update={"destination_path": normalized_destination})
        )

    def start_job(
        self,
        payload: SyncPreviewRequest,
        *,
        label: str | None = None,
        schedule_id: str | None = None,
        triggered_by: Literal["manual", "schedule"] = "manual",
    ) -> SyncJobRecord:
        state = self.state_store.snapshot()
        normalized_destination = normalize_destination_path(self.settings, payload.destination_path)
        payload = payload.model_copy(update={"destination_path": normalized_destination})
        if state.settings.putio.token is None:
            raise ValueError("Connect Put.io before starting a sync job.")
        preview = RcloneService(self.settings, state).preview(payload)
        resolved_label = label or (
            "Full library sync" if payload.mode == "all" else f"Sync {payload.folder_path}"
        )
        job = SyncJobRecord(
            id=f"job-{uuid.uuid4().hex[:12]}",
            label=resolved_label,
            mode=payload.mode,
            folder_path=payload.folder_path,
            destination_path=payload.destination_path,
            command_preview=preview.command_preview,
            status="queued",
            warnings=preview.warnings,
            refresh_requested=state.settings.jellyfin.enabled
            and state.settings.jellyfin.refresh_after_sync,
            schedule_id=schedule_id,
            triggered_by=triggered_by,
        )
        self.state_store.mutate(lambda current: current.append_job(job))

        worker = threading.Thread(
            target=self._run_job,
            args=(job.id, payload),
            daemon=True,
        )
        worker.start()
        return job

    def _run_job(self, job_id: str, payload: SyncPreviewRequest) -> None:
        def start_job(state: AppState) -> None:
            job = state.get_job(job_id)
            if job is None:
                return
            job.status = "running"
            job.started_at = datetime.now(timezone.utc).isoformat()

        self.state_store.mutate(start_job)
        state = self.state_store.snapshot()
        rclone = RcloneService(self.settings, state)

        binary = shutil.which(self.settings.rclone_binary)
        if binary is None:
            self._finish_failed(job_id, f"`{self.settings.rclone_binary}` is not installed.")
            return

        command = rclone.build_command(payload)
        environment = rclone.build_environment()
        destination = Path(payload.destination_path).expanduser()
        destination.mkdir(parents=True, exist_ok=True)

        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=environment,
            )
        except OSError as exc:
            self._finish_failed(job_id, str(exc))
            return

        with self._lock:
            self._processes[job_id] = process

        files_changed = False
        assert process.stdout is not None
        for line in process.stdout:
            cleaned = line.rstrip()
            if not cleaned:
                continue
            if self._line_indicates_file_change(cleaned):
                files_changed = True
            self._append_log(job_id, cleaned)

        return_code = process.wait()
        with self._lock:
            self._processes.pop(job_id, None)

        current = self.state_store.snapshot().get_job(job_id)
        if current is None:
            return
        if current.status == "cancelled":
            return
        if return_code != 0:
            self._finish_failed(job_id, f"rclone exited with status {return_code}.")
            return

        refresh_triggered = False
        snapshot = self.state_store.snapshot()
        jellyfin = snapshot.settings.jellyfin
        if jellyfin.enabled and jellyfin.refresh_after_sync:
            should_refresh = files_changed or not jellyfin.refresh_only_on_change
            if should_refresh:
                try:
                    JellyfinService(self.settings, snapshot).refresh_library()
                    refresh_triggered = True
                except Exception as exc:
                    self._append_log(job_id, f"Jellyfin refresh failed: {exc}")

        def complete(state: AppState) -> None:
            job = state.get_job(job_id)
            if job is None:
                return
            job.status = "completed"
            job.finished_at = datetime.now(timezone.utc).isoformat()
            job.files_changed = files_changed
            job.refresh_triggered = refresh_triggered

        self.state_store.mutate(complete)

    def _append_log(self, job_id: str, line: str) -> None:
        def mutate(state: AppState) -> None:
            job = state.get_job(job_id)
            if job is None:
                return
            job.log_lines.append(line)
            job.log_lines = job.log_lines[-200:]

        self.state_store.mutate(mutate)

    @classmethod
    def _line_indicates_file_change(cls, line: str) -> bool:
        return any(pattern.search(line) for pattern in cls._changed_line_patterns)

    def _finish_failed(self, job_id: str, message: str) -> None:
        def mutate(state: AppState) -> None:
            job = state.get_job(job_id)
            if job is None:
                return
            if job.status == "cancelled":
                return
            job.status = "failed"
            job.finished_at = datetime.now(timezone.utc).isoformat()
            job.error_message = message
            job.log_lines.append(message)
            job.log_lines = job.log_lines[-200:]

        self.state_store.mutate(mutate)
