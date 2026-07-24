import json
import os
import re
import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, UploadFile, File, Form
import httpx
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from db import init_db
from llm import chat as llm_chat, LLMError, provider_status, test_provider
from web_access import search_web, read_page, WebSearchError
from update_manager import create_code_snapshot, list_code_snapshots, rollback_code
from memory import (
    add_message, history, add_memory, retrieve_memories, list_memories,
    forget_memory, save_feedback, feedback_lessons
)
from security import valid_password
from updater import consolidate_learning, latest_reflections, list_versions
from laboratory import (apply_proposal, create_proposal, get_proposal, list_proposals, update_proposal_status, validate_proposal)
from coding_engine import add_lesson, list_lessons, run_self_diagnostic
from db import db, DB_PATH
from security import decrypt_text, encrypt_text
from conversations import ensure_conversation, list_sessions, rename_session, archive_session, delete_session, session_messages, search_sessions
from constitution import load_constitution, save_constitution
from library_engine import ingest, list_documents, search_knowledge
from vision_engine import analyze_image
from provider_config import public_config, save_provider_config

app = FastAPI(title="NÈURA Cloud", version="4.0.0")
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


class ProviderConfigIn(BaseModel):
    provider: str = Field(default="custom", max_length=50)
    api_base: str = Field(min_length=8, max_length=500)
    api_key: str = Field(default="", max_length=1000)
    model: str = Field(min_length=1, max_length=200)
    vision_model: str = Field(default="", max_length=200)


class ChatIn(BaseModel):
    session_id: str = Field(min_length=8, max_length=100)
    message: str = Field(min_length=1, max_length=12000)
    use_web: bool = False
    internet_approved: bool = False




class SessionRenameIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)

class SessionArchiveIn(BaseModel):
    archived: bool

class ConstitutionIn(BaseModel):
    content: str = Field(min_length=20, max_length=30000)


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
    status: Literal["proposed", "validated", "approved", "rejected", "applied", "failed"]


class DiaryIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=10000)


class CodingLessonIn(BaseModel):
    lesson: str = Field(min_length=5, max_length=8000)
    category: str = Field(default="manual", max_length=50)
    confidence: float = Field(default=0.8, ge=0.1, le=1.0)


class ApplyProposalIn(BaseModel):
    confirmation: str


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
    return provider_status()


@app.get("/api/provider-config")
def get_provider_config(authorization: str | None = Header(default=None)):
    auth(authorization)
    return public_config()


@app.put("/api/provider-config")
def put_provider_config(data: ProviderConfigIn, authorization: str | None = Header(default=None)):
    auth(authorization)
    try:
        return save_provider_config(data.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/provider-test")
async def provider_test(authorization: str | None = Header(default=None)):
    auth(authorization)
    try:
        answer = await test_provider()
        return {"ok": True, "answer": answer, "status": provider_status()}
    except LLMError as exc:
        raise HTTPException(502, str(exc))


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
    if data.use_web and not data.internet_approved:
        raise HTTPException(403, "Prima di accedere a Internet serve la tua autorizzazione esplicita.")
    ensure_conversation(data.session_id, data.message)
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
    knowledge = search_knowledge(data.message, 6)
    knowledge_context = "\n\n".join(
        f"DOCUMENTO: {x['filename']} ({x['category']})\n{x['content']}" for x in knowledge
    ) or "Nessun documento pertinente nella libreria."
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": "COSTITUZIONE VINCOLANTE DI NÈURA:\n" + load_constitution()},
        {"role": "system", "content": context},
        {"role": "system", "content": "CONOSCENZA DALLA LIBRERIA LOCALE:\n" + knowledge_context},
    ]
    web_sources = []
    if data.use_web:
        try:
            web_sources = await search_web(data.message, 5)
            web_context = "\n\n".join(
                f"FONTE {i+1}: {x['title']}\nURL: {x['url']}\nESTRATTO: {x['snippet']}"
                for i, x in enumerate(web_sources)
            )
            messages.append({
                "role": "system",
                "content": "Usa le seguenti fonti web recenti. Distingui chiaramente ciò che proviene dalle fonti e inserisci gli URL alla fine della risposta. Non inventare dettagli mancanti.\n\n" + web_context
            })
        except WebSearchError as exc:
            messages.append({"role": "system", "content": f"La ricerca web richiesta non è riuscita: {exc}. Dillo chiaramente all'utente e rispondi solo con ciò che sai."})
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
        "web_sources": web_sources,
        "library_sources": [{"filename":x["filename"],"category":x["category"]} for x in knowledge],
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
    return json.dumps(proposals[0].get("changes", []), ensure_ascii=False, indent=2)


@app.post("/api/web/search")
async def web_search_api(data: ChatIn, authorization: str | None = Header(default=None)):
    auth(authorization)
    try:
        return {"results": await search_web(data.message, 8)}
    except WebSearchError as exc:
        raise HTTPException(502, str(exc))


@app.get("/api/code-backups")
def code_backups(authorization: str | None = Header(default=None)):
    auth(authorization)
    return {"backups": list_code_snapshots()}


@app.post("/api/code-backups")
def code_snapshot(authorization: str | None = Header(default=None)):
    auth(authorization)
    return create_code_snapshot("manual")


@app.post("/api/code-backups/{filename}/rollback")
def code_rollback(filename: str, authorization: str | None = Header(default=None)):
    auth(authorization)
    try:
        return rollback_code(filename)
    except FileNotFoundError:
        raise HTTPException(404, "Backup del codice non trovato")


@app.post("/api/lab/proposals/{proposal_id}/validate")
def lab_validate(proposal_id: int, authorization: str | None = Header(default=None)):
    auth(authorization)
    try:
        return validate_proposal(proposal_id)
    except FileNotFoundError:
        raise HTTPException(404, "Proposta non trovata")
    except Exception as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/lab/proposals/{proposal_id}/apply")
def lab_apply(proposal_id: int, data: ApplyProposalIn,
              authorization: str | None = Header(default=None)):
    auth(authorization)
    if data.confirmation.strip() != f"APPLICA {proposal_id}":
        raise HTTPException(
            400, f"Conferma non valida. Scrivi esattamente: APPLICA {proposal_id}"
        )
    try:
        return apply_proposal(proposal_id)
    except FileNotFoundError:
        raise HTTPException(404, "Proposta non trovata")
    except Exception as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/coding/lessons")
def coding_lessons(authorization: str | None = Header(default=None)):
    auth(authorization)
    return {"lessons": list_lessons()}


@app.post("/api/coding/lessons")
def coding_lesson_add(data: CodingLessonIn,
                      authorization: str | None = Header(default=None)):
    auth(authorization)
    lesson_id = add_lesson(
        data.lesson, category=data.category,
        source="manual", confidence=data.confidence
    )
    return {"ok": True, "id": lesson_id}


@app.post("/api/self-diagnostic")
def self_diagnostic(authorization: str | None = Header(default=None)):
    auth(authorization)
    return run_self_diagnostic()


@app.get("/api/conversations")
def conversations_list(q: str = "", authorization: str | None = Header(default=None)):
    auth(authorization)
    return {"conversations": search_sessions(q) if q.strip() else list_sessions()}

@app.get("/api/conversations/{session_id}")
def conversation_read(session_id: str, authorization: str | None = Header(default=None)):
    auth(authorization)
    return {"messages": session_messages(session_id)}

@app.patch("/api/conversations/{session_id}/title")
def conversation_rename(session_id: str, data: SessionRenameIn, authorization: str | None = Header(default=None)):
    auth(authorization); rename_session(session_id, data.title); return {"ok": True}

@app.patch("/api/conversations/{session_id}/archive")
def conversation_archive(session_id: str, data: SessionArchiveIn, authorization: str | None = Header(default=None)):
    auth(authorization); archive_session(session_id, data.archived); return {"ok": True}

@app.delete("/api/conversations/{session_id}")
def conversation_delete(session_id: str, authorization: str | None = Header(default=None)):
    auth(authorization); delete_session(session_id); return {"ok": True}

@app.get("/api/constitution")
def constitution_get(authorization: str | None = Header(default=None)):
    auth(authorization); return {"content": load_constitution()}

@app.put("/api/constitution")
def constitution_put(data: ConstitutionIn, authorization: str | None = Header(default=None)):
    auth(authorization); save_constitution(data.content); return {"ok": True}

@app.get("/api/library")
def library_list(authorization: str | None = Header(default=None)):
    auth(authorization); return {"documents": list_documents()}

@app.post("/api/library/upload")
async def library_upload(file: UploadFile = File(...), category: str = Form("Generale"), learn: bool = Form(True), authorization: str | None = Header(default=None)):
    auth(authorization)
    try: return await ingest(file, category, learn)
    except ValueError as exc: raise HTTPException(400, str(exc))

@app.post("/api/vision/analyze")
async def vision_analyze(file: UploadFile = File(...), question: str = Form("Descrivi accuratamente questa immagine."), authorization: str | None = Header(default=None)):
    auth(authorization)
    data = await file.read()
    if len(data) > 20_000_000: raise HTTPException(413, "Immagine troppo grande")
    try: return {"answer": await analyze_image(data, question, file.content_type or "image/jpeg"), "filename": file.filename}
    except RuntimeError as exc: raise HTTPException(502, str(exc))
