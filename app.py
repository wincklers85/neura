import json
import os
import re
import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
import httpx
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from db import init_db
from llm import chat as llm_chat, LLMError
from memory import (
    add_message, history, add_memory, retrieve_memories, list_memories,
    forget_memory, save_feedback, feedback_lessons
)
from security import valid_password
from updater import consolidate_learning, latest_reflections, list_versions
from laboratory import create_proposal, list_proposals, update_proposal_status
from db import db, DB_PATH
from security import decrypt_text, encrypt_text

app = FastAPI(title="NÈURA", version="0.3.0")
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")

MAX_HISTORY = int(os.getenv("MAX_HISTORY", "18"))
MAX_MEMORIES = int(os.getenv("MAX_MEMORIES", "8"))

SYSTEM_PROMPT = """
Tu sei NÈURA, Nucleo Evolutivo di Ragionamento e Apprendimento.
Sei una consigliera privata, lucida, empatica, discreta e intellettualmente onesta.

Regole:
1. Ragiona con attenzione, ma mostra all'utente conclusioni e motivazioni sintetiche,
   non un monologo interno nascosto.
2. Distingui fatti, ipotesi, emozioni e giudizi.
3. Non assecondare automaticamente: segnala incoerenze, rischi e alternative.
4. Non inventare ricordi. Usa solo le memorie fornite nel contesto.
5. Per problemi personali, aiuta senza giudicare e senza manipolare.
6. Per decisioni importanti, proponi criteri, conseguenze e un passo concreto.
7. Non trattare una memoria incerta come certezza.
8. Proteggi la privacy: non ripetere segreti inutilmente.
9. Rispondi nella lingua dell'utente.
10. Se manca informazione essenziale, esplicita l'incertezza ma fai comunque
    il miglior ragionamento possibile.
""".strip()


class LoginIn(BaseModel):
    password: str


class ChatIn(BaseModel):
    session_id: str = Field(min_length=8, max_length=100)
    message: str = Field(min_length=1, max_length=12000)


class FeedbackIn(BaseModel):
    message_id: int
    rating: Literal[-1, 1]
    note: str = Field(default="", max_length=2000)


class MemoryIn(BaseModel):
    content: str = Field(min_length=1, max_length=5000)
    kind: str = Field(default="secret", max_length=30)
    importance: int = Field(default=7, ge=1, le=10)



class LabIn(BaseModel):
    goal: str = Field(min_length=5, max_length=6000)


class ProposalStatusIn(BaseModel):
    status: Literal["proposed", "approved", "rejected", "applied"]


class DiaryIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=10000)


TOKENS: set[str] = set()


def auth(authorization: str | None) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Accesso richiesto")
    if authorization[7:] not in TOKENS:
        raise HTTPException(401, "Sessione non valida")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
def health():
    return {"ok": True, "name": "NÈURA", "web": "ready"}


@app.get("/api/model-status")
async def model_status():
    base = os.getenv("LLM_BASE_URL", "http://127.0.0.1:8080/v1").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=2.5) as client:
            response = await client.get(f"{base}/models")
        return {"ready": response.status_code < 400, "model": os.getenv("MODEL_NAME", "neura-local"), "detail": "pronto" if response.status_code < 400 else response.text[:200]}
    except Exception:
        return {"ready": False, "model": os.getenv("MODEL_NAME", "neura-local"), "detail": "download o caricamento del modello in corso"}


@app.post("/api/login")
def login(data: LoginIn):
    if not valid_password(data.password):
        raise HTTPException(401, "Password errata")
    token = secrets.token_urlsafe(32)
    TOKENS.add(token)
    return {"token": token}


def memory_context(items: list[dict]) -> str:
    if not items:
        return "Nessuna memoria pertinente."
    return "\n".join(
        f"- [{m['kind']}; importanza {m['importance']}/10; "
        f"confidenza {m['confidence']:.0%}] {m['content']}"
        for m in items
    )


async def extract_memories(user_text: str, assistant_text: str) -> None:
    prompt = """
Estrai solo informazioni durevoli e utili per conversazioni future.
Non salvare saluti, dettagli temporanei o deduzioni fragili.
Restituisci esclusivamente JSON valido nella forma:
{"memories":[{"content":"...","kind":"fact|preference|secret|goal|lesson",
"importance":1-10,"confidence":0.0-1.0}]}
Massimo 4 memorie. Se non c'è nulla: {"memories":[]}.
""".strip()
    try:
        raw = await llm_chat([
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"UTENTE:\n{user_text}\n\nRISPOSTA:\n{assistant_text}"}
        ], temperature=0.1, max_tokens=450)
        match = re.search(r"\{.*\}", raw, flags=re.S)
        if not match:
            return
        data = json.loads(match.group(0))
        for item in data.get("memories", [])[:4]:
            add_memory(
                str(item.get("content", "")),
                str(item.get("kind", "fact"))[:30],
                int(item.get("importance", 5)),
                float(item.get("confidence", 0.65)),
            )
    except Exception:
        # L'estrazione non deve mai bloccare la conversazione.
        return


@app.post("/api/chat")
async def chat(data: ChatIn, authorization: str | None = Header(default=None)):
    auth(authorization)
    normalized = data.message.strip().lower().rstrip(".!?")
    if normalized in {"aggiornati", "auto aggiornati", "nèura aggiornati", "neura aggiornati"}:
        result = await consolidate_learning()
        answer = (
            f"Aggiornamento {result['version']} completato con stato {result['status']}. "
            f"Ho creato uno snapshot, consolidato le memorie e preparato "
            f"{result['examples']} esempi per un eventuale fine-tuning.\n\n"
            f"Sintesi:\n{result['summary']}"
        )
        user_id = add_message(data.session_id, "user", data.message)
        assistant_id = add_message(data.session_id, "assistant", answer)
        return {"answer": answer, "message_id": assistant_id, "user_message_id": user_id, "update": result}
    user_id = add_message(data.session_id, "user", data.message)
    relevant = retrieve_memories(data.message, MAX_MEMORIES)
    lessons = feedback_lessons(8)
    recent = history(data.session_id, MAX_HISTORY)

    reflections = latest_reflections(2)
    context = (
        "MEMORIE PERTINENTI:\n" + memory_context(relevant) +
        "\n\nLEZIONI DAI FEEDBACK:\n" +
        ("\n".join(f"- {x}" for x in lessons) if lessons else "Nessuna.") +
        "\n\nCONSOLIDAMENTI APPROVATI:\n" +
        ("\n---\n".join(reflections) if reflections else "Nessuno.")
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": context},
    ]
    # Evita di duplicare il messaggio appena inserito.
    for item in recent:
        messages.append({"role": item["role"], "content": item["content"]})

    try:
        answer = await llm_chat(messages)
    except LLMError as exc:
        raise HTTPException(502, str(exc))

    assistant_id = add_message(data.session_id, "assistant", answer)
    await extract_memories(data.message, answer)
    return {
        "answer": answer,
        "message_id": assistant_id,
        "used_memories": relevant,
        "user_message_id": user_id,
    }


@app.post("/api/feedback")
def feedback(data: FeedbackIn, authorization: str | None = Header(default=None)):
    auth(authorization)
    save_feedback(data.message_id, data.rating, data.note)
    return {"ok": True}


@app.get("/api/memories")
def memories(authorization: str | None = Header(default=None)):
    auth(authorization)
    return {"memories": list_memories(150)}


@app.post("/api/memories")
def create_memory(data: MemoryIn, authorization: str | None = Header(default=None)):
    auth(authorization)
    memory_id = add_memory(data.content, data.kind, data.importance, 1.0)
    return {"ok": True, "id": memory_id}


@app.delete("/api/memories/{memory_id}")
def delete_memory(memory_id: int, authorization: str | None = Header(default=None)):
    auth(authorization)
    forget_memory(memory_id)
    return {"ok": True}


@app.post("/api/update")
async def manual_update(authorization: str | None = Header(default=None)):
    auth(authorization)
    return await consolidate_learning()


@app.get("/api/update/versions")
def update_versions(authorization: str | None = Header(default=None)):
    auth(authorization)
    return {"versions": list_versions()}


@app.get("/api/dashboard")
def dashboard(authorization: str | None = Header(default=None)):
    auth(authorization)
    with db() as conn:
        conversations = conn.execute("SELECT COUNT(*) c FROM conversations").fetchone()["c"]
        memories = conn.execute("SELECT COUNT(*) c FROM memories WHERE active=1").fetchone()["c"]
        positive = conn.execute("SELECT COUNT(*) c FROM feedback WHERE rating=1").fetchone()["c"]
        negative = conn.execute("SELECT COUNT(*) c FROM feedback WHERE rating=-1").fetchone()["c"]
        updates = conn.execute("SELECT COUNT(*) c FROM update_versions").fetchone()["c"]
        diary = conn.execute("SELECT COUNT(*) c FROM diary").fetchone()["c"]
        timeline = conn.execute("""
            SELECT substr(created_at,1,10) day, COUNT(*) value
            FROM conversations GROUP BY substr(created_at,1,10)
            ORDER BY day DESC LIMIT 30
        """).fetchall()
    return {
        "conversations": conversations, "memories": memories,
        "positive_feedback": positive, "negative_feedback": negative,
        "updates": updates, "diary_entries": diary,
        "timeline": list(reversed([dict(r) for r in timeline]))
    }


@app.get("/api/diary")
def diary_list(authorization: str | None = Header(default=None)):
    auth(authorization)
    with db() as conn:
        rows = conn.execute(
            "SELECT id,title,content_enc,created_at FROM diary ORDER BY id DESC LIMIT 100"
        ).fetchall()
    return {"entries": [{
        "id": r["id"], "title": r["title"],
        "content": decrypt_text(r["content_enc"]), "created_at": r["created_at"]
    } for r in rows]}


@app.post("/api/diary")
def diary_create(data: DiaryIn, authorization: str | None = Header(default=None)):
    auth(authorization)
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO diary(title,content_enc) VALUES(?,?)",
            (data.title, encrypt_text(data.content))
        )
    return {"ok": True, "id": int(cur.lastrowid)}


@app.post("/api/backup")
def create_backup(authorization: str | None = Header(default=None)):
    auth(authorization)
    backup_dir = Path(os.getenv("DATA_DIR", "./data")) / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = backup_dir / f"neura-backup-{tag}.sqlite3"
    if not DB_PATH.exists():
        raise HTTPException(404, "Database non ancora creato")
    shutil.copy2(DB_PATH, target)
    return {"ok": True, "filename": target.name, "created_at": tag}


@app.get("/api/backups")
def list_backups(authorization: str | None = Header(default=None)):
    auth(authorization)
    backup_dir = Path(os.getenv("DATA_DIR", "./data")) / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    items = sorted(backup_dir.glob("*.sqlite3"), reverse=True)
    return {"backups": [
        {"filename": p.name, "size": p.stat().st_size,
         "created_at": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat()}
        for p in items[:30]
    ]}


@app.post("/api/lab/proposals")
async def lab_create(data: LabIn, authorization: str | None = Header(default=None)):
    auth(authorization)
    return await create_proposal(data.goal)


@app.get("/api/lab/proposals")
def lab_list(authorization: str | None = Header(default=None)):
    auth(authorization)
    return {"proposals": list_proposals()}


@app.patch("/api/lab/proposals/{proposal_id}")
def lab_status(proposal_id: int, data: ProposalStatusIn,
               authorization: str | None = Header(default=None)):
    auth(authorization)
    try:
        update_proposal_status(proposal_id, data.status)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True}


@app.get("/api/lab/proposals/{proposal_id}/patch", response_class=PlainTextResponse)
def lab_patch(proposal_id: int, authorization: str | None = Header(default=None)):
    auth(authorization)
    proposals = [p for p in list_proposals(200) if p["id"] == proposal_id]
    if not proposals:
        raise HTTPException(404, "Proposta non trovata")
    return proposals[0]["patch"] or "# Nessuna patch generata"
