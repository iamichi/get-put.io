from typing import Literal

from pydantic import BaseModel, Field

from app.models.state import AppSettings

class HealthResponse(BaseModel):
    status: Literal["ok"]
    product_name: str


class AppMetaResponse(BaseModel):
    name: str
    headline: str
    version: str


class ConnectionStatus(BaseModel):
    service: str
    connected: bool
    summary: str


class FolderNode(BaseModel):
    id: str
    name: str
    path: str
    child_count: int = 0


class BreadcrumbNode(BaseModel):
    name: str
    path: str


class PutioBrowserResponse(BaseModel):
    current_path: str
    parent_path: str | None = None
    breadcrumbs: list[BreadcrumbNode]
    entries: list[FolderNode]


class JellyfinLibrary(BaseModel):
    id: str
    name: str
    collection_type: str | None = None
    locations: list[str] = Field(default_factory=list)
    refresh_status: str | None = None


class JobSummary(BaseModel):
    id: str
    label: str
    mode: Literal["all", "folder"]
    target_path: str
    status: Literal["queued", "running", "completed", "failed"]
    last_run: str
    refresh_triggered: bool = False


class DashboardResponse(BaseModel):
    product_name: str
    tagline: str
    settings: AppSettings
    connections: list[ConnectionStatus]
    folders: list[FolderNode]
    putio_browser: PutioBrowserResponse
    jellyfin_libraries: list[JellyfinLibrary]
    destinations: list[str]
    jobs: list[JobSummary]
    putio_connected: bool
    jellyfin_enabled: bool


class SyncPreviewRequest(BaseModel):
    mode: Literal["all", "folder"] = "all"
    folder_path: str | None = None
    destination_path: str = Field(..., min_length=1)


class SyncPreviewResponse(BaseModel):
    title: str
    command_preview: str
    command_parts: list[str]
    steps: list[str]
    warnings: list[str]


class AuthStartResponse(BaseModel):
    auth_url: str


class SettingsResponse(BaseModel):
    settings: AppSettings


class SaveSettingsRequest(BaseModel):
    settings: AppSettings


class JellyfinTestResponse(BaseModel):
    ok: bool
    message: str


class JellyfinLibrariesResponse(BaseModel):
    libraries: list[JellyfinLibrary]


class JobDetailResponse(BaseModel):
    id: str
    label: str
    mode: Literal["all", "folder"]
    folder_path: str | None = None
    destination_path: str
    status: Literal["queued", "running", "completed", "failed"]
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    command_preview: str
    warnings: list[str]
    log_lines: list[str]
    refresh_requested: bool
    refresh_triggered: bool
    files_changed: bool
    error_message: str | None = None


class JobsResponse(BaseModel):
    jobs: list[JobDetailResponse]
