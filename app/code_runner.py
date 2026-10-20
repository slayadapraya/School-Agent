"""Opt-in, single-job container execution. Never falls back to a host shell.

Administrators configure pre-pulled images in settings. No image downloads happen
in a request. A failed/missing daemon leaves generation and downloads available.
"""

import os
import secrets
import selectors
import time
import subprocess
import tempfile
import threading
from pathlib import Path

LOCK = threading.Lock()
IMAGES = {
    "python": ("python:3.12-alpine", ["python", "-B", "/work/main.py"], "py"),
    "javascript": ("node:22-alpine", ["node", "/work/main.js"], "js"),
    "py": ("python:3.12-alpine", ["python", "-B", "/work/main.py"], "py"),
    "js": ("node:22-alpine", ["node", "/work/main.js"], "js"),
}


def run(s, user, row):
    if not s.permission(user, "run_code") or not s.permission(user, "generate_files"):
        raise s.APIError(403, "Code execution permission is required")
    if s.settings().get("code_execution_enabled") is not True:
        raise s.APIError(
            503,
            "Code execution is not enabled. Files can still be edited, previewed and downloaded.",
        )
    if row["language"] not in IMAGES:
        raise s.APIError(400, "The runner supports Python and JavaScript only")
    if not LOCK.acquire(blocking=False):
        raise s.APIError(429, "Another code run is in progress. Try again shortly.")
    name = "school-artifact-" + secrets.token_hex(8)
    try:
        image, command, suffix = IMAGES[row["language"]]
        with tempfile.TemporaryDirectory(prefix="school-artifact-") as directory:
            # The container's unprivileged user needs read access to this one file.
            os.chmod(directory, 0o755)
            file = Path(directory) / ("main." + suffix)
            file.write_text(row["content"], encoding="utf-8")
            file.chmod(0o644)
            args = [
                "docker",
                "run",
                "--rm",
                "--pull=never",
                "--name",
                name,
                "--network=none",
                "--read-only",
                "--log-driver=none",
                "--user=65534:65534",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--memory=128m",
                "--memory-swap=128m",
                "--cpus=0.5",
                "--pids-limit=32",
                "--ulimit",
                "nofile=64:64",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=16m",
                "--mount",
                f"type=bind,src={directory},dst=/work,readonly",
                "--workdir=/work",
                image,
                *command,
            ]
            # Drain a pipe incrementally: output is capped in RAM and cannot fill disk.
            process = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )
            raw = bytearray()
            timed_out = False
            truncated = False
            deadline = time.monotonic() + 8
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    while selector.get_map():
                        if time.monotonic() >= deadline:
                            timed_out = True
                            break
                        for event, _ in selector.select(timeout=0.1):
                            chunk = os.read(event.fileobj.fileno(), 4096)
                            if not chunk:
                                selector.unregister(event.fileobj)
                                continue
                            remaining = 32768 - len(raw)
                            raw.extend(chunk[:remaining])
                            if len(chunk) > remaining:
                                truncated = True
                                break
                        if truncated:
                            break
                if not timed_out and not truncated:
                    try:
                        process.wait(timeout=max(0.05, deadline - time.monotonic()))
                    except subprocess.TimeoutExpired:
                        timed_out = True
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=2)
                process.stdout.close()
            s.audit(user["id"], "run_generated_file", row["id"])
            return {
                "output": raw[:32768].decode("utf-8", errors="replace"),
                "truncated": truncated,
                "exit_code": process.returncode,
                "timed_out": timed_out,
            }
    except (OSError, subprocess.SubprocessError):
        raise s.APIError(
            503,
            "The container runner is unavailable. Ask an administrator to check Docker.",
        )
    finally:
        try:
            subprocess.run(
                ["docker", "rm", "-f", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pass
        LOCK.release()
