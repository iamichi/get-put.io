# Backend Guide

This backend is a FastAPI service that owns application state, Put.io authentication, sync execution, cleanup execution, and recurring scheduling.

## Prerequisites

- Python 3.11+
- `rclone`
- a writable state file location
- a writable storage root for synced media

## Run Locally

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

The frontend dev server is separate and lives in [frontend](/Users/ichi/Dev/get-putio/frontend).

## Test

```bash
cd backend
source .venv/bin/activate
pytest
```

## Backend Layout

- [app/main.py](/Users/ichi/Dev/get-putio/backend/app/main.py)
  FastAPI entrypoint, scheduler lifecycle, CORS, and frontend static serving.

- [app/config.py](/Users/ichi/Dev/get-putio/backend/app/config.py)
  Environment-backed configuration and path defaults.

- [app/api/routes.py](/Users/ichi/Dev/get-putio/backend/app/api/routes.py)
  HTTP routes for settings, Put.io auth, sync jobs, cleanup, Jellyfin, and schedules.

- [app/api/schemas.py](/Users/ichi/Dev/get-putio/backend/app/api/schemas.py)
  Request and response models. Keep these explicit; do not return raw state models unless the data is safe.

- [app/models/state.py](/Users/ichi/Dev/get-putio/backend/app/models/state.py)
  Persisted state for settings, jobs, schedules, and cleanup runs.

- [app/services/state.py](/Users/ichi/Dev/get-putio/backend/app/services/state.py)
  Thread-safe JSON store with restrictive file permissions.

- [app/services/putio.py](/Users/ichi/Dev/get-putio/backend/app/services/putio.py)
  OAuth flow, token handling, account lookups, and Put.io folder browsing.

- [app/services/rclone.py](/Users/ichi/Dev/get-putio/backend/app/services/rclone.py)
  Builds `rclone copy` or `rclone sync` commands from backend job settings.

- [app/services/jobs.py](/Users/ichi/Dev/get-putio/backend/app/services/jobs.py)
  Starts sync subprocesses, streams logs, tracks state, and handles cancellation.

- [app/services/storage_cleanup.py](/Users/ichi/Dev/get-putio/backend/app/services/storage_cleanup.py)
  Plans and runs cleanup against the storage root using free-space thresholds and file age.

- [app/services/jellyfin.py](/Users/ichi/Dev/get-putio/backend/app/services/jellyfin.py)
  Jellyfin connectivity, library listing, and refresh hooks.

- [app/services/scheduler.py](/Users/ichi/Dev/get-putio/backend/app/services/scheduler.py)
  In-process polling scheduler for recurring syncs and cleanup jobs.

- [tests/test_health.py](/Users/ichi/Dev/get-putio/backend/tests/test_health.py)
  Current regression coverage for routes and service behavior.

## State Model

There is no database.

The backend persists everything in one JSON state file. Typical locations:

- local host: whatever `GET_PUTIO_STATE_PATH` points to
- container: `/app/data/state.json`

The state file contains:

- Put.io settings and token state
- Jellyfin settings
- sync defaults
- storage cleanup settings
- sync job history
- cleanup run history
- recurring schedules
- cleanup schedule state

## Important Runtime Invariants

These rules matter when changing backend behavior:

- sync destinations must stay inside `GET_PUTIO_STORAGE_PATH`
- cleanup only touches files inside `GET_PUTIO_STORAGE_PATH`
- settings responses must stay redacted
- static file serving must enforce path containment
- Jellyfin URLs must be validated before use
- scheduler failures must be observable, not silent

## Sync Flow

Normal sync flow:

1. the API validates the request
2. destination paths are normalized under the configured storage root
3. `rclone` command arguments are built
4. a background subprocess starts
5. stdout and stderr are streamed into persisted job logs
6. the final job status is written
7. Jellyfin refresh runs if enabled and appropriate

Deletion handling is chosen per sync:

- `keep_local` uses `rclone copy`
- `mirror_remote` uses `rclone sync`

## Cleanup Flow

Cleanup is intentionally separate from Put.io mirroring.

The cleanup service:

1. checks free space on the storage root
2. decides whether cleanup is needed
3. walks eligible files under the storage root
4. excludes configured paths
5. filters by minimum age
6. sorts oldest-first
7. builds a reclaim plan
8. either returns the preview or deletes the selected files

Manual cleanup and scheduled cleanup both use the same service.

## Scheduler

The scheduler is an in-process polling loop. It only runs while the backend process is alive.

It is responsible for:

- recurring sync jobs
- scheduled cleanup runs

Relevant settings:

- `GET_PUTIO_SCHEDULE_TIMEZONE`
- `GET_PUTIO_SCHEDULER_POLL_SECONDS`

If you add new scheduled behavior, keep the scheduling decision in the scheduler service and the actual work in a dedicated service.

## Environment Variables

Common backend variables:

- `GET_PUTIO_STORAGE_PATH`
- `GET_PUTIO_STATE_PATH`
- `GET_PUTIO_SCHEDULE_TIMEZONE`
- `GET_PUTIO_SCHEDULER_POLL_SECONDS`
- `GET_PUTIO_RCLONE_BINARY`
- `GET_PUTIO_PUTIO_APP_ID`
- `GET_PUTIO_PUTIO_CLIENT_SECRET`
- `GET_PUTIO_PUTIO_REDIRECT_URI`
- `GET_PUTIO_PUTIO_ACCESS_TOKEN`
- `GET_PUTIO_JELLYFIN_BASE_URL`
- `GET_PUTIO_JELLYFIN_API_KEY`

`FRONTEND_URL` is also used by the backend for CORS and OAuth callback return handling.

## Changing The Backend Safely

When adding or changing behavior:

- keep route handlers thin
- move operational logic into services
- update API schemas alongside route changes
- add regression coverage in [test_health.py](/Users/ichi/Dev/get-putio/backend/tests/test_health.py)
- preserve redaction and path-containment checks

If you need a new subsystem, follow the current pattern:

- state shape in [app/models/state.py](/Users/ichi/Dev/get-putio/backend/app/models/state.py)
- persistence through [app/services/state.py](/Users/ichi/Dev/get-putio/backend/app/services/state.py)
- service logic in `app/services`
- schema exposure through [app/api/schemas.py](/Users/ichi/Dev/get-putio/backend/app/api/schemas.py)
- routes in [app/api/routes.py](/Users/ichi/Dev/get-putio/backend/app/api/routes.py)
