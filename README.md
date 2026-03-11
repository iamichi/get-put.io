# get-put.io

`get-put.io` is a self-hosted sync portal for pulling media from Put.io into local storage that Jellyfin can index. The first version focuses on a clean operator workflow: connect Put.io, choose `all files` or a specific folder, pick a destination path, run or schedule transfers, and trigger a Jellyfin library refresh.

## Why this shape

This project intentionally starts as an external service instead of a Jellyfin plugin:
- Put.io auth and transfer logic fit better in a standalone app than inside Jellyfin's plugin lifecycle.
- `rclone` already provides a battle-tested Put.io backend, resumable transfers, and folder-scoped copy/sync.
- Jellyfin can be refreshed through its HTTP API, so the app does not need to live inside the media server.
- Proxmox LXC keeps the deployment lightweight while still giving you isolation and snapshot-friendly operations.

## Stack

- Backend: FastAPI
- Frontend: React + Vite + TypeScript
- Transfer engine: `rclone`
- Media server integration: Jellyfin HTTP API
- Deployment: Docker Compose, with a Proxmox LXC bootstrap script
- Local development: native macOS or Linux

## Repo layout

```text
.
├── AGENTS.md
├── README.md
├── Makefile
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── pyproject.toml
│   ├── app/
│   └── tests/
├── frontend/
│   ├── package.json
│   └── src/
├── scripts/
│   ├── macos/
│   └── proxmox/
└── docs/
```

## Current scaffold status

This initial repo includes:
- a FastAPI API skeleton with service boundaries for Put.io, `rclone`, and Jellyfin
- a polished frontend shell with dashboard-like controls and API-backed sync preview
- a single-image Docker build that packages the built frontend with the backend
- a Proxmox LXC creation script and a macOS local development script

What is still stubbed:
- full Put.io OAuth flow
- persisted job queue and scheduler
- actual `rclone` execution and progress streaming
- Jellyfin authentication and library refresh calls

## Quick start: native development

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend expects the backend at `http://localhost:8000` by default.

## Quick start: macOS helper

If you want the native two-process workflow on macOS, use:

```bash
./scripts/macos/dev.sh
```

This script creates a Python virtualenv if needed, installs backend dependencies, and starts both the API and Vite dev server.

## macOS containers

This repo supports macOS without containers, which is the default recommendation for local development. If you prefer containers on macOS, use a broadly supported runtime such as Docker Desktop, OrbStack, or Colima.

Apple's newer `container` tooling can be explored as an optional path on Apple silicon Macs running macOS 26, but it is not the primary workflow for this repo yet.

## Quick start: Docker

Copy the example environment file and adjust it:

```bash
cp .env.example .env
docker compose up --build
```

The app will be available at `http://localhost:8787`.

## Proxmox LXC

The Proxmox bootstrap flow is split into two concerns:
- create a Debian 12 LXC with the right nesting and mount options
- install Docker and launch `get-put.io` inside that container

Start with:

```bash
./scripts/proxmox/create-lxc.sh
```

The script is environment-driven. Read the header comments before running it on a Proxmox host.

## Environment variables

Important variables:
- `GET_PUTIO_HOST`
- `GET_PUTIO_PORT`
- `GET_PUTIO_STORAGE_PATH`
- `PUTIO_APP_ID`
- `PUTIO_CLIENT_SECRET`
- `PUTIO_REDIRECT_URI`
- `PUTIO_ACCESS_TOKEN`
- `JELLYFIN_BASE_URL`
- `JELLYFIN_API_KEY`

## Recommended v1 workflow

1. Build the app as a standalone control plane.
2. Use `rclone` as the transfer layer instead of custom download logic.
3. Download into a staging path.
4. Move completed media into the Jellyfin library path.
5. Trigger a Jellyfin refresh after successful jobs.

## Next steps

- implement Put.io OAuth callback handling
- store connection state and sync jobs in SQLite
- wrap `rclone` execution with job lifecycle tracking
- add a scheduling UI and background worker
- wire Jellyfin refresh and path mapping rules
