import json
from db import db
from llm import chat as llm_chat
from security import encrypt_text, decrypt_text


async def create_proposal(goal: str) -> dict:
    prompt = """
Sei il Laboratorio di sviluppo di NÈURA. Devi proporre un miglioramento prudente
al software, senza applicarlo. Rispondi ESCLUSIVAMENTE con JSON valido:
{
 "title":"titolo breve",
 "rationale":"problema, beneficio, rischi e file coinvolti",
 "patch":"diff unificato o codice proposto; può essere vuoto se servono più dati",
 "tests":"test manuali e automatici da eseguire"
}
Non includere segreti, chiavi, credenziali o codice distruttivo. Non proporre
auto-modifiche senza revisione umana.
""".strip()
    raw = await llm_chat([
        {"role": "system", "content": prompt},
        {"role": "user", "content": goal}
    ], temperature=0.2, max_tokens=1500)
    try:
        start, end = raw.index("{"), raw.rindex("}") + 1
        data = json.loads(raw[start:end])
    except Exception:
        data = {
            "title": "Proposta di miglioramento",
            "rationale": raw,
            "patch": "",
            "tests": "Revisione manuale necessaria."
        }
    with db() as conn:
        cur = conn.execute("""
            INSERT INTO lab_proposals(title,status,rationale_enc,patch_enc,tests_enc)
            VALUES(?,?,?,?,?)
        """, (
            str(data.get("title", "Proposta"))[:160],
            "proposed",
            encrypt_text(str(data.get("rationale", ""))),
            encrypt_text(str(data.get("patch", ""))) if data.get("patch") else None,
            encrypt_text(str(data.get("tests", ""))) if data.get("tests") else None
        ))
        proposal_id = int(cur.lastrowid)
    return {"id": proposal_id, **data, "status": "proposed"}


def list_proposals(limit: int = 30) -> list[dict]:
    with db() as conn:
        rows = conn.execute("""
            SELECT id,title,status,rationale_enc,patch_enc,tests_enc,created_at
            FROM lab_proposals ORDER BY id DESC LIMIT ?
        """, (limit,)).fetchall()
    return [{
        "id": r["id"], "title": r["title"], "status": r["status"],
        "rationale": decrypt_text(r["rationale_enc"]),
        "patch": decrypt_text(r["patch_enc"]) if r["patch_enc"] else "",
        "tests": decrypt_text(r["tests_enc"]) if r["tests_enc"] else "",
        "created_at": r["created_at"]
    } for r in rows]


def update_proposal_status(proposal_id: int, status: str) -> None:
    allowed = {"proposed", "approved", "rejected", "applied"}
    if status not in allowed:
        raise ValueError("Stato non valido")
    with db() as conn:
        conn.execute("UPDATE lab_proposals SET status=? WHERE id=?", (status, proposal_id))
