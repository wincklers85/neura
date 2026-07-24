from __future__ import annotations
import json

from coding_engine import (
    add_lesson, apply_change_set, list_lessons, propose_change,
    test_change_set, validate_change_set
)
from db import db
from security import decrypt_text, encrypt_text


async def create_proposal(goal: str) -> dict:
    data = await propose_change(goal)
    validation = validate_change_set(data)
    payload = {
        "changes": data.get("changes", []),
        "expected_result": data.get("expected_result", ""),
        "risk": data.get("risk", "medium"),
    }
    with db() as conn:
        cur = conn.execute("""
            INSERT INTO lab_proposals(
                title,status,rationale_enc,patch_enc,tests_enc,validation_enc
            ) VALUES(?,?,?,?,?,?)
        """, (
            str(data.get("title", "Proposta"))[:160], "proposed",
            encrypt_text(str(data.get("rationale", ""))),
            encrypt_text(json.dumps(payload, ensure_ascii=False)),
            encrypt_text(json.dumps(data.get("tests", []), ensure_ascii=False)),
            encrypt_text(json.dumps(validation, ensure_ascii=False)),
        ))
        proposal_id = int(cur.lastrowid)
    return {"id": proposal_id, **data, "status": "proposed",
            "validation": validation}


def _row_to_dict(r) -> dict:
    raw = decrypt_text(r["patch_enc"]) if r["patch_enc"] else "{}"
    try:
        payload = json.loads(raw)
    except Exception:
        payload = {"changes": [], "legacy_patch": raw}
    try:
        tests = json.loads(decrypt_text(r["tests_enc"])) if r["tests_enc"] else []
    except Exception:
        tests = [decrypt_text(r["tests_enc"])] if r["tests_enc"] else []
    try:
        validation = json.loads(decrypt_text(r["validation_enc"])) if r["validation_enc"] else {}
    except Exception:
        validation = {}
    return {
        "id": r["id"], "title": r["title"], "status": r["status"],
        "rationale": decrypt_text(r["rationale_enc"]),
        "changes": payload.get("changes", []),
        "expected_result": payload.get("expected_result", ""),
        "risk": payload.get("risk", "unknown"),
        "tests": tests, "validation": validation,
        "applied_snapshot": r["applied_snapshot"],
        "created_at": r["created_at"],
    }


def get_proposal(proposal_id: int) -> dict:
    with db() as conn:
        r = conn.execute("""
            SELECT id,title,status,rationale_enc,patch_enc,tests_enc,
                   validation_enc,applied_snapshot,created_at
            FROM lab_proposals WHERE id=?
        """, (proposal_id,)).fetchone()
    if not r:
        raise FileNotFoundError(proposal_id)
    return _row_to_dict(r)


def list_proposals(limit: int = 30) -> list[dict]:
    with db() as conn:
        rows = conn.execute("""
            SELECT id,title,status,rationale_enc,patch_enc,tests_enc,
                   validation_enc,applied_snapshot,created_at
            FROM lab_proposals ORDER BY id DESC LIMIT ?
        """, (limit,)).fetchall()
    return [_row_to_dict(r) for r in rows]


def update_proposal_status(proposal_id: int, status: str) -> None:
    allowed = {"proposed", "validated", "approved", "rejected", "applied", "failed"}
    if status not in allowed:
        raise ValueError("Stato non valido")
    with db() as conn:
        conn.execute("UPDATE lab_proposals SET status=? WHERE id=?",
                     (status, proposal_id))


def validate_proposal(proposal_id: int) -> dict:
    proposal = get_proposal(proposal_id)
    data = {"changes": proposal["changes"]}
    report = test_change_set(data)
    status = "validated" if report["tests_passed"] else "failed"
    with db() as conn:
        conn.execute("""
            UPDATE lab_proposals SET status=?,validation_enc=? WHERE id=?
        """, (status, encrypt_text(json.dumps(report, ensure_ascii=False)),
              proposal_id))
    return report


def apply_proposal(proposal_id: int) -> dict:
    proposal = get_proposal(proposal_id)
    if proposal["status"] != "approved":
        raise ValueError("La proposta deve essere prima validata e approvata.")
    result = apply_change_set(
        {"changes": proposal["changes"]},
        f"proposal-{proposal_id}"
    )
    with db() as conn:
        conn.execute("""
            UPDATE lab_proposals
            SET status='applied',applied_snapshot=?,validation_enc=?
            WHERE id=?
        """, (
            result["snapshot"],
            encrypt_text(json.dumps(result["validation"], ensure_ascii=False)),
            proposal_id
        ))
    add_lesson(
        f"La proposta '{proposal['title']}' è stata applicata dopo validazione. "
        f"File modificati: {', '.join(result['written_files'])}. "
        "Conservare i controlli che hanno permesso l'esito positivo.",
        category="successful_update", source=f"proposal:{proposal_id}",
        confidence=0.85
    )
    return result
