from app.api.schemas import ConnectionStatus
from app.config import Settings


class JellyfinService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def connection_status(self) -> ConnectionStatus:
        connected = bool(self.settings.jellyfin_base_url and self.settings.jellyfin_api_key)
        summary = (
            "Base URL and API key configured."
            if connected
            else "Jellyfin connection not configured yet."
        )
        return ConnectionStatus(service="Jellyfin", connected=connected, summary=summary)

