"""Isolated, synthetic demonstration data and a loopback-only demo server.

Nothing in this module is imported by the normal server startup. Public demo
passwords are installed only into an empty, explicitly marked demo directory.
"""

from __future__ import annotations

import base64
import json
import secrets
import shutil
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from . import server as s

DEMO_ACCOUNTS = [
    ("Demo administrator", "admin", "demo.admin", "DemoAdmin-2026!"),
    ("Demo teacher", "teacher", "demo.teacher", "DemoTeacher-2026!"),
    ("Demo student Alex", "student", "demo.student1", "DemoStudent1-2026!"),
    ("Demo student Sam", "student", "demo.student2", "DemoStudent2-2026!"),
    ("Demo student Morgan", "student", "demo.student3", "DemoStudent3-2026!"),
]
MARKER = "school-agent-synthetic-demo-v1"


def seed(directory: Path):
    """Create sample data once. Refuse an existing database without our demo marker."""
    directory = directory.resolve()
    marker = directory / "demo-manifest.json"
    if directory == (s.ROOT / ".local").resolve():
        raise ValueError("The live .local directory cannot be used for the demo")
    if marker.exists():
        if json.loads(marker.read_text()).get("seed") != MARKER:
            raise ValueError("This directory is not a School Agent demo")
        s.STATE, s.DB = directory, directory / "school.sqlite3"
        if not s.DB.is_file():
            raise ValueError(
                "The demo database is missing; choose a fresh demo directory"
            )
        s.init()
        return
    if directory.exists() and any(directory.iterdir()):
        raise ValueError(
            "Demo setup requires an empty directory; existing files are untouched"
        )
    s.STATE, s.DB = directory, directory / "school.sqlite3"
    s.init()
    # These are only the random bootstrap accounts in the brand-new demo database.
    with s.connect() as con:
        con.execute("DELETE FROM users")
    for name, role, username, password in DEMO_ACCOUNTS:
        permissions = s.default_permissions(role)
        if role == "teacher":
            permissions.update(courses=["MATH101", "PHYS101"], manage_courses=False)
        s.add_account(name, role, username, password, permissions)
    now = time.time()
    with s.connect() as con:
        users = {r["username"]: dict(r) for r in con.execute("SELECT * FROM users")}
        for name, codes, members in [
            (
                "Foundations of maths and physics",
                ["MATH101", "PHYS101"],
                ["demo.teacher", "demo.student1", "demo.student2"],
            ),
            ("History seminar", ["HIST101"], ["demo.student3"]),
        ]:
            group = con.execute(
                "INSERT INTO classes(name,description,courses,policy,enabled) VALUES(?,?,?,?,1)",
                (name, "Synthetic demonstration class", json.dumps(codes), "{}"),
            ).lastrowid
            con.executemany(
                "INSERT INTO class_members VALUES(?,?)",
                [(group, users[u]["id"]) for u in members],
            )
        examples = [
            (
                "demo.admin",
                "GENERAL",
                "Planning a teaching workspace",
                "What can I manage here?",
                "Use People for accounts and individual policies, Classes for groups, and Activity & history for authorised student records. These are synthetic demonstration records.",
            ),
            (
                "demo.teacher",
                "PHYS101",
                "Preparing a waves lesson",
                "Help me plan an introduction to waves.",
                "Start with a moving rope, then compare wavelength, frequency and period. Ask students to describe what travels along the rope and what stays in place.",
            ),
            (
                "demo.student1",
                "PHYS101",
                "Understanding frequency and period",
                "I do not understand the difference between frequency and period.",
                "Frequency counts complete cycles per second, measured in hertz. Period is the time for one complete cycle, measured in seconds. Try counting cycles in a short repeating motion.",
            ),
            (
                "demo.student1",
                "MATH101",
                "What squared means",
                "What does squared mean?",
                "Squaring means multiplying a quantity by itself. Draw a square with equal side lengths to connect that operation to its area.",
            ),
            (
                "demo.student2",
                "PHYS101",
                "Comparing waves",
                "What should I notice when comparing two waves?",
                "Compare amplitude, wavelength and frequency. Describe each feature separately before deciding how the waves differ.",
            ),
            (
                "demo.student3",
                "HIST101",
                "Planning a history question",
                "How do I narrow a history research question?",
                "Choose a period, place and issue. Separate the sequence of events from explanations, then compare the claims in two sources.",
            ),
        ]
        for index, (username, course, title, question, reply) in enumerate(examples):
            tid = secrets.token_hex(16)
            user = users[username]
            created = now - (index % 3) * 86400 - 120
            con.execute(
                "INSERT INTO threads VALUES(?,?,?,?,?)",
                (tid, user["id"], course, title, created),
            )
            s.notes.create_initial(con, user, tid)
            for role, content in [("user", question), ("assistant", reply)]:
                con.execute(
                    "INSERT INTO messages(thread_id,role,content,meta,created) VALUES(?,?,?,?,?)",
                    (
                        tid,
                        role,
                        content,
                        json.dumps(
                            {
                                "mode": "guided",
                                "route": "demo",
                                "sources": [],
                                "demo": True,
                            }
                        ),
                        created,
                    ),
                )
            con.execute(
                "UPDATE chat_notes SET title=?,body=? WHERE thread_id=?",
                (
                    "My study notes",
                    "Sample note: key terms, questions to revisit, and useful evidence.",
                    tid,
                ),
            )
    s.course_materials.upload(
        s,
        users["demo.admin"],
        {
            "course_id": "PHYS101",
            "class_id": None,
            "name": "Demo wave concepts.txt",
            "data": base64.b64encode(
                b"Frequency counts complete cycles per second and is measured in hertz.\n\nPeriod is the time for one complete cycle. Wavelength is the distance between equivalent points on neighbouring cycles."
            ).decode(),
        },
    )
    # Replace the now-obsolete random bootstrap login file with the public demo logins.
    (directory / "credentials.json").write_text(
        json.dumps(
            {u: {"username": u, "password": p} for _, _, u, p in DEMO_ACCOUNTS},
            indent=2,
        )
    )
    marker.write_text(json.dumps({"seed": MARKER, "synthetic": True}, indent=2))
    for file in [marker, directory / "credentials.json"]:
        file.chmod(0o600)


def isolated_config(directory: Path):
    """Give demo administrators editable configuration without changing normal files."""
    target = Path(directory) / "config"
    if not target.exists():
        shutil.copytree(s.ROOT / "config", target)
    return Path(directory)


class DemoHandler(s.Handler):
    """Keep the normal access checks while disabling the host shell in public demos."""

    def respond(self, status, value, headers=None):
        if urlsplit(self.path).path == "/api/bootstrap" and status == 200:
            value = {**value, "demo": True}
        return super().respond(status, value, headers)

    def demo_terminal_blocked(self):
        if urlsplit(self.path).path.startswith("/api/admin/terminal"):
            user = self.user()
            if user["role"] != "admin":
                raise s.APIError(403, "Administrator access required")
            raise s.APIError(403, "Host terminal is disabled in the demo workspace")

    def get(self):
        self.demo_terminal_blocked()
        return super().get()

    def post(self):
        self.demo_terminal_blocked()
        return super().post()


def demo_reply(course, message, history, *args, **kwargs):
    """Clearly labelled sample replies let the interface run without model weights."""
    text = "This is a sample demo reply, not a live model response. Explore the seeded conversations for examples, try Notes and Files, or use the administrator account to manage the synthetic classes and policies. Normal server startup connects to your configured local model."
    return text, {"mode": "guided", "route": "demo", "sources": [], "demo": True}


def run(port=8140, directory=None):
    directory = Path(directory) if directory else s.ROOT / ".demo"
    config = {
        **s.settings(),
        "institution": "School Agent · Demo",
        "public_listener_enabled": False,
        "code_execution_enabled": False,
        "model_key": "demo-responder",
        "model": "demo-responder",
    }
    model = {
        "key": "demo-responder",
        "instance": "demo-responder",
        "transport": "qwen_chatml",
        "initial_prompt": "",
        "private_model": False,
    }
    with ExitStack() as stack:
        stack.enter_context(patch.object(s, "settings", return_value=config))
        seed(directory)
        config_root = isolated_config(directory)
        stack.enter_context(patch.object(s, "ROOT", config_root))
        stack.enter_context(
            patch.object(s.model_manager, "prepare", return_value=model)
        )
        stack.enter_context(
            patch.object(
                s.model_manager,
                "request",
                return_value={
                    "models": [
                        {
                            "key": "demo-responder",
                            "display_name": "Demo responder (sample replies)",
                            "type": "llm",
                            "loaded_instances": [],
                        }
                    ]
                },
            )
        )
        stack.enter_context(patch.object(s, "answer", side_effect=demo_reply))
        stack.enter_context(
            patch.object(
                s,
                "read_question",
                return_value="Demo image: live transcription is not connected.",
            )
        )
        http = s.Server(("127.0.0.1", port))
        http.RequestHandlerClass = DemoHandler
        print(
            f"Demo workspace: http://127.0.0.1:{http.server_port} — logins: DEMO_LOGINS.txt",
            flush=True,
        )
        try:
            http.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            http.server_close()
