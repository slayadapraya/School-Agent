"""Account-scoped cancellation; never cancel another user's local inference."""

from contextvars import ContextVar
from dataclasses import dataclass, field
import json
import socket
import threading

CURRENT = ContextVar("active_generation", default=None)
ACTIVE = {}
LOCK = threading.Lock()


@dataclass
class Generation:
    cancelled: threading.Event = field(default_factory=threading.Event)
    response: object = None


class Cancelled(Exception):
    pass


def check():
    state = CURRENT.get()
    if state and state.cancelled.is_set():
        raise Cancelled("Generation stopped by its owner")


def begin(user_id, thread_id):
    state = Generation()
    with LOCK:
        ACTIVE[(user_id, thread_id)] = state
    return CURRENT.set(state)


def finish(user_id, thread_id, token):
    with LOCK:
        ACTIVE.pop((user_id, thread_id), None)
    CURRENT.reset(token)


def stop(s, handler, user, data):
    tid = data.get("thread_id")
    handler.owned_thread(tid, user)
    with LOCK:
        state = ACTIVE.get((user["id"], tid))
        if state:
            state.cancelled.set()
            response = state.response
        else:
            response = None
    # Shut down only this request's socket. Never unload a model to cancel a reply.
    if response:
        try:
            response.fp.raw._sock.shutdown(socket.SHUT_RDWR)
        except (AttributeError, OSError):
            pass  # The response may have just finished; the flag is still checked.
    visible = data.get("visible_text")
    if visible is not None:
        if not isinstance(visible, str) or len(visible) > 20000:
            raise s.APIError(400, "Invalid visible reply")
        with s.connect() as con:
            row = con.execute(
                "SELECT id,role,content,meta FROM messages WHERE thread_id=? ORDER BY id DESC LIMIT 1",
                (tid,),
            ).fetchone()
            if row and row["role"] == "assistant":
                # Prefix-only truncation cannot inject a different answer into saved history.
                if not row["content"].startswith(visible):
                    raise s.APIError(409, "Reply changed; refresh this conversation")
                meta = json.loads(row["meta"])
                meta["stopped"] = True
                con.execute(
                    "UPDATE messages SET content=?,meta=? WHERE id=?",
                    (visible, json.dumps(meta), row["id"]),
                )
    return {"ok": True, "cancelled": bool(state)}
