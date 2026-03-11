from app.api.schemas import ConnectionStatus, FolderNode
from app.config import Settings


class PutioService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def connection_status(self) -> ConnectionStatus:
        connected = bool(self.settings.putio_access_token or self.settings.putio_app_id)
        summary = (
            "OAuth app or token configured."
            if connected
            else "No Put.io credentials configured yet."
        )
        return ConnectionStatus(service="Put.io", connected=connected, summary=summary)

    def list_folders(self) -> list[FolderNode]:
        # Placeholder data for the first UI pass. Replace with real API calls.
        return [
            FolderNode(id="root", name="Everything", path="/", child_count=3),
            FolderNode(id="movies", name="Movies", path="/Movies", child_count=124),
            FolderNode(id="series", name="Series", path="/Series", child_count=42),
        ]

