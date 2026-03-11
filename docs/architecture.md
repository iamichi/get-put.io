# Architecture

## Core model

`get-put.io` is split into four concerns:
- control plane API
- browser UI
- transfer engine
- media server integration

The API is the source of truth. The frontend renders state and submits intent. `rclone` remains the transfer engine instead of being reimplemented in application code.

## Why `rclone`

`rclone` keeps the hardest part of the system boring:
- Put.io remote handling
- resumable transfers
- folder-scoped operations
- local filesystem writes

The app should focus on:
- OAuth and connection state
- job definitions
- path mapping rules
- previewing and launching transfer commands
- refreshing Jellyfin once files are safely in place

## Expected v1 flow

1. User connects Put.io.
2. User chooses `all` or a folder.
3. User chooses a destination path.
4. The backend builds an `rclone` command plan.
5. Files land in a staging area.
6. Completed files are promoted into Jellyfin library paths.
7. Jellyfin refresh is triggered.

## Deployment targets

- Proxmox LXC with Docker Compose is the main self-hosting target.
- Native macOS is supported for development.
- Container runtimes on macOS are optional and not required for day-one usage.

