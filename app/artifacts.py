"""Small, conversation-owned generated text files. Bodies are loaded on demand.

Only complete fences from the final reviewed reply become files. Model filenames
are labels in SQLite, never paths on the host. Execution is a separate permission.
"""

import re
import secrets
import time
from urllib.parse import parse_qs, quote, urlsplit

MODEL_GUIDANCE = (
    " File generation is available: when asked to create code or a downloadable text document, "
    "include its full contents in complete fenced blocks using a language and filename. The "
    "opening fence, code lines and closing fence MUST be on separate lines. Preserve code "
    "newlines, spaces and indentation. Do not flatten a program into prose. A valid block is:\n"
    '```python filename=example.py\nprint("Hello")\n```\n The application saves each completed '
    "block as a downloadable file in the Files sidebar. Supported formats include Python, "
    "JavaScript, HTML, CSS, JSON, CSV, Markdown and plain text. Do not claim to have executed "
    "code. Do not output binary formats or pretend plain text is a PDF/DOCX. Preserve the "
    "caller's response format; if JSON is requested, encode the file fences inside its answer "
    "string. This feature never overrides student answer restrictions."
)

MAX_BYTES = 128 * 1024
MAX_FILES = 60
EXTENSIONS = {
    "python": "py",
    "py": "py",
    "javascript": "js",
    "js": "js",
    "typescript": "ts",
    "ts": "ts",
    "html": "html",
    "css": "css",
    "json": "json",
    "csv": "csv",
    "markdown": "md",
    "md": "md",
    "text": "txt",
    "txt": "txt",
    "sql": "sql",
    "bash": "sh",
    "sh": "sh",
    "java": "java",
    "c": "c",
    "cpp": "cpp",
    "yaml": "yaml",
    "yml": "yaml",
    "xml": "xml",
    "svg": "svg",
    "r": "r",
}
METADATA = "id,thread_id,name,language,version,created,updated,length(CAST(content AS BLOB)) AS size"


def requested(message, history):
    """Enable file tooling for this request, never just because a file exists.

    Keep short edit follow-ups useful while unrelated questions and social turns
    do not inherit a previous file-generation task.
    """
    from .conversation_intent import social_reply

    if social_reply(message):
        return False
    explicit = re.search(
        r"\b(?:files?|download(?:able)?|export|code|coding|scripts?|program(?:me)?|python|javascript|typescript|html|css|csv|json|markdown|website|web\s*page|sql|java|c\+\+)\b|\.(?:py|js|ts|html|css|csv|json|md)\b",
        message,
        re.I,
    )
    if explicit:
        return True
    edit = re.search(
        r"\b(?:redo|change|make|update|edit|fix|add|remove|replace|rewrite|convert|improve|refactor)\b",
        message,
        re.I,
    )
    return bool(edit and any("```" in item.get("content", "") for item in history[-4:]))


def init(con):
    con.execute("""CREATE TABLE IF NOT EXISTS artifacts(
        id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, user_id INTEGER NOT NULL,
        message_id INTEGER, name TEXT NOT NULL, language TEXT NOT NULL,
        content TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
        created REAL NOT NULL, updated REAL NOT NULL)""")
    con.execute(
        "CREATE INDEX IF NOT EXISTS artifacts_thread ON artifacts(thread_id,created)"
    )


def metadata(row):
    return {
        **dict(row),
        "generated": True,
        "url": "/api/artifacts/" + row["id"] + "/download",
    }


def extract(text):
    """Ignore incomplete/unknown fences; cap both response count and UTF-8 bytes."""
    result = []
    pattern = (
        r"^(?P<fence>`{3,})(?P<header>[^\n`]*)\n(?P<content>.*?)^(?P=fence)[ \t]*$"
    )
    for match in re.finditer(pattern, text, re.MULTILINE | re.DOTALL):
        header, content = match["header"], match["content"]
        token = header.strip().split(" ")[0].lower()
        # Accept a filename alone as well as `python filename="example.py"`.
        filename = re.search(r'(?:filename|file)=["\']?([^\s"\']+)', header)
        if "." in token and not filename:
            name = token
            language = next(
                (k for k, v in EXTENSIONS.items() if name.endswith("." + v)), ""
            )
        else:
            language = token
            name = filename.group(1) if filename else ""
        if language not in EXTENSIONS or not content.strip():
            continue
        if len(content.encode("utf-8")) > MAX_BYTES:
            continue
        # Flatten untrusted path-like names and ensure a harmless download basename.
        name = re.sub(
            r"[^A-Za-z0-9_.-]", "_", name.replace("\\", "/").rsplit("/", 1)[-1]
        )[:100]
        suffix = EXTENSIONS[language]
        if (
            not name
            or name.startswith(".")
            or name.rsplit(".", 1)[-1] not in set(EXTENSIONS.values())
        ):
            name = f"generated-{len(result) + 1}.{suffix}"
        if name in {item["name"] for item in result}:
            name = f"{len(result) + 1}-{name}"
        result.append({"name": name, "language": language, "content": content})
        if len(result) == 6:
            break
    return result


def save_reply(s, con, user, tid, mid, text, meta):
    if (
        not s.permission(user, "generate_files")
        or meta.get("stopped")
        or meta.get("student_preview")
    ):
        return []
    count = con.execute(
        "SELECT count(*) FROM artifacts WHERE thread_id=?", (tid,)
    ).fetchone()[0]
    out = []
    for file in extract(text)[: max(0, MAX_FILES - count)]:
        fid, now = secrets.token_hex(16), time.time()
        con.execute(
            "INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,1,?,?)",
            (
                fid,
                tid,
                user["id"],
                mid,
                file["name"],
                file["language"],
                file["content"],
                now,
                now,
            ),
        )
        row = con.execute(
            f"SELECT {METADATA} FROM artifacts WHERE id=?", (fid,)
        ).fetchone()
        out.append(metadata(row))
    return out


def owned(s, h, user, fid):
    with s.connect() as con:
        row = con.execute(
            "SELECT * FROM artifacts WHERE id=? AND user_id=?", (fid, user["id"])
        ).fetchone()
    if not row:
        raise s.APIError(404, "Generated file not found")
    h.owned_thread(row["thread_id"], user)
    return row


def serve_preview(h, content, interactive=False):
    """A separate response allows inline CSS without relaxing the app's CSP."""
    body = content.encode("utf-8")
    h.send_response(200)
    h.send_header(
        "Content-Security-Policy",
        "default-src 'none'; script-src "
        + ("'unsafe-inline'" if interactive else "'none'")
        + "; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'self'; form-action 'none'; base-uri 'none'; sandbox"
        + (" allow-scripts" if interactive else ""),
    )
    h.send_header("X-Content-Type-Options", "nosniff")
    h.send_header("Content-Type", "text/html; charset=utf-8")
    h.send_header("Cache-Control", "no-store")
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    h.wfile.write(body)


def preview_style(css):
    return "<style>" + re.sub(r"</style", r"<\\/style", css, flags=re.I) + "</style>"


def bundle_preview(s, user, tid, content, reply_text=""):
    """Inline only this reply's CSS/JS and explicitly linked owned chat files."""
    from html.parser import HTMLParser

    class Resources(HTMLParser):
        def __init__(self):
            super().__init__()
            self.links = []

        def handle_starttag(self, tag, attributes):
            attributes = dict(attributes)
            kind = (
                "css"
                if tag == "link"
                and "stylesheet" in (attributes.get("rel") or "").lower().split()
                else "js" if tag == "script" and attributes.get("src") else None
            )
            if kind:
                href = (
                    (attributes.get("href" if kind == "css" else "src") or "")
                    .split("?", 1)[0]
                    .split("#", 1)[0]
                )
                self.links.append(
                    (
                        self.get_starttag_text(),
                        kind,
                        href.replace("\\", "/").rsplit("/", 1)[-1].lower(),
                    )
                )

    links = Resources()
    links.feed(content)
    assets = {}
    for file in extract(reply_text):
        kind = (
            "css"
            if file["language"] == "css"
            else "js" if file["language"] in ("javascript", "js") else None
        )
        if kind:
            assets[kind, file["name"].lower()] = file["content"]
    names = list(dict.fromkeys(name for _, _, name in links.links))[:6]
    if names:
        with s.connect() as con:
            files = con.execute(
                "SELECT name,language,content FROM artifacts WHERE thread_id=? AND user_id=? AND language IN ('css','js','javascript') AND lower(name) IN ("
                + ",".join("?" for _ in names)
                + ") ORDER BY updated DESC LIMIT 6",
                (tid, user["id"], *names),
            ).fetchall()
        # Latest saved edits take precedence over the original reply's code.
        saved = set()
        for file in files:
            key = ("css" if file["language"] == "css" else "js", file["name"].lower())
            if key not in saved and len(file["content"].encode("utf-8")) <= MAX_BYTES:
                assets[key] = file["content"]
                saved.add(key)
    used = set()
    for tag, kind, name in links.links:
        key = kind, name
        if key in assets:
            source = assets[key]
            replacement = (
                preview_style(source)
                if kind == "css"
                else "<script>" + re.sub(r"</script", r"<\\/script", source, flags=re.I)
            )
            projected = len(content.encode("utf-8")) + content.count(tag) * (
                len(replacement.encode("utf-8")) - len(tag.encode("utf-8"))
            )
            if projected > MAX_BYTES * 4:
                raise s.APIError(400, "Combined preview is too large")
            content = content.replace(tag, replacement)
            used.add(key)
    extra_css = "".join(
        preview_style(source)
        for (kind, name), source in assets.items()
        if kind == "css" and (kind, name) not in used
    )
    extra_js = "".join(
        "<script>"
        + re.sub(r"</script", r"<\\/script", source, flags=re.I)
        + "</script>"
        for (kind, name), source in assets.items()
        if kind == "js" and (kind, name) not in used
    )
    if re.search(r"</head\s*>", content, flags=re.I):
        content = re.sub(
            r"</head\s*>",
            lambda match: extra_css + match[0],
            content,
            count=1,
            flags=re.I,
        )
    else:
        doctype = re.match(r"\s*<!doctype[^>]*>", content, flags=re.I)
        insertion = doctype.end() if doctype else 0
        content = content[:insertion] + extra_css + content[insertion:]
    result = content + extra_js
    if len(result.encode("utf-8")) > MAX_BYTES * 4:
        raise s.APIError(400, "Combined preview is too large")
    return result


def code_preview(s, h, user, path):
    """Preview a saved assistant block with its styles; never save or run code.

    The source is re-read under thread ownership on every request, including tabs
    opened separately. CSS may come only from that reply or its owner's chat files.
    """
    parts = path.split("/")
    if len(parts) != 6 or not parts[5].isdigit() or int(parts[5]) > 100:
        raise s.APIError(404, "Code preview not found")
    tid, mid, index = parts[3], parts[4], int(parts[5])
    h.owned_thread(tid, user)
    if not s.permission(user, "generate_files"):
        raise s.APIError(403, "Generated files permission required")
    with s.connect() as con:
        row = con.execute(
            "SELECT content FROM messages WHERE id=? AND thread_id=? AND role='assistant'",
            (mid, tid),
        ).fetchone()
    if not row:
        raise s.APIError(404, "Code preview not found")
    # Keep block indices identical to the renderer, including unknown languages.
    blocks = list(re.finditer(r"```([^\n`]*)\n([\s\S]*?)(?:```|$)", row["content"]))
    if index >= len(blocks):
        raise s.APIError(404, "Code preview not found")
    block = blocks[index]
    language = block[1].strip().split(" ")[0].lower()
    content = block[2]
    if (
        language not in ("html", "css", "svg")
        or not block[0].endswith("```")
        or len(content.encode("utf-8")) > MAX_BYTES
    ):
        raise s.APIError(
            400, "Preview needs a complete HTML, CSS or SVG block under 128 KiB"
        )

    if language == "css":
        content = (
            preview_style(content)
            + "<main><h1>CSS preview</h1><p>Sample paragraph</p><button>Sample button</button></main>"
        )
    else:
        content = bundle_preview(s, user, tid, content, row["content"])
    return serve_preview(h, content, interactive=True)


def get(s, h, user, path):
    parts = path.split("/")
    if path == "/api/artifacts":
        tid = parse_qs(urlsplit(h.path).query).get("thread_id", [""])[0]
        h.owned_thread(tid, user)
        with s.connect() as con:
            rows = con.execute(
                f"SELECT {METADATA} FROM artifacts WHERE thread_id=? AND user_id=? ORDER BY created DESC LIMIT ?",
                (tid, user["id"], MAX_FILES),
            ).fetchall()
        return h.respond(200, {"files": [metadata(r) for r in rows]})
    row = owned(s, h, user, parts[3])
    if len(parts) == 4:
        return h.respond(
            200,
            {
                "file": {
                    **metadata(
                        {
                            k: row[k]
                            for k in (
                                "id",
                                "thread_id",
                                "name",
                                "language",
                                "version",
                                "created",
                                "updated",
                            )
                        }
                    ),
                    "size": len(row["content"].encode()),
                    "content": row["content"],
                },
                "can_edit": s.permission(user, "generate_files"),
                "can_run": s.permission(user, "run_code"),
                "runner_enabled": s.settings().get("code_execution_enabled") is True,
            },
        )
    preview = parts[-1] == "preview"
    if parts[-1] not in ("download", "preview"):
        raise s.APIError(404, "Not found")
    if preview and row["language"] not in ("html", "css", "svg"):
        raise s.APIError(400, "Static preview supports HTML, CSS and SVG")
    content = row["content"]
    if preview and row["language"] == "css":
        content = (
            "<!doctype html><style>"
            + content
            + "</style><main><h1>CSS preview</h1><p>Sample paragraph</p><button>Sample button</button></main>"
        )
    if preview:
        with s.connect() as con:
            reply = con.execute(
                "SELECT content FROM messages WHERE id=? AND thread_id=? AND role='assistant'",
                (row["message_id"], row["thread_id"]),
            ).fetchone()
        if row["language"] != "css":
            content = bundle_preview(
                s, user, row["thread_id"], content, reply["content"] if reply else ""
            )
        return serve_preview(
            h, content, interactive=s.permission(user, "generate_files")
        )
    body = content.encode("utf-8")
    h.send_response(200)
    h.common_headers()
    h.send_header(
        "Content-Disposition", "attachment; filename*=UTF-8''" + quote(row["name"])
    )
    h.send_header("Content-Type", "text/plain; charset=utf-8")
    h.send_header("Cache-Control", "no-store")
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    h.wfile.write(body)


def post(s, h, user, path, data):
    fid = path.split("/")[3]
    row = owned(s, h, user, fid)
    if path.endswith("/run"):
        from . import code_runner

        return code_runner.run(s, user, row)
    if path != "/api/artifacts/" + fid:
        raise s.APIError(404, "Not found")
    if not s.permission(user, "generate_files"):
        raise s.APIError(
            403, "File generation and editing are disabled for this account"
        )
    content = data.get("content")
    if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_BYTES:
        raise s.APIError(400, "Generated files must be under 128 KiB")
    if type(data.get("version")) is not int:
        raise s.APIError(400, "A file version is required")
    with s.connect() as con:
        changed = con.execute(
            "UPDATE artifacts SET content=?,version=version+1,updated=? WHERE id=? AND user_id=? AND version=?",
            (content, time.time(), fid, user["id"], data["version"]),
        ).rowcount
        if not changed:
            raise s.APIError(
                409, "This file changed in another window. Reopen it before saving."
            )
    s.audit(user["id"], "edit_generated_file", fid)
    return {"ok": True, "version": data["version"] + 1}
