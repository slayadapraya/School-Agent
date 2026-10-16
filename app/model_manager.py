"""Account-scoped admin model choices; students always use the main tutor."""

import json, time
from urllib.request import Request, urlopen
from urllib.parse import urlsplit


def init(con):
    con.executescript(
        """CREATE TABLE IF NOT EXISTS admin_model_preferences(user_id INTEGER PRIMARY KEY,selected TEXT NOT NULL,prompts TEXT NOT NULL,pending INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS model_grants(user_id INTEGER PRIMARY KEY,models TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS thread_models(thread_id TEXT PRIMARY KEY,model_key TEXT NOT NULL);"""
    )


def request(s, path, payload=None, timeout=5):
    base = s.settings()["model_url"]
    url = urlsplit(base)
    if url.scheme != "http" or url.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("Local model URL required")
    root = base.rsplit("/v1", 1)[0]
    req = Request(
        root + "/api/v1/" + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read(1000000))


def main_key(s):
    return s.settings().get("model_key", s.settings()["model"])


def preferences(s, user):
    with s.connect() as con:
        row = con.execute(
            "SELECT * FROM admin_model_preferences WHERE user_id=?", (user["id"],)
        ).fetchone()
    return (
        {
            "selected": row["selected"],
            "initial_prompts": json.loads(row["prompts"]),
            "pending": bool(row["pending"]),
        }
        if row
        else {"selected": main_key(s), "initial_prompts": {}, "pending": False}
    )


def catalog(s, user):
    models = request(s, "models").get("models", [])
    return {
        "models": [
            {
                k: m.get(k)
                for k in (
                    "key",
                    "display_name",
                    "type",
                    "quantization",
                    "size_bytes",
                    "loaded_instances",
                    "architecture",
                )
            }
            for m in models
        ],
        "main": main_key(s),
        **preferences(s, user),
    }


def save(s, user, data, personal=False):
    if user["role"] != "admin" and not personal:
        raise s.APIError(403, "Administrator access required")
    key = data.get("model")
    text = data.get("initial_prompt", "")
    if personal:
        if key not in allowed(s, user):
            raise s.APIError(403, "This model is locked. Ask your teacher for access.")
        data = {**data, "select": True}
        text = (
            preferences(s, user)["initial_prompts"].get(key, "")
            if user["role"] == "admin"
            else ""
        )
    if not isinstance(text, str) or len(text) > 12000:
        raise s.APIError(
            400, "Use up to 12000 characters for the custom initial instructions"
        )
    if not s.MODEL_LOCK.acquire(blocking=False):
        raise s.APIError(
            409, "A model response is in progress; save again once it finishes"
        )
    try:
        available = request(s, "models").get("models", [])
        if not any(m["key"] == key and m["type"] == "llm" for m in available):
            raise s.APIError(400, "Choose a downloaded chat model")
        pref = preferences(s, user)
        pref["initial_prompts"][key] = text
        changed = data.get("select") is True and key != pref["selected"]
        if changed:
            pref.update(selected=key, pending=True)
        with s.connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO admin_model_preferences VALUES(?,?,?,?)",
                (
                    user["id"],
                    pref["selected"],
                    json.dumps(pref["initial_prompts"]),
                    int(pref["pending"]),
                ),
            )
        if changed:
            for m in available:
                if m["type"] == "llm":
                    for instance in m.get("loaded_instances", []):
                        request(s, "models/unload", {"instance_id": instance["id"]}, 30)
        s.audit(user["id"], "model_configuration", key)
        return {"ok": True, **pref}
    finally:
        s.MODEL_LOCK.release()


def chosen(s, user, tid, new_chat):
    # No client-supplied model key, role or prompt is trusted.
    pref = preferences(s, user)
    with s.connect() as con:
        row = con.execute(
            "SELECT model_key FROM thread_models WHERE thread_id=?", (tid,)
        ).fetchone()
    permitted = allowed(s, user)
    if pref["selected"] not in permitted:
        pref.update(selected=main_key(s), pending=False)
    if pref["pending"] and not new_chat:
        raise s.APIError(
            409,
            "Start a new chat and send its first message to use your selected model.",
        )
    key = pref["selected"] if new_chat else row["model_key"] if row else main_key(s)
    if key not in permitted:
        key = main_key(s)
    return key, pref["initial_prompts"].get(key, "") if user["role"] == "admin" else ""


def prepare(s, user, tid, new_chat, preview=False):
    # Preview always uses the restricted main tutor, regardless of admin model preferences.
    key, initial = (main_key(s), "") if preview else chosen(s, user, tid, new_chat)
    try:
        available = request(s, "models").get("models", [])
        model = next(m for m in available if m["key"] == key and m["type"] == "llm")
        loaded = model.get("loaded_instances", [])
        if loaded:
            instance = loaded[0]["id"]
        else:
            for m in available:
                if m["type"] == "llm":
                    for current in m.get("loaded_instances", []):
                        request(s, "models/unload", {"instance_id": current["id"]}, 30)
            instance = request(
                s,
                "models/load",
                {
                    "model": key,
                    "context_length": min(8192, model.get("max_context_length", 8192)),
                },
                180,
            )["instance_id"]
    except Exception as e:
        import logging

        logging.getLogger("school_agent").exception("Local model load failed")
        raise s.APIError(
            503,
            "The requested local model could not load. Check LM Studio or select a smaller model and retry.",
        ) from e
    if True:
        with s.connect() as con:
            con.execute("INSERT OR REPLACE INTO thread_models VALUES(?,?)", (tid, key))
            if new_chat:
                con.execute(
                    "UPDATE admin_model_preferences SET pending=0 WHERE user_id=?",
                    (user["id"],),
                )
    return {
        "key": key,
        "instance": instance,
        "transport": "qwen_chatml" if model.get("architecture") == "qwen35" else "chat",
        "initial_prompt": initial if user["role"] == "admin" and not preview else "",
        "private_model": user["role"] == "admin" and key != main_key(s) and not preview,
    }


def allowed(s, user):
    if user["role"] == "admin":
        return {
            m["key"]
            for m in request(s, "models").get("models", [])
            if m["type"] == "llm"
        }
    with s.connect() as con:
        row = con.execute(
            "SELECT models FROM model_grants WHERE user_id=?", (user["id"],)
        ).fetchone()
    return {main_key(s), *(json.loads(row[0]) if row else [])}


def selector(s, user):
    permitted = allowed(s, user)
    pref = preferences(s, user)
    return {
        "selected": pref["selected"] if pref["selected"] in permitted else main_key(s),
        "main": main_key(s),
        "models": [
            {
                "key": m["key"],
                "name": m["display_name"],
                "locked": m["key"] not in permitted,
            }
            for m in request(s, "models").get("models", [])
            if m["type"] == "llm"
        ],
    }


def access(s, user, data=None):
    if user["role"] not in ("teacher", "admin"):
        raise s.APIError(403, "Teacher access required")
    scope = s.oversight.student_ids(s, user)
    if data is not None:
        uid = data.get("user_id")
        keys = data.get("models")
        if type(uid) is not int or uid not in scope:
            raise s.APIError(403, "Choose one of your assigned students")
        inventory = {
            m["key"]
            for m in request(s, "models").get("models", [])
            if m["type"] == "llm"
        }
        if not isinstance(keys, list) or not all(
            isinstance(k, str) and k in inventory for k in keys
        ):
            raise s.APIError(400, "Choose downloaded chat models")
        with s.connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO model_grants VALUES(?,?)",
                (uid, json.dumps(sorted(set(keys)))),
            )
        s.audit(user["id"], "student_model_access", str(uid))
        return {"ok": True}
    with s.connect() as con:
        users = [
            {"id": r["id"], "name": r["name"]}
            for r in con.execute(
                'SELECT id,name FROM users WHERE role="student" ORDER BY name'
            )
            if r["id"] in scope
        ]
        grants = {
            r["user_id"]: json.loads(r["models"])
            for r in con.execute("SELECT * FROM model_grants")
        }
    return {
        "students": [{**u, "models": grants.get(u["id"], [])} for u in users],
        "main": main_key(s),
        "models": [
            {"key": m["key"], "name": m["display_name"]}
            for m in request(s, "models").get("models", [])
            if m["type"] == "llm"
        ],
    }
