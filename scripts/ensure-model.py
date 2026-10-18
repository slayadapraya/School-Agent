#!/usr/bin/env python3
"""Start the configured, already-downloaded local model without shell interpolation."""

import json
import os
import shutil
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
cfg = json.loads((root / "config/settings.json").read_text())
lms = (
    os.environ.get("LMS_BIN")
    or shutil.which("lms")
    or str(Path.home() / ".lmstudio/bin/lms")
)
subprocess.run([lms, "server", "start"], check=True, stdout=subprocess.DEVNULL)
loaded = json.loads(subprocess.check_output([lms, "ps", "--json"]))
if not any(m.get("identifier") == cfg["model"] for m in loaded):
    subprocess.run(
        [
            lms,
            "load",
            cfg.get("model_key", "qwen/qwen3.5-4b"),
            "--gpu",
            "max",
            "--context-length",
            str(cfg.get("context_length", 4096)),
            "--parallel",
            "1",
            "--identifier",
            cfg["model"],
            "--yes",
        ],
        check=True,
    )
