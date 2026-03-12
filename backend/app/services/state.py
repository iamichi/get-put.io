from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Callable, TypeVar
from urllib.parse import urlparse

from app.config import Settings, get_settings
from app.models.state import AppState

T = TypeVar("T")
LEGACY_NATIVE_REDIRECT_URI = "http://localhost:8000/api/auth/putio/callback"
CALLBACK_PATH = "/api/auth/putio/callback"


class StateStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path = settings.state_path
        self.lock = RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        self._state = self._load()

    def _load(self) -> AppState:
        if not self.path.exists():
            state = AppState.create_default()
            self._apply_runtime_defaults(state)
            self._save(state)
            return state

        os.chmod(self.path, 0o600)
        raw = json.loads(self.path.read_text())
        state = AppState.model_validate(raw)
        self._apply_runtime_defaults(state)
        return state

    def _apply_runtime_defaults(self, state: AppState) -> None:
        redirect_uri = state.settings.putio.redirect_uri.strip()
        configured_redirect_uri = self.settings.putio_redirect_uri.strip()
        frontend_url = self.settings.frontend_url.strip()
        frontend_parsed = urlparse(frontend_url) if frontend_url else None
        redirect_parsed = urlparse(redirect_uri) if redirect_uri else None
        should_replace_with_configured_redirect = not redirect_uri or (
            redirect_uri == LEGACY_NATIVE_REDIRECT_URI
            and configured_redirect_uri
            and configured_redirect_uri != LEGACY_NATIVE_REDIRECT_URI
        )

        if (
            redirect_parsed
            and frontend_parsed
            and frontend_parsed.hostname
            and frontend_parsed.port
            and redirect_parsed.path == CALLBACK_PATH
            and redirect_parsed.hostname == frontend_parsed.hostname
            and redirect_parsed.port != frontend_parsed.port
        ):
            should_replace_with_configured_redirect = True

        if should_replace_with_configured_redirect:
            state.settings.putio.redirect_uri = configured_redirect_uri or LEGACY_NATIVE_REDIRECT_URI

    def _save(self, state: AppState) -> None:
        state.touch()
        payload = state.model_dump_json(indent=2).encode()
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
        finally:
            os.chmod(self.path, 0o600)

    def snapshot(self) -> AppState:
        with self.lock:
            return self._state.model_copy(deep=True)

    def mutate(self, fn: Callable[[AppState], T]) -> T:
        with self.lock:
            result = fn(self._state)
            self._save(self._state)
            return result


@lru_cache(maxsize=1)
def get_state_store() -> StateStore:
    return StateStore(get_settings())
