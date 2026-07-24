from __future__ import annotations

import base64
import os

import httpx

from provider_config import load_provider_config


async def analyze_image(data: bytes, question: str, mime_type: str = "image/jpeg") -> str:
    cfg = load_provider_config()
    if not cfg["api_key"]:
        raise RuntimeError("Configura prima il motore AI nelle Impostazioni.")
    encoded = base64.b64encode(data).decode("ascii")
    payload = {
        "model": cfg["vision_model"] or cfg["model"],
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": question or "Descrivi accuratamente questa immagine."},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}},
            ],
        }],
        "max_tokens": 1400,
    }
    headers = {"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"}
    timeout = httpx.Timeout(float(os.getenv("LLM_TIMEOUT", "180")), connect=20.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{cfg['api_base']}/chat/completions", headers=headers, json=payload)
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
        answer = response.json()["choices"][0]["message"]["content"]
        if not answer:
            raise RuntimeError("risposta vuota")
        return answer.strip()
    except Exception as exc:
        raise RuntimeError(f"Modello visivo non disponibile: {exc}") from exc
