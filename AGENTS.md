# AGENTS.md

## Project intent
- `get-put.io` is a self-hosted Put.io to Jellyfin sync portal.
- The product goal is a lightweight control plane around `rclone`, not a custom downloader for v1.
- The backend owns orchestration, job state, auth flows, and Jellyfin refresh hooks.
- The frontend owns a polished control surface and should not reimplement backend business rules.

## Architecture guardrails
- Prefer `rclone` for Put.io transfer operations unless there is a concrete feature gap.
- Keep Put.io access behind a service boundary so OAuth and API details stay isolated.
- Treat Jellyfin as an external system; use explicit API calls instead of filesystem side effects alone.
- Do not expose partially downloaded files to Jellyfin libraries. Stage first, then move into the library path.
- Default to single-user admin workflows for v1. Add multi-user support only with a clear permissions model.

## Backend expectations
- Use FastAPI for HTTP endpoints.
- Keep request and response schemas in dedicated models.
- Make service classes thin and composable so they can be swapped with real integrations later.
- Prefer explicit configuration via environment variables and documented defaults.

## Frontend expectations
- Keep the visual style intentional. Avoid generic dashboard aesthetics.
- Use a strong typographic hierarchy, defined color tokens, and a few meaningful motion cues.
- Assume the backend may be unavailable during local UI development; design sensible loading and error states.

## Deployment expectations
- Primary deployment target: Proxmox LXC running Docker Compose.
- Secondary target: native macOS development without containers.
- Optional container runtimes on macOS are allowed, but the repo should not depend on Apple-only tooling.

## Verification
- For Python changes, run tests or at least import/compile validation when practical.
- For frontend changes, run a production build when dependencies are available.
- Do not introduce hidden magic scripts; keep entrypoints obvious from the README and `Makefile`.

