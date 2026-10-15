#!/usr/bin/env bash
set -euo pipefail
# Restore this application's original private route; preserve other ports/services.
tailscale funnel --https=8443 off
tailscale serve --bg --https=8443 --yes http://127.0.0.1:8137
