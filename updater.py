import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from db import DB_PATH, db
from llm import chat as llm_chat
from security import decrypt_text, encrypt_text

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
UPDATES_DIR = DATA_DIR / "updates"
UPDATES_DIR.mkdir(parents=True, exist_ok=True)


def _now_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def ensure_update_tables() -> None:
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS update_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_tag TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            summary_enc TEXT,
            dataset_path TEXT,
            snapshot_path TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)


def export_training_dataset(target: Path) -> int:
    """Esporta esempi approvati/corretti in JSONL per un futuro LoRA."""
    with db() as conn:
        rows = conn.execute("""
            SELECT f.rating, f.note_enc, c.id AS assistant_id,
                   c.session_id, c.content_enc AS assistant_enc,
                   (SELECT u.content_enc FROM conversations u
                    WHERE u.session_id=c.session_id AND u.role='user' AND u.id<c.id
                    ORDER BY u.id DESC LIMIT 1) AS user_enc
            FROM feedback f
            JOIN conversations c ON c.id=f.conversation_id
            WHERE c.role='assistant'
            ORDER BY f.id ASC
        """).fetchall()

    count = 0
    with target.open('w', encoding='utf-8') as fh:
        for row in rows:
            if not row['user_enc'] or not row['assistant_enc']:
                continue
            user = decrypt_text(row['user_enc'])
            assistant = decrypt_text(row['assistant_enc'])
            note = decrypt_text(row['note_enc']) if row['note_enc'] else ''
            record = {
                "messages": [
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": assistant},
                ],
                "rating": int(row['rating']),
                "correction_note": note,
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


async def consolidate_learning() -> dict:
    """Aggiornamento sicuro: snapshot, dataset, riflessione e nuova versione."""
    ensure_update_tables()
    tag = f"neura-{_now_tag()}"
    version_dir = UPDATES_DIR / tag
    version_dir.mkdir(parents=True, exist_ok=False)

    snapshot = version_dir / "neura.sqlite3.snapshot"
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, snapshot)

    dataset = version_dir / "training.jsonl"
    examples = export_training_dataset(dataset)

    with db() as conn:
        feedback_rows = conn.execute("""
            SELECT f.rating, f.note_enc, c.content_enc
            FROM feedback f LEFT JOIN conversations c ON c.id=f.conversation_id
            ORDER BY f.id DESC LIMIT 80
        """).fetchall()
        memories = conn.execute("""
            SELECT kind, content_enc, importance, confidence
            FROM memories WHERE active=1
            ORDER BY importance DESC, id DESC LIMIT 120
        """).fetchall()

    feedback_text = []
    for row in feedback_rows:
        answer = decrypt_text(row['content_enc'])[:600] if row['content_enc'] else ''
        note = decrypt_text(row['note_enc']) if row['note_enc'] else ''
        feedback_text.append({"rating": row['rating'], "answer": answer, "note": note})

    memory_text = [
        {
            "kind": r['kind'], "content": decrypt_text(r['content_enc']),
            "importance": r['importance'], "confidence": r['confidence']
        }
        for r in memories
    ]

    prompt = """
Sei il modulo di consolidamento di NÈURA. Analizza memorie e feedback.
Produci una sintesi operativa in italiano con:
- preferenze stabili dell'utente;
- errori da non ripetere;
- stile di risposta più utile;
- conflitti o memorie dubbie;
- massimo 12 regole pratiche.
Non inventare fatti e non ripetere segreti non necessari.
""".strip()

    try:
        summary = await llm_chat([
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps({
                "memories": memory_text,
                "feedback": feedback_text,
            }, ensure_ascii=False)}
        ], temperature=0.15, max_tokens=900)
        status = "completed"
    except Exception as exc:
        summary = f"Aggiornamento parziale: dataset e snapshot creati. Riflessione non disponibile: {exc}"
        status = "partial"

    (version_dir / "learning_summary.txt").write_text(summary, encoding='utf-8')
    with db() as conn:
        conn.execute(
            "INSERT INTO reflections(content_enc) VALUES(?)",
            (encrypt_text(summary),)
        )
        conn.execute("""
            INSERT INTO update_versions(version_tag,status,summary_enc,dataset_path,snapshot_path)
            VALUES(?,?,?,?,?)
        """, (tag, status, encrypt_text(summary), str(dataset), str(snapshot)))

    return {
        "version": tag,
        "status": status,
        "examples": examples,
        "summary": summary,
        "dataset": str(dataset),
        "snapshot": str(snapshot),
    }


def latest_reflections(limit: int = 3) -> list[str]:
    ensure_update_tables()
    with db() as conn:
        rows = conn.execute(
            "SELECT content_enc FROM reflections ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [decrypt_text(r['content_enc']) for r in rows]


def list_versions(limit: int = 20) -> list[dict]:
    ensure_update_tables()
    with db() as conn:
        rows = conn.execute("""
            SELECT id,version_tag,status,summary_enc,dataset_path,snapshot_path,created_at
            FROM update_versions ORDER BY id DESC LIMIT ?
        """, (limit,)).fetchall()
    return [{
        "id": r['id'], "version": r['version_tag'], "status": r['status'],
        "summary": decrypt_text(r['summary_enc']) if r['summary_enc'] else '',
        "dataset": r['dataset_path'], "snapshot": r['snapshot_path'],
        "created_at": r['created_at']
    } for r in rows]
