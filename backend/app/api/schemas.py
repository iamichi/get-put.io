from typing import Literal

from pydantic import BaseModel, Field


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


class JobSummary(BaseModel):
    id: str
    label: str
    mode: Literal["all", "folder"]
    target_path: str
    status: Literal["draft", "running", "completed", "failed"]
    last_run: str


class DashboardResponse(BaseModel):
    product_name: str
    tagline: str
    connections: list[ConnectionStatus]
    folders: list[FolderNode]
    destinations: list[str]
    jobs: list[JobSummary]


class SyncPreviewRequest(BaseModel):
    mode: Literal["all", "folder"] = "all"
    folder_path: str | None = None
    destination_path: str = Field(..., min_length=1)


class SyncPreviewResponse(BaseModel):
    title: str
    command_preview: str
    steps: list[str]
    warnings: list[str]

