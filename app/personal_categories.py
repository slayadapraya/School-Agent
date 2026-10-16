"""Admin-owned navigation categories; course policies and student subjects stay separate."""

import secrets


def init(con):
    con.executescript(
        """
    CREATE TABLE IF NOT EXISTS personal_categories(id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,name TEXT NOT NULL,position INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS personal_thread_positions(thread_id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,category_id TEXT,position INTEGER NOT NULL);
    """
    )


def require(s, user):
    if user["role"] != "admin":
        raise s.APIError(403, "Administrator access required")


def get(s, user):
    require(s, user)
    with s.connect() as con:
        categories = [
            dict(r)
            for r in con.execute(
                "SELECT id,name,position FROM personal_categories WHERE user_id=? ORDER BY position,id",
                (user["id"],),
            )
        ]
        threads = [
            dict(r)
            for r in con.execute(
                "SELECT thread_id,category_id,position FROM personal_thread_positions WHERE user_id=?",
                (user["id"],),
            )
        ]
    return {"categories": categories, "threads": threads}


def update(s, h, user, data):
    require(s, user)
    action = data.get("action")
    cid = data.get("category_id")
    with s.connect() as con:
        categories = [
            dict(r)
            for r in con.execute(
                "SELECT * FROM personal_categories WHERE user_id=? ORDER BY position,id",
                (user["id"],),
            )
        ]
        category = next((c for c in categories if c["id"] == cid), None)
        if action in ("create", "rename"):
            name = data.get("name", "")
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
                raise s.APIError(400, "Use a category name between 1 and 80 characters")
            if action == "create":
                if len(categories) >= 100:
                    raise s.APIError(400, "Maximum 100 categories")
                con.execute(
                    "INSERT INTO personal_categories VALUES(?,?,?,?)",
                    (secrets.token_hex(12), user["id"], name.strip(), len(categories)),
                )
            elif category:
                con.execute(
                    "UPDATE personal_categories SET name=? WHERE id=? AND user_id=?",
                    (name.strip(), cid, user["id"]),
                )
            else:
                raise s.APIError(404, "Category not found")
        elif action == "delete":
            if not category:
                raise s.APIError(404, "Category not found")
            con.execute(
                "UPDATE personal_thread_positions SET category_id=NULL WHERE category_id=? AND user_id=?",
                (cid, user["id"]),
            )
            con.execute(
                "DELETE FROM personal_categories WHERE id=? AND user_id=?",
                (cid, user["id"]),
            )
        elif action == "reorder":
            order = data.get("ids")
            if (
                not isinstance(order, list)
                or len(order) != len(categories)
                or set(order) != {c["id"] for c in categories}
            ):
                raise s.APIError(400, "Choose a valid category order")
            con.executemany(
                "UPDATE personal_categories SET position=? WHERE id=? AND user_id=?",
                [(i, key, user["id"]) for i, key in enumerate(order)],
            )
        elif action == "move_thread":
            tid = data.get("thread_id")
            h.owned_thread(tid, user)
            if cid is not None and not category:
                raise s.APIError(404, "Category not found")
            position = data.get("position", 0)
            if type(position) is not int or abs(position) > 10000000000000:
                raise s.APIError(400, "Invalid position")
            con.execute(
                "INSERT OR REPLACE INTO personal_thread_positions VALUES(?,?,?,?)",
                (tid, user["id"], cid, position),
            )
        elif action == "order_threads":
            order = data.get("ids")
            if (
                not isinstance(order, list)
                or len(order) > 500
                or len(set(order)) != len(order)
            ):
                raise s.APIError(400, "Choose a valid chat order")
            if cid is not None and not category:
                raise s.APIError(404, "Category not found")
            for tid in order:
                h.owned_thread(tid, user)
            con.executemany(
                "INSERT OR REPLACE INTO personal_thread_positions VALUES(?,?,?,?)",
                [(tid, user["id"], cid, i) for i, tid in enumerate(order)],
            )
        else:
            raise s.APIError(400, "Unknown category action")
    return get(s, user)
