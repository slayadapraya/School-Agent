#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "$0")/.." && pwd)"
python3 - "$project_dir" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1]);p=root/'config/settings.json';cfg=json.loads(p.read_text());cfg.update(public_listener_enabled=True,public_listener_port=8138);p.write_text(json.dumps(cfg,indent=2)+'\n')
PY
systemctl --user restart school-agent.service
tailscale funnel --bg --https=8443 --yes http://127.0.0.1:8138
