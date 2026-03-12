#!/usr/bin/env bash
set -euo pipefail

# Run this on a Proxmox host.
# You can pass values via env vars (non-interactive), or run with no vars and answer prompts.
# Optional environment variables:
#   CTID=1870
#   CT_HOSTNAME=get-putio
#   TEMPLATE=local:vztmpl/debian-12-standard_12.8-1_amd64.tar.zst
#   TEMPLATE_STORAGE=local
#   STORAGE=local-lvm
#   DISK_GB=8
#   MEMORY_MB=2048
#   SWAP_MB=512
#   CORES=2
#   BRIDGE=vmbr0
#   IP_CONFIG=dhcp
#   GATEWAY=
#   PUBLIC_URL=http://192.168.1.50:8787
#   UNPRIVILEGED=1
#   MEDIA_SOURCE=/path/on/proxmox/media
#   MEDIA_TARGET=/media
#   APPLY_MEDIA_ACL=auto|1|0
#   MEDIA_WRITE_UID=100000
#   APP_REPO_URL=https://github.com/iamichi/get-put.io.git
#   APP_BRANCH=main
#   APP_PORT=8787
#   INTERACTIVE=auto|1|0

if ! command -v pct >/dev/null 2>&1; then
  echo "pct is required. Run this on a Proxmox host."
  exit 1
fi

if ! command -v pveam >/dev/null 2>&1; then
  echo "pveam is required. Run this on a Proxmox VE host."
  exit 1
fi

log() { printf '%s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

prompt_default() {
  local prompt="$1"
  local default_value="$2"
  local answer=""
  read -r -p "${prompt} [${default_value}]: " answer || true
  if [ -z "${answer}" ]; then
    printf '%s\n' "${default_value}"
  else
    printf '%s\n' "${answer}"
  fi
}

next_ctid() {
  if command -v pvesh >/dev/null 2>&1; then
    pvesh get /cluster/nextid 2>/dev/null || echo "1870"
  else
    echo "1870"
  fi
}

is_valid_ipv4() {
  local ip="$1"
  local a b c d
  IFS='.' read -r a b c d <<< "${ip}"
  for octet in "${a:-}" "${b:-}" "${c:-}" "${d:-}"; do
    [[ "${octet}" =~ ^[0-9]+$ ]] || return 1
    [ "${octet}" -ge 0 ] && [ "${octet}" -le 255 ] || return 1
  done
  [ -n "${d:-}" ] || return 1
}

normalize_ip_config() {
  local raw="$1"
  local ip prefix
  if [ "${raw}" = "dhcp" ]; then
    printf '%s\n' "dhcp"
    return
  fi
  if [[ "${raw}" == */* ]]; then
    ip="${raw%/*}"
    prefix="${raw#*/}"
  else
    ip="${raw}"
    prefix="24"
    log "No CIDR prefix supplied for ${ip}; defaulting to /24."
  fi
  is_valid_ipv4 "${ip}" || die "IP_CONFIG must be dhcp or IPv4 CIDR (example: 10.10.10.5/24)."
  [[ "${prefix}" =~ ^[0-9]+$ ]] || die "IP_CONFIG CIDR prefix must be a number from 0-32."
  [ "${prefix}" -ge 0 ] && [ "${prefix}" -le 32 ] || die "IP_CONFIG CIDR prefix must be a number from 0-32."
  printf '%s\n' "${ip}/${prefix}"
}

detect_storage() {
  local available
  available="$(pvesm status 2>/dev/null | awk 'NR>1 {print $1}' || true)"
  if printf '%s\n' "${available}" | grep -qx "local-lvm"; then
    printf '%s\n' "local-lvm"
    return
  fi
  if printf '%s\n' "${available}" | grep -qx "local"; then
    printf '%s\n' "local"
    return
  fi
  printf '%s\n' "${available}" | head -n1
}

detect_bridge() {
  local first_bridge
  first_bridge="$(ip -o link show 2>/dev/null | awk -F': ' '{print $2}' | grep '^vmbr' | head -n1 || true)"
  if [ -n "${first_bridge}" ]; then
    printf '%s\n' "${first_bridge}"
  else
    printf '%s\n' "vmbr0"
  fi
}

latest_debian12_template() {
  pveam available --section system \
    | awk '{print $2}' \
    | grep -E '^debian-12-standard_.*_amd64\.tar\.zst$' \
    | sort -V \
    | tail -n1
}

ensure_template_present() {
  local template="$1"
  local storage_id template_file
  if [[ "${template}" != *":vztmpl/"* ]]; then
    die "TEMPLATE must use '<storage>:vztmpl/<file>' format. Got: ${template}"
  fi
  storage_id="${template%%:*}"
  template_file="${template#*:vztmpl/}"
  if pveam list "${storage_id}" 2>/dev/null | grep -Fq "/${template_file}"; then
    return
  fi
  log "Template ${template_file} not found in ${storage_id}; downloading..."
  pveam download "${storage_id}" "${template_file}"
}

ensure_acl_tool() {
  if command -v setfacl >/dev/null 2>&1; then
    return
  fi
  log "Installing acl package on the Proxmox host so media permissions can be adjusted..."
  apt-get update
  apt-get install -y acl
}

apply_media_acl() {
  local path="$1"
  local uid="$2"
  ensure_acl_tool
  log "Granting mapped container UID ${uid} write access on ${path}..."
  setfacl -R -m "u:${uid}:rwX" "${path}"
  find "${path}" -type d -exec setfacl -m "d:u:${uid}:rwX" {} +
}

INTERACTIVE="${INTERACTIVE:-auto}"
if [ "${INTERACTIVE}" = "auto" ]; then
  if [ -t 0 ]; then
    INTERACTIVE="1"
  else
    INTERACTIVE="0"
  fi
fi

ctid_was_set=0
hostname_was_set=0
ip_was_set=0
gateway_was_set=0
media_source_was_set=0
media_target_was_set=0

[ -n "${CTID+x}" ] && ctid_was_set=1
[ -n "${IP_CONFIG+x}" ] && ip_was_set=1
[ -n "${GATEWAY+x}" ] && gateway_was_set=1
[ -n "${MEDIA_SOURCE+x}" ] && media_source_was_set=1
[ -n "${MEDIA_TARGET+x}" ] && media_target_was_set=1

if [ -n "${CT_HOSTNAME:-}" ]; then
  hostname_was_set=1
fi

CTID="${CTID:-$(next_ctid)}"
CT_HOSTNAME="${CT_HOSTNAME:-get-putio}"
TEMPLATE_STORAGE="${TEMPLATE_STORAGE:-local}"
STORAGE="${STORAGE:-$(detect_storage)}"
DISK_GB="${DISK_GB:-8}"
MEMORY_MB="${MEMORY_MB:-2048}"
SWAP_MB="${SWAP_MB:-512}"
CORES="${CORES:-2}"
BRIDGE="${BRIDGE:-$(detect_bridge)}"
IP_CONFIG="${IP_CONFIG:-dhcp}"
GATEWAY="${GATEWAY:-}"
PUBLIC_URL="${PUBLIC_URL:-}"
UNPRIVILEGED="${UNPRIVILEGED:-1}"
MEDIA_SOURCE="${MEDIA_SOURCE:-}"
MEDIA_TARGET="${MEDIA_TARGET:-/media}"
APPLY_MEDIA_ACL="${APPLY_MEDIA_ACL:-auto}"
MEDIA_WRITE_UID="${MEDIA_WRITE_UID:-100000}"
APP_REPO_URL="${APP_REPO_URL:-https://github.com/iamichi/get-put.io.git}"
APP_BRANCH="${APP_BRANCH:-main}"
APP_PORT="${APP_PORT:-8787}"

if [ "${INTERACTIVE}" = "1" ]; then
  log "Starting get-put.io Proxmox installer (interactive mode). Press Enter to accept defaults."
  if [ "${ctid_was_set}" -eq 0 ]; then
    CTID="$(prompt_default "CTID" "${CTID}")"
  fi
  if [ "${hostname_was_set}" -eq 0 ]; then
    CT_HOSTNAME="$(prompt_default "Hostname" "${CT_HOSTNAME}")"
  fi
  if [ "${ip_was_set}" -eq 0 ]; then
    read -r -p "Use DHCP networking? [Y/n]: " use_dhcp || true
    case "${use_dhcp:-Y}" in
      n|N)
        IP_CONFIG="$(normalize_ip_config "$(prompt_default "Static IP/CIDR" "192.168.1.50/24")")"
        if [ "${gateway_was_set}" -eq 0 ]; then
          GATEWAY="$(prompt_default "Gateway" "192.168.1.1")"
        fi
        ;;
      *)
        IP_CONFIG="dhcp"
        ;;
    esac
  fi
  if [ "${media_source_was_set}" -eq 0 ]; then
    read -r -p "Mount a host media path into the LXC? [y/N]: " mount_media || true
    case "${mount_media:-N}" in
      y|Y)
        MEDIA_SOURCE="$(prompt_default "Host media path" "/path/on/proxmox/media")"
        if [ "${media_target_was_set}" -eq 0 ]; then
          MEDIA_TARGET="$(prompt_default "Container mount point" "${MEDIA_TARGET}")"
        fi
        ;;
      *)
        MEDIA_SOURCE=""
        ;;
    esac
  fi
  if [ -z "${ROOT_PASSWORD:-}" ] && [ -z "${SSH_PUBLIC_KEY_FILE:-}" ]; then
    default_ssh_key="/root/.ssh/authorized_keys"
    if [ -f "${default_ssh_key}" ]; then
      read -r -p "Use SSH key auth from ${default_ssh_key}? [Y/n]: " use_key_auth || true
      case "${use_key_auth:-Y}" in
        n|N)
          read -r -s -p "Root password: " ROOT_PASSWORD
          echo
          ;;
        *)
          SSH_PUBLIC_KEY_FILE="${default_ssh_key}"
          ;;
      esac
    else
      read -r -s -p "Root password: " ROOT_PASSWORD
      echo
    fi
  fi
fi

if [ -z "${ROOT_PASSWORD:-}" ] && [ -z "${SSH_PUBLIC_KEY_FILE:-}" ]; then
  die "Set ROOT_PASSWORD or SSH_PUBLIC_KEY_FILE (or run interactively in a TTY)."
fi

if [ -z "${STORAGE}" ]; then
  die "Could not detect a Proxmox storage target. Set STORAGE explicitly."
fi

IP_CONFIG="$(normalize_ip_config "${IP_CONFIG}")"
if [ "${IP_CONFIG}" != "dhcp" ] && [ -n "${GATEWAY}" ]; then
  is_valid_ipv4 "${GATEWAY}" || die "GATEWAY must be a valid IPv4 address."
fi

if [ -z "${TEMPLATE:-}" ]; then
  log "Refreshing container template list..."
  pveam update
  template_file="$(latest_debian12_template || true)"
  if [ -z "${template_file}" ]; then
    die "No Debian 12 LXC template found in pveam available output."
  fi
  TEMPLATE="${TEMPLATE_STORAGE}:vztmpl/${template_file}"
fi

ensure_template_present "${TEMPLATE}"

if pct status "${CTID}" >/dev/null 2>&1; then
  die "Container ${CTID} already exists."
fi

NET0="name=eth0,bridge=${BRIDGE},ip=${IP_CONFIG}"
if [ "${IP_CONFIG}" != "dhcp" ] && [ -n "${GATEWAY}" ]; then
  NET0="${NET0},gw=${GATEWAY}"
fi

CREATE_ARGS=(
  "${CTID}" "${TEMPLATE}"
  --hostname "${CT_HOSTNAME}"
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
  [ -f "${SSH_PUBLIC_KEY_FILE}" ] || die "SSH public key file not found: ${SSH_PUBLIC_KEY_FILE}"
  CREATE_ARGS+=(--ssh-public-keys "${SSH_PUBLIC_KEY_FILE}")
fi

log "Creating container ${CTID} (${CT_HOSTNAME}) on storage ${STORAGE} using template ${TEMPLATE}..."
pct create "${CREATE_ARGS[@]}"

if [ -n "${MEDIA_SOURCE}" ]; then
  [ -d "${MEDIA_SOURCE}" ] || die "MEDIA_SOURCE path not found on the Proxmox host: ${MEDIA_SOURCE}"
  if [ "${UNPRIVILEGED}" = "1" ]; then
    case "${APPLY_MEDIA_ACL}" in
      auto|1)
        apply_media_acl "${MEDIA_SOURCE}" "${MEDIA_WRITE_UID}"
        ;;
      0)
        ;;
      *)
        die "APPLY_MEDIA_ACL must be auto, 1, or 0."
        ;;
    esac
  fi
  pct set "${CTID}" -mp0 "${MEDIA_SOURCE},mp=${MEDIA_TARGET}"
fi

pct start "${CTID}"

pct exec "${CTID}" -- bash -lc "apt-get update && apt-get install -y ca-certificates curl gnupg git"
pct exec "${CTID}" -- bash -lc "install -m 0755 -d /etc/apt/keyrings"
pct exec "${CTID}" -- bash -lc "curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg"
pct exec "${CTID}" -- bash -lc "chmod a+r /etc/apt/keyrings/docker.gpg"
pct exec "${CTID}" -- bash -lc "echo \"deb [arch=\$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \$(. /etc/os-release && echo \$VERSION_CODENAME) stable\" >/etc/apt/sources.list.d/docker.list"
pct exec "${CTID}" -- bash -lc "apt-get update && apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin"

resolve_container_ip() {
  local detected_ip=""
  for _ in $(seq 1 15); do
    detected_ip="$(pct exec "${CTID}" -- bash -lc "hostname -I | awk '{print \$1}'" 2>/dev/null | tr -d '\r')"
    if [ -n "${detected_ip}" ]; then
      printf '%s\n' "${detected_ip}"
      return 0
    fi
    sleep 2
  done
  return 1
}

if [ "${IP_CONFIG}" != "dhcp" ] && [ -z "${PUBLIC_URL}" ]; then
  PUBLIC_URL="http://${IP_CONFIG%%/*}:${APP_PORT}"
fi

if [ -z "${PUBLIC_URL}" ]; then
  if DETECTED_IP="$(resolve_container_ip)"; then
    PUBLIC_URL="http://${DETECTED_IP}:${APP_PORT}"
  fi
fi

pct exec "${CTID}" -- bash -lc "rm -rf /opt/get-putio && git clone --depth 1 --branch ${APP_BRANCH} ${APP_REPO_URL} /opt/get-putio"
pct exec "${CTID}" -- bash -lc "cd /opt/get-putio && cp -n .env.example .env"

if [ -n "${PUBLIC_URL}" ]; then
  pct exec "${CTID}" -- bash -lc "cd /opt/get-putio && sed -i \"s|^FRONTEND_URL=.*$|FRONTEND_URL=${PUBLIC_URL}|\" .env && sed -i \"s|^PUTIO_REDIRECT_URI=.*$|PUTIO_REDIRECT_URI=${PUBLIC_URL}/api/auth/putio/callback|\" .env"
fi

if [ -n "${MEDIA_SOURCE}" ]; then
  pct exec "${CTID}" -- bash -lc "cd /opt/get-putio && if grep -q '^MEDIA_BIND_SOURCE=' .env; then sed -i \"s|^MEDIA_BIND_SOURCE=.*$|MEDIA_BIND_SOURCE=${MEDIA_TARGET}|\" .env; else echo 'MEDIA_BIND_SOURCE=${MEDIA_TARGET}' >> .env; fi"
fi

pct exec "${CTID}" -- bash -lc "cd /opt/get-putio && docker compose up -d --build"

echo "Container ${CTID} created and get-put.io deployed."
if [ -n "${PUBLIC_URL}" ]; then
  echo "Open ${PUBLIC_URL}"
  echo "Put.io redirect URI: ${PUBLIC_URL}/api/auth/putio/callback"
else
  echo "Could not detect a PUBLIC_URL automatically."
  echo "Edit /opt/get-putio/.env inside the container and set FRONTEND_URL plus PUTIO_REDIRECT_URI."
fi

if [ -n "${MEDIA_SOURCE}" ]; then
  echo
  echo "Media mount configured: ${MEDIA_SOURCE} -> ${MEDIA_TARGET}"
  if [ "${UNPRIVILEGED}" = "1" ]; then
    if [ "${APPLY_MEDIA_ACL}" = "0" ]; then
      echo "This container is unprivileged, and ACL adjustment was skipped."
      echo "If syncs fail with 'permission denied', grant write access on the host path to UID/GID ${MEDIA_WRITE_UID}, or recreate the container with UNPRIVILEGED=0."
    else
      echo "This container is unprivileged, so the installer granted write ACLs on the host path for mapped UID/GID ${MEDIA_WRITE_UID}."
    fi
  else
    echo "Check the host path ownership and permissions if syncs fail with 'permission denied'."
  fi
fi
