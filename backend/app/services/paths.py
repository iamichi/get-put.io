from __future__ import annotations

from pathlib import Path

from app.config import Settings


def normalize_destination_path(settings: Settings, destination_path: str) -> str:
    candidate = Path(destination_path).expanduser().resolve(strict=False)
    storage_root = settings.storage_path.expanduser().resolve(strict=False)
    if not candidate.is_relative_to(storage_root):
        raise ValueError("Destination must be inside the configured storage root.")
    return str(candidate)
