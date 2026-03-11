# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

get-put.io is a self-hosted sync portal that pulls media from Put.io into local storage for Jellyfin indexing. It wraps `rclone` as the transfer engine rather than implementing custom download logic.

## Commands

### Backend development
```bash
cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

### Frontend development
```bash
cd frontend && npm install && npm run dev
```
Frontend dev server runs on port 5173 and proxies API calls to the backend at localhost:8000.

### Run both (macOS)
```bash
./scripts/macos/dev.sh
```

### Tests
```bash
cd backend && source .venv/bin/activate && pytest                # all tests
cd backend && source .venv/bin/activate && pytest tests/test_health.py  # single test
```

### Build
```bash
cd frontend && npm run build          # frontend production build (includes tsc --noEmit)
docker build -t get-putio:latest .    # full Docker image
docker compose up --build             # run with Docker Compose (serves on :8787)
```

### Makefile shortcuts
`make backend-install`, `make frontend-install`, `make dev-backend`, `make dev-frontend`, `make test`, `make build-frontend`, `make docker-build`

## Architecture

### Backend (FastAPI, Python 3.11+)
- `backend/app/main.py` — App entrypoint. Mounts API router, CORS, and serves built frontend static files from `app/static/` when present. Starts the scheduler on lifespan.
- `backend/app/config.py` — Pydantic Settings with `GET_PUTIO_` env prefix. Loads `.env` from repo root or `backend/` directory.
- `backend/app/api/routes.py` — All API routes under `/api`. Covers dashboard, Put.io OAuth + browsing, Jellyfin integration, job CRUD, and schedule management.
- `backend/app/api/schemas.py` — Pydantic request/response models for the API.
- `backend/app/models/state.py` — `AppState` model. All persistent state lives in a single JSON file (`state.json`).
- `backend/app/services/state.py` — `StateStore` with snapshot/mutate pattern for thread-safe JSON state access.
- `backend/app/services/putio.py` — Put.io OAuth flows and `rclone`-based file browsing.
- `backend/app/services/rclone.py` — Subprocess wrapper around the `rclone` binary for copy/sync operations.
- `backend/app/services/jellyfin.py` — Jellyfin HTTP API client for library listing and refresh triggers.
- `backend/app/services/jobs.py` — Job lifecycle: preview, start (spawns rclone), cancel, and optional post-sync Jellyfin refresh.
- `backend/app/services/scheduler.py` — Polling-based recurring job scheduler.

### Frontend (React + Vite + TypeScript)
- `frontend/src/App.tsx` — Single-page app root.
- `frontend/src/lib/api.ts` — API client functions calling the backend.
- All UI is plain React with no component library.

### State model
There is no database. All app state (settings, jobs, schedules) is persisted to a single JSON file via `StateStore`. The mutate pattern (read → modify → write) handles concurrency.

### Deployment
- Docker: multi-stage build (Node for frontend, Python for runtime with rclone). Serves on port 8000 internally, mapped to 8787 in compose.
- Proxmox: `scripts/proxmox/create-lxc.sh` bootstraps a Debian 12 LXC with Docker.
- macOS: native dev without containers is the default.

## Key conventions

- All API routes are prefixed with `/api`.
- Settings use `GET_PUTIO_` env prefix; Put.io and Jellyfin settings use their own prefixes (see `.env.example`).
- The frontend build output goes to `frontend/dist/`, which Docker copies into `backend/app/static/` for single-binary serving.
- Prefer `rclone` for all Put.io transfer operations.
- Treat Jellyfin as an external system — use its HTTP API, don't rely on filesystem side effects.
- Stage files before moving into Jellyfin library paths; don't expose partial downloads.
