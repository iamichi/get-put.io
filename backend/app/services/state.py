from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Callable, TypeVar

from app.config import Settings, get_settings
from app.models.state import AppState

T = TypeVar("T")


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
            self._save(state)
            return state

        os.chmod(self.path, 0o600)
        raw = json.loads(self.path.read_text())
        return AppState.model_validate(raw)

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
