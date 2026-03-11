# get-put.io

`get-put.io` is a self-hosted web app for pulling media from Put.io into local storage and refreshing Jellyfin after successful syncs. It supports:

- Put.io OAuth or manual token entry
- syncing all of Put.io or a specific folder
- recurring sync schedules
- two sync deletion policies:
  - `Keep local files`
  - `Mirror Put.io deletions`
- optional local storage cleanup when free space gets low

## Install options

You can run `get-put.io` in three practical ways:

- Proxmox LXC
- containers on macOS or Linux
- directly on the local host

The default container port is `8787`.

## Proxmox LXC

Run the bootstrap script on a Proxmox host. It creates a Debian 12 LXC, installs Docker in that container, clones this repo, writes `.env`, and starts `get-put.io`.

`CTID` is the Proxmox container ID. It must be a unique numeric ID on that Proxmox node because Proxmox uses it to create and manage the LXC. If `1870` is already in use, choose another unused ID.

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

SSH key example:

```bash
SSH_PUBLIC_KEY_FILE=/root/.ssh/authorized_keys \
CTID=1870 \
HOSTNAME=get-putio \
bash -c "$(curl -fsSL https://raw.githubusercontent.com/iamichi/get-put.io/main/scripts/proxmox/create-lxc.sh)"
```

Useful optional variables:

- `PUBLIC_URL=http://192.168.1.50:8787`
- `MEDIA_SOURCE=/mnt/pve/media`
- `MEDIA_TARGET=/srv/media`
- `APP_PORT=8787`
- `APP_BRANCH=main`

When the script finishes it prints:

- the dashboard URL
- the Put.io callback URL you should register

## Docker Compose

This is the simplest container install outside Proxmox.

```bash
cp .env.example .env
mkdir -p data/app data/media
docker compose up -d --build
```

Then open [http://localhost:8787](http://localhost:8787).

Persistent data:

- app state: `./data/app`
- synced media: `./data/media`

If you will open the app from another host or another port, update `FRONTEND_URL` and `PUTIO_REDIRECT_URI` in `.env` before the first Put.io login.

## Apple container CLI

If you use Apple’s `container` CLI on Apple silicon:

```bash
cp .env.example .env
./scripts/macos/run-apple-container.sh
```

That script:

- builds the image from this repo
- mounts `./data/app` into `/app/data`
- mounts `./data/media` into `/media`
- publishes the app on [http://127.0.0.1:8787](http://127.0.0.1:8787)

## Local host run

Install these first:

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

That starts the backend on `http://localhost:8000` and the frontend on `http://localhost:5173`.

If you want to start them manually:

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

## Required configuration

Review `.env.example` before first run.

Important values:

- `FRONTEND_URL`
- `PUTIO_REDIRECT_URI`
- `GET_PUTIO_STORAGE_PATH`
- `GET_PUTIO_STATE_PATH`
- `GET_PUTIO_SCHEDULE_TIMEZONE`

Optional bootstrap values:

- `PUTIO_APP_ID`
- `PUTIO_CLIENT_SECRET`
- `PUTIO_ACCESS_TOKEN`
- `JELLYFIN_BASE_URL`
- `JELLYFIN_API_KEY`

Typical native-host values:

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

## Connect Put.io

1. Open the dashboard.
2. Go to `Put.io`.
3. Enter your Put.io client ID, client secret, and redirect URI.
4. Save the settings.
5. Create the OAuth app in Put.io at [https://app.put.io/oauth/new](https://app.put.io/oauth/new).
6. Register the callback URL that exactly matches your deployment.
7. Click `Start Put.io login`.

Common callback URLs:

- native host: `http://localhost:8000/api/auth/putio/callback`
- default container install: `http://localhost:8787/api/auth/putio/callback`
- Proxmox or LAN install: `http://<host-or-ip>:8787/api/auth/putio/callback`

If you already have a Put.io OAuth token, you can paste it into the manual token field instead of using the browser login flow.

## Connect Jellyfin

1. Go to `Jellyfin`.
2. Enable Jellyfin integration.
3. Enter the Jellyfin base URL and API key.
4. Test the connection.
5. Optionally pick Jellyfin library locations to reuse as sync destinations.
6. Choose whether Jellyfin should refresh after every sync or only when files changed.

Use a normal `http://` or `https://` Jellyfin URL without embedded credentials.

## Use sync

Go to `Sync` and choose:

- `Specific folder`
- `Everything`

Then set:

- the Put.io path
- the local destination path
- the deletion policy

Deletion policies:

- `Keep local files`
  Local files stay on disk even if they disappear from Put.io.
- `Mirror Put.io deletions`
  Local files missing from Put.io are also deleted locally. This is destructive.

Then click `Run sync now`, or save that selection as a recurring job in `Jobs`.

## Use storage cleanup

Go to `Storage` to configure local cleanup separately from Put.io sync mirroring.

Cleanup settings include:

- enable or disable cleanup
- run when free space drops below a chosen free-space percentage
- reclaim up to a higher target free-space percentage
- minimum file age before a file becomes eligible
- excluded paths
- optional cleanup schedule

Cleanup behavior:

- cleanup is independent from Put.io deletions
- it deletes the oldest eligible local files first
- it only targets files under `GET_PUTIO_STORAGE_PATH`
- you can preview the cleanup plan before running it

## Use schedules

Go to `Jobs` to manage recurring syncs.

Supported schedule types:

- `daily`
- `interval`

Rules:

- recurring jobs save the current sync scope, destination, and deletion policy from `Sync`
- interval schedules run every `1` to `168` hours
- daily schedules run at the configured `HH:MM` in `GET_PUTIO_SCHEDULE_TIMEZONE`
- the scheduler checks for due work every `GET_PUTIO_SCHEDULER_POLL_SECONDS` seconds

Cleanup schedules are configured separately in `Storage`.

## Data locations

By default, container installs store:

- state in `./data/app/state.json` on the host
- media in `./data/media` on the host

The state file contains your saved settings, job history, and schedule state.

## License

MIT. See [LICENSE](LICENSE).
