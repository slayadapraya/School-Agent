"""Public live summaries contain only fixed phases and remain owner-scoped."""

import unittest
from test_administration import Administration
from app import server as s, generation_control as g


class GenerationActivity(unittest.TestCase):
    setUp = Administration.setUp
    tearDown = Administration.tearDown
    request = Administration.request
    login = Administration.login

    def test_progress_is_live_bounded_and_owner_only(self):
        cookie = self.login("admin")
        tid = self.request(
            "/api/threads", {"course_id": "GENERAL", "title": "Activity test"}, cookie
        )[1]["id"]
        path = "/api/chat/activity?thread_id=" + tid
        token = g.begin(self.people["admin"]["id"], tid)
        try:
            g.report("drafting")
            g.report("drafting")
            g.report("private reasoning must not be exposed")
            value = self.request(path, cookie=cookie)[1]
            self.assertTrue(value["active"])
            g.model_started()
            g.model_chunk()
            g.model_chunk()
            live = self.request(path, cookie=cookie)[1]
            self.assertTrue(live["model_active"])
            self.assertEqual(live["stream_updates"], 2)
            self.assertEqual(live["request_updates"], 2)
            self.assertGreaterEqual(live["elapsed_ms"], 0)
            g.model_finished()
            self.assertFalse(self.request(path, cookie=cookie)[1]["model_active"])
            g.model_started()
            self.assertEqual(self.request(path, cookie=cookie)[1]["request_updates"], 0)
            g.model_finished()

            self.assertEqual(
                [step["phase"] for step in value["steps"]], ["context", "drafting"]
            )
            self.assertNotIn("private reasoning", str(value))
            for _ in range(12):
                g.report("reviewing")
                g.report("revising")
            self.assertLessEqual(len(self.request(path, cookie=cookie)[1]["steps"]), 8)
            self.assertEqual(self.request(path, cookie=self.login("student"))[0], 404)
            self.assertEqual(self.request(path)[0], 401)
        finally:
            g.finish(self.people["admin"]["id"], tid, token)
        self.assertEqual(
            self.request(path, cookie=cookie)[1], {"active": False, "steps": []}
        )


class GenerationTransport(unittest.TestCase):
    def test_real_stream_adapter_counts_arrivals_without_exposing_reasoning(self):
        import io
        from unittest.mock import patch

        class Response(io.BytesIO):
            headers = {"Content-Type": "text/event-stream"}

            def __iter__(self):
                self.assert_active = g.CURRENT.get().model_active
                yield b'data: {"choices":[{"delta":{"reasoning_content":"private model text"}}]}\n'
                yield b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n'
                yield b"data: [DONE]\n"

        response = Response()
        token = g.begin(0, "transport-fixture")
        try:
            with (
                patch.object(
                    s,
                    "settings",
                    return_value={
                        "model_url": "http://127.0.0.1:1234/v1",
                        "model": "fixture",
                        "transport": "chat",
                    },
                ),
                patch.object(s, "urlopen", return_value=response),
            ):
                text = s.model_json(
                    [{"role": "user", "content": "Hi"}], 700, text_only=True
                )
            self.assertEqual(text, "Hello")
            self.assertTrue(response.assert_active)
            self.assertEqual(g.CURRENT.get().stream_updates, 2)
            self.assertFalse(g.CURRENT.get().model_active)
            self.assertNotIn("private model text", str(g.CURRENT.get().activity))
        finally:
            g.finish(0, "transport-fixture", token)
