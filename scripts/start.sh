#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
exec python3 -m app.server --port "${SCHOOL_AGENT_PORT:-8137}"
