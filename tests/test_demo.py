"""The public demo installs known logins only in a separate, synthetic workspace."""

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import test_administration as fixtures
from app import demo
from app import server as s


class DemoWorkspace(unittest.TestCase):
    request = fixtures.Administration.request

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = s.STATE, s.DB
        self.directory = Path(self.tmp.name) / "demo"
        demo.seed(self.directory)
        self.http = s.Server(("127.0.0.1", 0))
        self.http.RequestHandlerClass = demo.DemoHandler
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        s.STATE, s.DB = self.old
        self.tmp.cleanup()

    def login_demo(self, username):
        password = next(p for _, _, u, p in demo.DEMO_ACCOUNTS if u == username)
        code, data, cookie = self.request(
            "/api/login", {"username": username, "password": password}
        )
        self.assertEqual(code, 200, data)
        return cookie.split(";")[0]

    def test_all_documented_logins_and_demo_banner(self):
        text = (s.ROOT / "DEMO_LOGINS.txt").read_text()
        for _, role, username, password in demo.DEMO_ACCOUNTS:
            self.assertIn(username, text)
            self.assertIn(password, text)
            cookie = self.login_demo(username)
            code, boot, _ = self.request("/api/bootstrap", cookie=cookie)
            self.assertEqual(code, 200)
            self.assertEqual(boot["user"]["role"], role)
            self.assertTrue(boot["demo"])
        with s.connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM users").fetchone()[0], 5)

    def test_teacher_roster_and_student_record_boundaries(self):
        teacher = self.login_demo("demo.teacher")
        notes = self.request("/api/staff/notes", cookie=teacher)[1]["notes"]
        self.assertEqual(
            {n["student"] for n in notes}, {"Demo student Alex", "Demo student Sam"}
        )
        student = self.login_demo("demo.student1")
        self.assertEqual(self.request("/api/staff/notes", cookie=student)[0], 403)
        with s.connect() as con:
            other = con.execute(
                "SELECT t.id FROM threads t JOIN users u ON u.id=t.user_id WHERE u.username='demo.student3'"
            ).fetchone()[0]
        self.assertEqual(self.request("/api/threads/" + other, cookie=student)[0], 404)
        self.assertEqual(self.request("/api/admin/management", cookie=teacher)[0], 403)

    def test_public_demo_admin_password_cannot_open_a_host_terminal(self):
        admin = self.login_demo("demo.admin")
        with patch.object(s.host_terminal, "handle") as shell:
            self.assertEqual(
                self.request(
                    "/api/admin/terminal",
                    {"action": "open", "password": "DemoAdmin-2026!"},
                    admin,
                )[0],
                403,
            )
            self.assertEqual(
                self.request("/api/admin/terminal/stream", cookie=admin)[0], 403
            )
            shell.assert_not_called()

    def test_restarting_seed_preserves_demo_edits(self):
        with s.connect() as con:
            con.execute("UPDATE chat_notes SET body='Retained demo edit'")
        demo.seed(self.directory)
        with s.connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM users").fetchone()[0], 5)
            self.assertEqual(
                con.execute("SELECT body FROM chat_notes LIMIT 1").fetchone()[0],
                "Retained demo edit",
            )

    def test_seed_refuses_live_or_existing_non_demo_directories(self):
        occupied = Path(self.tmp.name) / "existing"
        occupied.mkdir()
        (occupied / "keep.txt").write_text("Keep this file")
        with self.assertRaises(ValueError):
            demo.seed(occupied)
        self.assertEqual((occupied / "keep.txt").read_text(), "Keep this file")
        with self.assertRaises(ValueError):
            demo.seed(s.ROOT / ".local")
        self.assertEqual(s.DB, self.directory / "school.sqlite3")

    def test_normal_startup_does_not_install_demo_passwords(self):
        s.STATE = Path(self.tmp.name) / "ordinary"
        s.DB = s.STATE / "ordinary.sqlite"
        s.init()
        with s.connect() as con:
            names = {r[0] for r in con.execute("SELECT username FROM users")}
        self.assertTrue(names.isdisjoint({u for _, _, u, _ in demo.DEMO_ACCOUNTS}))

    def test_demo_admin_subject_changes_only_update_demo_configuration(self):
        original = (s.ROOT / "config/courses.json").read_bytes()
        config_root = demo.isolated_config(self.directory)
        admin = self.login_demo("demo.admin")
        with patch.object(s, "ROOT", config_root):
            code, data, _ = self.request(
                "/api/admin/subjects",
                {"id": "DEMOX", "name": "Demo-only subject"},
                admin,
            )
            self.assertEqual(code, 200, data)
            self.assertTrue(any(c["id"] == "DEMOX101" for c in s.courses()))
        self.assertEqual((s.ROOT / "config/courses.json").read_bytes(), original)
        self.assertFalse(any(c["id"] == "DEMOX101" for c in s.courses()))
