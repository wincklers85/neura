from __future__ import annotations
import os
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
CODE_BACKUP_DIR = DATA_DIR / "code_backups"
EXCLUDED = {"data", ".venv", "__pycache__", ".git"}


def _tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def create_code_snapshot(label: str = "manual") -> dict:
    CODE_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(c for c in label if c.isalnum() or c in "-_ ").strip().replace(" ", "-")[:40] or "snapshot"
    target = CODE_BACKUP_DIR / f"neura-code-{_tag()}-{safe}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for p in BASE_DIR.rglob("*"):
            if not p.is_file() or any(part in EXCLUDED for part in p.relative_to(BASE_DIR).parts):
                continue
            z.write(p, p.relative_to(BASE_DIR))
    return {"filename": target.name, "size": target.stat().st_size, "created_at": datetime.now(timezone.utc).isoformat()}


def list_code_snapshots() -> list[dict]:
    CODE_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return [{"filename": p.name, "size": p.stat().st_size, "created_at": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat()}
            for p in sorted(CODE_BACKUP_DIR.glob("*.zip"), reverse=True)]


def rollback_code(filename: str) -> dict:
    name = Path(filename).name
    source = CODE_BACKUP_DIR / name
    if not source.exists():
        raise FileNotFoundError(name)
    safety = create_code_snapshot("before-rollback")
    with zipfile.ZipFile(source, "r") as z:
        members = [m for m in z.infolist() if not m.filename.startswith("/") and ".." not in Path(m.filename).parts]
        z.extractall(BASE_DIR, members=members)
    return {"ok": True, "restored": name, "safety_snapshot": safety["filename"], "restart_required": True}
