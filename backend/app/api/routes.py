from html import escape

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.api.schemas import (
    AppMetaResponse,
    AuthStartResponse,
    DashboardResponse,
    HealthResponse,
    JellyfinLibrariesResponse,
    JellyfinLibrary,
    JellyfinTestResponse,
    JobDetailResponse,
    JobsResponse,
    PutioManualTokenRequest,
    PutioBrowserResponse,
    SaveScheduleRequest,
    SaveSettingsRequest,
    ScheduleResponse,
    SchedulesResponse,
    SettingsResponse,
    SyncPreviewRequest,
    SyncPreviewResponse,
)
from app.config import Settings, get_settings
from app.models.state import AppState
from app.services.jobs import JobService
from app.services.jellyfin import JellyfinService
from app.services.paths import normalize_destination_path
from app.services.putio import PutioService
from app.services.scheduler import SchedulerService, get_scheduler_service
from app.services.state import StateStore, get_state_store
from app.models.state import utc_now

router = APIRouter(prefix="/api")


def dashboard_url(settings: Settings) -> str:
    return settings.frontend_url.rstrip("/") or "/"


def oauth_error_page(message: str, *, status_code: int = 400) -> HTMLResponse:
    safe_message = escape(message)
    return HTMLResponse(
        f"<h1>Put.io login failed</h1><p>{safe_message}</p>",
        status_code=status_code,
    )


def redact_settings(settings_model):
    safe_settings = settings_model.model_copy(deep=True)
    safe_settings.putio.client_secret = ""
    safe_settings.putio.token = None
    safe_settings.putio.oauth_state = None
    safe_settings.jellyfin.api_key = ""
    return safe_settings


def settings_dependency() -> Settings:
    return get_settings()


def state_store_dependency() -> StateStore:
    return get_state_store()


def state_dependency(store: StateStore = Depends(state_store_dependency)) -> AppState:
    return store.snapshot()


def scheduler_dependency() -> SchedulerService:
    return get_scheduler_service()


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(settings_dependency)) -> HealthResponse:
    return HealthResponse(status="ok", product_name=settings.product_name)


@router.get("/meta", response_model=AppMetaResponse)
def meta(settings: Settings = Depends(settings_dependency)) -> AppMetaResponse:
    return AppMetaResponse(
        name=settings.product_name,
        headline="Put.io downlink for Jellyfin libraries.",
        version="0.1.0",
    )


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(
    settings: Settings = Depends(settings_dependency),
    state: AppState = Depends(state_dependency),
) -> DashboardResponse:
    putio = PutioService(settings, state)
    try:
        browser = putio.browse_path("/")
    except ValueError:
        browser = PutioBrowserResponse(current_path="/", parent_path=None, breadcrumbs=[], entries=[])

    destination_candidates = [state.settings.sync_defaults.destination_path]
    destination_candidates.extend(
        [
            str(settings.storage_path),
            str(settings.storage_path / "staging"),
            str(settings.storage_path / "library" / "movies"),
        ]
    )
    return DashboardResponse(
        product_name=settings.product_name,
        tagline="A calmer control plane for syncing cloud media into local libraries.",
        settings=redact_settings(state.settings),
        connections=[
            putio.connection_status(),
            JellyfinService(settings, state).connection_status(),
        ],
        folders=browser.entries,
        putio_browser=browser,
        jellyfin_libraries=[],
        destinations=[candidate for candidate in dict.fromkeys(destination_candidates) if candidate],
        jobs=[
            {
                "id": job.id,
                "label": job.label,
                "mode": job.mode,
                "target_path": job.destination_path,
                "status": job.status,
                "last_run": job.finished_at or job.started_at or job.created_at,
                "refresh_triggered": job.refresh_triggered,
            }
            for job in state.latest_jobs(limit=10)
        ],
        schedules=[
            ScheduleResponse.model_validate(schedule.model_dump())
            for schedule in get_scheduler_service().list_schedules()
        ],
        putio_connected=state.settings.putio.token is not None,
        jellyfin_enabled=state.settings.jellyfin.enabled,
    )


@router.get("/putio/browser", response_model=PutioBrowserResponse)
def browse_putio(
    path: str = Query(default="/"),
    settings: Settings = Depends(settings_dependency),
    state: AppState = Depends(state_dependency),
) -> PutioBrowserResponse:
    try:
        return PutioService(settings, state).browse_path(path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/jellyfin/libraries", response_model=JellyfinLibrariesResponse)
def jellyfin_libraries(
    settings: Settings = Depends(settings_dependency),
    state: AppState = Depends(state_dependency),
) -> JellyfinLibrariesResponse:
    try:
        libraries = JellyfinService(settings, state).list_libraries()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JellyfinLibrariesResponse(libraries=libraries)


@router.get("/settings", response_model=SettingsResponse)
def get_settings_route(state: AppState = Depends(state_dependency)) -> SettingsResponse:
    return SettingsResponse(settings=redact_settings(state.settings))


@router.put("/settings", response_model=SettingsResponse)
def save_settings(
    payload: SaveSettingsRequest,
    settings: Settings = Depends(settings_dependency),
    store: StateStore = Depends(state_store_dependency),
) -> SettingsResponse:
    try:
        if payload.settings.jellyfin.base_url:
            JellyfinService.validate_base_url(payload.settings.jellyfin.base_url)
        if payload.settings.sync_defaults.destination_path:
            payload.settings.sync_defaults.destination_path = normalize_destination_path(
                settings,
                payload.settings.sync_defaults.destination_path,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    def mutate(state: AppState) -> AppState:
        next_settings = payload.settings.model_copy(deep=True)
        if not next_settings.putio.client_secret:
            next_settings.putio.client_secret = state.settings.putio.client_secret
        next_settings.putio.token = state.settings.putio.token
        next_settings.putio.oauth_state = state.settings.putio.oauth_state
        next_settings.putio.account_username = state.settings.putio.account_username
        next_settings.putio.account_user_id = state.settings.putio.account_user_id
        next_settings.putio.connected_at = state.settings.putio.connected_at
        if not next_settings.jellyfin.api_key:
            next_settings.jellyfin.api_key = state.settings.jellyfin.api_key
        state.settings = next_settings
        return state

    state = store.mutate(mutate)
    return SettingsResponse(settings=redact_settings(state.settings))


@router.get("/auth/putio/start", response_model=AuthStartResponse)
def start_putio_auth(
    settings: Settings = Depends(settings_dependency),
    store: StateStore = Depends(state_store_dependency),
) -> AuthStartResponse:
    state = store.snapshot()
    service = PutioService(settings, state)
    try:
        auth_url, oauth_state = service.build_auth_url()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    def mutate(current: AppState) -> None:
        current.settings.putio.oauth_state = oauth_state

    store.mutate(mutate)
    return AuthStartResponse(auth_url=auth_url)


@router.get("/auth/putio/callback", response_class=HTMLResponse)
def putio_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    settings: Settings = Depends(settings_dependency),
    store: StateStore = Depends(state_store_dependency),
) -> HTMLResponse:
    if error:
        return oauth_error_page(error)

    current = store.snapshot()
    stored_state = current.settings.putio.oauth_state
    if not state or not stored_state or state != stored_state:
        if stored_state is not None:
            def clear_oauth_state(state_model: AppState) -> None:
                state_model.settings.putio.oauth_state = None

            store.mutate(clear_oauth_state)
        return oauth_error_page("Invalid state token.")
    if code is None:
        return oauth_error_page("No code returned.")

    service = PutioService(settings, current)
    try:
        token = service.exchange_code(code)
        user_id, username = service.fetch_account(token)
    except Exception as exc:  # pragma: no cover - external API failure path
        return oauth_error_page(str(exc))

    def mutate(state_model: AppState) -> None:
        state_model.settings.putio.token = token
        state_model.settings.putio.account_user_id = user_id
        state_model.settings.putio.account_username = username
        state_model.settings.putio.connected_at = utc_now()
        state_model.settings.putio.oauth_state = None

    store.mutate(mutate)
    return_url = escape(dashboard_url(settings), quote=True)
    return HTMLResponse(
        f"""
        <html>
          <body style="font-family: sans-serif; background:#071018; color:#eef5ef; padding:2rem;">
            <h1>Put.io connected</h1>
            <p>You can close this tab and return to get-put.io.</p>
            <p><a href="{return_url}" style="color:#a6f4c5;">Return to dashboard</a></p>
          </body>
        </html>
        """
    )


@router.post("/auth/putio/disconnect", response_model=SettingsResponse)
def disconnect_putio(store: StateStore = Depends(state_store_dependency)) -> SettingsResponse:
    def mutate(state: AppState) -> AppState:
        state.settings.putio.token = None
        state.settings.putio.account_user_id = None
        state.settings.putio.account_username = None
        state.settings.putio.connected_at = None
        state.settings.putio.oauth_state = None
        return state

    state = store.mutate(mutate)
    return SettingsResponse(settings=redact_settings(state.settings))


@router.post("/auth/putio/manual-token", response_model=SettingsResponse)
def save_putio_manual_token(
    payload: PutioManualTokenRequest,
    settings: Settings = Depends(settings_dependency),
    store: StateStore = Depends(state_store_dependency),
) -> SettingsResponse:
    current = store.snapshot()
    service = PutioService(settings, current)
    token = service.manual_token(payload.oauth_token)
    try:
        user_id, username = service.fetch_account(token)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid Put.io token: {exc}") from exc

    def mutate(state_model: AppState) -> AppState:
        state_model.settings.putio.token = token
        state_model.settings.putio.account_user_id = user_id
        state_model.settings.putio.account_username = username
        state_model.settings.putio.connected_at = utc_now()
        state_model.settings.putio.oauth_state = None
        return state_model

    state = store.mutate(mutate)
    return SettingsResponse(settings=redact_settings(state.settings))


@router.post("/jellyfin/test", response_model=JellyfinTestResponse)
def test_jellyfin(
    settings: Settings = Depends(settings_dependency),
    state: AppState = Depends(state_dependency),
) -> JellyfinTestResponse:
    try:
        name = JellyfinService(settings, state).test_connection()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JellyfinTestResponse(ok=True, message=f"Connected to {name}.")


@router.post("/jobs/preview", response_model=SyncPreviewResponse)
def preview_job(
    payload: SyncPreviewRequest,
    settings: Settings = Depends(settings_dependency),
    store: StateStore = Depends(state_store_dependency),
) -> SyncPreviewResponse:
    try:
        return JobService(settings, store).preview(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/jobs/run", response_model=JobDetailResponse)
def run_job(
    payload: SyncPreviewRequest,
    settings: Settings = Depends(settings_dependency),
    store: StateStore = Depends(state_store_dependency),
) -> JobDetailResponse:
    try:
        job = JobService(settings, store).start_job(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JobDetailResponse.model_validate(job.model_dump())


@router.get("/schedules", response_model=SchedulesResponse)
def list_schedules(scheduler: SchedulerService = Depends(scheduler_dependency)) -> SchedulesResponse:
    schedules = scheduler.list_schedules()
    return SchedulesResponse(
        schedules=[ScheduleResponse.model_validate(schedule.model_dump()) for schedule in schedules]
    )


@router.post("/schedules", response_model=ScheduleResponse)
def create_schedule(
    payload: SaveScheduleRequest,
    scheduler: SchedulerService = Depends(scheduler_dependency),
) -> ScheduleResponse:
    try:
        schedule = scheduler.create_schedule(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ScheduleResponse.model_validate(schedule.model_dump())


@router.put("/schedules/{schedule_id}", response_model=ScheduleResponse)
def update_schedule(
    schedule_id: str,
    payload: SaveScheduleRequest,
    scheduler: SchedulerService = Depends(scheduler_dependency),
) -> ScheduleResponse:
    try:
        schedule = scheduler.update_schedule(schedule_id, **payload.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Schedule not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ScheduleResponse.model_validate(schedule.model_dump())


@router.post("/schedules/{schedule_id}/run", response_model=JobDetailResponse)
def run_schedule(
    schedule_id: str,
    scheduler: SchedulerService = Depends(scheduler_dependency),
    settings: Settings = Depends(settings_dependency),
    store: StateStore = Depends(state_store_dependency),
) -> JobDetailResponse:
    try:
        scheduler.trigger_schedule(schedule_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Schedule not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    schedule = scheduler.get_schedule(schedule_id)
    if schedule is None or schedule.last_job_id is None:
        raise HTTPException(status_code=500, detail="Schedule trigger failed.")
    job = JobService(settings, store).get_job(schedule.last_job_id)
    if job is None:
        raise HTTPException(status_code=500, detail="Scheduled job record missing.")
    return JobDetailResponse.model_validate(job.model_dump())


@router.delete("/schedules/{schedule_id}", status_code=204)
def delete_schedule(
    schedule_id: str,
    scheduler: SchedulerService = Depends(scheduler_dependency),
) -> None:
    scheduler.delete_schedule(schedule_id)


@router.get("/jobs", response_model=JobsResponse)
def list_jobs(
    settings: Settings = Depends(settings_dependency),
    store: StateStore = Depends(state_store_dependency),
) -> JobsResponse:
    jobs = JobService(settings, store).list_jobs()
    return JobsResponse(jobs=[JobDetailResponse.model_validate(job.model_dump()) for job in jobs])


@router.get("/jobs/{job_id}", response_model=JobDetailResponse)
def get_job(
    job_id: str,
    settings: Settings = Depends(settings_dependency),
    store: StateStore = Depends(state_store_dependency),
) -> JobDetailResponse:
    job = JobService(settings, store).get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return JobDetailResponse.model_validate(job.model_dump())


@router.post("/jobs/{job_id}/cancel", response_model=JobDetailResponse)
def cancel_job(
    job_id: str,
    settings: Settings = Depends(settings_dependency),
    store: StateStore = Depends(state_store_dependency),
) -> JobDetailResponse:
    try:
        job = JobService(settings, store).cancel_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JobDetailResponse.model_validate(job.model_dump())
