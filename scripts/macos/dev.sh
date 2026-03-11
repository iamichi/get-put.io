#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
FRONTEND_DIR="${ROOT_DIR}/frontend"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required."
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required."
  exit 1
fi

if [ ! -d "${BACKEND_DIR}/.venv" ]; then
  python3 -m venv "${BACKEND_DIR}/.venv"
fi

source "${BACKEND_DIR}/.venv/bin/activate"
pip install -e "${BACKEND_DIR}[dev]"

if [ ! -d "${FRONTEND_DIR}/node_modules" ]; then
  (cd "${FRONTEND_DIR}" && npm install)
fi

cleanup() {
  if [ -n "${BACKEND_PID:-}" ]; then
    kill "${BACKEND_PID}" >/dev/null 2>&1 || true
  fi
  if [ -n "${FRONTEND_PID:-}" ]; then
    kill "${FRONTEND_PID}" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT

(
  cd "${BACKEND_DIR}"
  source .venv/bin/activate
  exec uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
) &
BACKEND_PID=$!

(
  cd "${FRONTEND_DIR}"
  exec npm run dev -- --host 0.0.0.0
) &
FRONTEND_PID=$!

wait "${BACKEND_PID}" "${FRONTEND_PID}"

