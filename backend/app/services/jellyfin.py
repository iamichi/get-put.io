from __future__ import annotations

import ipaddress

import httpx
from urllib.parse import urlparse

from app.api.schemas import ConnectionStatus, JellyfinLibrary
from app.config import Settings
from app.models.state import AppState


class JellyfinService:
    def __init__(self, settings: Settings, state: AppState) -> None:
        self.settings = settings
        self.state = state

    def connection_status(self) -> ConnectionStatus:
        jellyfin = self.state.settings.jellyfin
        connected = jellyfin.enabled and bool(jellyfin.base_url and jellyfin.api_key)
        summary = (
            "Base URL and API key configured."
            if connected
            else "Jellyfin integration disabled or incomplete."
        )
        return ConnectionStatus(service="Jellyfin", connected=connected, summary=summary)

    def test_connection(self) -> str:
        jellyfin = self.state.settings.jellyfin
        if not jellyfin.base_url or not jellyfin.api_key:
            raise ValueError("Jellyfin base URL and API key are required.")
        self.validate_base_url(jellyfin.base_url)

        response = httpx.get(
            f"{jellyfin.base_url.rstrip('/')}/System/Info",
            headers=self._headers(jellyfin.api_key),
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("ServerName", "Jellyfin")

    def refresh_library(self) -> None:
        jellyfin = self.state.settings.jellyfin
        if not jellyfin.enabled:
            return
        if not jellyfin.base_url or not jellyfin.api_key:
            raise ValueError("Jellyfin base URL and API key are required.")
        self.validate_base_url(jellyfin.base_url)

        response = httpx.post(
            f"{jellyfin.base_url.rstrip('/')}/Library/Refresh",
            headers=self._headers(jellyfin.api_key),
            timeout=60,
        )
        response.raise_for_status()

    def list_libraries(self) -> list[JellyfinLibrary]:
        jellyfin = self.state.settings.jellyfin
        if not jellyfin.base_url or not jellyfin.api_key:
            return []
        self.validate_base_url(jellyfin.base_url)

        response = httpx.get(
            f"{jellyfin.base_url.rstrip('/')}/Library/VirtualFolders",
            headers=self._headers(jellyfin.api_key),
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        libraries: list[JellyfinLibrary] = []
        for item in payload:
            item_id = item.get("ItemId")
            if not item_id:
                continue
            libraries.append(
                JellyfinLibrary(
                    id=item_id,
                    name=item.get("Name") or "Unnamed library",
                    collection_type=item.get("CollectionType"),
                    locations=item.get("Locations") or [],
                    refresh_status=item.get("RefreshStatus"),
                )
            )
        return libraries

    @staticmethod
    def _headers(api_key: str) -> dict[str, str]:
        return {
            "Authorization": f'MediaBrowser Token="{api_key}"',
            "X-Emby-Token": api_key,
        }

    @staticmethod
    def validate_base_url(base_url: str) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Invalid Jellyfin URL.")
        if parsed.username or parsed.password:
            raise ValueError("Jellyfin URL must not include embedded credentials.")
        host = parsed.hostname
        if host is None:
            raise ValueError("Invalid Jellyfin URL.")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return
        if address.is_link_local or address.is_multicast or address.is_reserved or address.is_unspecified:
            raise ValueError("Jellyfin URL must point to a unicast host.")
