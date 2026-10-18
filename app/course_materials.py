"""Class-scoped teaching files and page-aware retrieval. Never reads chat records."""

from __future__ import annotations
import base64
import collections
import io
import json
import math
import posixpath
import re
import secrets
import subprocess
import tempfile
import time
import unicodedata
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from urllib.parse import parse_qs, quote

MAX_FILE = 6 * 1024 * 1024
TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
    ".md": "text/plain",
}
STOP = set(
    "a an and are as at be been but by can could do does explain for from give how i in into is it its me my of on or our please says so some tell that the their them there these they this to understand us using was we what when where which why will with would you your lecture notes material course more again".split()
)


def init(con):
    con.executescript(
        """CREATE TABLE IF NOT EXISTS course_materials(
        id TEXT PRIMARY KEY,course_id TEXT NOT NULL,class_id INTEGER,uploaded_by INTEGER NOT NULL,
        name TEXT NOT NULL,mime TEXT NOT NULL,body BLOB NOT NULL,page_count INTEGER NOT NULL,
        unit_kind TEXT NOT NULL,created REAL NOT NULL,archived INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS course_material_chunks(
        id TEXT PRIMARY KEY,material_id TEXT NOT NULL,page INTEGER NOT NULL,label TEXT NOT NULL,text TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS material_course ON course_materials(course_id,class_id,archived);
        CREATE INDEX IF NOT EXISTS material_chunks ON course_material_chunks(material_id,page);"""
    )


def teaching_groups(s, user):
    if user["role"] == "admin":
        return [g for g in s.administration.groups(s) if g["enabled"]]
    if user["role"] != "teacher":
        return []
    return [g for g in s.administration.groups(s, user["id"]) if g["enabled"]]


def allowed(s, user, material, write=False):
    if user["role"] == "admin":
        return True
    if not s.course_access(user, material["course_id"]):
        return False
    groups = [
        g
        for g in s.administration.groups(s, user["id"])
        if g["enabled"] and material["course_id"] in g["courses"]
    ]
    if write:
        return (
            user["role"] == "teacher"
            and material["uploaded_by"] == user["id"]
            and any(g["id"] == material["class_id"] for g in groups)
        )
    if material["class_id"] is None:
        return True
    return any(g["id"] == material["class_id"] for g in groups)


def metadata(s, user, row):
    return {
        k: row[k]
        for k in (
            "id",
            "course_id",
            "class_id",
            "name",
            "mime",
            "page_count",
            "unit_kind",
            "created",
            "archived",
        )
    } | {
        "can_manage": allowed(s, user, row, True),
        "url": f"/api/course-materials/{row['id']}/content",
    }


def listing(s, user, code=None):
    if code and not s.course_access(user, code):
        raise s.APIError(403, "Subject access required")
    with s.connect() as con:
        rows = con.execute(
            "SELECT id,course_id,class_id,uploaded_by,name,mime,page_count,unit_kind,created,archived FROM course_materials"
            + (" WHERE course_id=?" if code else "")
            + " ORDER BY created DESC",
            (code,) if code else (),
        ).fetchall()
    docs = [
        metadata(s, user, dict(r))
        for r in rows
        if allowed(s, user, dict(r))
        and (not r["archived"] or allowed(s, user, dict(r), True))
    ]
    groups = teaching_groups(s, user)
    codes = {c for g in groups for c in g["courses"]}
    return {
        "materials": docs,
        "groups": [
            {"id": g["id"], "name": g["name"], "courses": g["courses"]} for g in groups
        ],
        "courses": [
            {"id": c["id"], "name": c["name"]}
            for c in s.courses()
            if user["role"] == "admin" or c["id"] in codes
        ],
        "can_upload": user["role"] == "admin"
        or user["role"] == "teacher"
        and bool(groups),
    }


def xml(z, name):
    entry = z.getinfo(name)
    if entry.file_size > 2000000:
        raise ValueError("Document text is too large")
    raw = z.read(entry)
    if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
        raise ValueError("Unsupported XML document")
    return ET.fromstring(raw)


def text_units(text):
    # These are logical sections, never fabricated DOCX/TXT page numbers.
    paragraphs = re.split(r"\n\s*\n", text.strip())
    units = []
    current = ""
    for p in paragraphs:
        for start in range(0, len(p), 1800):
            part = p[start : start + 1800]
            if current and len(current) + len(part) > 1800:
                units.append(current)
                current = ""
            current += ("\n\n" if current else "") + part
    if current:
        units.append(current)
    return units


def extract(body, suffix):
    if suffix in (".txt", ".md"):
        text = body.decode("utf-8-sig", errors="strict")
        if "\x00" in text:
            raise ValueError("Upload a UTF-8 text file")
        if len(text) > 240000:
            raise ValueError("Limit a teaching text file to 240,000 characters")
        pages = text_units(text)
        kind = "Section"
    elif suffix == ".pdf":
        if not body.startswith(b"%PDF-"):
            raise ValueError("Invalid PDF")
        with tempfile.TemporaryDirectory(prefix="school-material-") as directory:
            path = Path(directory) / "source.pdf"
            out = Path(directory) / "text.txt"
            path.write_bytes(body)
            try:
                info = subprocess.run(
                    ["pdfinfo", str(path)], capture_output=True, timeout=5, check=True
                )
                count = re.search(rb"^Pages:\s+(\d+)", info.stdout, re.M)
                if not count or int(count[1]) > 80:
                    raise ValueError("Upload a PDF with at most 80 pages")
                subprocess.run(
                    ["pdftotext", "-layout", str(path), str(out)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=15,
                    check=True,
                )
                if out.stat().st_size > 2000000:
                    raise ValueError("PDF text is too large")
                pages = out.read_text(errors="replace").split("\f")
                pages = pages[: int(count[1])]
            except (FileNotFoundError, subprocess.SubprocessError):
                raise ValueError(
                    "Unable to read this PDF. Use a text-based, unlocked PDF, or upload a text document."
                )
        kind = "Page"
    else:
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            if (
                sum(i.file_size for i in z.infolist()) > 24000000
                or len(z.infolist()) > 3000
            ):
                raise ValueError("Expanded office document is too large")
            if suffix == ".docx":
                root = xml(z, "word/document.xml")
                ns = {
                    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                }
                text = "\n\n".join(
                    "".join(t.text or "" for t in p.findall(".//w:t", ns))
                    for p in root.findall(".//w:p", ns)
                )
                if len(text) > 240000:
                    raise ValueError("Document text is too large")
                pages = text_units(text)
                kind = "Section"
            else:
                root = xml(z, "ppt/presentation.xml")
                ns = {
                    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
                    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
                    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
                }
                rels = {
                    r.get("Id"): r for r in xml(z, "ppt/_rels/presentation.xml.rels")
                }
                slides = root.findall("p:sldIdLst/p:sldId", ns)
                if len(slides) > 120:
                    raise ValueError("Upload at most 120 slides")
                pages = []
                for slide in slides:
                    rel = rels[slide.get("{" + ns["r"] + "}id")]
                    if rel.get("TargetMode") == "External":
                        raise ValueError("External slides are not supported")
                    target = rel.get("Target", "")
                    name = posixpath.normpath(
                        target.lstrip("/")
                        if target.startswith("/")
                        else "ppt/" + target
                    )
                    if not re.fullmatch(r"ppt/slides/[^/]+\.xml", name):
                        raise ValueError("Invalid slide reference")
                    doc = xml(z, name)
                    pages.append(
                        "\n".join(
                            "".join(t.text or "" for t in p.findall(".//a:t", ns))
                            for p in doc.findall(".//a:p", ns)
                        )
                    )
                kind = "Slide"
    if not pages or not any(p.strip() for p in pages):
        raise ValueError(
            "No readable text was found. Scanned PDFs and image-only slides need text recognition first."
        )
    if sum(len(p) for p in pages) > 500000:
        raise ValueError("Document contains too much text; split it into smaller files")
    chunks = []
    for number, page in enumerate(pages, 1):
        # Keep physical page/slide numbers even when intermediate pages are blank.
        text = re.sub(r"[ \t]+", " ", page).strip()
        for start in range(0, len(text), 1350):
            passage = text[start : start + 1600].strip()
            if passage:
                chunks.append((number, f"{kind} {number}", passage))
    if len(chunks) > 600:
        raise ValueError(
            "Document contains too many passages; split it into smaller files"
        )
    return chunks, len(pages), kind


def upload(s, user, data):
    if user["role"] not in ("admin", "teacher"):
        raise s.APIError(403, "Teacher access required")
    code = data.get("course_id")
    known = {c["id"] for c in s.courses()}
    if not isinstance(code, str) or code not in known:
        raise s.APIError(400, "Select a valid subject")
    group = data.get("class_id")
    if group is not None and (type(group) is not int or group < 1):
        raise s.APIError(400, "Select a valid class")
    groups = teaching_groups(s, user)
    if group is not None and not any(
        g["id"] == group and code in g["courses"] for g in groups
    ):
        raise s.APIError(403, "Select a subject in one of your assigned classes")
    if user["role"] == "teacher" and group is None:
        raise s.APIError(
            403, "Teachers publish to their assigned classes; select a class"
        )
    name = data.get("name", "")
    encoded = data.get("data", "")
    if (
        not isinstance(name, str)
        or not 1 <= len(name) <= 180
        or any(c in name for c in ("\x00", "\r", "\n", "/", "\\"))
    ):
        raise s.APIError(400, "Use a plain file name under 180 characters")
    suffix = Path(name).suffix.lower()
    if suffix not in TYPES:
        raise s.APIError(400, "Supported teaching files: PDF, DOCX, PPTX, TXT and MD")
    if not isinstance(encoded, str) or len(encoded) > MAX_FILE * 4 // 3 + 8:
        raise s.APIError(400, "Files must be at most 6 MB")
    try:
        body = base64.b64decode(encoded, validate=True)
    except Exception:
        raise s.APIError(400, "Invalid file data")
    if not 0 < len(body) <= MAX_FILE:
        raise s.APIError(400, "Files must be at most 6 MB")
    try:
        chunks, count, kind = extract(body, suffix)
    except Exception as e:
        raise s.APIError(
            400,
            (
                str(e)[:180]
                if isinstance(e, ValueError)
                else "This file could not be read. Check its format and try again."
            ),
        )
    with s.connect() as con:
        if (
            con.execute(
                "SELECT COUNT(*) FROM course_materials WHERE course_id=? AND archived=0",
                (code,),
            ).fetchone()[0]
            >= 40
        ):
            raise s.APIError(400, "This subject already has 40 active teaching files")
        mid = secrets.token_hex(16)
        con.execute(
            "INSERT INTO course_materials(id,course_id,class_id,uploaded_by,name,mime,body,page_count,unit_kind,created) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                mid,
                code,
                group,
                user["id"],
                name,
                TYPES[suffix],
                body,
                count,
                kind,
                time.time(),
            ),
        )
        con.executemany(
            "INSERT INTO course_material_chunks VALUES(?,?,?,?,?)",
            [
                (secrets.token_hex(16), mid, page, label, text)
                for page, label, text in chunks
            ],
        )
    s.audit(
        user["id"],
        "course_material_upload",
        json.dumps({"material": mid, "subject": code, "class": group}),
    )
    return {"id": mid, "page_count": count, "unit_kind": kind, "passages": len(chunks)}


def authorize(s, user, mid):
    with s.connect() as con:
        row = con.execute(
            "SELECT * FROM course_materials WHERE id=?", (mid,)
        ).fetchone()
    if not row or not allowed(s, user, dict(row)):
        raise s.APIError(404, "Teaching file not found")
    return dict(row)


def tokens(text):
    text = "".join(
        c
        for c in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(c)
    )
    out = []
    for w in re.findall(r"\w+", text):
        if len(w) < 2 or w in STOP:
            continue
        if w.endswith("ies") and len(w) > 5:
            w = w[:-3] + "y"
        elif w.endswith("s") and len(w) > 4 and not w.endswith(("ss", "us", "is")):
            w = w[:-1]
        out.append(w)
    return out[:180]


def retrieve(s, user, code, question, history=()):
    if not s.course_access(user, code):
        return []
    query = tokens(question)
    if len(query) < 3 and (
        re.search(r"\b(it|that|this|again|why|more|simpler)\b", question, re.I)
        or not query
    ):
        for turn in reversed(history[-6:]):
            if turn["role"] == "user":
                query += tokens(turn["content"])[:40]
                break
    wanted = set(query)
    if not wanted:
        return []
    with s.connect() as con:
        docs = [
            dict(r)
            for r in con.execute(
                "SELECT id,course_id,class_id,uploaded_by,name,mime,archived FROM course_materials WHERE course_id=? AND archived=0",
                (code,),
            )
            if allowed(s, user, dict(r))
        ]
        if not docs:
            return []
        ids = {d["id"]: d for d in docs}
        marks = ",".join("?" for _ in ids)
        rows = [
            dict(r)
            for r in con.execute(
                "SELECT * FROM course_material_chunks WHERE material_id IN ("
                + marks
                + ")",
                tuple(ids),
            )
        ]
    counters = [
        collections.Counter(tokens(r["text"] + " " + ids[r["material_id"]]["name"]))
        for r in rows
    ]
    frequency = collections.Counter(t for c in counters for t in c if t in wanted)
    scored = []
    for row, terms in zip(rows, counters):
        overlap = wanted & terms.keys()
        if not overlap:
            continue
        score = sum(
            math.log(1 + len(rows) / (1 + frequency[t])) * (1 + math.log(terms[t]))
            for t in overlap
        )
        scored.append((score, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    selected = []
    per_page = set()
    budget = 4800
    for score, row in scored:
        # Avoid repeating overlapping chunks of the same page in one answer.
        key = (row["material_id"], row["page"])
        if key in per_page:
            continue
        doc = ids[row["material_id"]]
        text = row["text"][: min(1500, budget)]
        budget -= len(text)
        selected.append(
            {
                "id": "material-" + row["id"],
                "title": doc["name"],
                "locator": code + " · " + row["label"],
                "url": f"/api/course-materials/{doc['id']}/content"
                + (f"#page={row['page']}" if doc["mime"] == "application/pdf" else ""),
                "text": text,
                "page": row["page"],
                "page_label": row["label"],
                "material_id": doc["id"],
                "chunk_id": row["id"],
            }
        )
        per_page.add(key)
        if len(selected) >= 3 or budget < 300:
            break
    return selected


def get(s, h, user, path):
    if path == "/api/course-materials":
        code = parse_qs(h.path.partition("?")[2]).get("course", [""])[0]
        return h.respond(200, listing(s, user, code or None))
    if path.startswith("/api/course-materials/passages/"):
        cid = path.rsplit("/", 1)[-1]
        with s.connect() as con:
            chunk = con.execute(
                "SELECT * FROM course_material_chunks WHERE id=?", (cid,)
            ).fetchone()
        if not chunk:
            raise s.APIError(404, "Passage not found")
        doc = authorize(s, user, chunk["material_id"])
        return h.respond(
            200,
            {
                "material": metadata(s, user, doc),
                "passage": {k: chunk[k] for k in ("id", "page", "label", "text")},
            },
        )
    parts = path.strip("/").split("/")
    if len(parts) == 3:
        doc = authorize(s, user, parts[2])
        with s.connect() as con:
            chunks = [
                dict(r)
                for r in con.execute(
                    "SELECT id,page,label,text FROM course_material_chunks WHERE material_id=? ORDER BY page,rowid",
                    (doc["id"],),
                )
            ]
        return h.respond(200, {"material": metadata(s, user, doc), "passages": chunks})
    if len(parts) != 4 or parts[-1] != "content":
        raise s.APIError(404, "Teaching file not found")
    doc = authorize(s, user, parts[2])
    body = doc["body"]
    h.send_response(200)
    h.common_headers(embedded=doc["mime"] == "application/pdf")
    h.send_header("Content-Type", doc["mime"])
    h.send_header("Cache-Control", "no-store")
    h.send_header(
        "Content-Disposition",
        ("inline" if doc["mime"] == "application/pdf" else "attachment")
        + "; filename*=UTF-8''"
        + quote(doc["name"], safe=""),
    )
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    h.wfile.write(body)


def update(s, user, mid, data):
    doc = authorize(s, user, mid)
    if not allowed(s, user, doc, True):
        raise s.APIError(403, "Only the uploader or administrator can manage this file")
    if set(data) != {"archived"} or type(data["archived"]) is not bool:
        raise s.APIError(400, "Choose archive or restore")
    with s.connect() as con:
        con.execute(
            "UPDATE course_materials SET archived=? WHERE id=?",
            (int(data["archived"]), mid),
        )
    s.audit(
        user["id"],
        "course_material_archive",
        json.dumps({"material": mid, "archived": data["archived"]}),
    )
    return {"ok": True}
