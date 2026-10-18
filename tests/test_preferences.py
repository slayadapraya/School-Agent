import base64
import unittest
from unittest.mock import patch
from app import server as s, preferences as p, model_manager as mm
from test_administration import Administration


class PreferencesHTTP(unittest.TestCase):
    setUp = Administration.setUp
    tearDown = Administration.tearDown
    request = Administration.request
    login = Administration.login

    def test_prompts_roles_and_save(self):
        a = self.login("teach")
        b = self.login("student")
        self.assertEqual(self.request("/api/preferences/prompts", cookie=b)[0], 403)
        self.assertEqual(
            self.request(
                "/api/preferences/prompts",
                {"name": "student-tutor.txt", "text": "Use short hints."},
                a,
            )[0],
            200,
        )
        self.assertEqual(p.prompt(s, "student-tutor.txt"), "Use short hints.")

    def test_memories_isolation_and_delete(self):
        a = self.login("student")
        b = self.login("other")
        m = self.request(
            "/api/preferences/memories",
            {"text": "I study engineering", "category": "degree"},
            a,
        )[1]["memories"][0]
        self.assertEqual(
            self.request("/api/preferences/memories", cookie=b)[1]["memories"], []
        )
        self.assertEqual(
            self.request(
                "/api/preferences/memories", {"id": m["id"], "text": "Hijack"}, b
            )[0],
            404,
        )
        self.request(
            "/api/preferences/memories", {"action": "toggle", "enabled": False}, a
        )
        self.assertEqual(p.profile(s, self.people["student"]), [])
        self.request(
            "/api/preferences/memories", {"action": "delete", "id": m["id"]}, a
        )
        self.assertEqual(
            self.request("/api/preferences/memories", cookie=a)[1]["memories"], []
        )

    def test_file_context_and_access(self):
        a = self.login("student")
        b = self.login("other")
        tid = self.request("/api/threads", {"course_id": "GENERAL"}, a)[1]["id"]
        code, f, _ = self.request(
            "/api/files",
            {
                "thread_id": tid,
                "name": "course.txt",
                "data": base64.b64encode(b"Engineering turbines").decode(),
            },
            a,
        )
        self.assertEqual(code, 201)
        self.assertEqual(
            self.request(f["url"] + "?preview=1", cookie=a)[1]["text"],
            "Engineering turbines",
        )
        self.assertEqual(self.request(f["url"] + "?preview=1", cookie=b)[0], 404)
        with s.connect() as con:
            self.assertIn("turbines", s.files.context(con, tid))

    def test_admin_models_only_blank_and_role_scope(self):
        inventory = {
            "models": [
                {
                    "key": "qwen3.5-9b",
                    "type": "llm",
                    "loaded_instances": [{"id": "main-instance"}],
                    "architecture": "qwen35",
                },
                {
                    "key": "dolphin",
                    "type": "llm",
                    "loaded_instances": [],
                    "architecture": "llama",
                },
            ]
        }
        admin = self.login("admin")
        for name in ("student", "teach"):
            self.assertEqual(
                self.request("/api/admin/models", cookie=self.login(name))[0], 403
            )
        with patch.object(mm, "request", return_value=inventory):
            self.assertEqual(
                self.request("/api/admin/models", cookie=admin)[1]["initial_prompts"],
                {},
            )
            r = self.request(
                "/api/admin/models",
                {"model": "dolphin", "initial_prompt": "Be concise", "select": True},
                admin,
            )
            self.assertEqual(r[0], 200)
            self.assertTrue(r[1]["pending"])
        with patch.object(mm, "request", return_value=inventory):
            self.assertEqual(
                mm.chosen(s, self.people["student"], "x", True), ("qwen3.5-9b", "")
            )
            self.assertEqual(
                mm.chosen(s, self.people["admin"], "x", True), ("dolphin", "Be concise")
            )
            with self.assertRaises(s.APIError):
                mm.chosen(s, self.people["admin"], "x", False)
