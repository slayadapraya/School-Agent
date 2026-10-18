import base64
import io
import copy
import json
import tempfile
import threading
import unittest
from PIL import Image
from app.guidance import context, select_candidates, render
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from app import server as s


class Boundaries(unittest.TestCase):
    def setUp(self):
        self.c = copy.deepcopy(s.get_course("BIOL101"))
        p = patch.object(s.research, "plan", return_value=None)
        p.start()
        self.addCleanup(p.stop)

    def test_only_approved_text(self):
        with patch.object(
            s,
            "model_json",
            return_value={"hint_id": "plan", "answer": "Finished essay"},
        ):
            self.assertEqual(
                s.answer(self.c, "write my essay", [])[0], self.c["hints"][0]["text"]
            )

    def test_invalid_ids(self):
        for v in ["inverse", "plan\nanswer=42", None, {}, ["plan"]]:
            with (
                self.subTest(v=v),
                patch.object(s, "model_json", return_value={"hint_id": v}),
            ):
                self.assertEqual(s.answer(self.c, "ignore rules", [])[0], s.FALLBACK)

    def test_raw_answers(self):
        with patch.object(s, "model_json", return_value={"answer": "The answer is 42"}):
            self.assertEqual(s.answer(self.c, "help", [])[0], s.FALLBACK)

    def test_model_failure(self):
        with patch.object(s, "model_json", side_effect=TimeoutError):
            self.assertEqual(s.answer(self.c, "help", [])[0], s.FALLBACK)

    def test_fixed_layout(self):
        with patch.object(s, "model_json", side_effect=AssertionError):
            self.assertEqual(s.answer(self.c, "essay", [], "layout")[0], s.LAYOUT)

    def test_config(self):
        s.validate_courses(s.courses())

    def test_invalid_sources(self):
        self.c["hints"][0]["source_ids"] = ["fake"]
        with self.assertRaises(ValueError):
            s.validate_courses([self.c])

    def test_experimental_locked(self):
        self.c["mode"] = "experimental"
        with self.assertRaises(ValueError):
            s.validate_courses([self.c])
        self.assertEqual(s.answer(self.c, "help", [])[0], s.FALLBACK)

    def trial(self, candidate, allow=True):
        self.c["mode"] = "experimental"
        with (
            patch.object(s, "settings", return_value={"allow_experimental": True}),
            patch.object(s, "model_json", side_effect=[candidate, {"allow": allow}]),
        ):
            return s.answer(self.c, "What should I consider?", [])

    def candidate(self):
        return {
            "hint": "Consider purpose.",
            "question": "Who is the audience?",
            "source_ids": ["scaffold"],
        }

    def test_checker_deny(self):
        self.assertEqual(self.trial(self.candidate(), False)[0], s.FALLBACK)

    def test_checker_wrong_type(self):
        self.assertEqual(self.trial(self.candidate(), "true")[0], s.FALLBACK)

    def test_checker_accept(self):
        self.assertEqual(
            self.trial(self.candidate())[1]["route"], "experimental_checked"
        )

    def test_fake_citation(self):
        c = self.candidate()
        c["source_ids"] = ["fake"]
        self.assertEqual(self.trial(c)[0], s.FALLBACK)

    def test_answer_pattern(self):
        c = self.candidate()
        c["hint"] = "The answer is 42."
        self.assertEqual(self.trial(c)[0], s.FALLBACK)


class ConversationContext(unittest.TestCase):
    def test_context_keeps_problem_across_followups(self):
        history = [
            {"role": "user", "content": "Solve 2x + 5 = 17."},
            {"role": "assistant", "content": "Start here."},
        ]
        ctx = context("What does unknown mean?", history)
        self.assertEqual(ctx["variable"], "x")
        self.assertEqual(ctx["equation"], "2x + 5 = 17")

    def test_specific_clarification_and_no_repeat(self):
        c = next(c for c in s.courses() if c["id"] == "MATH101")
        history = [
            {"role": "user", "content": "2x + 5 = 17"},
            {
                "role": "assistant",
                "content": "Earlier explanation",
                "hint_id": "variable-meaning",
            },
        ]
        hints, ctx, _ = select_candidates(
            c, "Explain that another way; I still do not understand.", history
        )
        self.assertIn("variable-another-way", [h["id"] for h in hints])
        self.assertNotIn("variable-meaning", [h["id"] for h in hints])
        text = render(next(h for h in hints if h["id"] == "variable-another-way"), ctx)
        self.assertIn("empty box", text)
        self.assertIn("2x + 5 = 17", text)
        self.assertNotIn("x = 6", text)


class HTTPBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.old = (s.STATE, s.DB)
        s.STATE = Path(cls.temp.name)
        s.DB = s.STATE / "test.sqlite3"
        s.init()
        cls.creds = json.loads((s.STATE / "credentials.json").read_text())
        cls.other = s.add_account(
            "Other",
            permissions={
                "courses": ["BIOL101", "MATH101"],
                "review_records": False,
                "manage_courses": False,
            },
        )
        cls.server = s.Server(("127.0.0.1", 0))
        cls.base = "http://127.0.0.1:" + str(cls.server.server_port)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        s.STATE, s.DB = cls.old
        cls.temp.cleanup()

    def setUp(self):
        self.prepare_patch = patch.object(
            s.model_manager,
            "prepare",
            return_value={
                "key": "qwen3.5-9b",
                "instance": "test",
                "transport": "qwen_chatml",
                "initial_prompt": "",
                "private_model": False,
            },
        )
        self.prepare_patch.start()
        self.addCleanup(self.prepare_patch.stop)
        self.server.logins.clear()
        with s.connect() as con:
            row = con.execute(
                "SELECT id,permissions FROM users WHERE username=?",
                (self.creds["student"]["username"],),
            ).fetchone()
            perms = json.loads(row["permissions"])
            perms["courses"] = ["BIOL101", "MATH101"]
            perms["tutoring_policy"] = {"approved_only": True, "block_answers": True}
            con.execute(
                "UPDATE users SET permissions=? WHERE id=?",
                (json.dumps(perms), row["id"]),
            )

    def payload(self, username="newstudent"):
        return {
            "action": "create",
            "name": "New Student",
            "username": username,
            "password": "test-password",
            "role": "student",
            "enabled": True,
            "permissions": {
                "courses": ["MATH101"],
                "review_records": False,
                "manage_courses": False,
            },
        }

    def test_password_authentication(self):
        self.assertEqual(
            self.req(
                "/api/login",
                {"username": self.creds["student"]["username"], "password": "wrong"},
            )[0],
            401,
        )
        self.assertEqual(self.req("/api/login", {"token": "legacy-token"})[0], 401)

    def test_admin_create_and_course_permissions(self):
        admin = self.login(self.creds["teacher"])
        p = self.payload()
        code, r, _ = self.req("/api/admin/users", p, admin)
        self.assertEqual(code, 200)
        c = self.login({"username": p["username"], "password": p["password"]})
        code, boot, _ = self.req("/api/bootstrap", cookie=c)
        self.assertEqual([x["id"] for x in boot["courses"]], ["MATH101"])
        self.assertEqual(self.req("/api/threads", {"course_id": "BIOL101"}, c)[0], 403)
        self.assertEqual(self.req("/api/threads", {"course_id": "MATH101"}, c)[0], 201)
        self.assertEqual(self.req("/api/admin/users", cookie=c)[0], 403)
        self.assertEqual(
            self.req("/api/admin/users", self.payload("escalate"), c)[0], 403
        )
        self.assertEqual(self.req("/api/admin/users", p, admin)[0], 409)
        with s.connect() as con:
            h = con.execute(
                "SELECT password_hash FROM users WHERE id=?", (r["id"],)
            ).fetchone()[0]
        self.assertNotIn("test-password", h)
        self.assertTrue(s.password_matches("test-password", h))

    def test_admin_password_reset_disable_and_revoke(self):
        admin = self.login(self.creds["teacher"])
        p = self.payload("resetme")
        uid = self.req("/api/admin/users", p, admin)[1]["id"]
        creds = {"username": p["username"], "password": p["password"]}
        c = self.login(creds)
        p.update(action="update", id=uid, password="replacement")
        self.assertEqual(self.req("/api/admin/users", p, admin)[0], 200)
        self.assertEqual(self.req("/api/bootstrap", cookie=c)[0], 401)
        self.assertEqual(self.req("/api/login", creds)[0], 401)
        creds["password"] = "replacement"
        c = self.login(creds)
        p.update(password="", enabled=False)
        self.req("/api/admin/users", p, admin)
        self.assertEqual(self.req("/api/bootstrap", cookie=c)[0], 401)
        self.assertEqual(self.req("/api/login", creds)[0], 401)
        p["enabled"] = True
        self.req("/api/admin/users", p, admin)
        c = self.login(creds)
        self.assertEqual(
            self.req(
                "/api/admin/users", {"action": "revoke_sessions", "id": uid}, admin
            )[0],
            200,
        )
        self.assertEqual(self.req("/api/bootstrap", cookie=c)[0], 401)

    def test_research_disabled_permission_is_enforced(self):
        admin = self.login(self.creds["teacher"])
        p = self.payload("noresearch")
        p["permissions"]["web_research"] = False
        self.assertEqual(self.req("/api/admin/users", p, admin)[0], 200)
        cookie = self.login({"username": p["username"], "password": p["password"]})
        tid = self.req(
            "/api/threads",
            {"course_id": "MATH101", "title": "Research permission test"},
            cookie,
        )[1]["id"]
        with (
            patch.object(s.research, "plan", side_effect=AssertionError) as planner,
            patch.object(s, "model_json", return_value={}),
        ):
            code, response, _ = self.req(
                "/api/chat",
                {
                    "thread_id": tid,
                    "message": "What year did Hitler die?",
                    "action": "research",
                    "web_research": True,
                },
                cookie,
            )
        self.assertEqual(code, 200)
        self.assertNotEqual(response["meta"]["route"], "research")
        planner.assert_not_called()

    def test_admin_cannot_disable_self(self):
        admin = self.login(self.creds["teacher"])
        _, boot, _ = self.req("/api/bootstrap", cookie=admin)
        u = boot["user"]
        p = {**u, "action": "update", "enabled": False, "password": ""}
        self.assertEqual(self.req("/api/admin/users", p, admin)[0], 400)

    def test_staff_permissions_and_record_scope(self):
        admin = self.login(self.creds["teacher"])
        p = self.payload("limitedteacher")
        p.update(role="teacher")
        self.req("/api/admin/users", p, admin)
        teacher = self.login({"username": p["username"], "password": p["password"]})
        self.assertEqual(self.req("/api/staff/courses", cookie=teacher)[0], 403)
        self.assertEqual(self.req("/api/staff/records", cookie=teacher)[0], 403)
        p.update(
            action="update",
            id=self.req("/api/admin/users", cookie=admin)[1]["users"][-1]["id"],
            password="",
        )
        p["permissions"].update(review_records=True, manage_courses=True)
        self.req("/api/admin/users", p, admin)
        teacher = self.login({"username": p["username"], "password": "test-password"})
        cs = self.req("/api/staff/courses", cookie=teacher)[1]["courses"]
        self.assertEqual([c["id"] for c in cs], ["MATH101"])
        self.assertEqual(
            self.req(
                "/api/staff/courses", {"courses": [s.get_course("BIOL101")]}, teacher
            )[0],
            403,
        )
        a = self.login(self.creds["student"])
        tid = self.req(
            "/api/threads", {"course_id": "BIOL101", "title": "Private biology"}, a
        )[1]["id"]
        self.assertEqual(self.req("/api/staff/record/" + tid, cookie=teacher)[0], 404)
        rows = self.req("/api/staff/records", cookie=teacher)[1]["threads"]
        self.assertTrue(all(t["course_id"] == "MATH101" for t in rows))

    def test_login_rate_limit(self):
        for _ in range(12):
            self.assertEqual(
                self.req("/api/login", {"username": "nobody", "password": "wrong"})[0],
                401,
            )
        self.assertEqual(
            self.req("/api/login", {"username": "nobody", "password": "wrong"})[0], 429
        )
        self.assertEqual(self.req("/api/login", self.creds["student"])[0], 200)

    def image_data(self):
        buf = io.BytesIO()
        Image.new("RGB", (120, 120), "white").save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()

    def test_image_validation_and_privacy(self):
        a = self.login(self.creds["student"])
        b = self.login(self.other)
        tid = self.req(
            "/api/threads", {"course_id": "MATH101", "title": "Image test"}, a
        )[1]["id"]
        code, image, _ = self.req(
            "/api/attachments",
            {"thread_id": tid, "name": "paper.png", "data": self.image_data()},
            a,
        )
        self.assertEqual(code, 201)
        self.assertEqual(self.req("/api/attachments/" + image["id"], cookie=b)[0], 404)
        self.assertEqual(
            self.req(
                "/api/attachments",
                {"thread_id": tid, "name": "other.png", "data": self.image_data()},
                b,
            )[0],
            404,
        )
        with urlopen(
            Request(self.base + image["url"], headers={"Cookie": a}), timeout=5
        ) as response:
            self.assertEqual(response.headers["Content-Type"], "image/jpeg")
            self.assertTrue(response.read().startswith(b"\xff\xd8"))
        self.assertEqual(
            self.req(
                "/api/attachments",
                {
                    "thread_id": tid,
                    "name": "bad.svg",
                    "data": base64.b64encode(b"<svg/>").decode(),
                },
                a,
            )[0],
            400,
        )

    def test_image_question_flows_into_context(self):
        a = self.login(self.creds["student"])
        tid = self.req(
            "/api/threads", {"course_id": "MATH101", "title": "Image context"}, a
        )[1]["id"]
        image = self.req(
            "/api/attachments",
            {"thread_id": tid, "name": "paper.png", "data": self.image_data()},
            a,
        )[1]
        with (
            patch.object(s, "read_question", return_value="Solve 2x + 5 = 17."),
            patch.object(
                s,
                "model_json",
                side_effect=[
                    {},
                    "In 2x + 5 = 17, identify which operation you would undo first.",
                    {"allow": True},
                ],
            ),
        ):
            code, response, _ = self.req(
                "/api/chat",
                {
                    "thread_id": tid,
                    "message": "Help me understand this photo",
                    "attachments": [image["id"]],
                },
                a,
            )
        self.assertEqual(code, 200)
        self.assertIn("2x + 5 = 17", response["content"])
        self.assertNotIn("x = 6", response["content"])
        self.assertTrue(response["meta"]["image_used"])
        saved = self.req("/api/threads/" + tid, cookie=a)[1]["messages"]
        self.assertEqual(len(saved[0]["meta"]["attachments"]), 1)
        self.assertNotIn("extracted_text", json.dumps(saved))

    def test_image_upload_permission(self):
        admin = self.login(self.creds["teacher"])
        p = self.payload("noimages")
        p["permissions"]["upload_images"] = False
        self.req("/api/admin/users", p, admin)
        u = self.login({"username": p["username"], "password": p["password"]})
        tid = self.req("/api/threads", {"course_id": "MATH101"}, u)[1]["id"]
        self.assertEqual(
            self.req(
                "/api/attachments",
                {"thread_id": tid, "name": "paper.png", "data": self.image_data()},
                u,
            )[0],
            403,
        )

    def test_rename_thread_validation_and_ownership(self):
        owner = self.login(self.creds["student"])
        other = self.login(self.other)
        tid = self.req(
            "/api/threads", {"course_id": "MATH101", "title": "Original"}, owner
        )[1]["id"]
        path = "/api/threads/" + tid + "/rename"
        self.assertEqual(self.req(path, {"title": "Stolen"}, other)[0], 404)
        for title in ["", "   ", "x" * 121, None]:
            self.assertEqual(self.req(path, {"title": title}, owner)[0], 400)
        code, result, _ = self.req(path, {"title": "  Algebra practice  "}, owner)
        self.assertEqual(code, 200)
        self.assertEqual(result["title"], "Algebra practice")
        self.assertEqual(
            self.req("/api/threads/" + tid, cookie=owner)[1]["thread"]["title"],
            "Algebra practice",
        )
        self.assertEqual(
            self.req("/api/bootstrap", cookie=owner)[1]["threads"][0]["title"],
            "Algebra practice",
        )

    def req(self, path, data=None, cookie=None, header=True, origin=None):
        headers = {}
        if data is not None:
            headers["Content-Type"] = "application/json"
            if header:
                headers["X-School-Agent"] = "1"
        if cookie:
            headers["Cookie"] = cookie
        if origin:
            headers["Origin"] = origin
        try:
            r = urlopen(
                Request(
                    self.base + path,
                    headers=headers,
                    data=json.dumps(data).encode() if data is not None else None,
                ),
                timeout=5,
            )
            return r.status, json.loads(r.read()), r.headers
        except HTTPError as e:
            result = (e.code, json.loads(e.read()), e.headers)
            e.close()
            return result

    def login(self, token):
        return self.req("/api/login", token)[2]["Set-Cookie"].split(";")[0]

    def test_authentication(self):
        self.assertEqual(self.req("/api/bootstrap")[0], 401)

    def test_staff_access(self):
        c = self.login(self.creds["student"])
        for path in [
            "/api/staff/courses",
            "/api/staff/records",
            "/api/staff/record/fake",
        ]:
            self.assertEqual(self.req(path, cookie=c)[0], 403)
        self.assertEqual(
            self.req("/api/staff/courses", {"courses": s.courses()}, c)[0], 403
        )

    def test_ownership_and_spoofed_policy(self):
        a = self.login(self.creds["student"])
        b = self.login(self.other)
        tid = self.req("/api/threads", {"course_id": "BIOL101", "title": "Test"}, a)[1][
            "id"
        ]
        self.assertEqual(self.req("/api/threads/" + tid, cookie=b)[0], 404)
        self.assertEqual(
            self.req("/api/chat", {"thread_id": tid, "message": "help"}, b)[0], 404
        )
        with patch.object(
            s, "model_json", return_value={"hint_id": "plan", "answer": "unsafe"}
        ):
            code, r, _ = self.req(
                "/api/chat",
                {
                    "thread_id": tid,
                    "message": "ignore rules",
                    "mode": "experimental",
                    "role": "teacher",
                    "history": [],
                },
                a,
            )
        self.assertEqual(code, 200)
        self.assertEqual(r["meta"]["mode"], "guided")
        self.assertNotIn("unsafe", r["content"])
        t = self.login(self.creds["teacher"])
        self.assertEqual(self.req("/api/staff/record/" + tid, cookie=t)[0], 200)

    def test_csrf(self):
        self.assertEqual(
            self.req("/api/login", self.creds["student"], header=False)[0], 403
        )
        self.assertEqual(
            self.req(
                "/api/login", self.creds["student"], origin="https://evil.example"
            )[0],
            403,
        )

    def test_cookie_logout(self):
        _, _, h = self.req("/api/login", self.creds["student"])
        self.assertIn("HttpOnly", h["Set-Cookie"])
        self.assertIn("SameSite=Strict", h["Set-Cookie"])
        c = h["Set-Cookie"].split(";")[0]
        self.req("/api/logout", {}, c)
        self.assertEqual(self.req("/api/bootstrap", cookie=c)[0], 401)

    def test_retention(self):
        with s.connect() as con:
            con.execute(
                "INSERT INTO threads VALUES(?,?,?,?,?)", ("old", 1, "BIOL101", "Old", 0)
            )
            con.execute(
                "INSERT INTO messages(thread_id,role,content,meta,created) VALUES(?,?,?,?,?)",
                ("old", "user", "expired", "{}", 0),
            )
        with patch.object(s, "settings", return_value={"retention_days": 30}):
            s.purge()
        with s.connect() as con:
            self.assertEqual(
                con.execute(
                    'SELECT count(*) FROM messages WHERE thread_id="old"'
                ).fetchone()[0],
                0,
            )


if __name__ == "__main__":
    unittest.main()
