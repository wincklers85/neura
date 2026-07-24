from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from security import decrypt_text, encrypt_text

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
CONFIG_PATH = DATA_DIR / "provider.json"

PROVIDERS: dict[str, dict[str, str]] = {
    "openai": {
        "label": "OpenAI",
        "api_base": "https://api.openai.com/v1",
        "model": "gpt-4.1-mini",
        "vision_model": "gpt-4.1-mini",
    },
    "openrouter": {
        "label": "OpenRouter",
        "api_base": "https://openrouter.ai/api/v1",
        "model": "openai/gpt-4.1-mini",
        "vision_model": "openai/gpt-4.1-mini",
    },
    "groq": {
        "label": "Groq",
        "api_base": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "vision_model": "meta-llama/llama-4-scout-17b-16e-instruct",
    },
    "deepseek": {
        "label": "DeepSeek",
        "api_base": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "vision_model": "deepseek-chat",
    },
    "custom": {
        "label": "Compatibile OpenAI / personalizzato",
        "api_base": "",
        "model": "",
        "vision_model": "",
    },
}


def _env_config() -> dict[str, Any]:
    key = os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", "")).strip()
    return {
        "provider": os.getenv("LLM_PROVIDER", "openai"),
        "api_base": os.getenv("LLM_API_BASE", "https://api.openai.com/v1").rstrip("/"),
        "api_key": key,
        "model": os.getenv("MODEL_NAME", "gpt-4.1-mini"),
        "vision_model": os.getenv("VISION_MODEL", os.getenv("MODEL_NAME", "gpt-4.1-mini")),
        "source": "render",
    }


def load_provider_config(include_secret: bool = True) -> dict[str, Any]:
    base = _env_config()
    if CONFIG_PATH.exists():
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            stored_key = raw.get("api_key_enc", "")
            key = decrypt_text(stored_key) if stored_key else ""
            if key == "[contenuto non decifrabile]":
                key = ""
            base.update({
                "provider": raw.get("provider", base["provider"]),
                "api_base": str(raw.get("api_base", base["api_base"])).rstrip("/"),
                "api_key": key or base["api_key"],
                "model": raw.get("model", base["model"]),
                "vision_model": raw.get("vision_model", base["vision_model"]),
                "source": "impostazioni",
            })
        except (OSError, ValueError, TypeError):
            pass
    if not include_secret:
        base["api_key"] = ""
    return base


def save_provider_config(config: dict[str, str]) -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    provider = config.get("provider", "custom")
    api_base = config.get("api_base", "").strip().rstrip("/")
    model = config.get("model", "").strip()
    vision_model = config.get("vision_model", "").strip() or model
    api_key = config.get("api_key", "").strip()
    if not api_base or not model:
        raise ValueError("Indirizzo API e modello sono obbligatori.")
    current = load_provider_config()
    if not api_key:
        api_key = current.get("api_key", "")
    if not api_key:
        raise ValueError("Inserisci la chiave API.")
    payload = {
        "provider": provider,
        "api_base": api_base,
        "model": model,
        "vision_model": vision_model,
        "api_key_enc": encrypt_text(api_key),
    }
    temp = CONFIG_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(CONFIG_PATH)
    return load_provider_config(include_secret=False)


def public_config() -> dict[str, Any]:
    cfg = load_provider_config()
    return {
        "provider": cfg["provider"],
        "api_base": cfg["api_base"],
        "model": cfg["model"],
        "vision_model": cfg["vision_model"],
        "has_api_key": bool(cfg["api_key"]),
        "source": cfg["source"],
        "providers": PROVIDERS,
    }
