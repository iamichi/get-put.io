from __future__ import annotations

import json
import os
from pathlib import Path

from app.api.schemas import SyncPreviewRequest, SyncPreviewResponse
from app.config import Settings
from app.models.state import AppState
from app.services.jellyfin import JellyfinService


class RcloneService:
    def __init__(self, settings: Settings, state: AppState) -> None:
        self.settings = settings
        self.state = state

    def preview(self, payload: SyncPreviewRequest) -> SyncPreviewResponse:
        remote_path = self._remote_path(payload)
        destination = Path(payload.destination_path).expanduser()
        command_parts = self.build_command(payload)
        command = " ".join(command_parts)

        warnings: list[str] = []
        if destination == self.settings.storage_path:
            warnings.append(
                "Destination matches the primary library root. Consider a staging directory first."
            )
        if payload.deletion_policy == "mirror_remote":
            warnings.append(
                "Mirror mode will delete local files that no longer exist in Put.io."
            )
        if payload.mode == "folder" and not payload.folder_path:
            warnings.append("Folder mode needs a Put.io folder path.")
        if self.state.settings.putio.token is None:
            warnings.append("Put.io is not connected yet.")
        if self.state.settings.jellyfin.enabled and not self.state.settings.jellyfin.api_key:
            warnings.append("Jellyfin integration is enabled but the API key is empty.")
        selected_library_ids = set(self.state.settings.jellyfin.selected_library_ids)
        if selected_library_ids:
            try:
                libraries = {
                    library.id: library
                    for library in JellyfinService(self.settings, self.state).list_libraries()
                }
                selected_locations: list[str] = []
                for library_id in selected_library_ids:
                    library = libraries.get(library_id)
                    if library is not None:
                        selected_locations.extend(library.locations)
                if selected_locations and not any(
                    str(destination).startswith(location.rstrip("/")) for location in selected_locations
                ):
                    warnings.append(
                        "Destination is outside the selected Jellyfin library locations."
                    )
            except Exception:
                warnings.append("Could not validate the destination against Jellyfin libraries.")

        return SyncPreviewResponse(
            title="Sync preview",
            command_preview=command,
            command_parts=command_parts,
            steps=[
                "Resolve the selected Put.io scope into an rclone remote path.",
                (
                    "Mirror the Put.io scope into the selected local destination, deleting missing local files."
                    if payload.deletion_policy == "mirror_remote"
                    else "Copy files into the selected local destination."
                ),
                "Stream progress into the job log while rclone runs.",
                "Trigger a Jellyfin refresh after the transfer succeeds if enabled.",
            ],
            warnings=warnings,
        )

    def build_command(self, payload: SyncPreviewRequest) -> list[str]:
        remote_path = self._remote_path(payload)
        destination = str(Path(payload.destination_path).expanduser())
        verb = "sync" if payload.deletion_policy == "mirror_remote" else "copy"
        return [
            self.settings.rclone_binary,
            verb,
            remote_path,
            destination,
            "--create-empty-src-dirs",
            "--fast-list",
            "--stats=1s",
            "--stats-one-line",
            "--checksum",
        ]

    def build_environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        environment["RCLONE_CONFIG_PUTIO_TYPE"] = "putio"

        putio = self.state.settings.putio
        if putio.app_id:
            environment["RCLONE_CONFIG_PUTIO_CLIENT_ID"] = putio.app_id
        elif self.settings.putio_app_id:
            environment["RCLONE_CONFIG_PUTIO_CLIENT_ID"] = self.settings.putio_app_id

        if putio.client_secret:
            environment["RCLONE_CONFIG_PUTIO_CLIENT_SECRET"] = putio.client_secret
        elif self.settings.putio_client_secret:
            environment["RCLONE_CONFIG_PUTIO_CLIENT_SECRET"] = self.settings.putio_client_secret

        if putio.token is None:
            raise ValueError("Put.io token is not configured.")
        environment["RCLONE_CONFIG_PUTIO_TOKEN"] = json.dumps(putio.token.model_dump(exclude_none=True))
        return environment

    def _remote_path(self, payload: SyncPreviewRequest) -> str:
        remote_path = "putio:"
        if payload.mode == "folder" and payload.folder_path:
            cleaned_path = payload.folder_path.strip("/")
            remote_path = f"putio:{cleaned_path}"
        return remote_path
