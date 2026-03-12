# get-put.io

`get-put.io` is a self-hosted web app for pulling media from Put.io into local storage, optionally refreshing Jellyfin after syncs, and cleaning up old local files when disk space gets tight.

## What It Does

- connect to Put.io with OAuth or a pasted token
- sync either everything or one selected Put.io folder
- keep local files, or mirror deletions from Put.io
- trigger Jellyfin refreshes after successful syncs
- schedule recurring syncs
- preview and run local storage cleanup

## Before You Start

You need:

- a machine to run `get-put.io`
- a destination path for downloaded media
- `rclone`
- a Put.io OAuth app or a Put.io OAuth token

If you want Jellyfin integration, you also need:

- the Jellyfin server URL
- a Jellyfin API key

## Installation

Choose one of these:

- Proxmox LXC
- Apple Container CLI
- Docker Compose
- Local host

### Proxmox LXC

Run this on the Proxmox host.

Fast path (interactive prompts, one command):

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/iamichi/get-put.io/main/scripts/proxmox/create-lxc.sh)"
```

What the script does automatically:

- picks a default `CTID` (next available ID)
- prompts for hostname/network/auth if not provided
- can prompt for a host media path to mount into the LXC
- discovers a Debian 12 template and downloads it if missing
- deploys Docker + `get-put.io` inside the new LXC

If you prefer non-interactive mode, pass env vars:

```bash
ROOT_PASSWORD='change-me' \
CTID=1870 \
CT_HOSTNAME=get-putio \
IP_CONFIG='192.168.1.50/24' \
GATEWAY='192.168.1.1' \
bash -c "$(curl -fsSL https://raw.githubusercontent.com/iamichi/get-put.io/main/scripts/proxmox/create-lxc.sh)"
```

Useful optional variables:

- `ROOT_PASSWORD=...`
- `SSH_PUBLIC_KEY_FILE=/root/.ssh/authorized_keys`
- `MEDIA_SOURCE=/path/on/proxmox/media`
- `MEDIA_TARGET=/media`
- `APPLY_MEDIA_ACL=auto`
- `MEDIA_WRITE_UID=100000`
- `PUBLIC_URL=http://192.168.1.50:8787`
- `APP_PORT=8787`
- `APP_BRANCH=main`
- `TEMPLATE=local:vztmpl/debian-12-standard_<version>_amd64.tar.zst`
- `TEMPLATE_STORAGE=local`

When the script finishes it prints:

- the app URL
- the Put.io callback URL

If Jellyfin already has media mounted in Proxmox, `get-put.io` should use the same host path and the same container mount point.

Example:

- Jellyfin LXC mount: `/path/on/proxmox/media,mp=/media`
- `get-put.io` LXC mount: `/path/on/proxmox/media,mp=/media`
- Docker bind source inside `get-put.io`: `/media`
- then a sync destination like `/media/movies` writes to the shared media drive, not the LXC root disk

Important:

- if `MEDIA_SOURCE` is set and `get-put.io` is created as an unprivileged LXC, the installer applies write ACLs for the mapped container UID by default
- set `APPLY_MEDIA_ACL=0` if you want to handle permissions yourself
- if `get-put.io` is created as an unprivileged LXC, container root maps to host UID/GID `100000`
- that means the mounted host path must be writable by that mapped UID/GID, or syncs will fail with `permission denied`
- using the same mount as Jellyfin is not enough if Jellyfin is running with different privilege mode or different host-side permissions

To compare privilege mode:

```bash
pct config <jellyfin-ctid> | grep '^unprivileged'
pct config <CTID> | grep '^unprivileged'
```

To inspect the host path permissions:

```bash
ls -ld /path/on/proxmox/media /path/on/proxmox/media/<library-subdir>
```

Two practical fixes:

- let the installer apply ACLs automatically for UID/GID `100000`, or grant them yourself later
- or recreate `get-put.io` with `UNPRIVILEGED=0` if you want it to behave more like a privileged media container

To see how Jellyfin is mounted on the Proxmox host:

```bash
pct config <jellyfin-ctid> | grep '^mp'
```

To get into the `get-put.io` container after creation:

```bash
pct enter <CTID>
```

Useful checks inside the LXC:

```bash
df -h /media /media/movies
cd /opt/get-putio
grep '^MEDIA_BIND_SOURCE=' .env
docker compose ps
docker compose logs --tail=100
```

### Apple Container CLI

If you are using Apple’s `container` CLI on macOS:

```bash
cp .env.example .env
./scripts/macos/run-apple-container.sh
```

This starts the app on [http://127.0.0.1:8787](http://127.0.0.1:8787) and mounts:

- `./data/app` to `/app/data`
- `./data/media` to `/media`

If you want a different URL or storage path, update `.env` first.

### Docker Compose

```bash
cp .env.example .env
mkdir -p data/app data/media
docker compose up -d --build
```

Then open [http://localhost:8787](http://localhost:8787).

Default container paths:

- app state: `./data/app`
- media: `./data/media`

### Local Host

Install:

- `python3`
- `npm`
- `rclone`

On macOS:

```bash
brew install rclone
```

Fastest local start:

```bash
./scripts/macos/dev.sh
```

This runs:

- backend on `http://localhost:8000`
- frontend on `http://localhost:5173`

Manual local start:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

## Configuration

Review `.env.example` before first use.

The main settings are:

- `FRONTEND_URL`
- `PUTIO_REDIRECT_URI`
- `GET_PUTIO_STORAGE_PATH`
- `GET_PUTIO_STATE_PATH`
- `GET_PUTIO_SCHEDULE_TIMEZONE`

Typical local values:

```dotenv
FRONTEND_URL=http://localhost:5173
PUTIO_REDIRECT_URI=http://localhost:8000/api/auth/putio/callback
GET_PUTIO_STORAGE_PATH=/absolute/path/to/media
GET_PUTIO_STATE_PATH=/absolute/path/to/state.json
GET_PUTIO_SCHEDULE_TIMEZONE=Europe/Lisbon
```

Typical container values:

```dotenv
FRONTEND_URL=http://localhost:8787
PUTIO_REDIRECT_URI=http://localhost:8787/api/auth/putio/callback
GET_PUTIO_STORAGE_PATH=/media
GET_PUTIO_STATE_PATH=/app/data/state.json
```

`GET_PUTIO_STORAGE_PATH` is important:

- sync destinations must stay inside this storage root
- cleanup only deletes files inside this storage root

## Put.io Setup

Open the app and go to `Put.io`.

Enter:

- Put.io client ID
- Put.io client secret
- OAuth redirect URI

Then save the settings and create your Put.io app at [https://app.put.io/oauth/new](https://app.put.io/oauth/new).

The callback URL in Put.io must exactly match the redirect URI configured in `get-put.io`.

Common callback URLs:

- native host: `http://localhost:8000/api/auth/putio/callback`
- container install: `http://localhost:8787/api/auth/putio/callback`
- LAN or Proxmox install: `http://<host-or-ip>:8787/api/auth/putio/callback`

If you already have a Put.io OAuth token, you can paste that into the manual token field instead of using the browser login flow.

## Jellyfin Setup

Open the `Jellyfin` tab and enter:

- Jellyfin base URL
- Jellyfin API key

Then:

- enable Jellyfin integration if you want refresh hooks
- test the connection
- choose whether Jellyfin should refresh after syncs

## Running Syncs

Open the `Sync` tab and choose:

- `Everything`
- `Specific folder`

Then set:

- the Put.io path
- the local destination path
- the deletion policy

Deletion policy:

- `Keep local files`
  Files removed from Put.io stay on disk locally.
- `Mirror Put.io deletions`
  Local files are removed when they disappear from Put.io. This is destructive.

The destination path must be a full local path on the machine running `get-put.io`, and it must stay inside `GET_PUTIO_STORAGE_PATH`.

Use `Run sync now` for a one-off job, or save the current sync selection as a recurring job in `Jobs`.

## Recurring Jobs

Open the `Jobs` tab to create or edit recurring syncs.

A recurring job stores:

- sync scope
- Put.io path
- destination path
- deletion policy
- schedule

Supported schedule types:

- `daily`
- `interval`

## Storage Cleanup

Open the `Storage` tab to manage local cleanup separately from Put.io sync behavior.

Cleanup can be configured with:

- enabled or disabled
- free-space threshold
- free-space target
- minimum file age
- excluded paths
- optional cleanup schedule

Cleanup behavior:

- it only touches files inside `GET_PUTIO_STORAGE_PATH`
- it is independent of Put.io deletion mirroring
- it works oldest-first
- it supports preview before deletion

## Where Data Lives

Default container paths:

- state file: `./data/app/state.json`
- media: `./data/media`

The state file stores:

- app settings
- Put.io connection state
- Jellyfin settings
- sync history
- recurring schedules
- cleanup history

## Troubleshooting

`Invalid redirect_uri`

- the Put.io app callback URL does not exactly match the redirect URI configured in `get-put.io`

Jellyfin test fails

- check the base URL
- check the API key
- confirm the Jellyfin server is reachable from the machine running `get-put.io`

Sync cannot start

- confirm `rclone` is installed
- confirm the destination path is inside `GET_PUTIO_STORAGE_PATH`
- confirm Put.io is connected
- if you are using Proxmox LXC, confirm the host media path is mounted into the container at `/media`

Sync fails with `no space left on device`

- this usually means the destination path is writing into the LXC root disk, not your shared media mount
- in Proxmox, check the mount points with `pct config <CTID> | grep '^mp'`
- inside the container, check `df -h /media /media/movies`
- inside `/opt/get-putio/.env`, confirm `MEDIA_BIND_SOURCE=/media`
- if Jellyfin already uses `/media`, mount the same host path into `get-put.io` at `/media`

## License

MIT. See [LICENSE](LICENSE).
