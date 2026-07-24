from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

API_BASE = os.getenv("LLM_API_BASE", "https://api.openai.com/v1").rstrip("/")
API_KEY = os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", "")).strip()
MODEL = os.getenv("MODEL_NAME", "gpt-4.1-mini")
TIMEOUT = float(os.getenv("LLM_TIMEOUT", "180"))
MAX_CONCURRENT = max(1, int(os.getenv("LLM_MAX_CONCURRENT", "3")))
RETRIES = max(0, int(os.getenv("LLM_RETRIES", "2")))

_gate = asyncio.Semaphore(MAX_CONCURRENT)


class LLMError(RuntimeError):
    pass


def provider_status() -> dict[str, Any]:
    return {
        "ready": bool(API_KEY),
        "provider": "openai-compatible-cloud",
        "model": MODEL,
        "api_base": API_BASE,
        "detail": "pronto" if API_KEY else "LLM_API_KEY non configurata",
    }


async def chat(messages: list[dict], temperature: float = 0.45, max_tokens: int = 1400) -> str:
    if not API_KEY:
        raise LLMError("Il motore cloud non è configurato: imposta LLM_API_KEY su Render.")

    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

    last_error: Exception | None = None
    async with _gate:
        for attempt in range(RETRIES + 1):
            try:
                timeout = httpx.Timeout(TIMEOUT, connect=20.0)
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(f"{API_BASE}/chat/completions", headers=headers, json=payload)

                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < RETRIES:
                        await asyncio.sleep(1.5 * (attempt + 1))
                        continue
                if response.status_code >= 400:
                    detail = response.text[:700]
                    raise LLMError(f"Servizio AI: HTTP {response.status_code}. {detail}")

                data = response.json()
                content = data["choices"][0]["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise LLMError("Il servizio AI ha restituito una risposta vuota.")
                return content.strip()
            except LLMError:
                raise
            except (httpx.TimeoutException, httpx.NetworkError, KeyError, TypeError, ValueError) as exc:
                last_error = exc
                if attempt < RETRIES:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue

    raise LLMError(f"Il servizio AI non risponde dopo più tentativi: {last_error}")
