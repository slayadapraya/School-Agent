"""Administrator-only, session-bound host PTYs. No model has access to these APIs."""

import atexit
import base64
import hashlib
import json
import select
import fcntl
import os
import pty
import secrets
import signal
import socket
import struct
import subprocess
import sys
import termios
import threading
import time


class Terminals:
    def __init__(self):
        self.sessions = {}
        self.lock = threading.RLock()
        threading.Thread(target=self._janitor, daemon=True).start()
        atexit.register(self.close_all)

    def _close(self, key):
        item = self.sessions.pop(key, None)
        if not item:
            return
        try:
            os.killpg(item["process"].pid, signal.SIGHUP)
        except ProcessLookupError:
            pass
        try:
            item["process"].wait(timeout=0.3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(item["process"].pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            item["process"].wait(timeout=1)
        os.close(item["fd"])

    def close_all(self):
        with self.lock:
            for key in list(self.sessions):
                self._close(key)

    def _janitor(self):
        while True:
            time.sleep(10)
            with self.lock:
                for key, item in list(self.sessions.items()):
                    if time.time() - item["input_at"] > 300 or not item["authorized"]():
                        self._close(key)

    def open(self, owner, cookie, cwd, authorized=lambda: True):
        with self.lock:
            if sum(s["owner"] == owner for s in self.sessions.values()) >= 2:
                raise ValueError("Close an existing terminal first (maximum two).")
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
            env = {
                k: v
                for k, v in os.environ.items()
                if k
                in (
                    "PATH",
                    "HOME",
                    "USER",
                    "LOGNAME",
                    "LANG",
                    "LC_ALL",
                    "SHELL",
                    "XDG_RUNTIME_DIR",
                    "DBUS_SESSION_BUS_ADDRESS",
                )
            }
            env.update(
                TERM="xterm-256color",
                COLORTERM="truecolor",
                HISTFILE="/dev/null",
                PS1=r"\[\e[1;32m\]\u@\h\[\e[0m\]:\[\e[1;36m\]\w\[\e[0m\] \$ ",
                LS_COLORS="di=1;34:ln=1;36:ex=1;32",
            )
            try:
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        "import fcntl,termios,os;fcntl.ioctl(0,termios.TIOCSCTTY,0);os.execv('/bin/bash',['bash','--noprofile','--norc','-i'])",
                    ],
                    stdin=slave,
                    stdout=slave,
                    stderr=slave,
                    cwd=cwd,
                    env=env,
                    start_new_session=True,
                )
            except Exception:
                os.close(master)
                raise
            finally:
                os.close(slave)
            os.set_blocking(master, False)
            key = secrets.token_urlsafe(32)
            now = time.time()
            self.sessions[key] = {
                "owner": owner,
                "cookie": cookie,
                "fd": master,
                "process": process,
                "created": now,
                "input_at": now,
                "authorized": authorized,
            }
            return {
                "id": key,
                "host": socket.gethostname(),
                "user": env.get("USER", "server user"),
                "idle_seconds": 300,
                "max_seconds": None,
            }

    def operate(self, owner, cookie, data):
        with self.lock:
            key = data.get("id")
            item = self.sessions.get(key) if isinstance(key, str) else None
            if not item or item["owner"] != owner or item["cookie"] != cookie:
                raise KeyError("Terminal not found or expired")
            if time.time() - item["input_at"] > 300:
                self._close(key)
                raise KeyError("Terminal expired; connect again")
            if data.get("action") == "close":
                self._close(key)
                return {"closed": True}
            text = data.get("input", "")
            if not isinstance(text, str) or len(text) > 8192:
                raise ValueError("Terminal input too large")
            if text:
                item["input_at"] = time.time()
                try:
                    os.write(item["fd"], text.encode())
                except (BlockingIOError, OSError):
                    pass
            if "cols" in data or "rows" in data:
                cols = max(20, min(300, int(data.get("cols", 80))))
                rows = max(5, min(100, int(data.get("rows", 24))))
                fcntl.ioctl(
                    item["fd"],
                    termios.TIOCSWINSZ,
                    struct.pack("HHHH", rows, cols, 0, 0),
                )
                try:
                    os.killpg(item["process"].pid, signal.SIGWINCH)
                except ProcessLookupError:
                    pass
            output = bytearray()
            while len(output) < 65536:
                try:
                    chunk = os.read(item["fd"], min(8192, 65536 - len(output)))
                    if not chunk:
                        break
                    output.extend(chunk)
                except (BlockingIOError, OSError):
                    break
            closed = item["process"].poll() is not None
            if closed:
                self._close(key)
            return {"output": base64.b64encode(output).decode(), "closed": closed}


terminals = Terminals()


def handle(app, handler, user, data):
    if user["role"] != "admin":
        raise app.APIError(403, "Administrator access required")
    cookie = app.SimpleCookie(handler.headers.get("Cookie", ""))["sa_session"].value
    cookie = app.digest(cookie)
    if data.get("action") == "open":
        password = data.get("password", "")
        if not isinstance(password, str) or len(password) > 256:
            raise app.APIError(400, "Enter your current password")
        # Reauthentication is rate limited separately from ordinary page requests.
        now = time.time()
        with handler.server.rate_lock:
            attempts = [
                t
                for t in handler.server.logins.get("terminal:" + str(user["id"]), [])
                if now - t < 60
            ]
            if len(attempts) >= 5:
                raise app.APIError(
                    429, "Too many terminal unlock attempts; wait a minute"
                )
            handler.server.logins["terminal:" + str(user["id"])] = attempts + [now]
        if not app.password_matches(password, user["password_hash"]):
            raise app.APIError(403, "Current password is incorrect")

        def authorized():
            try:
                with app.connect() as con:
                    row = con.execute(
                        "SELECT u.role,u.enabled FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.id=? AND s.expires>?",
                        (cookie, time.time()),
                    ).fetchone()
                return bool(row and row["enabled"] and row["role"] == "admin")
            except Exception:
                return False

        try:
            result = terminals.open(user["id"], cookie, app.ROOT, authorized)
        except ValueError as e:
            raise app.APIError(409, str(e))
        app.audit(user["id"], "terminal_open", result["host"])
        return handler.respond(201, result)
    if data.get("action") not in ("poll", "close"):
        raise app.APIError(400, "Invalid terminal action")
    try:
        result = terminals.operate(user["id"], cookie, data)
    except KeyError:
        raise app.APIError(404, "Terminal not found or expired")
    except ValueError:
        raise app.APIError(400, "Invalid terminal input or dimensions")
    if data["action"] == "close":
        app.audit(user["id"], "terminal_close", "Administrator disconnected")
    return handler.respond(200, result)


def stream(app, handler, user):
    """Same-origin RFC 6455 transport: immediate input and binary PTY output."""
    from urllib.parse import parse_qs, urlsplit

    if user["role"] != "admin":
        raise app.APIError(403, "Administrator access required")
    origin = urlsplit(handler.headers.get("Origin", ""))
    if not origin.netloc or origin.netloc != handler.headers.get("Host"):
        raise app.APIError(403, "Same-origin terminal connection required")
    if (
        handler.headers.get("Upgrade", "").lower() != "websocket"
        or "upgrade" not in handler.headers.get("Connection", "").lower()
        or handler.headers.get("Sec-WebSocket-Version") != "13"
    ):
        raise app.APIError(400, "WebSocket connection required")
    websocket_key = handler.headers.get("Sec-WebSocket-Key", "")
    try:
        if len(base64.b64decode(websocket_key, validate=True)) != 16:
            raise ValueError()
    except Exception:
        raise app.APIError(400, "Invalid WebSocket key")
    key = parse_qs(urlsplit(handler.path).query).get("id", [""])[0]
    cookie = app.digest(
        app.SimpleCookie(handler.headers.get("Cookie", ""))["sa_session"].value
    )
    with terminals.lock:
        item = terminals.sessions.get(key)
        if not item or item["owner"] != user["id"] or item["cookie"] != cookie:
            raise app.APIError(404, "Terminal not found")
        if item.get("streaming"):
            raise app.APIError(409, "Terminal already connected")
        item["streaming"] = True
    accept = base64.b64encode(
        hashlib.sha1(
            (websocket_key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()
        ).digest()
    ).decode()
    handler.protocol_version = "HTTP/1.1"
    handler.close_connection = True
    handler.send_response(101)
    handler.send_header("Upgrade", "websocket")
    handler.send_header("Connection", "Upgrade")
    handler.send_header("Sec-WebSocket-Accept", accept)
    handler.end_headers()
    handler.wfile.flush()
    sock = handler.connection
    sock.settimeout(2)

    def send(opcode, data=b""):
        length = len(data)
        header = bytes([0x80 | opcode])
        header += (
            bytes([length])
            if length < 126
            else (
                b"\x7e" + struct.pack("!H", length)
                if length < 65536
                else b"\x7f" + struct.pack("!Q", length)
            )
        )
        sock.sendall(header + data)

    pending = bytearray()
    last_auth = 0
    last_ping = time.time()
    try:
        while True:
            with terminals.lock:
                if key not in terminals.sessions:
                    break
                if time.time() - last_auth > 1:
                    if not item["authorized"]():
                        break
                    last_auth = time.time()
                if time.time() - item["input_at"] > 300:
                    break
            if time.time() - last_ping > 25:
                send(9)
                last_ping = time.time()
            ready, _, _ = select.select([sock, item["fd"]], [], [], 0.5)
            if item["fd"] in ready:
                result = terminals.operate(
                    user["id"], cookie, {"id": key, "action": "poll"}
                )
                if result.get("output"):
                    send(2, base64.b64decode(result["output"]))
                if result.get("closed"):
                    break
            if sock not in ready:
                continue
            data = sock.recv(16384)
            if not data:
                break
            pending.extend(data)
            if len(pending) > 65536:
                break
            while len(pending) >= 2:
                first, second = pending[:2]
                opcode = first & 15
                size = second & 127
                offset = 2
                if not first & 128 or not second & 128:
                    raise ValueError("Masked complete client frames required")
                if size == 126:
                    if len(pending) < 4:
                        break
                    size = struct.unpack("!H", pending[2:4])[0]
                    offset = 4
                elif size == 127:
                    raise ValueError("Terminal frame too large")
                if size > 16384 or opcode >= 8 and size > 125:
                    raise ValueError("Terminal frame too large")
                if len(pending) < offset + 4 + size:
                    break
                mask = pending[offset : offset + 4]
                offset += 4
                payload = bytes(
                    value ^ mask[i % 4]
                    for i, value in enumerate(pending[offset : offset + size])
                )
                del pending[: offset + size]
                if opcode == 8:
                    return
                if opcode == 9:
                    send(10, payload)
                    continue
                if opcode == 10:
                    continue
                if opcode != 1:
                    raise ValueError("JSON input frame required")
                event = json.loads(payload.decode("utf-8"))
                if not isinstance(event, dict):
                    raise ValueError("Invalid input")
                # Session and action come from the authenticated connection, never client fields.
                event = {
                    k: v for k, v in event.items() if k in ("input", "cols", "rows")
                }
                result = terminals.operate(
                    user["id"], cookie, {**event, "id": key, "action": "poll"}
                )
                if result.get("output"):
                    send(2, base64.b64decode(result["output"]))
                if result.get("closed"):
                    return
    except (OSError, ValueError, KeyError):
        pass
    finally:
        with terminals.lock:
            terminals._close(key)
        try:
            send(8, struct.pack("!H", 1000))
        except OSError:
            pass
        app.audit(user["id"], "terminal_close", "Live connection ended")
