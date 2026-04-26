#!/usr/bin/env bash

set -euo pipefail

SERVICE_NAME="salesmanager"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
CONTAINER_NAME="salesmanager"
IMAGE="ghcr.io/gemblerz/salesmanager:latest"
HOST_PORT="5000"
CONTAINER_PORT="5000"

check_service() {
  if ! command -v systemctl >/dev/null 2>&1; then
    echo "Error: systemctl is not available on this system."
    exit 1
  fi

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

if [[ "${1:-}" == "--check" ]]; then
  check_service
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Please run as root (e.g. sudo ./install.sh)."
  exit 1
fi

if [[ ! -d /run/systemd/system ]]; then
  echo "Error: systemd does not appear to be the init system."
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is not installed or not in PATH."
  exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "Error: systemctl is not available on this system."
  exit 1
fi

DOCKER_BIN="$(command -v docker)"

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
ExecStart=${DOCKER_BIN} run --rm --name ${CONTAINER_NAME} -p ${HOST_PORT}:${CONTAINER_PORT} ${IMAGE}
ExecStop=${DOCKER_BIN} stop ${CONTAINER_NAME}

[Install]
WantedBy=multi-user.target
EOF

echo "Reloading systemd daemon..."
systemctl daemon-reload

echo "Enabling and starting ${SERVICE_NAME}.service..."
systemctl enable --now "${SERVICE_NAME}.service"

check_service
