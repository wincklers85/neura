from __future__ import annotations

import base64
import os

import httpx


async def analyze_image(data: bytes, question: str, mime_type: str = "image/jpeg") -> str:
    api_base = os.getenv("LLM_API_BASE", "https://api.openai.com/v1").rstrip("/")
    api_key = os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", "")).strip()
    model = os.getenv("VISION_MODEL", os.getenv("MODEL_NAME", "gpt-4.1-mini"))
    if not api_key:
        raise RuntimeError("LLM_API_KEY non configurata")

    encoded = base64.b64encode(data).decode("ascii")
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": question or "Descrivi accuratamente questa immagine."},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}},
            ],
        }],
        "max_tokens": 1200,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        timeout = httpx.Timeout(float(os.getenv("LLM_TIMEOUT", "180")), connect=20.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{api_base}/chat/completions", headers=headers, json=payload)
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
        answer = response.json()["choices"][0]["message"]["content"]
        if not answer:
            raise RuntimeError("risposta vuota")
        return answer.strip()
    except Exception as exc:
        raise RuntimeError(f"Modello visivo non disponibile: {exc}") from exc
