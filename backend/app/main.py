from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import get_settings
from app.services.scheduler import get_scheduler_service

settings = get_settings()


def resolve_static_asset(static_root: Path, full_path: str) -> Path | None:
    candidate = (static_root / Path(full_path)).resolve()
    resolved_root = static_root.resolve()
    if candidate.is_relative_to(resolved_root) and candidate.exists() and candidate.is_file():
        return candidate
    return None


@asynccontextmanager
async def lifespan(_: FastAPI):
    scheduler = get_scheduler_service()
    scheduler.start()
    try:
        yield
    finally:
        scheduler.stop()


app = FastAPI(title=settings.product_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url.rstrip("/"),
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8787",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

static_dir = settings.frontend_dist
if static_dir.exists():
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def frontend_root() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    def frontend_catch_all(full_path: str) -> FileResponse:
        candidate = resolve_static_asset(static_dir, full_path)
        if candidate is not None:
            return FileResponse(candidate)
        return FileResponse(static_dir / "index.html")
