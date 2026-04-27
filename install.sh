#!/usr/bin/env bash

set -euo pipefail

SERVICE_NAME="salesmanager"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
CONTAINER_NAME="salesmanager-systemd"
IMAGE="ghcr.io/gemblerz/salesmanager:latest"
HOST_PORT="5000"
CONTAINER_PORT="5000"
CONFIG_DIR="/etc/salesmanager"
ENV_FILE="${CONFIG_DIR}/app.env"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ARGS_FILE="${SCRIPT_DIR}/app-args.yml"
DEPLOYMENT_TYPE="public"
SITE_PASSWORD="salesmanager"

ensure_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: $1 is not installed or not in PATH."
    exit 1
  fi
}

check_service() {
  ensure_command systemctl

  if ! systemctl list-unit-files | grep -q "^${SERVICE_NAME}\.service"; then
    echo "Service ${SERVICE_NAME}.service is not installed."
    exit 1
  fi

  if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
    echo "Service ${SERVICE_NAME}.service is active and running."
    exit 0
  fi

  echo "Service ${SERVICE_NAME}.service is not running."
  systemctl --no-pager --full status "${SERVICE_NAME}.service" || true
  exit 1
}

usage() {
  cat <<EOF
Usage:
  sudo ./install.sh [--app-args <path-to-yaml>]
  ./install.sh --check
EOF
}

trim_value() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  if [[ "$value" == \"* && "$value" == *\" ]]; then
    value="${value:1:${#value}-2}"
  elif [[ "$value" == \'* && "$value" == *\' ]]; then
    value="${value:1:${#value}-2}"
  fi
  printf '%s' "$value"
}

read_yaml_scalar() {
  local file="$1"
  local key="$2"
  local line
  line="$(grep -E "^[[:space:]]*${key}[[:space:]]*:[[:space:]]*" "$file" | head -n1 || true)"
  if [[ -z "$line" ]]; then
    return 1
  fi
  line="${line#*:}"
  line="${line%%#*}"
  trim_value "$line"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check)
      check_service
      ;;
    --app-args)
      if [[ $# -lt 2 ]]; then
        echo "Error: --app-args requires a YAML file path."
        usage
        exit 1
      fi
      APP_ARGS_FILE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Error: Unknown argument '$1'."
      usage
      exit 1
      ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Please run as root (e.g. sudo ./install.sh)."
  exit 1
fi

if [[ ! -d /run/systemd/system ]]; then
  echo "Error: systemd does not appear to be the init system."
  exit 1
fi

ensure_command docker
ensure_command systemctl

DOCKER_BIN="$(command -v docker)"

if [[ ! -f "$APP_ARGS_FILE" ]]; then
  echo "Error: app arguments file not found: $APP_ARGS_FILE"
  exit 1
fi

if deployment_value="$(read_yaml_scalar "$APP_ARGS_FILE" "deployment_type")"; then
  DEPLOYMENT_TYPE="$(printf '%s' "$deployment_value" | tr '[:upper:]' '[:lower:]')"
fi
if password_value="$(read_yaml_scalar "$APP_ARGS_FILE" "site_password")"; then
  SITE_PASSWORD="$password_value"
fi

if [[ "$DEPLOYMENT_TYPE" != "local" && "$DEPLOYMENT_TYPE" != "public" ]]; then
  echo "Error: deployment_type must be 'local' or 'public' in $APP_ARGS_FILE"
  exit 1
fi

if [[ "$DEPLOYMENT_TYPE" == "public" && -z "$SITE_PASSWORD" ]]; then
  echo "Error: site_password is required when deployment_type is 'public'."
  exit 1
fi

mkdir -p "$CONFIG_DIR"
{
  printf 'DEPLOYMENT_TYPE=%s\n' "$DEPLOYMENT_TYPE"
  if [[ "$DEPLOYMENT_TYPE" == "public" ]]; then
    printf 'SITE_PASSWORD=%s\n' "$SITE_PASSWORD"
  fi
} > "$ENV_FILE"
chmod 600 "$ENV_FILE"

echo "Pulling container image: ${IMAGE}"
"${DOCKER_BIN}" pull "${IMAGE}"

cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=Sales Manager container
Wants=network-online.target docker.service
After=network-online.target docker.service

[Service]
Type=simple
Restart=always
RestartSec=5
ExecStartPre=-${DOCKER_BIN} rm -f ${CONTAINER_NAME}
ExecStart=${DOCKER_BIN} run --pull always --rm --name ${CONTAINER_NAME} --env-file ${ENV_FILE} -p ${HOST_PORT}:${CONTAINER_PORT} ${IMAGE}
ExecStop=${DOCKER_BIN} stop ${CONTAINER_NAME}

[Install]
WantedBy=multi-user.target
EOF

echo "Reloading systemd daemon..."
systemctl daemon-reload

echo "Enabling and starting ${SERVICE_NAME}.service..."
systemctl enable --now "${SERVICE_NAME}.service"

check_service
