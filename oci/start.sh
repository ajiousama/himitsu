#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.."

if [ "$(uname -m)" != "aarch64" ]; then
  echo "STOP: this preparation targets Oracle Ampere A1 (arm64/aarch64)." >&2
  exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "STOP: install Docker Engine and Docker Compose plugin first." >&2
  exit 1
fi
docker compose version
docker compose -f oci/compose.yml up -d --build
docker compose -f oci/compose.yml ps
echo "Test locally: http://127.0.0.1:18080/health and http://127.0.0.1:18081/health"
