from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from db import db
from llm import chat as llm_chat
from security import decrypt_text, encrypt_text
from update_manager import BASE_DIR, create_code_snapshot

ALLOWED_SUFFIXES = {".py", ".js", ".css", ".html", ".md", ".txt", ".json", ".ps1", ".cmd"}
EXCLUDED_PARTS = {"data", ".venv", "__pycache__", ".git", "code_backups"}
MAX_FILE_BYTES = 180_000
MAX_CHANGED_FILES = 8
MAX_TOTAL_CHARS = 300_000

FORBIDDEN_PATTERNS = [
    r"(?i)password\s*=",
    r"(?i)api[_-]?key\s*=",
    r"(?i)secret\s*=",
    r"(?i)token\s*=",
    r"(?i)remove-item\s+.*-recurse",
    r"(?i)rm\s+-rf",
    r"(?i)format\s+[a-z]:",
    r"(?i)subprocess\.(?:run|popen).*shell\s*=\s*true",
    r"(?i)os\.system\s*\(",
]


def _safe_relative(path: str) -> Path:
    p = Path(path.replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts or not p.parts:
        raise ValueError(f"Percorso non consentito: {path}")
    if any(part in EXCLUDED_PARTS for part in p.parts):
        raise ValueError(f"Percorso escluso: {path}")
    if p.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ValueError(f"Tipo file non consentito: {path}")
    return p


def source_manifest() -> list[dict[str, Any]]:
    result = []
    for p in sorted(BASE_DIR.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(BASE_DIR)
        if any(part in EXCLUDED_PARTS for part in rel.parts):
            continue
        if p.suffix.lower() not in ALLOWED_SUFFIXES or p.stat().st_size > MAX_FILE_BYTES:
            continue
        result.append({"path": rel.as_posix(), "size": p.stat().st_size})
    return result


def source_bundle(max_chars: int = 70_000) -> str:
    sections, used = [], 0
    priority = ["app.py", "coding_engine.py", "laboratory.py", "update_manager.py",
                "db.py", "llm.py", "memory.py", "static/app.js",
                "static/index.html", "static/style.css"]
    available = {x["path"] for x in source_manifest()}
    ordered = [p for p in priority if p in available] + sorted(available - set(priority))
    for rel in ordered:
        p = BASE_DIR / rel
        text = p.read_text(encoding="utf-8", errors="replace")
        block = f"\n\n### FILE: {rel}\n{text}"
        if used + len(block) > max_chars:
            continue
        sections.append(block)
        used += len(block)
    return "".join(sections)


def list_lessons(limit: int = 80) -> list[dict]:
    with db() as conn:
        rows = conn.execute("""
            SELECT id,category,lesson_enc,source,confidence,created_at
            FROM coding_lessons WHERE active=1 ORDER BY id DESC LIMIT ?
        """, (limit,)).fetchall()
    return [{
        "id": r["id"], "category": r["category"],
        "lesson": decrypt_text(r["lesson_enc"]), "source": r["source"],
        "confidence": r["confidence"], "created_at": r["created_at"]
    } for r in rows]


def add_lesson(lesson: str, category: str = "general",
               source: str = "manual", confidence: float = 0.8) -> int:
    lesson = lesson.strip()
    if not lesson:
        raise ValueError("Lezione vuota")
    with db() as conn:
        cur = conn.execute("""
            INSERT INTO coding_lessons(category,lesson_enc,source,confidence)
            VALUES(?,?,?,?)
        """, (category[:50], encrypt_text(lesson[:8000]), source[:80],
              max(0.1, min(1.0, confidence))))
        return int(cur.lastrowid)


def _lessons_context() -> str:
    lessons = list_lessons(40)
    if not lessons:
        return "Nessuna lezione di programmazione ancora consolidata."
    return "\n".join(
        f"- [{x['category']}, confidenza {x['confidence']:.0%}] {x['lesson']}"
        for x in lessons
    )


async def propose_change(goal: str) -> dict:
    system = """
Sei il motore di manutenzione software di NÈURA. Analizzi il codice reale fornito,
usi le lezioni pregresse e prepari una modifica prudente. Non puoi applicarla.

Rispondi ESCLUSIVAMENTE con JSON valido in questo formato:
{
  "title": "titolo breve",
  "rationale": "problema, causa, beneficio e rischi",
  "changes": [
    {
      "path": "percorso/relativo.ext",
      "action": "replace",
      "content": "CONTENUTO COMPLETO DEL FILE DOPO LA MODIFICA"
    }
  ],
  "tests": ["test 1", "test 2"],
  "expected_result": "risultato atteso",
  "risk": "low|medium|high"
}

Regole inderogabili:
- massimo 8 file;
- usa solo percorsi già esistenti, salvo un nuovo modulo chiaramente necessario;
- restituisci il contenuto completo dei file, non frammenti e non diff;
- non inserire password, token, chiavi o credenziali;
- non disattivare login, backup, validazione, rollback o controlli di sicurezza;
- non usare comandi distruttivi;
- non dichiarare che i test sono riusciti: saranno eseguiti dopo;
- se la richiesta è insicura o troppo ampia, restituisci changes vuoto e spiegalo.
""".strip()
    user = f"""
OBIETTIVO:
{goal}

LEZIONI APPRESE:
{_lessons_context()}

MANIFESTO FILE:
{json.dumps(source_manifest(), ensure_ascii=False)}

CODICE DISPONIBILE:
{source_bundle()}
""".strip()
    raw = await llm_chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.1,
        max_tokens=7000,
    )
    try:
        start, end = raw.index("{"), raw.rindex("}") + 1
        result = json.loads(raw[start:end])
    except Exception as exc:
        raise ValueError(f"Il modello non ha restituito una proposta JSON valida: {exc}")
    if not isinstance(result.get("changes"), list):
        raise ValueError("La proposta non contiene una lista changes valida")
    return result


def validate_change_set(data: dict) -> dict:
    errors, warnings = [], []
    changes = data.get("changes") or []
    if not changes:
        errors.append("La proposta non contiene modifiche.")
    if len(changes) > MAX_CHANGED_FILES:
        errors.append(f"Troppi file modificati: massimo {MAX_CHANGED_FILES}.")
    seen, total = set(), 0
    for i, change in enumerate(changes):
        try:
            rel = _safe_relative(str(change.get("path", "")))
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if rel.as_posix() in seen:
            errors.append(f"File duplicato: {rel.as_posix()}")
        seen.add(rel.as_posix())
        if change.get("action") != "replace":
            errors.append(f"Azione non consentita per {rel}: usare replace.")
        content = change.get("content")
        if not isinstance(content, str):
            errors.append(f"Contenuto non valido per {rel}.")
            continue
        total += len(content)
        if len(content.encode("utf-8")) > MAX_FILE_BYTES:
            errors.append(f"File troppo grande: {rel}.")
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, content):
                errors.append(f"Schema potenzialmente pericoloso in {rel}: {pattern}")
        if rel.suffix == ".py":
            try:
                ast.parse(content, filename=rel.as_posix())
            except SyntaxError as exc:
                errors.append(f"Errore sintattico Python in {rel}: {exc}")
        if not (BASE_DIR / rel).exists():
            warnings.append(f"Nuovo file: {rel.as_posix()}")
    if total > MAX_TOTAL_CHARS:
        errors.append("La modifica complessiva è troppo grande.")
    return {
        "valid": not errors, "errors": errors, "warnings": warnings,
        "changed_files": sorted(seen), "total_characters": total
    }


def _write_staging(data: dict, staging: Path) -> None:
    shutil.copytree(
        BASE_DIR, staging, dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("data", ".venv", "__pycache__", ".git")
    )
    for change in data.get("changes", []):
        rel = _safe_relative(change["path"])
        target = staging / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(change["content"], encoding="utf-8")


def test_change_set(data: dict) -> dict:
    validation = validate_change_set(data)
    if not validation["valid"]:
        return {**validation, "tests_passed": False, "test_output": "Validazione fallita."}
    with tempfile.TemporaryDirectory(prefix="neura-stage-") as tmp:
        staging = Path(tmp) / "app"
        _write_staging(data, staging)
        results, passed = [], True

        py_files = [p for p in staging.rglob("*.py")
                    if not any(x in EXCLUDED_PARTS for x in p.relative_to(staging).parts)]
        for p in py_files:
            proc = subprocess.run(
                [sys.executable, "-m", "py_compile", str(p)],
                capture_output=True, text=True, timeout=30
            )
            results.append(f"py_compile {p.relative_to(staging)}: "
                           f"{'OK' if proc.returncode == 0 else proc.stderr.strip()}")
            passed &= proc.returncode == 0

        # Controlli minimi sui file indispensabili.
        for required in ["app.py", "db.py", "security.py", "update_manager.py",
                         "static/index.html", "static/app.js"]:
            ok = (staging / required).exists()
            results.append(f"file richiesto {required}: {'OK' if ok else 'MANCANTE'}")
            passed &= ok

        # Verifica che gli endpoint di sicurezza fondamentali non siano spariti.
        app_text = (staging / "app.py").read_text(encoding="utf-8", errors="replace")
        for marker in ["/api/login", "/api/code-backups", "auth("]:
            ok = marker in app_text
            results.append(f"controllo sicurezza {marker}: {'OK' if ok else 'MANCANTE'}")
            passed &= ok

        return {
            **validation, "tests_passed": passed,
            "test_output": "\n".join(results)
        }


def apply_change_set(data: dict, label: str) -> dict:
    report = test_change_set(data)
    if not report["tests_passed"]:
        raise ValueError("La modifica non ha superato i test e non è stata applicata.")
    snapshot = create_code_snapshot(f"before-{label}")
    written = []
    try:
        for change in data.get("changes", []):
            rel = _safe_relative(change["path"])
            target = BASE_DIR / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(change["content"], encoding="utf-8")
            written.append(rel.as_posix())
    except Exception:
        # Ripristino immediato dallo snapshot in caso di scrittura incompleta.
        from update_manager import rollback_code
        rollback_code(snapshot["filename"])
        raise
    return {
        "ok": True, "snapshot": snapshot["filename"],
        "written_files": written, "restart_required": True,
        "validation": report
    }


def run_self_diagnostic() -> dict:
    findings, status = [], "healthy"
    required = ["app.py", "db.py", "llm.py", "security.py",
                "update_manager.py", "static/index.html", "static/app.js"]
    for rel in required:
        if not (BASE_DIR / rel).exists():
            findings.append(f"File mancante: {rel}")
            status = "error"
    for p in BASE_DIR.glob("*.py"):
        try:
            ast.parse(p.read_text(encoding="utf-8"), filename=p.name)
        except Exception as exc:
            findings.append(f"Errore Python in {p.name}: {exc}")
            status = "error"
    if not findings:
        findings.append("Struttura e sintassi di base risultano integre.")
    report = "\n".join(findings)
    with db() as conn:
        conn.execute(
            "INSERT INTO self_diagnostics(status,report_enc) VALUES(?,?)",
            (status, encrypt_text(report))
        )
    return {"status": status, "report": report,
            "created_at": datetime.now(timezone.utc).isoformat()}
