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
- a polished frontend shell for integration setup, nested Put.io folder browsing, library-aware destination choices, sync previews, and live job logs
- a single-image Docker build that packages the built frontend with the backend
- a Proxmox LXC creation script plus macOS native and Apple container launch scripts

What is still stubbed:
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

You can run it directly on a Proxmox host without cloning this repo first.

DHCP example:

```bash
ROOT_PASSWORD='change-me' \
CTID=1870 \
HOSTNAME=get-putio \
bash -c "$(curl -fsSL https://raw.githubusercontent.com/iamichi/get-put.io/main/scripts/proxmox/create-lxc.sh)"
```

Static IP example:

```bash
ROOT_PASSWORD='change-me' \
CTID=1870 \
HOSTNAME=get-putio \
IP_CONFIG='192.168.1.50/24' \
GATEWAY='192.168.1.1' \
bash -c "$(curl -fsSL https://raw.githubusercontent.com/iamichi/get-put.io/main/scripts/proxmox/create-lxc.sh)"
```

SSH key example instead of a root password:

```bash
SSH_PUBLIC_KEY_FILE=/root/.ssh/authorized_keys \
CTID=1870 \
HOSTNAME=get-putio \
bash -c "$(curl -fsSL https://raw.githubusercontent.com/iamichi/get-put.io/main/scripts/proxmox/create-lxc.sh)"
```

The script is env-driven, not interactive:
- it does not prompt for an IP address
- if you leave `IP_CONFIG=dhcp`, it requests DHCP and then tries to detect the assigned container IP automatically
- if you set `IP_CONFIG` and `GATEWAY`, it uses that static address and derives the app URL from it
- it now defaults `APP_REPO_URL` to `https://github.com/iamichi/get-put.io.git` and deploys `main` automatically

Optional useful variables:
- `PUBLIC_URL=http://192.168.1.50:8787`
- `MEDIA_SOURCE=/mnt/pve/media`
- `MEDIA_TARGET=/srv/media`
- `APP_BRANCH=main`
- `APP_PORT=8787`

If you prefer to inspect the script first, use:

```bash
curl -fsSL https://raw.githubusercontent.com/iamichi/get-put.io/main/scripts/proxmox/create-lxc.sh -o /root/create-get-putio-lxc.sh
bash /root/create-get-putio-lxc.sh
```

If you already cloned the repo locally on the Proxmox host, you can still use:

```bash
./scripts/proxmox/create-lxc.sh
```

On success, the script prints the app URL and the Put.io redirect URI you should register for OAuth.

## Environment variables

Important variables:
- `GET_PUTIO_HOST`
- `GET_PUTIO_PORT`
- `FRONTEND_URL`
- `GET_PUTIO_STORAGE_PATH`
- `GET_PUTIO_STATE_PATH`
- `GET_PUTIO_SCHEDULE_TIMEZONE`
- `GET_PUTIO_SCHEDULER_POLL_SECONDS`
- `RCLONE_BINARY`
- `PUTIO_APP_ID`
- `PUTIO_CLIENT_SECRET`
- `PUTIO_REDIRECT_URI`
- `PUTIO_ACCESS_TOKEN`
- `JELLYFIN_BASE_URL`
- `JELLYFIN_API_KEY`

`FRONTEND_URL` controls where the Put.io OAuth callback success page sends you after login.
- Native dev should use `http://localhost:5173`
- Docker, Apple containers, and single-port deployments should usually use `http://localhost:8787`

## Recommended v1 workflow

1. Build the app as a standalone control plane.
2. Create a Put.io OAuth app and set its redirect URI to this service.
3. Use `rclone` as the transfer layer instead of custom download logic.
4. Choose a destination path, ideally a staging path or a Jellyfin library mount.
5. Save recurring jobs for your common sync lanes if you want hands-off imports.
6. Trigger a Jellyfin refresh after successful jobs if enabled.

If the browser OAuth flow is inconvenient, you can also paste the OAuth token shown on your Put.io app's Secrets page into the UI as a manual fallback.

## Next steps

- add scheduling and recurring jobs
- persist richer transfer metrics and job history
- improve Put.io folder browsing and path mapping
- add cancellation and retry flows
