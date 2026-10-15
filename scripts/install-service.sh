#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "$0")/.." && pwd)"
unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$unit_dir"
python3 - "$project_dir" "$unit_dir/school-agent.service" <<'PY'
import sys
from pathlib import Path
project=Path(sys.argv[1]);target=Path(sys.argv[2])
def quote(s):return '"'+str(s).replace('\\','\\\\').replace('"','\\"').replace('%','%%')+'"'
target.write_text('[Unit]\nDescription=School Agent local tutoring pilot\nAfter=network.target\n\n[Service]\nType=simple\nWorkingDirectory='+str(project).replace('%','%%')+'\nExecStartPre=-'+quote(project/'scripts/start-model.sh')+'\nExecStart='+quote(project/'scripts/start.sh')+'\nRestart=on-failure\nRestartSec=4\nTimeoutStartSec=120\nUMask=0077\nNoNewPrivileges=true\n\n[Install]\nWantedBy=default.target\n')
PY
systemctl --user daemon-reload
systemctl --user enable --now school-agent.service
