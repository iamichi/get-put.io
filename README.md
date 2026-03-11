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
- a FastAPI backend with persisted settings, Put.io OAuth, runnable `rclone` jobs, and a Jellyfin refresh hook
- a polished frontend shell for integration setup, sync previews, and live job logs
- a single-image Docker build that packages the built frontend with the backend
- a Proxmox LXC creation script plus macOS native and Apple container launch scripts

What is still stubbed:
- recurring job scheduling
- deeper Put.io folder browsing beyond the root level
- cancellation, retries, and richer transfer metrics
- multi-user auth and permissions

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

For real sync jobs on macOS, install `rclone` too:

```bash
brew install rclone
```

## Quick start: macOS helper

If you want the native two-process workflow on macOS, use:

```bash
./scripts/macos/dev.sh
```

This script creates a Python virtualenv if needed, installs backend dependencies, and starts both the API and Vite dev server.

## macOS containers

This repo supports macOS without containers, which is the default recommendation for local development. If you prefer containers on macOS, use a broadly supported runtime such as Docker Desktop, OrbStack, or Colima.

Apple's `container` CLI can also run this project if you are on Apple silicon with macOS 26 and have installed the tool and started its system service.

Quick path:

```bash
cp .env.example .env
./scripts/macos/run-apple-container.sh
```

That script:
- builds the image from this repo's `Dockerfile`
- mounts `./data/app` into `/app/data`
- mounts `./data/media` into `/media`
- publishes the app on `http://127.0.0.1:8787`

Manual Apple container flow:

```bash
container system start
container build --tag get-putio:local --file ./Dockerfile .
container run -d \
  --name get-putio \
  --publish 127.0.0.1:8787:8000 \
  --env-file ./.env \
  --volume "$(pwd)/data/app:/app/data" \
  --volume "$(pwd)/data/media:/media" \
  get-putio:local
```

Official references:
- [Apple container README](https://github.com/apple/container)
- [Apple container how-to](https://github.com/apple/container/blob/main/docs/how-to.md)
- [Apple container command reference](https://github.com/apple/container/blob/main/docs/command-reference.md)

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
- `GET_PUTIO_STATE_PATH`
- `RCLONE_BINARY`
- `PUTIO_APP_ID`
- `PUTIO_CLIENT_SECRET`
- `PUTIO_REDIRECT_URI`
- `PUTIO_ACCESS_TOKEN`
- `JELLYFIN_BASE_URL`
- `JELLYFIN_API_KEY`

## Recommended v1 workflow

1. Build the app as a standalone control plane.
2. Create a Put.io OAuth app and set its redirect URI to this service.
3. Use `rclone` as the transfer layer instead of custom download logic.
4. Choose a destination path, ideally a staging path or a Jellyfin library mount.
5. Trigger a Jellyfin refresh after successful jobs if enabled.

## Next steps

- add scheduling and recurring jobs
- persist richer transfer metrics and job history
- improve Put.io folder browsing and path mapping
- add cancellation and retry flows
