"""Permanent, account-owned notes tied to their original conversation."""

import json
import secrets
import re
import time


def init(con):
    con.executescript("""
        CREATE TABLE IF NOT EXISTS experimental_features(name TEXT PRIMARY KEY,enabled INTEGER NOT NULL);
        INSERT OR IGNORE INTO experimental_features VALUES('notes',1);
        CREATE TABLE IF NOT EXISTS chat_notes(
            id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,thread_id TEXT NOT NULL,
            title TEXT NOT NULL,body TEXT NOT NULL,version INTEGER NOT NULL,
            created REAL NOT NULL,updated REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS notes_owner_thread ON chat_notes(user_id,thread_id,updated);
    """)

    # Preserve existing notes while adding their optional organisation colour.
    if "colour" not in {row[1] for row in con.execute("PRAGMA table_info(chat_notes)")}:
        con.execute(
            "ALTER TABLE chat_notes ADD COLUMN colour TEXT NOT NULL DEFAULT '#bed6ab'"
        )

    columns = {row[1] for row in con.execute("PRAGMA table_info(chat_notes)")}
    if "text_size" not in columns:
        con.execute(
            "ALTER TABLE chat_notes ADD COLUMN text_size INTEGER NOT NULL DEFAULT 14"
        )
    if "body_html" not in columns:
        con.execute(
            "ALTER TABLE chat_notes ADD COLUMN body_html TEXT NOT NULL DEFAULT ''"
        )


def features(s):
    """Retain the legacy API shape, but never gate the standard Notes feature."""
    with s.connect() as con:
        flags = {
            r["name"]: bool(r["enabled"])
            for r in con.execute("SELECT * FROM experimental_features")
        }
    # Old installations may have notes=0. Preserve the row for migration compatibility.
    return {**flags, "notes": True}


def feature_update(s, user, data):
    if user["role"] != "admin":
        raise s.APIError(403, "Administrator access required")
    if data.get("name") == "notes":
        raise s.APIError(400, "Notes is a permanent feature and cannot be disabled")
    raise s.APIError(400, "No experimental options are currently available")


def authorize(s, h, user, nid):
    with s.connect() as con:
        row = con.execute(
            "SELECT * FROM chat_notes WHERE id=? AND user_id=?", (nid, user["id"])
        ).fetchone()
    if not row:
        raise s.APIError(404, "Note not found")
    h.owned_thread(row["thread_id"], user, include_deleted=True)
    return dict(row)


def get(s, h, user, nid=None):
    if nid:
        return {"note": authorize(s, h, user, nid)}
    with s.connect() as con:
        rows = con.execute(
            "SELECT n.id,n.thread_id,n.title,n.colour,substr(n.body,1,140) AS preview,n.version,n.updated,t.title AS chat_title,t.course_id,t.user_id FROM chat_notes n JOIN threads t ON t.id=n.thread_id WHERE n.user_id=? ORDER BY n.updated DESC LIMIT 500",
            (user["id"],),
        ).fetchall()
    # Recheck course/role boundaries even if the account changed after writing a note.
    result = []
    access = {}
    for row in rows:
        if row["thread_id"] not in access:
            access[row["thread_id"]] = s.oversight.personal_access(
                s,
                user,
                {
                    "id": row["thread_id"],
                    "user_id": row["user_id"],
                    "course_id": row["course_id"],
                },
            )
        if access[row["thread_id"]]:
            item = dict(row)
            item.pop("user_id", None)
            result.append(item)
    return {"notes": result}


def save(s, h, user, data, nid=None):
    # Updates use optimistic versions: concurrent edits never silently overwrite a draft.
    if nid:
        note = authorize(s, h, user, nid)
        title = data.get("title")
        body = data.get("body")
        version = data.get("version")
        text_size = data.get("text_size", note["text_size"])
        body_html = clean_note_html(data.get("body_html", ""))
        colour = data.get("colour", note["colour"])
        if (
            not isinstance(title, str)
            or not isinstance(body, str)
            or not 1 <= len(title.strip()) <= 100
            or len(body) > 20000
            or type(version) is not int
            or type(text_size) is not int
            or not 12 <= text_size <= 24
            or not isinstance(colour, str)
            or not re.fullmatch(r"#[0-9a-fA-F]{6}", colour)
        ):
            raise s.APIError(
                400,
                "Use a title under 100 characters and a note under 20000 characters",
            )
        with s.connect() as con:
            changed = con.execute(
                "UPDATE chat_notes SET title=?,body=?,colour=?,text_size=?,body_html=?,version=version+1,updated=? WHERE id=? AND user_id=? AND version=?",
                (
                    title.strip(),
                    body,
                    colour.lower(),
                    text_size,
                    body_html,
                    time.time(),
                    nid,
                    user["id"],
                    version,
                ),
            ).rowcount
        if not changed:
            raise s.APIError(
                409,
                "This note changed elsewhere. Your local draft has been kept; retry after reviewing it.",
            )
    else:
        thread = h.owned_thread(data.get("thread_id"), user)
        with s.connect() as con:
            if (
                con.execute(
                    "SELECT COUNT(*) FROM chat_notes WHERE user_id=?", (user["id"],)
                ).fetchone()[0]
                >= 500
            ):
                raise s.APIError(400, "This account already has 500 notes")
            nid = secrets.token_hex(16)
            now = time.time()
            con.execute(
                "INSERT INTO chat_notes(id,user_id,thread_id,title,body,version,created,updated) VALUES(?,?,?,?,?,?,?,?)",
                (nid, user["id"], thread["id"], "Untitled note", "", 1, now, now),
            )
    return {"note": authorize(s, h, user, nid)}


def model_context(s, user, thread_id, message, selected_id=None):
    """A bounded read-only snapshot: SQL ownership plus the same chat access checks as the UI."""
    import re

    terms = set(re.findall(r"[a-z0-9]{3,}", message.lower())) - {
        "the",
        "you",
        "your",
        "these",
        "that",
        "notes",
        "note",
        "have",
        "can",
        "see",
        "what",
        "about",
        "please",
    }
    with s.connect() as con:
        rows = con.execute(
            "SELECT n.id,n.thread_id,n.title,n.body,n.colour,n.updated,t.title AS chat_title,t.course_id FROM chat_notes n JOIN threads t ON t.id=n.thread_id WHERE n.user_id=? AND t.user_id=? ORDER BY n.updated DESC LIMIT 500",
            (user["id"], user["id"]),
        ).fetchall()
    available = []
    access = {}
    for row in rows:
        if row["thread_id"] not in access:
            access[row["thread_id"]] = s.oversight.personal_access(
                s,
                user,
                {
                    "id": row["thread_id"],
                    "user_id": user["id"],
                    "course_id": row["course_id"],
                },
            )
        if access[row["thread_id"]]:
            available.append(dict(row))

    def score(n):
        text = (n["title"] + " " + n["body"]).lower()
        return (
            n["id"] == selected_id,
            n["thread_id"] == thread_id,
            sum(term in text for term in terms),
            n["updated"],
        )

    ranked = sorted(available, key=score, reverse=True)
    selected = []
    budget = 6500
    for n in ranked:
        if len(selected) >= 6 or budget < 100:
            break
        if (
            n["thread_id"] != thread_id
            and terms
            and not any(t in (n["title"] + " " + n["body"]).lower() for t in terms)
        ):
            continue
        body = n["body"][: min(1800, budget)]
        budget -= len(body) + len(n["title"])
        selected.append(
            {
                "title": n["title"],
                "colour": n["colour"],
                "colour_name": colour_name(n["colour"]),
                "selected_in_chat": n["id"] == selected_id,
                "body": body,
                "empty": not n["body"].strip(),
                "truncated": len(body) < len(n["body"]),
                "current_chat": n["thread_id"] == thread_id,
                "chat_title": n["chat_title"],
                "course": n["course_id"],
            }
        )
    return {
        "enabled": True,
        "available_count": len(available),
        "current_chat_count": sum(n["thread_id"] == thread_id for n in available),
        "notes": selected,
    }


def colour_name(colour):
    """A colour label lets the model resolve references such as 'the blue note'."""
    presets = {
        "green": "#bed6ab",
        "blue": "#9bc9e8",
        "purple": "#d5b4e8",
        "pink": "#edb7ad",
        "yellow": "#ecd38f",
        "grey": "#b8c4ce",
    }

    def rgb(value):
        return tuple(int(value[i : i + 2], 16) for i in (1, 3, 5))

    target = rgb(colour)
    return min(
        presets,
        key=lambda name: sum((a - b) ** 2 for a, b in zip(target, rgb(presets[name]))),
    )


def clean_note_html(value):
    """Keep only local text formatting: no attributes, links, media or scripts."""
    from html import escape
    from html.parser import HTMLParser

    if not isinstance(value, str) or len(value) > 100000:
        return ""

    class Formatting(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.parts = []

        def handle_starttag(self, tag, attrs):
            if tag in {"b", "strong", "i", "em", "br", "div", "p"}:
                self.parts.append("<" + tag + ">")

        def handle_endtag(self, tag):
            if tag in {"b", "strong", "i", "em", "div", "p"}:
                self.parts.append("</" + tag + ">")

        def handle_data(self, data):
            self.parts.append(escape(data))

    parser = Formatting()
    parser.feed(value)
    return "".join(parser.parts)


def staff_notes(s, user, nid=None):
    """Staff review uses the existing roster boundaries; never broadens AI note access."""
    if user["role"] not in ("admin", "teacher") or not s.permission(
        user, "review_records"
    ):
        raise s.APIError(403, "Staff review access required")
    ids = s.oversight.student_ids(s, user)
    if not ids:
        if nid:
            raise s.APIError(404, "Note not found")
        return {"notes": []}
    placeholders = ",".join("?" for _ in ids)
    fields = (
        "n.*"
        if nid
        else "n.id,n.user_id,n.thread_id,n.title,n.colour,n.text_size,n.updated,substr(n.body,1,140) AS preview"
    )
    query = f"SELECT {fields},u.name AS student,t.title AS chat_title,t.course_id FROM chat_notes n JOIN users u ON u.id=n.user_id JOIN threads t ON t.id=n.thread_id WHERE u.role='student' AND t.user_id=n.user_id AND n.user_id IN ({placeholders}) AND t.id NOT IN (SELECT thread_id FROM staff_private_threads)"
    args = list(ids)
    if nid:
        query += " AND n.id=?"
        args.append(nid)
    query += " ORDER BY n.updated DESC LIMIT 500"
    with s.connect() as con:
        rows = con.execute(query, args).fetchall()
    result = [
        dict(row)
        for row in rows
        if user["role"] == "admin" or s.course_access(user, row["course_id"])
    ]
    if nid:
        if not result:
            raise s.APIError(404, "Note not found")
        s.audit(user["id"], "review_student_note", nid)
        return {"note": result[0]}
    return {"notes": result}


def create_initial(con, user, thread_id):
    """Create the first blank note in the same transaction as its new thread."""
    if (
        con.execute(
            "SELECT COUNT(*) FROM chat_notes WHERE user_id=?", (user["id"],)
        ).fetchone()[0]
        >= 500
    ):
        return
    now = time.time()
    con.execute(
        "INSERT INTO chat_notes(id,user_id,thread_id,title,body,version,created,updated) VALUES(?,?,?,?,?,?,?,?)",
        (
            secrets.token_hex(16),
            user["id"],
            thread_id,
            "Untitled note",
            "",
            1,
            now,
            now,
        ),
    )
