from __future__ import annotations
import re
from pathlib import Path
from uuid import uuid4
from fastapi import UploadFile
from db import db
from security import encrypt_text, decrypt_text

LIB = Path("data/library")
LIB.mkdir(parents=True, exist_ok=True)


def _extract(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".txt", ".md", ".csv", ".json", ".py", ".html"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    if ext == ".pdf":
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    if ext == ".docx":
        from docx import Document
        return "\n".join(p.text for p in Document(str(path)).paragraphs)
    raise ValueError("Formato non supportato. Usa PDF, DOCX, TXT, MD, CSV, JSON, PY o HTML.")


def _chunks(text: str, size: int = 1800, overlap: int = 250):
    text = re.sub(r"\s+", " ", text).strip()
    i=0
    while i < len(text):
        yield text[i:i+size]
        i += max(1,size-overlap)


async def ingest(upload: UploadFile, category: str, learn: bool) -> dict:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", upload.filename or "documento")
    target = LIB / f"{uuid4().hex[:10]}_{safe}"
    target.write_bytes(await upload.read())
    text = _extract(target)
    with db() as conn:
        cur = conn.execute("INSERT INTO library_documents(filename,category,path,learned,char_count) VALUES(?,?,?,?,?)",
                           (upload.filename or safe, category[:80], str(target), 1 if learn else 0, len(text)))
        doc_id = int(cur.lastrowid)
        if learn:
            for idx, chunk in enumerate(_chunks(text)):
                conn.execute("INSERT INTO library_chunks(document_id,chunk_index,content_enc) VALUES(?,?,?)",
                             (doc_id, idx, encrypt_text(chunk)))
    return {"id":doc_id,"filename":upload.filename,"category":category,"learned":learn,"characters":len(text)}


def list_documents() -> list[dict]:
    with db() as conn:
        rows=conn.execute("SELECT id,filename,category,learned,char_count,created_at FROM library_documents ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def search_knowledge(query: str, limit: int = 8) -> list[dict]:
    terms=[t for t in re.findall(r"\w+", query.lower()) if len(t)>2][:12]
    with db() as conn:
        rows=conn.execute("""SELECT c.id,c.document_id,c.content_enc,d.filename,d.category
                             FROM library_chunks c JOIN library_documents d ON d.id=c.document_id
                             ORDER BY c.id DESC LIMIT 3000""").fetchall()
    scored=[]
    for r in rows:
        text=decrypt_text(r["content_enc"])
        score=sum(text.lower().count(t) for t in terms)
        if score: scored.append((score,{"document_id":r["document_id"],"filename":r["filename"],"category":r["category"],"content":text}))
    scored.sort(key=lambda x:x[0], reverse=True)
    return [x[1] for x in scored[:limit]]
