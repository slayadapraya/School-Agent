import base64
import json
import time
import unittest
from app import host_terminal as h, server as s


class HostTerminal(unittest.TestCase):
    import test_administration as fixtures

    setUp = fixtures.Administration.setUp
    request = fixtures.Administration.request
    login = fixtures.Administration.login

    def tearDown(self):
        h.terminals.close_all()
        self.fixtures.Administration.tearDown(self)

    def open(self, cookie):
        password = json.loads((s.STATE / "credentials.json").read_text())["teacher"][
            "password"
        ]
        return self.request(
            "/api/admin/terminal", {"action": "open", "password": password}, cookie
        )

    def test_nonadmins_cannot_open_or_operate_terminal(self):
        self.assertEqual(
            self.request("/api/admin/terminal", {"action": "open"})[0], 401
        )
        for name in ("student", "teach"):
            cookie = self.login(name)
            for action in ("open", "poll", "close"):
                self.assertEqual(
                    self.request(
                        "/api/admin/terminal",
                        {"action": action, "id": "guess", "password": "test"},
                        cookie,
                    )[0],
                    403,
                )
        self.assertEqual(len(h.terminals.sessions), 0)

    def test_unlock_requires_password_and_rate_limits(self):
        cookie = self.login("admin")
        for i in range(5):
            self.assertEqual(
                self.request(
                    "/api/admin/terminal",
                    {"action": "open", "password": "wrong"},
                    cookie,
                )[0],
                403,
            )
        self.assertEqual(self.open(cookie)[0], 429)
        self.assertFalse(h.terminals.sessions)

    def test_real_interactive_shell_and_close(self):
        cookie = self.login("admin")
        code, result, _ = self.open(cookie)
        self.assertEqual(code, 201)
        key = result["id"]
        self.assertTrue(result["host"])
        output = ""
        self.request(
            "/api/admin/terminal",
            {
                "action": "poll",
                "id": key,
                "input": "printf 'terminal_%s\\n' verified\r",
                "cols": 100,
                "rows": 30,
            },
            cookie,
        )
        for i in range(30):
            code, r, _ = self.request(
                "/api/admin/terminal", {"action": "poll", "id": key}, cookie
            )
            self.assertEqual(code, 200)
            output += base64.b64decode(r["output"]).decode(errors="replace")
            if "terminal_verified" in output:
                break
            time.sleep(0.03)
        self.assertIn("terminal_verified", output)
        self.assertNotIn("no job control", output)
        self.assertEqual(
            self.request("/api/admin/terminal", {"action": "close", "id": key}, cookie)[
                0
            ],
            200,
        )
        self.assertEqual(
            self.request("/api/admin/terminal", {"action": "poll", "id": key}, cookie)[
                0
            ],
            404,
        )

    def test_other_login_session_cannot_hijack_shell(self):
        cookie = self.login("admin")
        key = self.open(cookie)[1]["id"]
        other = self.login("admin")
        self.assertEqual(
            self.request(
                "/api/admin/terminal",
                {"action": "poll", "id": key, "input": "whoami\r"},
                other,
            )[0],
            404,
        )
        self.assertEqual(
            self.request("/api/admin/terminal", {"action": "close", "id": key}, other)[
                0
            ],
            404,
        )
        self.assertIn(key, h.terminals.sessions)

    def test_demotion_and_logout_revoke_access(self):
        cookie = self.login("admin")
        key = self.open(cookie)[1]["id"]
        with s.connect() as con:
            con.execute("UPDATE users SET role='teacher' WHERE username='admin'")
        self.assertEqual(
            self.request("/api/admin/terminal", {"action": "poll", "id": key}, cookie)[
                0
            ],
            403,
        )
        self.assertFalse(h.terminals.sessions[key]["authorized"]())
        with s.connect() as con:
            con.execute("UPDATE users SET role='admin' WHERE username='admin'")
        self.request("/api/logout", {}, cookie)
        self.assertEqual(
            self.request("/api/admin/terminal", {"action": "poll", "id": key}, cookie)[
                0
            ],
            401,
        )
        self.assertFalse(h.terminals.sessions[key]["authorized"]())

    def test_idle_expiry_and_session_limit(self):
        cookie = self.login("admin")
        key = self.open(cookie)[1]["id"]
        self.open(cookie)
        self.assertEqual(self.open(cookie)[0], 409)
        h.terminals.sessions[key]["input_at"] -= 301
        self.assertEqual(
            self.request("/api/admin/terminal", {"action": "poll", "id": key}, cookie)[
                0
            ],
            404,
        )
        self.assertNotIn(key, h.terminals.sessions)


if __name__ == "__main__":
    unittest.main()


class TerminalWebSocket(unittest.TestCase):
    import test_administration as fixtures

    setUp = fixtures.Administration.setUp
    tearDown = HostTerminal.tearDown
    request = fixtures.Administration.request
    login = fixtures.Administration.login
    open = HostTerminal.open

    def upgrade(self, cookie, key, origin=None):
        import socket, base64, os

        sock = socket.create_connection(("127.0.0.1", self.http.server_port))
        sock.settimeout(1)
        host = "127.0.0.1:" + str(self.http.server_port)
        headers = f'GET /api/admin/terminal-stream?id={key} HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin or "http://"+host}\r\nCookie: {cookie}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: {base64.b64encode(os.urandom(16)).decode()}\r\n\r\n'
        sock.sendall(headers.encode())
        data = b""
        while b"\r\n\r\n" not in data:
            data += sock.recv(4096)
        return sock, data

    def send(self, sock, value, opcode=1):
        import os, struct

        mask = os.urandom(4)
        size = len(value)
        header = bytes([0x80 | opcode]) + (
            bytes([0x80 | size])
            if size < 126
            else bytes([0xFE]) + struct.pack("!H", size)
        )
        sock.sendall(
            header + mask + bytes(v ^ mask[i % 4] for i, v in enumerate(value))
        )

    def test_live_shell_has_colour_and_immediate_output(self):
        cookie = self.login("admin")
        key = self.open(cookie)[1]["id"]
        sock, initial = self.upgrade(cookie, key)
        try:
            self.assertTrue(initial.startswith(b"HTTP/1.1 101"))
            self.send(
                sock,
                json.dumps({"input": "printf 'websocket_%s\\n' verified\r"}).encode(),
            )
            data = initial
            start = time.monotonic()
            while b"websocket_verified" not in data and time.monotonic() - start < 2:
                data += sock.recv(8192)
            self.assertIn(b"websocket_verified", data)
            self.assertIn(b"\x1b[1;32m", data)
            self.assertLess(time.monotonic() - start, 1.5)
            self.send(sock, b"", 8)
        finally:
            sock.close()

    def test_websocket_rejects_cross_origin(self):
        cookie = self.login("admin")
        key = self.open(cookie)[1]["id"]
        sock, response = self.upgrade(cookie, key, "https://untrusted.example")
        try:
            self.assertIn(b"403", response.split(b"\r\n")[0])
        finally:
            sock.close()

    def test_websocket_rejects_other_login_session(self):
        cookie = self.login("admin")
        key = self.open(cookie)[1]["id"]
        sock, response = self.upgrade(self.login("admin"), key)
        try:
            self.assertIn(b"404", response.split(b"\r\n")[0])
        finally:
            sock.close()

    def test_websocket_rejects_students_and_teachers(self):
        for name in ("student", "teach"):
            sock, response = self.upgrade(self.login(name), "guess")
            try:
                self.assertIn(b"403", response.split(b"\r\n")[0])
            finally:
                sock.close()
