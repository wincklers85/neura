from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

from provider_config import load_provider_config

TIMEOUT = float(os.getenv("LLM_TIMEOUT", "180"))
MAX_CONCURRENT = max(1, int(os.getenv("LLM_MAX_CONCURRENT", "2")))
RETRIES = max(0, int(os.getenv("LLM_RETRIES", "2")))
_gate = asyncio.Semaphore(MAX_CONCURRENT)


class LLMError(RuntimeError):
    pass


def provider_status() -> dict[str, Any]:
    cfg = load_provider_config()
    return {
        "ready": bool(cfg["api_key"] and cfg["api_base"] and cfg["model"]),
        "provider": cfg["provider"],
        "model": cfg["model"],
        "api_base": cfg["api_base"],
        "source": cfg["source"],
        "detail": "pronto" if cfg["api_key"] else "chiave API non configurata",
    }


async def _request(messages: list[dict], temperature: float, max_tokens: int) -> str:
    cfg = load_provider_config()
    if not cfg["api_key"]:
        raise LLMError("Il motore AI non è configurato. Apri Impostazioni → Motore AI e inserisci una chiave API.")
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"}
    if cfg["provider"] == "openrouter":
        headers["HTTP-Referer"] = os.getenv("APP_PUBLIC_URL", "https://neura.onrender.com")
        headers["X-Title"] = "NEURA"

    last_error: Exception | None = None
    for attempt in range(RETRIES + 1):
        try:
            timeout = httpx.Timeout(TIMEOUT, connect=20.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(f"{cfg['api_base']}/chat/completions", headers=headers, json=payload)
            if response.status_code in (408, 409, 429) or response.status_code >= 500:
                if attempt < RETRIES:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
            if response.status_code >= 400:
                try:
                    detail = response.json().get("error", {}).get("message") or response.text[:700]
                except Exception:
                    detail = response.text[:700]
                raise LLMError(f"Il fornitore AI ha risposto HTTP {response.status_code}: {detail}")
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise LLMError("Il fornitore AI ha restituito una risposta vuota.")
            return content.strip()
        except LLMError:
            raise
        except (httpx.TimeoutException, httpx.NetworkError, KeyError, TypeError, ValueError) as exc:
            last_error = exc
            if attempt < RETRIES:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
    raise LLMError(f"Il servizio AI non risponde dopo più tentativi: {last_error}")


async def chat(messages: list[dict], temperature: float = 0.45, max_tokens: int = 1800) -> str:
    async with _gate:
        return await _request(messages, temperature, max_tokens)


async def test_provider() -> str:
    return await chat([
        {"role": "system", "content": "Rispondi esclusivamente con: CONNESSIONE OK"},
        {"role": "user", "content": "Test"},
    ], temperature=0, max_tokens=20)
