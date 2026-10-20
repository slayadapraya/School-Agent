"""Account-scoped cancellation; never cancel another user's local inference."""

from contextvars import ContextVar
from dataclasses import dataclass, field
import json
import socket
import threading
import time

CURRENT = ContextVar("active_generation", default=None)
ACTIVE = {}
LOCK = threading.Lock()


@dataclass
class Generation:
    cancelled: threading.Event = field(default_factory=threading.Event)
    response: object = None
    started: float = field(default_factory=time.monotonic)
    activity: list = field(default_factory=list)
    stream_updates: int = 0
    request_updates: int = 0
    model_active: bool = False


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
    token = CURRENT.set(state)
    report("context")
    return token


# Only these public activity summaries are exposed. Prompts, tokens, model thought
# text, file bodies and raw logs never enter this account-scoped progress channel.
PHASES = {
    "context": (
        "Reading your question",
        "Using your latest message and the context of this chat.",
    ),
    "attachments": (
        "Reading attachments",
        "Extracting useful text from the files or photos you shared.",
    ),
    "sources": (
        "Finding supporting material",
        "Looking for relevant material to support this response.",
    ),
    "planning": (
        "Choosing an approach",
        "Identifying the topic and the kind of help your question needs.",
    ),
    "drafting": ("Writing a response", "Preparing an answer to your latest question."),
    "reviewing": (
        "Checking the response",
        "Reviewing the draft against the question and applicable tutoring rules.",
    ),
    "revising": ("Improving the draft", "Revising the response after its checks."),
    "saving": (
        "Finishing up",
        "Saving the response and any generated files to this chat.",
    ),
}


def report(phase):
    state = CURRENT.get()
    if not state or phase not in PHASES:
        return
    with LOCK:
        if state.activity and state.activity[-1]["phase"] == phase:
            return
        label, detail = PHASES[phase]
        state.activity.append({"phase": phase, "label": label, "detail": detail})
        del state.activity[:-8]


def model_started():
    state = CURRENT.get()
    if state:
        with LOCK:
            state.model_active = True
            state.request_updates = 0


def model_chunk():
    # Count arrivals only. Never retain or expose the chunk's private contents.
    state = CURRENT.get()
    if state:
        with LOCK:
            state.stream_updates += 1
            state.request_updates += 1


def model_finished():
    state = CURRENT.get()
    if state:
        with LOCK:
            state.model_active = False


def activity(s, handler, user, thread_id):
    handler.owned_thread(thread_id, user)
    with LOCK:
        state = ACTIVE.get((user["id"], thread_id))
        return {
            "active": bool(state),
            "steps": [dict(step) for step in state.activity] if state else [],
            **(
                {
                    "elapsed_ms": int((time.monotonic() - state.started) * 1000),
                    "stream_updates": state.stream_updates,
                    "request_updates": state.request_updates,
                    "model_active": state.model_active,
                }
                if state
                else {}
            ),
        }


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
