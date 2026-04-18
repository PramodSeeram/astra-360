import json
import logging
import os
import re
import time

import httpx

logger = logging.getLogger(__name__)

LLM_URL = os.getenv("LLM_URL", "http://localhost:11434/api/generate")
LLM_MODEL = os.getenv("LLM_MODEL", "mistral")


def call_llm(prompt: str, temperature: float = 0.0) -> str:
    payload = {
        "model": LLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }
    with httpx.Client(timeout=90.0) as client:
        for attempt in range(3):
            try:
                response = client.post(LLM_URL, json=payload)
                response.raise_for_status()
                return response.json().get("response", "").strip()
            except Exception as exc:
                logger.warning("LLM request failed on attempt %s: %s", attempt + 1, exc)
                if attempt == 2:
                    raise
                time.sleep(1.5)
    return ""


_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def extract_json_object(text: str) -> dict | None:
    """Best-effort parse of a JSON object from an LLM reply."""
    if not text or not text.strip():
        return None
    raw = text.strip()
    m = _JSON_FENCE.search(raw)
    if m:
        raw = m.group(1).strip()
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(raw[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None
