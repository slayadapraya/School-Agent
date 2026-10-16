"""Recoverable removal of personal General chats; assessed records stay intact."""

import time


def init(con):
    con.execute(
        "CREATE TABLE IF NOT EXISTS archived_threads(thread_id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,created REAL NOT NULL)"
    )


def deleted(s, user):
    with s.connect() as con:
        rows = con.execute(
            'SELECT t.id,t.title FROM threads t JOIN archived_threads a ON a.thread_id=t.id WHERE a.user_id=? AND t.user_id=? AND (t.course_id="GENERAL" OR ?=1) ORDER BY a.created DESC',
            (user["id"], user["id"], int(user["role"] == "admin")),
        ).fetchall()
    return {"threads": [dict(r) for r in rows]}


def update(s, handler, user, tid, restore=False):
    thread = handler.owned_thread(tid, user, include_deleted=restore)
    if user["role"] != "admin" and thread["course_id"] != "GENERAL":
        raise s.APIError(
            400, "Only General chats can be deleted here; subject records are retained"
        )
    with s.connect() as con:
        if restore:
            con.execute(
                "DELETE FROM archived_threads WHERE thread_id=? AND user_id=?",
                (tid, user["id"]),
            )
        else:
            con.execute(
                "INSERT OR REPLACE INTO archived_threads VALUES(?,?,?)",
                (tid, user["id"], time.time()),
            )
    s.audit(user["id"], "restore_chat" if restore else "delete_chat", tid)
    return {"ok": True}
