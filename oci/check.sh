#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.."

docker compose -f oci/compose.yml ps
for port in 18080 18081; do
  echo
  echo "=== localhost:${port}/health ==="
  if ! curl --fail --show-error --silent --max-time 8 "http://127.0.0.1:${port}/health"; then
    echo "CHECK FAILED for ${port}" >&2
    exit 1
  fi
done
echo
echo "Both endpoints answered /health. Playback and resource tests are still required before switching."
