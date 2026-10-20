"""Generated files: isolated HTTP fixtures, ownership, review boundary and bounds."""

import json
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

import test_administration as fixtures
from app import server as s, artifacts, code_runner, model_output

CODE = 'Here is the file.\n\n```python filename=hello.py\nprint("Hello")\n```'


class Artifacts(unittest.TestCase):
    setUp = fixtures.Administration.setUp
    tearDown = fixtures.Administration.tearDown
    request = fixtures.Administration.request
    login = fixtures.Administration.login

    def new_thread(self, cookie):
        return self.request(
            "/api/threads", {"course_id": "GENERAL", "title": "Generated test"}, cookie
        )[1]["id"]

    def reply(self, cookie, tid, text=CODE, **extra):
        with patch.object(
            s,
            "answer",
            return_value=(
                text,
                {"mode": "configured", "route": "configured_tutoring", "sources": []},
            ),
        ):
            code, data, _ = self.request(
                "/api/chat",
                {"thread_id": tid, "message": "Create a Python file", **extra},
                cookie,
            )
        self.assertEqual(code, 200, data)
        return data

    def generated(self):
        cookie = self.login("admin")
        tid = self.new_thread(cookie)
        file = self.reply(cookie, tid)["meta"]["artifacts"][0]
        return cookie, tid, file

    def test_generated_file_persists_and_lists_metadata_without_body(self):
        cookie, tid, file = self.generated()
        listing = self.request("/api/artifacts?thread_id=" + tid, cookie=cookie)[1][
            "files"
        ]
        self.assertEqual(listing[0]["name"], "hello.py")
        self.assertNotIn("content", listing[0])
        loaded = self.request("/api/artifacts/" + file["id"], cookie=cookie)[1]
        self.assertEqual(loaded["file"]["content"], 'print("Hello")\n')
        self.assertFalse(loaded["runner_enabled"])
        messages = self.request("/api/threads/" + tid, cookie=cookie)[1]["messages"]
        self.assertEqual(messages[-1]["meta"]["artifacts"][0]["id"], file["id"])
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.http.server_port}" + file["url"],
            headers={"Cookie": cookie},
        )
        with urllib.request.urlopen(req) as response:
            self.assertIn("attachment;", response.headers["Content-Disposition"])
            self.assertEqual(response.read(), b'print("Hello")\n')

    def test_owner_only_even_for_other_admin_or_teacher(self):
        cookie, tid, file = self.generated()
        s.add_account("Second admin", "admin", "secondadmin", "test")
        for username in ("student", "teach", "other", "secondadmin"):
            other = self.login(username)
            for suffix in ("", "/download", "/preview"):
                self.assertEqual(
                    self.request("/api/artifacts/" + file["id"] + suffix, cookie=other)[
                        0
                    ],
                    404,
                )
            self.assertEqual(
                self.request(
                    "/api/artifacts/" + file["id"],
                    {"version": 1, "content": "changed"},
                    other,
                )[0],
                404,
            )
            self.assertEqual(
                self.request("/api/artifacts/" + file["id"] + "/run", {}, other)[0], 404
            )
        self.assertEqual(
            self.request(
                "/api/artifacts?thread_id=" + tid, cookie=self.login("student")
            )[0],
            404,
        )

    def test_permissions_default_off_grant_revoke_and_read_existing(self):
        user = self.people["teach"]
        with s.connect() as con:
            initial = json.loads(user["permissions"])
            initial["courses"] = ["GENERAL"]
            con.execute(
                "UPDATE users SET permissions=? WHERE id=?",
                (json.dumps(initial), user["id"]),
            )
        user = {**user, "permissions": json.dumps(initial)}
        cookie = self.login("teach")
        tid = self.new_thread(cookie)
        self.assertNotIn("artifacts", self.reply(cookie, tid)["meta"])
        with s.connect() as con:
            permissions = json.loads(user["permissions"])
            permissions["generate_files"] = True
            con.execute(
                "UPDATE users SET permissions=? WHERE id=?",
                (json.dumps(permissions), user["id"]),
            )
            con.execute(
                "UPDATE messages SET created=created-3 WHERE thread_id=?", (tid,)
            )
        file = self.reply(cookie, tid)["meta"]["artifacts"][0]
        with s.connect() as con:
            permissions["generate_files"] = False
            con.execute(
                "UPDATE users SET permissions=? WHERE id=?",
                (json.dumps(permissions), user["id"]),
            )
        self.assertEqual(
            self.request("/api/artifacts/" + file["id"], cookie=cookie)[0], 200
        )
        self.assertEqual(
            self.request(
                "/api/artifacts/" + file["id"],
                {"version": 1, "content": "changed"},
                cookie,
            )[0],
            403,
        )
        self.assertEqual(
            self.request("/api/artifacts/" + file["id"] + "/run", {}, cookie)[0], 403
        )

    def test_optimistic_save_and_limit(self):
        cookie, tid, file = self.generated()
        endpoint = "/api/artifacts/" + file["id"]
        self.assertEqual(
            self.request(endpoint, {"version": 1, "content": "print(2)\n"}, cookie)[1][
                "version"
            ],
            2,
        )
        self.assertEqual(
            self.request(endpoint, {"version": 1, "content": "stale"}, cookie)[0], 409
        )
        self.assertEqual(
            self.request(
                endpoint,
                {"version": 2, "content": "x" * (artifacts.MAX_BYTES + 1)},
                cookie,
            )[0],
            400,
        )
        self.assertEqual(
            self.request(endpoint, {"version": True, "content": "x"}, cookie)[0], 400
        )

    def test_interactive_preview_is_opaque_and_has_no_network_permission(self):
        cookie = self.login("admin")
        tid = self.new_thread(cookie)
        code = "```html filename=index.html\n<h1>Hi</h1><script>alert(1)</script>\n```"
        file = self.reply(cookie, tid, code)["meta"]["artifacts"][0]
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.http.server_port}/api/artifacts/"
            + file["id"]
            + "/preview",
            headers={"Cookie": cookie},
        )
        with urllib.request.urlopen(req) as response:
            policy = response.headers["Content-Security-Policy"]
            for part in (
                "default-src 'none'",
                "script-src 'unsafe-inline'",
                "sandbox allow-scripts",
                "frame-ancestors 'self'",
            ):
                self.assertIn(part, policy)
            self.assertNotIn("allow-same-origin", policy)
            self.assertNotIn("unsafe-eval", policy)
            self.assertIn(b"<h1>Hi</h1>", response.read())

    def preview_response(self, cookie, path):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.http.server_port}" + path,
            headers={"Cookie": cookie},
        )
        with urllib.request.urlopen(req) as response:
            return response.read().decode(), response.headers

    def test_inline_preview_bundles_styles_scripts_and_checks_ownership(self):
        cookie = self.login("admin")
        tid = self.new_thread(cookie)
        text = (
            '```html filename=index.html\n<link rel="stylesheet" href="site.css"><h1>Hello</h1><script src="site.js"></script>\n```\n'
            "```css filename=site.css\nh1 { color: green; }\n```\n"
            '```js filename=site.js\ndocument.body.dataset.ran="yes";\n```'
        )
        files = self.reply(cookie, tid, text)["meta"]["artifacts"]
        messages = self.request("/api/threads/" + tid, cookie=cookie)[1]["messages"]
        mid = messages[-1]["id"]
        path = f"/api/code-preview/{tid}/{mid}/0"
        body, headers = self.preview_response(cookie, path)
        self.assertIn("h1 { color: green; }", body)
        self.assertIn('document.body.dataset.ran="yes";', body)
        self.assertNotIn('src="site.js"', body)
        self.assertNotIn('href="site.css"', body)
        self.assertIn("style-src 'unsafe-inline'", headers["Content-Security-Policy"])
        self.assertIn("sandbox allow-scripts", headers["Content-Security-Policy"])
        self.assertNotIn("allow-same-origin", headers["Content-Security-Policy"])
        self.assertEqual(headers["Cache-Control"], "no-store")
        for username in ("student", "teach", "other"):
            self.assertEqual(self.request(path, cookie=self.login(username))[0], 404)
        self.assertEqual(self.request(path)[0], 401)
        self.assertEqual(
            self.request(
                f"/api/code-preview/{tid}/{messages[0]['id']}/0", cookie=cookie
            )[0],
            404,
        )
        self.assertEqual(
            self.request(f"/api/code-preview/{tid}/{mid}/99", cookie=cookie)[0], 404
        )
        # Saved CSS edits affect previews without rewriting the original reply.
        css = next(file for file in files if file["language"] == "css")
        self.request(
            "/api/artifacts/" + css["id"],
            {"version": 1, "content": "h1 { color: blue; }"},
            cookie,
        )
        self.assertIn("color: blue", self.preview_response(cookie, path)[0])
        self.request("/api/threads/" + tid + "/delete", {}, cookie)
        self.assertEqual(self.request(path, cookie=cookie)[0], 404)

    def test_inline_preview_permission_incomplete_size_and_unknown_block(self):
        cookie = self.login("admin")
        tid = self.new_thread(cookie)
        with s.connect() as con:
            mid = con.execute(
                "INSERT INTO messages(thread_id,role,content,meta,created) VALUES(?,?,?,?,?)",
                (tid, "assistant", "```html\n<h1>Incomplete</h1>", "{}", 0),
            ).lastrowid
        path = f"/api/code-preview/{tid}/{mid}/0"
        self.assertEqual(self.request(path, cookie=cookie)[0], 400)
        for text in (
            "```python\nprint(1)\n```",
            "```html\n" + ("a" * (artifacts.MAX_BYTES + 1)) + "\n```",
        ):
            with s.connect() as con:
                con.execute("UPDATE messages SET content=? WHERE id=?", (text, mid))
            self.assertEqual(self.request(path, cookie=cookie)[0], 400)
        with s.connect() as con:
            permissions = json.loads(self.people["teach"]["permissions"])
            permissions["courses"] = ["GENERAL"]
            con.execute(
                "UPDATE users SET permissions=? WHERE id=?",
                (json.dumps(permissions), self.people["teach"]["id"]),
            )
        teacher = self.login("teach")
        teacher_tid = self.new_thread(teacher)
        with s.connect() as con:
            teacher_mid = con.execute(
                "INSERT INTO messages(thread_id,role,content,meta,created) VALUES(?,?,?,?,?)",
                (teacher_tid, "assistant", "```html\n<h1>Hi</h1>\n```", "{}", 0),
            ).lastrowid
        self.assertEqual(
            self.request(
                f"/api/code-preview/{teacher_tid}/{teacher_mid}/0", cookie=teacher
            )[0],
            403,
        )

    def test_runner_off_by_default_and_never_starts_host_command(self):
        cookie, tid, file = self.generated()
        with patch.object(code_runner.subprocess, "Popen") as process:
            self.assertEqual(
                self.request("/api/artifacts/" + file["id"] + "/run", {}, cookie)[0],
                503,
            )
            process.assert_not_called()

    def test_student_preview_never_exports_even_with_admin_permission(self):
        cookie = self.login("admin")
        tid = self.new_thread(cookie)
        self.assertNotIn(
            "artifacts", self.reply(cookie, tid, student_preview=True)["meta"]
        )

    def test_archived_thread_files_cannot_be_opened(self):
        cookie, tid, file = self.generated()
        self.assertEqual(
            self.request("/api/threads/" + tid + "/delete", {}, cookie)[0], 200
        )
        self.assertEqual(
            self.request("/api/artifacts/" + file["id"], cookie=cookie)[0], 404
        )


class Extraction(unittest.TestCase):
    def test_complete_fences_only_and_safe_names(self):
        self.assertEqual(artifacts.extract("```python\nprint(1)"), [])
        self.assertEqual(artifacts.extract("```unknown\nprint(1)\n```"), [])
        self.assertEqual(
            artifacts.extract("```python filename=../../a.py\nprint(1)\n```")[0][
                "name"
            ],
            "a.py",
        )
        self.assertEqual(
            artifacts.extract("```python filename=bad.exe\nprint(1)\n```")[0]["name"],
            "generated-1.py",
        )
        self.assertEqual(
            artifacts.extract("```index.html\n<h1>Hi</h1>\n```")[0]["name"],
            "index.html",
        )
        self.assertEqual(len(artifacts.extract(("\n" + CODE + "\n") * 10)), 6)
        self.assertEqual(
            artifacts.extract("```text\n" + "x" * (artifacts.MAX_BYTES + 1) + "\n```"),
            [],
        )

    def test_code_escapes_and_json_keys_survive_prose_cleanup(self):
        code = '```python filename=escaped.py\nprint("\\n")\nvalue = {"answer": "hello"}\n# x^2 \\times\n```'
        self.assertEqual(model_output.clean_conversation(code), code)
        self.assertEqual(
            model_output.clean_conversation("Math $x^2$\n\n" + code),
            "Math x²\n\n" + code,
        )


class ContainerRunner(unittest.TestCase):
    """Exercise pipe handling with trusted fixtures, never generated code on the host."""

    def test_container_command_is_restricted_and_cleanup_always_runs(self):
        import subprocess
        import sys
        from types import SimpleNamespace

        real_process = subprocess.Popen
        calls = []
        server = SimpleNamespace(
            permission=lambda user, permission: True,
            settings=lambda: {"code_execution_enabled": True},
            audit=lambda *args: None,
            APIError=s.APIError,
        )

        def simulated_docker(args, **kwargs):
            calls.append(args)
            return real_process(
                [sys.executable, "-c", 'print("Trusted runner fixture")'], **kwargs
            )

        with (
            patch.object(code_runner.subprocess, "Popen", side_effect=simulated_docker),
            patch.object(code_runner.subprocess, "run") as cleanup,
        ):
            result = code_runner.run(
                server,
                {"id": 1},
                {
                    "id": "test-file",
                    "language": "python",
                    "content": "UNTRUSTED CONTENT NEVER EXECUTED BY THIS TEST",
                },
            )
        self.assertEqual(result["output"], "Trusted runner fixture\n")
        self.assertEqual(result["exit_code"], 0)
        for argument in (
            "--network=none",
            "--read-only",
            "--user=65534:65534",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--memory=128m",
            "--memory-swap=128m",
            "--cpus=0.5",
            "--pids-limit=32",
            "--pull=never",
            "--log-driver=none",
        ):
            self.assertIn(argument, calls[0])
        self.assertEqual(calls[0][-3:], ["python", "-B", "/work/main.py"])
        self.assertEqual(cleanup.call_args.args[0][:3], ["docker", "rm", "-f"])
        self.assertFalse(code_runner.LOCK.locked())

    def test_output_cap_and_missing_runtime_release_slot(self):
        import subprocess
        import sys
        from types import SimpleNamespace

        real_process = subprocess.Popen
        server = SimpleNamespace(
            permission=lambda *args: True,
            settings=lambda: {"code_execution_enabled": True},
            audit=lambda *args: None,
            APIError=s.APIError,
        )
        row = {"id": "test-file", "language": "python", "content": "not executed"}
        with (
            patch.object(
                code_runner.subprocess,
                "Popen",
                side_effect=lambda args, **kwargs: real_process(
                    [sys.executable, "-c", 'print("x" * 300000)'], **kwargs
                ),
            ),
            patch.object(code_runner.subprocess, "run"),
        ):
            result = code_runner.run(server, {"id": 1}, row)
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["output"]), 32768)
        with (
            patch.object(
                code_runner.subprocess, "Popen", side_effect=FileNotFoundError
            ),
            patch.object(code_runner.subprocess, "run"),
        ):
            with self.assertRaises(s.APIError) as error:
                code_runner.run(server, {"id": 1}, row)
            self.assertEqual(error.exception.status, 503)
        self.assertFalse(code_runner.LOCK.locked())
        code_runner.LOCK.acquire()
        try:
            with patch.object(code_runner.subprocess, "Popen") as process:
                with self.assertRaises(s.APIError) as error:
                    code_runner.run(server, {"id": 1}, row)
                self.assertEqual(error.exception.status, 429)
                process.assert_not_called()
        finally:
            code_runner.LOCK.release()


class FileResponseRecovery(unittest.TestCase):
    def test_raw_file_fences_survive_transport_and_normal_review_input(self):
        import io

        class Response(io.BytesIO):
            headers = {"Content-Type": "application/json"}

        response = Response(json.dumps({"choices": [{"text": CODE}]}).encode())
        settings = {
            "model_url": "http://127.0.0.1:1234/v1",
            "model": "fixture",
            "transport": "qwen_chatml",
        }
        with (
            patch.object(s, "settings", return_value=settings),
            patch.object(s, "urlopen", return_value=response),
        ):
            with self.assertRaises(json.JSONDecodeError) as error:
                s.model_json([{"role": "user", "content": "Create a file"}], 1500)
        self.assertEqual(error.exception.doc, CODE)
        token = s.preferences.MODEL_CONTEXT.set({"generate_files": True})
        try:
            with (
                patch.object(s, "settings", return_value={}),
                patch.object(s, "model_json", side_effect=error.exception),
            ):
                candidate = s.conversation_candidate(
                    [{"role": "user", "content": "Create a file"}]
                )
            self.assertEqual(candidate["answer"], CODE)
            self.assertEqual(
                artifacts.extract(model_output.clean_conversation(candidate["answer"]))[
                    0
                ]["name"],
                "hello.py",
            )
        finally:
            s.preferences.MODEL_CONTEXT.reset(token)

    def test_json_file_content_survives_nested_fences(self):
        text = '````markdown filename=readme.md\n# Example\n```python\nprint("Hi")\n```\n````'
        self.assertEqual(
            artifacts.extract(text)[0]["content"],
            '# Example\n```python\nprint("Hi")\n```\n',
        )
        self.assertEqual(model_output.clean_conversation(text), text)
