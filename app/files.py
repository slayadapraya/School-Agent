"""Conversation-owned documents, downloads and bounded text extraction."""

import base64
import io
import json
import secrets
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree

TYPES = {
    ".txt": "text/plain",
    ".md": "text/plain",
    ".csv": "text/plain",
    ".json": "text/plain",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def init(con):
    con.execute(
        "CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,thread_id TEXT NOT NULL,user_id INTEGER NOT NULL,name TEXT NOT NULL,mime TEXT NOT NULL,body BLOB NOT NULL,text TEXT NOT NULL,created REAL NOT NULL)"
    )


def extract(body, suffix):
    if suffix in (".txt", ".md", ".csv", ".json"):
        return body.decode("utf-8-sig", errors="replace")[:24000]
    if suffix == ".docx":
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            entry = z.getinfo("word/document.xml")
            if entry.file_size > 2000000:
                raise ValueError("Document text is too large")
            root = ElementTree.fromstring(z.read(entry))
            return "\n".join(
                "".join(p.itertext())
                for p in root.iter(
                    "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"
                )
            )[:24000]
    if not body.startswith(b"%PDF-"):
        raise ValueError("Invalid PDF")
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(body)
        f.flush()
        try:
            r = subprocess.run(
                ["pdftotext", "-f", "1", "-l", "30", "-layout", f.name, "-"],
                capture_output=True,
                timeout=10,
                check=True,
            )
        except (FileNotFoundError, subprocess.SubprocessError):
            raise ValueError(
                "Could not extract PDF text; upload a text-based PDF or paste its text"
            )
        text = r.stdout[:100000].decode("utf-8", errors="replace")[:24000]
        if not text.strip():
            raise ValueError(
                "This PDF has no readable text. Upload its pages as photos instead."
            )
        return text


def upload(s, h, user, data):
    t = h.owned_thread(data.get("thread_id"), user)
    if (
        not s.permission(user, "upload_images")
        or not s.administration.policy(s, user, t["course_id"])["upload_images"]
    ):
        raise s.APIError(403, "Uploads are disabled for this account")
    name = data.get("name", "")
    encoded = data.get("data", "")
    if (
        not isinstance(name, str)
        or not 1 <= len(name) <= 180
        or not isinstance(encoded, str)
    ):
        raise s.APIError(400, "Invalid file")
    suffix = Path(name).suffix.lower()
    if suffix not in TYPES:
        raise s.APIError(400, "Supported documents: PDF, DOCX, TXT, MD, CSV and JSON")
    try:
        body = base64.b64decode(encoded, validate=True)
    except Exception:
        raise s.APIError(400, "Invalid file data")
    if not 1 <= len(body) <= 6 * 1024 * 1024:
        raise s.APIError(400, "Files must be under 6 MB")
    try:
        text = extract(body, suffix)
    except Exception as e:
        raise s.APIError(400, str(e)[:180])
    with s.connect() as con:
        if (
            con.execute(
                "SELECT COUNT(*) FROM documents WHERE thread_id=?", (t["id"],)
            ).fetchone()[0]
            >= 20
        ):
            raise s.APIError(400, "This conversation already has 20 documents")
        fid = secrets.token_hex(16)
        con.execute(
            "INSERT INTO documents VALUES(?,?,?,?,?,?,?,?)",
            (fid, t["id"], user["id"], name, TYPES[suffix], body, text, time.time()),
        )
    return {
        "id": fid,
        "name": name,
        "url": "/api/files/" + fid,
        "document": True,
        "mime": TYPES[suffix],
    }


def get(s, h, user, path):
    fid = path.rsplit("/", 1)[-1]
    with s.connect() as con:
        row = con.execute("SELECT * FROM documents WHERE id=?", (fid,)).fetchone()
    if not row:
        raise s.APIError(404, "File not found")
    h.owned_thread(row["thread_id"], user)
    if "?preview" in h.path:
        return h.respond(
            200, {"name": row["name"], "text": row["text"], "mime": row["mime"]}
        )
    from urllib.parse import quote

    body = row["body"]
    h.send_response(200)
    # Keep office/text files as downloads; only PDF bytes may be framed by the viewer.
    inline = "inline=1" in h.path and row["mime"] == "application/pdf"
    h.common_headers(embedded=inline)
    h.send_header("Content-Type", row["mime"])
    h.send_header(
        "Content-Disposition",
        ("inline" if inline else "attachment")
        + "; filename*=UTF-8''"
        + quote(row["name"], safe=""),
    )
    h.send_header("Cache-Control", "no-store")
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    h.wfile.write(body)


def context(con, tid):
    rows = con.execute(
        "SELECT id,name,text FROM documents WHERE thread_id=? ORDER BY created DESC LIMIT 8",
        (tid,),
    ).fetchall()
    budget = 9000
    out = []
    for r in rows:
        text = r["text"][: min(5000, budget)]
        budget -= len(text)
        if text:
            out.append({"name": r["name"], "text": text})
    return json.dumps(out, ensure_ascii=False) if out else ""
