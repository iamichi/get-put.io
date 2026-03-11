from __future__ import annotations

import shutil
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.api.schemas import CleanupPreviewResponse
from app.config import Settings
from app.models.state import AppState, CleanupRunRecord
from app.services.state import StateStore


@dataclass
class CleanupCandidate:
    path: Path
    size: int
    modified_at: float


@dataclass
class CleanupPlan:
    free_percent: float
    threshold_free_percent: int
    target_free_percent: int
    eligible_candidates: list[CleanupCandidate]
    selected_candidates: list[CleanupCandidate]

    @property
    def would_run(self) -> bool:
        return bool(self.selected_candidates)

    @property
    def estimated_bytes_reclaimed(self) -> int:
        return sum(candidate.size for candidate in self.selected_candidates)


class StorageCleanupService:
    _lock = threading.RLock()

    def __init__(self, settings: Settings, state_store: StateStore) -> None:
        self.settings = settings
        self.state_store = state_store

    def list_runs(self) -> list[CleanupRunRecord]:
        return self.state_store.snapshot().latest_cleanup_runs(limit=25)

    def get_run(self, run_id: str) -> CleanupRunRecord | None:
        return self.state_store.snapshot().get_cleanup_run(run_id)

    def preview(self) -> CleanupPreviewResponse:
        state = self.state_store.snapshot()
        plan = self._build_plan(state)
        return self._preview_response(plan)

    def start_run(self, *, triggered_by: str = "manual") -> CleanupRunRecord:
        plan = self._build_plan(self.state_store.snapshot())
        run = CleanupRunRecord(
            id=f"cleanup-{uuid.uuid4().hex[:12]}",
            status="queued",
            free_percent_before=plan.free_percent,
            triggered_by=triggered_by,  # type: ignore[arg-type]
        )
        self.state_store.mutate(lambda state: state.append_cleanup_run(run))

        worker = threading.Thread(
            target=self._run_cleanup,
            args=(run.id, triggered_by),
            daemon=True,
        )
        worker.start()
        return run

    def _run_cleanup(self, run_id: str, triggered_by: str) -> None:
        def mark_running(state: AppState) -> None:
            run = state.get_cleanup_run(run_id)
            if run is None:
                return
            run.status = "running"
            run.started_at = datetime.now(timezone.utc).isoformat()

        self.state_store.mutate(mark_running)
        snapshot = self.state_store.snapshot()
        plan = self._build_plan(snapshot)

        deleted_files = 0
        reclaimed_bytes = 0
        logs: list[str] = [
            f"Free space before cleanup: {plan.free_percent:.1f}%",
            f"Threshold: {plan.threshold_free_percent}% free, target: {plan.target_free_percent}% free.",
        ]

        if not snapshot.settings.storage_cleanup.enabled:
            logs.append("Cleanup is disabled. No files deleted.")
            self._finish_run(run_id, deleted_files, reclaimed_bytes, logs)
            return

        if not plan.selected_candidates:
            logs.append("No eligible files matched the current cleanup policy.")
            self._finish_run(run_id, deleted_files, reclaimed_bytes, logs)
            return

        for candidate in plan.selected_candidates:
            try:
                candidate.path.unlink()
                deleted_files += 1
                reclaimed_bytes += candidate.size
                logs.append(
                    f"Deleted {candidate.path} ({self._format_bytes(candidate.size)})."
                )
            except OSError as exc:
                logs.append(f"Failed to delete {candidate.path}: {exc}")

        free_percent_after = self._free_percent(self.settings.storage_path)

        def complete(state: AppState) -> None:
            run = state.get_cleanup_run(run_id)
            if run is None:
                return
            run.status = "completed"
            run.finished_at = datetime.now(timezone.utc).isoformat()
            run.deleted_files = deleted_files
            run.reclaimed_bytes = reclaimed_bytes
            run.free_percent_after = free_percent_after
            run.log_lines = logs[-200:]
            state.cleanup_schedule.last_run_at = run.finished_at
            state.cleanup_schedule.last_job_id = run.id
            state.touch()

        self.state_store.mutate(complete)

    def _finish_run(self, run_id: str, deleted_files: int, reclaimed_bytes: int, logs: list[str]) -> None:
        free_percent_after = self._free_percent(self.settings.storage_path)

        def complete(state: AppState) -> None:
            run = state.get_cleanup_run(run_id)
            if run is None:
                return
            run.status = "completed"
            run.finished_at = datetime.now(timezone.utc).isoformat()
            run.deleted_files = deleted_files
            run.reclaimed_bytes = reclaimed_bytes
            run.free_percent_after = free_percent_after
            run.log_lines = logs[-200:]
            state.cleanup_schedule.last_run_at = run.finished_at
            state.cleanup_schedule.last_job_id = run.id
            state.touch()

        self.state_store.mutate(complete)

    def _preview_response(self, plan: CleanupPlan) -> CleanupPreviewResponse:
        sample_paths = [str(candidate.path) for candidate in plan.selected_candidates[:5]]
        return CleanupPreviewResponse(
            would_run=plan.would_run,
            free_percent=plan.free_percent,
            threshold_free_percent=plan.threshold_free_percent,
            target_free_percent=plan.target_free_percent,
            estimated_files_to_delete=len(plan.selected_candidates),
            estimated_bytes_reclaimed=plan.estimated_bytes_reclaimed,
            candidate_count=len(plan.eligible_candidates),
            sample_paths=sample_paths,
            summary=(
                "Cleanup would delete the oldest eligible files to reach the target free space."
                if plan.would_run
                else "No cleanup needed under the current policy."
            ),
        )

    def _build_plan(self, state: AppState) -> CleanupPlan:
        cleanup = state.settings.storage_cleanup
        storage_root = self.settings.storage_path.expanduser().resolve(strict=False)
        free_percent = self._free_percent(storage_root)

        if not cleanup.enabled:
            return CleanupPlan(
                free_percent=free_percent,
                threshold_free_percent=cleanup.threshold_free_percent,
                target_free_percent=cleanup.target_free_percent,
                eligible_candidates=[],
                selected_candidates=[],
            )

        cutoff = datetime.now(timezone.utc) - timedelta(days=max(cleanup.min_age_days, 0))
        excluded_roots = [
            Path(path).expanduser().resolve(strict=False)
            for path in cleanup.exclude_paths
            if path.strip()
        ]

        candidates: list[CleanupCandidate] = []
        for file_path in storage_root.rglob("*"):
            if not file_path.is_file() or file_path.is_symlink():
                continue
            resolved_path = file_path.resolve(strict=False)
            if any(resolved_path.is_relative_to(excluded) for excluded in excluded_roots):
                continue
            stat = file_path.stat()
            modified_at = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
            if modified_at > cutoff:
                continue
            candidates.append(
                CleanupCandidate(
                    path=resolved_path,
                    size=stat.st_size,
                    modified_at=stat.st_mtime,
                )
            )

        candidates.sort(key=lambda candidate: candidate.modified_at)
        if free_percent >= cleanup.target_free_percent:
            selected: list[CleanupCandidate] = []
        else:
            total, _, free = self._disk_usage(storage_root)
            target_free_bytes = int(total * (cleanup.target_free_percent / 100))
            bytes_needed = max(target_free_bytes - free, 0)
            selected = []
            reclaimed = 0
            for candidate in candidates:
                selected.append(candidate)
                reclaimed += candidate.size
                if reclaimed >= bytes_needed:
                    break

        return CleanupPlan(
            free_percent=free_percent,
            threshold_free_percent=cleanup.threshold_free_percent,
            target_free_percent=cleanup.target_free_percent,
            eligible_candidates=candidates,
            selected_candidates=selected,
        )

    @staticmethod
    def _disk_usage(path: Path) -> tuple[int, int, int]:
        disk = shutil.disk_usage(path)
        return disk.total, disk.used, disk.free

    def should_run_scheduled_cleanup(self, state: AppState) -> bool:
        cleanup = state.settings.storage_cleanup
        if not cleanup.enabled or not cleanup.schedule_enabled:
            return False
        plan = self._build_plan(state)
        return plan.free_percent < cleanup.threshold_free_percent and plan.would_run

    def _free_percent(self, path: Path) -> float:
        total, _, free = self._disk_usage(path)
        if total <= 0:
            return 0
        return round((free / total) * 100, 1)

    @staticmethod
    def _format_bytes(size: int) -> str:
        units = ["B", "KB", "MB", "GB", "TB"]
        value = float(size)
        for unit in units:
            if value < 1024 or unit == units[-1]:
                return f"{value:.1f} {unit}"
            value /= 1024
        return f"{size} B"
