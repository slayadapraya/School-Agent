#!/usr/bin/env python3
"""Disposable browser-test server. Never reads the installed application's state.

Binds an OS-selected loopback port, creates synthetic accounts and a small teaching
PDF, then prints connection details as one JSON line. Termination removes its state.
"""

import base64
import json
import signal
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from app import server as s
from evaluation_fixtures import PHYSICS_PAGES, pdf


def main():
    with tempfile.TemporaryDirectory(prefix="school-workspace-ui-") as directory:
        s.STATE = Path(directory)
        s.DB = s.STATE / "test.sqlite"
        s.init()
        password = "Workspace-Tests-Only-7391"
        with s.connect() as con:
            con.execute(
                "UPDATE users SET password_hash=? WHERE username IN ('admin','student')",
                (s.password_hash(password),),
            )
            con.execute(
                "UPDATE users SET name='Test administrator' WHERE username='admin'"
            )
            con.execute("UPDATE users SET name='Test student' WHERE username='student'")
            admin = dict(
                con.execute("SELECT * FROM users WHERE username='admin'").fetchone()
            )
        s.add_account("Test second student", "student", "second", password)
        # Publish a source fixture directly using the same authenticated module path.
        s.course_materials.upload(
            s,
            admin,
            {
                "course_id": "MATH101",
                "name": "Waves lecture.pdf",
                "data": base64.b64encode(pdf(PHYSICS_PAGES)).decode(),
                "class_id": None,
            },
        )
        model = {
            "key": "test",
            "instance": "test",
            "transport": "qwen_chatml",
            "initial_prompt": "",
            "private_model": False,
        }
        with (
            patch.object(s.model_manager, "prepare", return_value=model),
            patch.object(
                s,
                "answer",
                return_value=(
                    "A synthetic UI-test reply.",
                    {"mode": "guided", "route": "configured_tutoring", "sources": []},
                ),
            ),
            patch.object(
                s, "read_question", return_value="A synthetic image transcription."
            ),
        ):
            http = s.Server(("127.0.0.1", 0))

            def stop(*_):
                threading.Thread(target=http.shutdown, daemon=True).start()

            signal.signal(signal.SIGTERM, stop)
            signal.signal(signal.SIGINT, stop)
            print(
                json.dumps(
                    {
                        "url": f"http://127.0.0.1:{http.server_port}",
                        "password": password,
                    }
                ),
                flush=True,
            )
            try:
                http.serve_forever()
            finally:
                http.server_close()


if __name__ == "__main__":
    main()
