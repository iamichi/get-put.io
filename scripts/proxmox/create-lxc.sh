#!/usr/bin/env bash
set -euo pipefail

# Run this on a Proxmox host. Provide either ROOT_PASSWORD or SSH_PUBLIC_KEY_FILE.
# Optional environment variables:
#   CTID=1870
#   HOSTNAME=get-putio
#   TEMPLATE=local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst
#   STORAGE=local-lvm
#   DISK_GB=8
#   MEMORY_MB=2048
#   SWAP_MB=512
#   CORES=2
#   BRIDGE=vmbr0
#   IP_CONFIG=dhcp
#   GATEWAY=
#   UNPRIVILEGED=1
#   MEDIA_SOURCE=/mnt/pve/media
#   MEDIA_TARGET=/srv/media
#   APP_REPO_URL=https://github.com/your-user/get-putio.git
#   APP_BRANCH=main

if ! command -v pct >/dev/null 2>&1; then
  echo "pct is required. Run this on a Proxmox host."
  exit 1
fi

if [ -z "${ROOT_PASSWORD:-}" ] && [ -z "${SSH_PUBLIC_KEY_FILE:-}" ]; then
  echo "Set ROOT_PASSWORD or SSH_PUBLIC_KEY_FILE before running this script."
  exit 1
fi

CTID="${CTID:-1870}"
HOSTNAME="${HOSTNAME:-get-putio}"
TEMPLATE="${TEMPLATE:-local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst}"
STORAGE="${STORAGE:-local-lvm}"
DISK_GB="${DISK_GB:-8}"
MEMORY_MB="${MEMORY_MB:-2048}"
SWAP_MB="${SWAP_MB:-512}"
CORES="${CORES:-2}"
BRIDGE="${BRIDGE:-vmbr0}"
IP_CONFIG="${IP_CONFIG:-dhcp}"
GATEWAY="${GATEWAY:-}"
UNPRIVILEGED="${UNPRIVILEGED:-1}"
MEDIA_SOURCE="${MEDIA_SOURCE:-}"
MEDIA_TARGET="${MEDIA_TARGET:-/srv/media}"
APP_REPO_URL="${APP_REPO_URL:-}"
APP_BRANCH="${APP_BRANCH:-main}"

if pct status "${CTID}" >/dev/null 2>&1; then
  echo "Container ${CTID} already exists."
  exit 1
fi

NET0="name=eth0,bridge=${BRIDGE},ip=${IP_CONFIG}"
if [ "${IP_CONFIG}" != "dhcp" ] && [ -n "${GATEWAY}" ]; then
  NET0="${NET0},gw=${GATEWAY}"
fi

CREATE_ARGS=(
  "${CTID}" "${TEMPLATE}"
  --hostname "${HOSTNAME}"
  --ostype debian
  --rootfs "${STORAGE}:${DISK_GB}"
  --memory "${MEMORY_MB}"
  --swap "${SWAP_MB}"
  --cores "${CORES}"
  --net0 "${NET0}"
  --features nesting=1,keyctl=1
  --onboot 1
  --unprivileged "${UNPRIVILEGED}"
)

if [ -n "${ROOT_PASSWORD:-}" ]; then
  CREATE_ARGS+=(--password "${ROOT_PASSWORD}")
fi

if [ -n "${SSH_PUBLIC_KEY_FILE:-}" ]; then
  CREATE_ARGS+=(--ssh-public-keys "${SSH_PUBLIC_KEY_FILE}")
fi

pct create "${CREATE_ARGS[@]}"

if [ -n "${MEDIA_SOURCE}" ]; then
  pct set "${CTID}" -mp0 "${MEDIA_SOURCE},mp=${MEDIA_TARGET}"
fi

pct start "${CTID}"

pct exec "${CTID}" -- bash -lc "apt-get update && apt-get install -y ca-certificates curl gnupg git"
pct exec "${CTID}" -- bash -lc "install -m 0755 -d /etc/apt/keyrings"
pct exec "${CTID}" -- bash -lc "curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg"
pct exec "${CTID}" -- bash -lc "chmod a+r /etc/apt/keyrings/docker.gpg"
pct exec "${CTID}" -- bash -lc "echo \"deb [arch=\$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \$(. /etc/os-release && echo \$VERSION_CODENAME) stable\" >/etc/apt/sources.list.d/docker.list"
pct exec "${CTID}" -- bash -lc "apt-get update && apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin"

if [ -n "${APP_REPO_URL}" ]; then
  pct exec "${CTID}" -- bash -lc "rm -rf /opt/get-putio && git clone --depth 1 --branch ${APP_BRANCH} ${APP_REPO_URL} /opt/get-putio"
  pct exec "${CTID}" -- bash -lc "cd /opt/get-putio && cp -n .env.example .env && docker compose up -d --build"
else
  echo "Container ${CTID} created and Docker installed."
  echo "Set APP_REPO_URL to auto-deploy the app after you push this repo to a remote."
fi

