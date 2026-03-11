from __future__ import annotations

import secrets
from urllib.parse import urlencode

import httpx

from app.api.schemas import ConnectionStatus, FolderNode
from app.config import Settings
from app.models.state import AppState, PutioToken


AUTH_URL = "https://api.put.io/v2/oauth2/authenticate"
TOKEN_URL = "https://api.put.io/v2/oauth2/access_token"
VALIDATE_URL = "https://api.put.io/v2/oauth2/validate"
ACCOUNT_INFO_URL = "https://api.put.io/v2/account/info"
LIST_FILES_URL = "https://api.put.io/v2/files/list"
CONTINUE_LIST_URL = "https://api.put.io/v2/files/list/continue"


class PutioService:
    def __init__(self, settings: Settings, state: AppState) -> None:
        self.settings = settings
        self.state = state

    def connection_status(self) -> ConnectionStatus:
        connected = self.state.settings.putio.token is not None
        summary = (
            f"Connected as {self.state.settings.putio.account_username}."
            if connected
            else "No Put.io session configured yet."
        )
        return ConnectionStatus(service="Put.io", connected=connected, summary=summary)

    def build_auth_url(self) -> tuple[str, str]:
        app_id = self.state.settings.putio.app_id or self.settings.putio_app_id
        redirect_uri = self.state.settings.putio.redirect_uri or self.settings.putio_redirect_uri
        if not app_id:
            raise ValueError("Put.io app ID is not configured.")

        oauth_state = secrets.token_urlsafe(24)
        query = urlencode(
            {
                "client_id": app_id,
                "response_type": "code",
                "redirect_uri": redirect_uri,
                "state": oauth_state,
            }
        )
        return f"{AUTH_URL}?{query}", oauth_state

    def exchange_code(self, code: str) -> PutioToken:
        app_id = self.state.settings.putio.app_id or self.settings.putio_app_id
        client_secret = self.state.settings.putio.client_secret or self.settings.putio_client_secret
        redirect_uri = self.state.settings.putio.redirect_uri or self.settings.putio_redirect_uri
        if not app_id or not client_secret:
            raise ValueError("Put.io app credentials are missing.")

        response = httpx.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": app_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
            },
            timeout=30,
        )
        response.raise_for_status()
        return PutioToken.model_validate(response.json())

    def fetch_account(self, token: PutioToken) -> tuple[int | None, str | None]:
        headers = {"Authorization": f"Bearer {token.access_token}"}
        validate = httpx.get(VALIDATE_URL, headers=headers, timeout=30)
        validate.raise_for_status()
        user_id = validate.json().get("user_id")

        info = httpx.get(ACCOUNT_INFO_URL, headers=headers, timeout=30)
        info.raise_for_status()
        username = info.json().get("info", {}).get("username")
        return user_id, username

    def list_folders(self, parent_id: int = 0) -> list[FolderNode]:
        token = self.state.settings.putio.token
        if token is None:
            return []

        headers = {"Authorization": f"Bearer {token.access_token}"}
        try:
            response = httpx.get(
                LIST_FILES_URL,
                params={"parent_id": parent_id, "per_page": 1000},
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            files = payload.get("files", [])
            cursor = payload.get("cursor")
            while cursor:
                next_response = httpx.post(
                    CONTINUE_LIST_URL,
                    json={"cursor": cursor},
                    headers=headers,
                    timeout=30,
                )
                next_response.raise_for_status()
                next_payload = next_response.json()
                files.extend(next_payload.get("files", []))
                cursor = next_payload.get("cursor")
        except httpx.HTTPError:
            return []

        folders: list[FolderNode] = [FolderNode(id="root", name="Everything", path="/", child_count=0)]
        for item in files:
            if item.get("content_type") != "application/x-directory":
                continue
            folders.append(
                FolderNode(
                    id=str(item["id"]),
                    name=item["name"],
                    path=f"/{item['name']}",
                    child_count=0,
                )
            )
        return folders
