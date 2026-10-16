"""Bounded, private diagnostic entries; deliberately exclude request and model text."""

import datetime
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import re
import subprocess
import traceback


class PrivateErrorFormatter(logging.Formatter):
    def format(self, record):
        frames = traceback.extract_tb(record.exc_info[2]) if record.exc_info else []
        # Do not serialize exception arguments, local variables, request bodies or source lines.
        entry = {
            "time": datetime.datetime.fromtimestamp(
                record.created, datetime.timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "summary": record.getMessage()[:300],
            "type": record.exc_info[0].__name__ if record.exc_info else "",
            "frames": [f"{f.filename}:{f.lineno} in {f.name}" for f in frames[-14:]],
        }
        return json.dumps(entry, ensure_ascii=False)


def configure(state):
    logger = logging.getLogger("school_agent")
    if any(getattr(h, "school_error_log", False) for h in logger.handlers):
        return
    path = state / "errors.jsonl"
    path.touch(mode=0o600, exist_ok=True)
    os.chmod(path, 0o600)
    handler = RotatingFileHandler(
        path, maxBytes=512_000, backupCount=2, encoding="utf-8"
    )
    handler.school_error_log = True
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(PrivateErrorFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)


def read(s, user):
    if user["role"] != "admin":
        raise s.APIError(403, "Administrator access required")
    entries = []
    # Include rotated application diagnostics and service stdout/stderr across restarts.
    for name in ("errors.jsonl.2", "errors.jsonl.1", "errors.jsonl"):
        path = s.STATE / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    entries.append(item)
            except ValueError:
                continue
    journal_available = True
    try:
        result = subprocess.run(
            [
                "journalctl",
                "--user",
                "-u",
                "school-agent.service",
                "-n",
                "1000",
                "--no-pager",
                "-o",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        )
        levels = {
            "0": "CRITICAL",
            "1": "CRITICAL",
            "2": "CRITICAL",
            "3": "ERROR",
            "4": "WARNING",
            "5": "INFO",
            "6": "INFO",
            "7": "DEBUG",
        }
        for line in result.stdout.splitlines():
            try:
                row = json.loads(line)
                message = row.get("MESSAGE", "")
                if not isinstance(message, str):
                    continue
                message = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", message).strip()
                # Suppress access-log noise, not errors which happen to mention GET.
                if re.match(
                    r'^(?:\S+ - - .*?)?["\[]?(GET|HEAD|OPTIONS) /\S* HTTP/', message
                ):
                    continue
                if not message:
                    continue
                stamp = datetime.datetime.fromtimestamp(
                    int(row["__REALTIME_TIMESTAMP"]) / 1e6, datetime.timezone.utc
                ).isoformat()
                entries.append(
                    {
                        "time": stamp,
                        "level": levels.get(row.get("PRIORITY"), "INFO"),
                        "type": "Service",
                        "summary": message[:300],
                        "frames": [message[300:12000]] if len(message) > 300 else [],
                    }
                )
            except (ValueError, KeyError, TypeError):
                continue
    except (OSError, subprocess.SubprocessError):
        journal_available = False
    entries.sort(key=lambda item: item.get("time", ""))
    return {
        "entries": entries[-1000:],
        "limit": 1000,
        "journal_available": journal_available,
    }
