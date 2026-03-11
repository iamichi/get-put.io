#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE_NAME="${IMAGE_NAME:-get-putio:local}"
CONTAINER_NAME="${CONTAINER_NAME:-get-putio}"
HOST_PORT="${HOST_PORT:-8787}"

if ! command -v container >/dev/null 2>&1; then
  echo "Apple's container CLI is not installed."
  echo "Install it from https://github.com/apple/container and run: container system start"
  exit 1
fi

mkdir -p "${ROOT_DIR}/data/app" "${ROOT_DIR}/data/media"

if [ ! -f "${ROOT_DIR}/.env" ]; then
  cp "${ROOT_DIR}/.env.example" "${ROOT_DIR}/.env"
fi

container system start
container builder start --cpus 4 --memory 6g >/dev/null 2>&1 || true
container build --tag "${IMAGE_NAME}" --file "${ROOT_DIR}/Dockerfile" "${ROOT_DIR}"
container delete --force "${CONTAINER_NAME}" >/dev/null 2>&1 || true
container run -d \
  --name "${CONTAINER_NAME}" \
  --publish "127.0.0.1:${HOST_PORT}:8000" \
  --env-file "${ROOT_DIR}/.env" \
  --volume "${ROOT_DIR}/data/app:/app/data" \
  --volume "${ROOT_DIR}/data/media:/media" \
  "${IMAGE_NAME}"

echo "get-put.io is starting on http://127.0.0.1:${HOST_PORT}"
