import json
import unittest
from unittest.mock import patch
from app import server as s
from app.student_tutor import expected_values, leak


class StudentGuidance(unittest.TestCase):
    import test_administration as fixtures

    setUp = fixtures.Administration.setUp
    tearDown = fixtures.Administration.tearDown
    request = fixtures.Administration.request
    login = fixtures.Administration.login

    def open_thread(self, name="student"):
        cookie = self.login(name)
        return (
            cookie,
            self.request("/api/threads", {"course_id": "GENERAL"}, cookie)[1]["id"],
        )

    def ask(self, cookie, tid, message, **extra):
        with s.connect() as con:
            con.execute(
                "UPDATE messages SET created=created-2 WHERE thread_id=?", (tid,)
            )
        code, r, _ = self.request(
            "/api/chat", {"thread_id": tid, "message": message, **extra}, cookie
        )
        self.assertEqual(code, 200, r)
        return r

    def test_actual_history_reaches_generation_and_review(self):
        cookie, tid = self.open_thread()
        with patch.object(
            s,
            "model_json",
            side_effect=[
                {},
                "Write 9 × 9, then calculate it yourself.",
                {"allow": True},
                {},
                "We are still looking at the same square. Think of equal rows of dots.",
                {"allow": True},
            ],
        ) as model:
            self.ask(cookie, tid, "give me the answers to 9 squared bro")
            r = self.ask(cookie, tid, "nah idk bro gimme the answers")
        messages = model.call_args_list[4].args[0]
        self.assertEqual(messages[-1]["content"], "nah idk bro gimme the answers")
        self.assertIn(
            {"role": "user", "content": "give me the answers to 9 squared bro"},
            messages,
        )
        self.assertTrue(any(m["role"] == "assistant" for m in messages))
        self.assertNotIn("81", r["content"])

    def test_student_policy_cannot_be_disabled(self):
        with s.connect() as con:
            row = con.execute(
                "SELECT id,permissions FROM users WHERE username='student'"
            ).fetchone()
            p = json.loads(row["permissions"])
            p["tutoring_policy"] = {
                "block_answers": False,
                "review_output": False,
                "overviews": True,
            }
            con.execute(
                "UPDATE users SET permissions=? WHERE id=?", (json.dumps(p), row["id"])
            )
        cookie, tid = self.open_thread()
        p = self.request("/api/bootstrap", cookie=cookie)[1]["courses"][0]["policy"]
        self.assertTrue(p["student_guidance"])
        self.assertTrue(p["block_answers"])
        self.assertTrue(p["review_output"])
        self.assertTrue(p["overviews"])
        with patch.object(
            s,
            "model_json",
            side_effect=[{}, "Try writing two equal factors first.", {"allow": True}],
        ):
            r = self.ask(
                cookie, tid, "9 squared", role="admin", policy={"block_answers": False}
            )
        self.assertEqual(r["meta"]["route"], "student_guidance")

    def test_numeric_leak_is_revised_before_review(self):
        cookie, tid = self.open_thread()
        with patch.object(
            s,
            "model_json",
            side_effect=[
                {},
                "The answer is 81.",
                "Try writing the factors first.",
                {"allow": True},
            ],
        ) as model:
            r = self.ask(cookie, tid, "9 squared")
        self.assertNotIn("81", r["content"])
        self.assertEqual(model.call_count, 4)

    def test_reviewer_blocks_completed_work_and_failure_is_closed(self):
        cookie, tid = self.open_thread()
        with patch.object(
            s,
            "model_json",
            side_effect=[
                {},
                "A finished essay.",
                {"allow": False, "issues": "Completed work"},
                "A revised finished essay.",
                {"allow": False, "issues": "Still completed"},
            ],
        ):
            r = self.ask(cookie, tid, "Write my essay.")
        self.assertEqual(r["meta"]["route"], "guidance_unavailable")
        self.assertNotIn("finished essay", r["content"])
        with patch.object(s, "model_json", side_effect=TimeoutError):
            r = self.ask(cookie, tid, "Try again")
        self.assertEqual(r["meta"]["route"], "guidance_unavailable")

    def test_research_and_preview_do_not_bypass_review(self):
        for name, extra in [
            ("student", {"action": "research"}),
            ("admin", {"student_preview": True}),
        ]:
            cookie, tid = self.open_thread(name)
            with (
                patch.object(
                    s,
                    "model_json",
                    side_effect=[
                        {},
                        "Write the unevaluated factors first.",
                        {"allow": True},
                    ],
                ),
                patch.object(s.research, "plan", side_effect=AssertionError),
            ):
                r = self.ask(cookie, tid, "What is 9 squared?", **extra)
            self.assertEqual(r["meta"]["route"], "student_guidance")

    def test_admin_can_use_its_personal_assistant(self):
        cookie, tid = self.open_thread("admin")
        with patch.object(
            s,
            "model_json",
            return_value={"answer": "9 squared is 81.", "source_ids": []},
        ):
            r = self.ask(cookie, tid, "9 squared")
        self.assertEqual(r["meta"]["route"], "configured_tutoring")

    def test_numeric_guard_is_bounded_and_does_not_execute_input(self):
        for q, answer in [
            ("9 squared", "eighty-one"),
            ("12 + 7", "19"),
            ("2x + 5 = 17", "x = 6"),
            ("10 x 10", "100"),
        ]:
            self.assertTrue(leak(answer, expected_values(q, [])))
        self.assertFalse(leak("Write 9 × 9.", expected_values("9 squared", [])))
        self.assertEqual(expected_values('__import__("os").system("id")', []), set())
