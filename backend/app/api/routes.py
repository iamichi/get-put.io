from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.api.schemas import (
    AppMetaResponse,
    AuthStartResponse,
    DashboardResponse,
    HealthResponse,
    JellyfinTestResponse,
    JobDetailResponse,
    JobsResponse,
    SaveSettingsRequest,
    SettingsResponse,
    SyncPreviewRequest,
    SyncPreviewResponse,
)
from app.config import Settings, get_settings
from app.models.state import AppState
from app.services.jobs import JobService
from app.services.jellyfin import JellyfinService
from app.services.putio import PutioService
from app.services.state import StateStore, get_state_store
from app.models.state import utc_now

router = APIRouter(prefix="/api")


def settings_dependency() -> Settings:
    return get_settings()


def state_store_dependency() -> StateStore:
    return get_state_store()


def state_dependency(store: StateStore = Depends(state_store_dependency)) -> AppState:
    return store.snapshot()


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
    jellyfin = JellyfinService(settings, state)
    return DashboardResponse(
        product_name=settings.product_name,
        tagline="A calmer control plane for syncing cloud media into local libraries.",
        settings=state.settings,
        connections=[
            putio.connection_status(),
            jellyfin.connection_status(),
        ],
        folders=putio.list_folders(),
        destinations=[
            state.settings.sync_defaults.destination_path,
            str(settings.storage_path),
            str(settings.storage_path / "staging"),
            str(settings.storage_path / "library" / "movies"),
        ],
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
        putio_connected=state.settings.putio.token is not None,
        jellyfin_enabled=state.settings.jellyfin.enabled,
    )


@router.get("/settings", response_model=SettingsResponse)
def get_settings_route(state: AppState = Depends(state_dependency)) -> SettingsResponse:
    return SettingsResponse(settings=state.settings)


@router.put("/settings", response_model=SettingsResponse)
def save_settings(
    payload: SaveSettingsRequest,
    store: StateStore = Depends(state_store_dependency),
) -> SettingsResponse:
    def mutate(state: AppState) -> AppState:
        state.settings = payload.settings
        return state

    state = store.mutate(mutate)
    return SettingsResponse(settings=state.settings)


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
        return HTMLResponse(f"<h1>Put.io login failed</h1><p>{error}</p>", status_code=400)

    current = store.snapshot()
    if state != current.settings.putio.oauth_state:
        return HTMLResponse("<h1>Put.io login failed</h1><p>Invalid state token.</p>", status_code=400)
    if code is None:
        return HTMLResponse("<h1>Put.io login failed</h1><p>No code returned.</p>", status_code=400)

    service = PutioService(settings, current)
    try:
        token = service.exchange_code(code)
        user_id, username = service.fetch_account(token)
    except Exception as exc:  # pragma: no cover - external API failure path
        return HTMLResponse(f"<h1>Put.io login failed</h1><p>{exc}</p>", status_code=400)

    def mutate(state_model: AppState) -> None:
        state_model.settings.putio.token = token
        state_model.settings.putio.account_user_id = user_id
        state_model.settings.putio.account_username = username
        state_model.settings.putio.connected_at = utc_now()
        state_model.settings.putio.oauth_state = None

    store.mutate(mutate)
    return HTMLResponse(
        """
        <html>
          <body style="font-family: sans-serif; background:#071018; color:#eef5ef; padding:2rem;">
            <h1>Put.io connected</h1>
            <p>You can close this tab and return to get-put.io.</p>
            <p><a href="/" style="color:#a6f4c5;">Return to dashboard</a></p>
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
    return SettingsResponse(settings=state.settings)


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
    return JobService(settings, store).preview(payload)


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
