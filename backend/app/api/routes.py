from fastapi import APIRouter, Depends

from app.api.schemas import (
    AppMetaResponse,
    DashboardResponse,
    HealthResponse,
    SyncPreviewRequest,
    SyncPreviewResponse,
)
from app.config import Settings, get_settings
from app.services.jellyfin import JellyfinService
from app.services.putio import PutioService
from app.services.rclone import RcloneService

router = APIRouter(prefix="/api")


def settings_dependency() -> Settings:
    return get_settings()


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
def dashboard(settings: Settings = Depends(settings_dependency)) -> DashboardResponse:
    putio = PutioService(settings)
    jellyfin = JellyfinService(settings)
    return DashboardResponse(
        product_name=settings.product_name,
        tagline="A calmer control plane for syncing cloud media into local libraries.",
        connections=[
            putio.connection_status(),
            jellyfin.connection_status(),
        ],
        folders=putio.list_folders(),
        destinations=[
            str(settings.storage_path),
            str(settings.storage_path / "staging"),
            str(settings.storage_path / "library" / "movies"),
        ],
        jobs=[
            {
                "id": "job-nightly-all",
                "label": "Nightly full sweep",
                "mode": "all",
                "target_path": str(settings.storage_path / "staging"),
                "status": "draft",
                "last_run": "Not run yet",
            },
            {
                "id": "job-series",
                "label": "Series-only sync",
                "mode": "folder",
                "target_path": str(settings.storage_path / "library" / "tv"),
                "status": "draft",
                "last_run": "Not run yet",
            },
        ],
    )


@router.post("/jobs/preview", response_model=SyncPreviewResponse)
def preview_job(
    payload: SyncPreviewRequest,
    settings: Settings = Depends(settings_dependency),
) -> SyncPreviewResponse:
    return RcloneService(settings).preview(payload)

