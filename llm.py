import asyncio
import json
import os
import httpx

BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:8080/v1").rstrip("/")
API_KEY = os.getenv("LLM_API_KEY", "")
MODEL = os.getenv("MODEL_NAME", "neura-local")
TIMEOUT = float(os.getenv("LLM_TIMEOUT", "300"))
STARTUP_RETRIES = int(os.getenv("LLM_STARTUP_RETRIES", "30"))

class LLMError(RuntimeError):
    pass

async def _post(payload: dict) -> httpx.Response:
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        return await client.post(f"{BASE_URL}/chat/completions", headers=headers, json=payload)

async def chat(messages: list[dict], temperature: float = 0.45, max_tokens: int = 700) -> str:
    payload = {"model": MODEL, "messages": messages, "temperature": temperature, "max_tokens": max_tokens, "stream": False}
    last_error = ""
    for attempt in range(STARTUP_RETRIES):
        try:
            response = await _post(payload)
            if response.status_code < 400:
                data = response.json()
                return data["choices"][0]["message"]["content"].strip()
            last_error = f"{response.status_code}: {response.text[:500]}"
        except (httpx.ConnectError, httpx.ReadTimeout, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        await asyncio.sleep(min(2 + attempt, 10))
    raise LLMError("Il motore locale non è ancora disponibile. Al primo avvio potrebbe stare scaricando il modello. Ultimo errore: " + last_error)
