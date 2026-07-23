import math
import re
from collections import Counter
from typing import Iterable
from db import db
from security import encrypt_text, decrypt_text

STOPWORDS = {
    "che","di","a","da","in","con","su","per","tra","fra","il","lo","la","i","gli","le",
    "un","uno","una","e","o","ma","se","come","sono","sei","è","ho","hai","ha","mi","ti",
    "si","non","più","anche","questo","questa","quello","quella","del","della","dei","delle",
    "nel","nella","dei","alle","alla","al","io","tu","lui","lei","noi","voi","loro"
}


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-zA-ZÀ-ÿ0-9']{3,}", text.lower())
    return [w for w in words if w not in STOPWORDS]


def keywords(text: str, limit: int = 14) -> str:
    counts = Counter(tokenize(text))
    return " ".join(w for w, _ in counts.most_common(limit))


def add_message(session_id: str, role: str, content: str) -> int:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO conversations(session_id, role, content_enc) VALUES(?,?,?)",
            (session_id, role, encrypt_text(content)),
        )
        return int(cur.lastrowid)


def history(session_id: str, limit: int = 18) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, role, content_enc, created_at
            FROM conversations WHERE session_id=?
            ORDER BY id DESC LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
    return [
        {"id": r["id"], "role": r["role"], "content": decrypt_text(r["content_enc"]),
         "created_at": r["created_at"]}
        for r in reversed(rows)
    ]


def add_memory(content: str, kind: str = "fact", importance: int = 5,
               confidence: float = 0.7) -> int:
    content = content.strip()
    if not content:
        return 0
    k = keywords(content)
    with db() as conn:
        # Evita duplicati identici dopo decifratura, su un insieme limitato.
        recent = conn.execute(
            "SELECT id, content_enc FROM memories WHERE active=1 ORDER BY id DESC LIMIT 100"
        ).fetchall()
        for r in recent:
            if decrypt_text(r["content_enc"]).strip().lower() == content.lower():
                return int(r["id"])
        cur = conn.execute(
            """
            INSERT INTO memories(kind, content_enc, keywords, importance, confidence)
            VALUES(?,?,?,?,?)
            """,
            (kind, encrypt_text(content), k, max(1, min(10, importance)),
             max(0.0, min(1.0, confidence))),
        )
        return int(cur.lastrowid)


def retrieve_memories(query: str, limit: int = 8) -> list[dict]:
    q = set(tokenize(query))
    if not q:
        return []
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, kind, content_enc, keywords, importance, confidence, created_at
            FROM memories WHERE active=1 ORDER BY id DESC LIMIT 600
            """
        ).fetchall()

    scored = []
    for r in rows:
        terms = set((r["keywords"] or "").split())
        overlap = len(q & terms)
        if overlap == 0:
            continue
        score = overlap * 2.0 + math.log1p(r["importance"]) + float(r["confidence"])
        scored.append((score, r))
    scored.sort(key=lambda x: x[0], reverse=True)

    selected = []
    ids = []
    for score, r in scored[:limit]:
        ids.append(r["id"])
        selected.append({
            "id": r["id"],
            "kind": r["kind"],
            "content": decrypt_text(r["content_enc"]),
            "importance": r["importance"],
            "confidence": r["confidence"],
            "score": round(score, 3),
        })
    if ids:
        with db() as conn:
            conn.executemany(
                "UPDATE memories SET last_used_at=CURRENT_TIMESTAMP WHERE id=?",
                [(i,) for i in ids],
            )
    return selected


def list_memories(limit: int = 100) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, kind, content_enc, importance, confidence, created_at
            FROM memories WHERE active=1 ORDER BY importance DESC, id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [{
        "id": r["id"], "kind": r["kind"],
        "content": decrypt_text(r["content_enc"]),
        "importance": r["importance"], "confidence": r["confidence"],
        "created_at": r["created_at"]
    } for r in rows]


def forget_memory(memory_id: int) -> None:
    with db() as conn:
        conn.execute("UPDATE memories SET active=0 WHERE id=?", (memory_id,))


def save_feedback(conversation_id: int, rating: int, note: str = "") -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO feedback(conversation_id, rating, note_enc) VALUES(?,?,?)",
            (conversation_id, 1 if rating > 0 else -1,
             encrypt_text(note) if note else None),
        )


def feedback_lessons(limit: int = 10) -> list[str]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT f.rating, f.note_enc, c.content_enc
            FROM feedback f
            LEFT JOIN conversations c ON c.id=f.conversation_id
            ORDER BY f.id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    out = []
    for r in rows:
        answer = decrypt_text(r["content_enc"])[:500] if r["content_enc"] else ""
        note = decrypt_text(r["note_enc"]) if r["note_enc"] else ""
        label = "RISPOSTA APPREZZATA" if r["rating"] > 0 else "RISPOSTA DA EVITARE"
        out.append(f"{label}: {note or answer}")
    return out
