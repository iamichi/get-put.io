from __future__ import annotations

from pathlib import Path

from app.api.schemas import BreadcrumbNode, FolderNode, PutioBrowserResponse


class FilesystemBrowserService:
    def browse_path(self, path: str | None = None) -> PutioBrowserResponse:
        normalized = self._resolve_existing_directory(path)
        entries: list[FolderNode] = []

        try:
            directories = sorted(
                (item for item in normalized.iterdir() if item.is_dir()),
                key=lambda item: item.name.lower(),
            )
        except OSError as exc:
            raise ValueError(f"Unable to browse local path: {normalized}") from exc

        for item in directories:
            entries.append(
                FolderNode(
                    id=str(item),
                    name=item.name or str(item),
                    path=str(item),
                    child_count=0,
                )
            )

        breadcrumbs = [BreadcrumbNode(name="/", path="/")]
        current = Path("/")
        for part in normalized.parts[1:]:
            current = current / part
            breadcrumbs.append(BreadcrumbNode(name=part, path=str(current)))

        parent_path = str(normalized.parent) if normalized != normalized.parent else None
        return PutioBrowserResponse(
            current_path=str(normalized),
            parent_path=parent_path,
            breadcrumbs=breadcrumbs,
            entries=entries,
        )

    def _resolve_existing_directory(self, path: str | None) -> Path:
        candidate = Path(path or Path.home()).expanduser()
        if candidate.exists() and candidate.is_dir():
            return candidate.resolve()

        fallback = candidate
        while not fallback.exists() and fallback != fallback.parent:
            fallback = fallback.parent
        if fallback.exists() and fallback.is_dir():
            return fallback.resolve()
        return Path.home().resolve()
