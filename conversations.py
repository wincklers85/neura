from __future__ import annotations

from datetime import datetime, timezone
from db import db
from security import decrypt_text


def ensure_conversation(session_id: str, first_message: str | None = None) -> None:
    title = (first_message or "Nuova conversazione").strip().replace("\n", " ")[:72] or "Nuova conversazione"
    with db() as conn:
        row = conn.execute("SELECT session_id FROM chat_sessions WHERE session_id=?", (session_id,)).fetchone()
        if row:
            conn.execute("UPDATE chat_sessions SET updated_at=CURRENT_TIMESTAMP WHERE session_id=?", (session_id,))
        else:
            conn.execute("INSERT INTO chat_sessions(session_id,title) VALUES(?,?)", (session_id, title))


def list_sessions(limit: int = 200) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """SELECT s.session_id,s.title,s.archived,s.created_at,s.updated_at,
                      COUNT(c.id) message_count
               FROM chat_sessions s LEFT JOIN conversations c ON c.session_id=s.session_id
               GROUP BY s.session_id ORDER BY s.updated_at DESC LIMIT ?""", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def rename_session(session_id: str, title: str) -> None:
    with db() as conn:
        conn.execute("UPDATE chat_sessions SET title=?,updated_at=CURRENT_TIMESTAMP WHERE session_id=?", (title[:120], session_id))


def archive_session(session_id: str, archived: bool) -> None:
    with db() as conn:
        conn.execute("UPDATE chat_sessions SET archived=?,updated_at=CURRENT_TIMESTAMP WHERE session_id=?", (1 if archived else 0, session_id))


def delete_session(session_id: str) -> None:
    with db() as conn:
        conn.execute("DELETE FROM conversations WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM chat_sessions WHERE session_id=?", (session_id,))


def session_messages(session_id: str, limit: int = 1000) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT id,role,content_enc,created_at FROM conversations WHERE session_id=? ORDER BY id ASC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    return [{"id":r["id"],"role":r["role"],"content":decrypt_text(r["content_enc"]),"created_at":r["created_at"]} for r in rows]


def search_sessions(query: str, limit: int = 50) -> list[dict]:
    q = query.strip().lower()
    if not q:
        return list_sessions(limit)
    results = []
    with db() as conn:
        sessions = conn.execute("SELECT session_id,title,archived,created_at,updated_at FROM chat_sessions ORDER BY updated_at DESC").fetchall()
        messages = conn.execute("SELECT session_id,content_enc,created_at FROM conversations ORDER BY id DESC").fetchall()
    snippets: dict[str,str] = {}
    for m in messages:
        text = decrypt_text(m["content_enc"])
        if q in text.lower() and m["session_id"] not in snippets:
            pos = text.lower().find(q)
            snippets[m["session_id"]] = text[max(0,pos-80):pos+180]
    for s in sessions:
        if q in s["title"].lower() or s["session_id"] in snippets:
            d = dict(s); d["snippet"] = snippets.get(s["session_id"], "")
            results.append(d)
            if len(results) >= limit: break
    return results
