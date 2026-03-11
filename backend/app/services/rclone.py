from pathlib import Path

from app.api.schemas import SyncPreviewRequest, SyncPreviewResponse
from app.config import Settings


class RcloneService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def preview(self, payload: SyncPreviewRequest) -> SyncPreviewResponse:
        remote_path = "putio:"
        if payload.mode == "folder" and payload.folder_path:
            cleaned_path = payload.folder_path.strip("/")
            remote_path = f"putio:{cleaned_path}"

        destination = Path(payload.destination_path).expanduser()
        command = f"rclone copy {remote_path} {destination}"

        warnings: list[str] = []
        if destination == self.settings.storage_path:
            warnings.append(
                "Destination matches the primary library root. Consider a staging directory first."
            )
        if payload.mode == "folder" and not payload.folder_path:
            warnings.append("Folder mode needs a Put.io folder path.")

        return SyncPreviewResponse(
            title="Sync preview",
            command_preview=command,
            steps=[
                "Resolve the selected Put.io scope into an rclone remote path.",
                "Copy files into the selected local destination.",
                "Move or promote completed files into the Jellyfin library path.",
                "Trigger a Jellyfin refresh after the transfer succeeds.",
            ],
            warnings=warnings,
        )

