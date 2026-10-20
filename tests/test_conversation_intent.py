"""A social turn after a coding task cannot resume work or create another file."""

import unittest
from unittest.mock import patch

import test_administration as fixtures
from app import server as s, artifacts, conversation_intent


class IntentPatterns(unittest.TestCase):
    def test_only_standalone_social_messages_match(self):
        for text in (
            "hi",
            "Hi!",
            "hey bro",
            "hello there",
            "thanks mate",
            "ok",
            "okay thanks",
            "good morning",
            "how are you today?",
            "stop",
            "never mind",
        ):
            self.assertIsNotNone(conversation_intent.social_reply(text), text)
        for text in (
            "Hi, explain wave frequency",
            "Okay, make it blue",
            "Thanks, can you fix the header?",
            "What does hello mean in this code?",
            "How are you storing files?",
            "Create a Python file",
        ):
            self.assertIsNone(conversation_intent.social_reply(text), text)

    def test_file_intent_requires_current_request_not_previous_task(self):
        history = [
            {
                "role": "assistant",
                "content": "```html filename=demo.html\n<h1>Demo</h1>\n```",
            }
        ]
        for text in (
            "hi",
            "thanks",
            "okay",
            "What is 9 squared?",
            "How do waves work?",
        ):
            self.assertFalse(artifacts.requested(text, history), text)
        for text in (
            "Create a downloadable file",
            "Write a Python function",
            "Redo it in blue",
            "Add a header",
            "Can you fix that?",
        ):
            self.assertTrue(artifacts.requested(text, history), text)
        self.assertFalse(artifacts.requested("Make it more concise", []))


class SocialAfterCode(unittest.TestCase):
    setUp = fixtures.Administration.setUp
    tearDown = fixtures.Administration.tearDown
    request = fixtures.Administration.request
    login = fixtures.Administration.login

    def test_hi_after_website_never_calls_model_or_exports_another_file(self):
        cookie = self.login("admin")
        tid = self.request(
            "/api/threads",
            {"course_id": "GENERAL", "title": "Synthetic website"},
            cookie,
        )[1]["id"]
        with patch.object(
            s,
            "answer",
            return_value=(
                "```html filename=demo.html\n<h1>Synthetic website</h1>\n```",
                {"mode": "configured", "route": "configured_tutoring", "sources": []},
            ),
        ):
            first = self.request(
                "/api/chat",
                {"thread_id": tid, "message": "Create a website file"},
                cookie,
            )
        self.assertEqual(len(first[1]["meta"]["artifacts"]), 1)
        for text in ("hi", "thanks", "okay", "stop"):
            with s.connect() as con:
                con.execute(
                    "UPDATE messages SET created=created-3 WHERE thread_id=?", (tid,)
                )
            with (
                patch.object(
                    s,
                    "answer",
                    side_effect=AssertionError("Social turn must not resume tutoring"),
                ),
                patch.object(
                    s,
                    "model_json",
                    side_effect=AssertionError(
                        "Social turn must not call an inference model"
                    ),
                ),
            ):
                status, reply, _ = self.request(
                    "/api/chat", {"thread_id": tid, "message": text}, cookie
                )
            self.assertEqual(status, 200, reply)
            self.assertEqual(reply["meta"]["route"], "social")
            self.assertNotIn("artifacts", reply["meta"])
            self.assertLess(len(reply["content"]), 100)
        self.assertEqual(
            len(
                self.request("/api/artifacts?thread_id=" + tid, cookie=cookie)[1][
                    "files"
                ]
            ),
            1,
        )

    def test_non_file_question_cannot_export_hallucinated_code(self):
        cookie = self.login("admin")
        tid = self.request(
            "/api/threads", {"course_id": "GENERAL", "title": "New topic"}, cookie
        )[1]["id"]
        with patch.object(
            s,
            "answer",
            return_value=(
                "```html filename=unrequested.html\n<h1>Wrong topic</h1>\n```",
                {"mode": "configured", "route": "configured_tutoring", "sources": []},
            ),
        ):
            status, reply, _ = self.request(
                "/api/chat", {"thread_id": tid, "message": "What is 9 squared?"}, cookie
            )
        self.assertEqual(status, 200)
        self.assertNotIn("artifacts", reply["meta"])
        self.assertEqual(
            self.request("/api/artifacts?thread_id=" + tid, cookie=cookie)[1]["files"],
            [],
        )
