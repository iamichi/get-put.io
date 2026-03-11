from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

from app.api.schemas import SyncPreviewRequest
from app.config import Settings, get_settings
from app.models.state import AppState, RecurringSchedule, utc_now
from app.services.jobs import JobService
from app.services.paths import normalize_destination_path
from app.services.storage_cleanup import StorageCleanupService
from app.services.state import StateStore, get_state_store


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self, settings: Settings, state_store: StateStore) -> None:
        self.settings = settings
        self.state_store = state_store
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def list_schedules(self) -> list[RecurringSchedule]:
        schedules = self.state_store.snapshot().schedules
        return sorted(schedules, key=lambda schedule: schedule.name.lower())

    def get_schedule(self, schedule_id: str) -> RecurringSchedule | None:
        return self.state_store.snapshot().get_schedule(schedule_id)

    def create_schedule(
        self,
        *,
        name: str,
        enabled: bool,
        mode: str,
        folder_path: str | None,
        destination_path: str,
        deletion_policy: str,
        schedule_type: str,
        interval_hours: int,
        daily_time: str,
    ) -> RecurringSchedule:
        normalized_destination = normalize_destination_path(self.settings, destination_path)
        schedule = RecurringSchedule(
            id=f"schedule-{uuid.uuid4().hex[:12]}",
            name=name,
            enabled=enabled,
            mode=mode,
            folder_path=folder_path,
            destination_path=normalized_destination,
            deletion_policy=deletion_policy,
            schedule_type=schedule_type,
            interval_hours=interval_hours,
            daily_time=daily_time,
        )
        schedule.next_run_at = self.compute_next_run(schedule).isoformat() if schedule.enabled else None
        return self.state_store.mutate(lambda state: state.upsert_schedule(schedule))

    def update_schedule(
        self,
        schedule_id: str,
        *,
        name: str,
        enabled: bool,
        mode: str,
        folder_path: str | None,
        destination_path: str,
        deletion_policy: str,
        schedule_type: str,
        interval_hours: int,
        daily_time: str,
    ) -> RecurringSchedule:
        normalized_destination = normalize_destination_path(self.settings, destination_path)
        def mutate(state: AppState) -> RecurringSchedule:
            current = state.get_schedule(schedule_id)
            if current is None:
                raise KeyError(schedule_id)

            updated = current.model_copy(deep=True)
            updated.name = name
            updated.enabled = enabled
            updated.mode = mode  # type: ignore[assignment]
            updated.folder_path = folder_path
            updated.destination_path = normalized_destination
            updated.deletion_policy = deletion_policy  # type: ignore[assignment]
            updated.schedule_type = schedule_type  # type: ignore[assignment]
            updated.interval_hours = interval_hours
            updated.daily_time = daily_time
            updated.updated_at = utc_now()
            updated.next_run_at = (
                self.compute_next_run(updated).isoformat() if enabled else None
            )
            return state.upsert_schedule(updated)

        return self.state_store.mutate(mutate)

    def delete_schedule(self, schedule_id: str) -> None:
        self.state_store.mutate(lambda state: state.delete_schedule(schedule_id))

    def trigger_schedule(self, schedule_id: str) -> None:
        schedule = self.get_schedule(schedule_id)
        if schedule is None:
            raise KeyError(schedule_id)

        payload = SyncPreviewRequest(
            mode=schedule.mode,
            folder_path=schedule.folder_path,
            destination_path=schedule.destination_path,
            deletion_policy=schedule.deletion_policy,
        )
        job = JobService(self.settings, self.state_store).start_job(
            payload,
            label=schedule.name,
            schedule_id=schedule.id,
            triggered_by="schedule",
        )
        triggered_at = datetime.now(timezone.utc)

        def mutate(state: AppState) -> None:
            current = state.get_schedule(schedule_id)
            if current is None:
                return
            current.last_run_at = triggered_at.isoformat()
            current.last_job_id = job.id
            current.next_run_at = self.compute_next_run(current, from_utc=triggered_at).isoformat()
            current.updated_at = utc_now()

        self.state_store.mutate(mutate)

    def start(self) -> None:
        self.refresh_cleanup_schedule()
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._loop, name="get-putio-scheduler", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._stop_event.set()
            thread = self._thread
            self._thread = None
        if thread and thread.is_alive():
            thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                due_schedules = self._claim_due_schedules()
                for schedule in due_schedules:
                    try:
                        self.trigger_schedule(schedule.id)
                    except Exception:
                        logger.exception("Failed to trigger schedule %s", schedule.id)
                        continue
                self._run_due_cleanup()
            finally:
                self._stop_event.wait(self.settings.scheduler_poll_seconds)

    def _claim_due_schedules(self) -> list[RecurringSchedule]:
        now_utc = datetime.now(timezone.utc)
        schedules = self.state_store.snapshot().schedules
        claimed: list[RecurringSchedule] = []
        for schedule in schedules:
            if not schedule.enabled or not schedule.next_run_at:
                continue
            if _parse_iso(schedule.next_run_at) > now_utc:
                continue
            claimed.append(schedule.model_copy(deep=True))
        return claimed

    def refresh_cleanup_schedule(self) -> None:
        def mutate(state: AppState) -> None:
            cleanup = state.settings.storage_cleanup
            if not cleanup.enabled or not cleanup.schedule_enabled:
                state.cleanup_schedule.next_run_at = None
                return
            state.cleanup_schedule.next_run_at = self.compute_next_run_from_parts(
                schedule_type=cleanup.schedule_type,
                interval_hours=cleanup.interval_hours,
                daily_time=cleanup.daily_time,
            ).isoformat()

        self.state_store.mutate(mutate)

    def _run_due_cleanup(self) -> None:
        snapshot = self.state_store.snapshot()
        next_run_at = snapshot.cleanup_schedule.next_run_at
        if not next_run_at:
            return
        if _parse_iso(next_run_at) > datetime.now(timezone.utc):
            return

        service = StorageCleanupService(self.settings, self.state_store)
        cleanup = snapshot.settings.storage_cleanup
        should_run = service.should_run_scheduled_cleanup(snapshot)
        next_run = self.compute_next_run_from_parts(
            schedule_type=cleanup.schedule_type,
            interval_hours=cleanup.interval_hours,
            daily_time=cleanup.daily_time,
        ).isoformat()
        if should_run:
            run = service.start_run(triggered_by="schedule")

            def mutate(state: AppState) -> None:
                state.cleanup_schedule.next_run_at = next_run
                state.cleanup_schedule.last_job_id = run.id
                state.touch()

            self.state_store.mutate(mutate)
            return

        def mutate(state: AppState) -> None:
            state.cleanup_schedule.next_run_at = next_run
            state.touch()

        self.state_store.mutate(mutate)

    def compute_next_run(
        self,
        schedule: RecurringSchedule,
        from_utc: datetime | None = None,
    ) -> datetime:
        return self.compute_next_run_from_parts(
            schedule_type=schedule.schedule_type,
            interval_hours=schedule.interval_hours,
            daily_time=schedule.daily_time,
            from_utc=from_utc,
        )

    def compute_next_run_from_parts(
        self,
        *,
        schedule_type: str,
        interval_hours: int,
        daily_time: str,
        from_utc: datetime | None = None,
    ) -> datetime:
        anchor = (from_utc or datetime.now(timezone.utc)).astimezone(ZoneInfo(self.settings.schedule_timezone))
        if schedule_type == "interval":
            return (anchor + timedelta(hours=max(interval_hours, 1))).astimezone(timezone.utc)

        hour_text, minute_text = daily_time.split(":", maxsplit=1)
        candidate = anchor.replace(hour=int(hour_text), minute=int(minute_text), second=0, microsecond=0)
        if candidate <= anchor:
            candidate += timedelta(days=1)
        return candidate.astimezone(timezone.utc)


@lru_cache(maxsize=1)
def get_scheduler_service() -> SchedulerService:
    return SchedulerService(get_settings(), get_state_store())
