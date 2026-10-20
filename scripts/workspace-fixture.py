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

        def fixture_answer(course, message, history, *args, **kwargs):
            if "activity-test" in message:
                import time

                for phase in ("planning", "drafting", "reviewing"):
                    s.generation_control.report(phase)
                    s.generation_control.model_started()
                    for _ in range(6):
                        s.generation_control.model_chunk()
                        time.sleep(0.15)
                    s.generation_control.model_finished()
                return (
                    "A wave carries energy while the material itself oscillates around its resting position.",
                    {"mode": "guided", "route": "demo", "sources": []},
                )
            if "artifact-test" in message:
                return (
                    'Here are the requested files.\n\n```html filename=demo.html\n<link rel="stylesheet" href="demo.css"><h1>Artifact preview</h1><button onclick="document.getElementById(\'details\').hidden=false">Show details</button><section id="details" hidden>Another section</section><script>document.body.dataset.executed="yes";try { parent.document.body.dataset.previewEscaped="yes"; } catch (error) { document.body.dataset.isolated="yes"; }</script>\n```\n\n```python filename=hello.py\nprint("Hello from a file")\n```\n\n```css filename=demo.css\nh1 { color: rgb(25, 120, 80); }\n```',
                    {
                        "mode": "configured",
                        "route": "configured_tutoring",
                        "sources": [],
                    },
                )
            return "A synthetic UI-test reply.", {
                "mode": "guided",
                "route": "configured_tutoring",
                "sources": [],
            }

        with (
            patch.object(s.model_manager, "prepare", return_value=model),
            patch.object(
                s,
                "answer",
                side_effect=fixture_answer,
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
