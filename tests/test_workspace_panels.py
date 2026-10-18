"""Permanent Notes migration and authenticated inline document regression tests.

Each case runs against the disposable HTTP/SQLite fixture, never live accounts.
"""

import base64
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import test_administration as fixtures
from app import server as s

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluation_fixtures import pdf


class WorkspacePanels(unittest.TestCase):
    setUp = fixtures.Administration.setUp
    tearDown = fixtures.Administration.tearDown
    request = fixtures.Administration.request
    login = fixtures.Administration.login

    def new_thread(self, cookie):
        code, data, _ = self.request(
            "/api/threads", {"course_id": "GENERAL", "title": "Pocket test"}, cookie
        )
        self.assertEqual(code, 201)
        return data["id"]

    def download(self, path, cookie):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.http.server_port}{path}",
            headers={"Cookie": cookie},
        )
        return urllib.request.urlopen(request)

    def test_notes_remain_available_when_legacy_flag_is_disabled(self):
        owner = self.login("student")
        with s.connect() as con:
            con.execute("UPDATE experimental_features SET enabled=0 WHERE name='notes'")
        self.assertTrue(self.request("/api/features", cookie=owner)[1]["notes"])
        tid = self.new_thread(owner)
        notes = self.request("/api/notes", cookie=owner)[1]["notes"]
        self.assertEqual(len(notes), 1)
        note = notes[0]
        self.assertEqual(note["thread_id"], tid)
        code, saved, _ = self.request(
            "/api/notes/" + note["id"],
            {
                "title": "Frequency",
                "body": "Measured in hertz",
                "version": note["version"],
            },
            owner,
        )
        self.assertEqual(code, 200)
        context = s.notes.model_context(s, self.people["student"], tid, "frequency")
        self.assertIn("Measured in hertz", str(context))
        self.assertEqual(self.request("/api/notes", {"thread_id": tid}, owner)[0], 200)
        self.assertEqual(
            self.request("/api/notes/" + note["id"], cookie=self.login("other"))[0], 404
        )

    def test_retired_toggle_cannot_disable_notes_or_bypass_admin_access(self):
        payload = {"name": "notes", "enabled": False}
        self.assertEqual(
            self.request("/api/features", payload, self.login("student"))[0], 403
        )
        self.assertEqual(
            self.request("/api/features", payload, self.login("admin"))[0], 400
        )
        self.assertTrue(s.notes.features(s)["notes"])

    def test_pdf_inline_preview_keeps_ownership_and_download_headers(self):
        owner, other = self.login("student"), self.login("other")
        tid = self.new_thread(owner)
        body = pdf(["First page: waves", "Second page: frequency"])
        code, file, _ = self.request(
            "/api/files",
            {
                "thread_id": tid,
                "name": "Waves.pdf",
                "data": base64.b64encode(body).decode(),
            },
            owner,
        )
        self.assertEqual(code, 201)
        listing = self.request("/api/threads/" + tid, cookie=owner)[1]["files"]
        self.assertEqual(listing[0]["mime"], "application/pdf")
        with self.download(file["url"] + "?inline=1", owner) as response:
            self.assertEqual(response.headers["Content-Type"], "application/pdf")
            self.assertTrue(
                response.headers["Content-Disposition"].startswith("inline;")
            )
            self.assertIn(
                "frame-ancestors 'self'", response.headers["Content-Security-Policy"]
            )
            self.assertEqual(response.read(), body)
        with self.download(file["url"], owner) as response:
            self.assertTrue(
                response.headers["Content-Disposition"].startswith("attachment;")
            )
            self.assertIn(
                "frame-ancestors 'none'", response.headers["Content-Security-Policy"]
            )
        with self.assertRaises(urllib.error.HTTPError) as denied:
            self.download(file["url"] + "?inline=1", other)
        self.assertEqual(denied.exception.code, 404)
        denied.exception.close()

    def test_text_documents_cannot_be_loaded_as_active_inline_content(self):
        owner = self.login("student")
        tid = self.new_thread(owner)
        code, file, _ = self.request(
            "/api/files",
            {
                "thread_id": tid,
                "name": "plain.txt",
                "data": base64.b64encode(b"<script>bad()</script>").decode(),
            },
            owner,
        )
        self.assertEqual(code, 201)
        with self.download(file["url"] + "?inline=1", owner) as response:
            self.assertTrue(
                response.headers["Content-Disposition"].startswith("attachment;")
            )
            self.assertIn(
                "frame-ancestors 'none'", response.headers["Content-Security-Policy"]
            )
