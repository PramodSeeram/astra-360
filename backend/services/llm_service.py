import json
import logging
import os
import re
import time

import httpx

logger = logging.getLogger(__name__)


def _resolve_llm_url() -> str:
    direct = (os.getenv("LLM_URL") or "").strip()
    if direct:
        return direct
    host = (os.getenv("OLLAMA_HOST") or "").strip().rstrip("/")
    if host:
        return f"{host}/api/generate"
    return "http://localhost:11434/api/generate"


def _resolve_llm_model() -> str:
    for key in ("LLM_MODEL", "OLLAMA_MODEL"):
        v = (os.getenv(key) or "").strip()
        if v:
            return v
    return "astra-llm:latest"


# Call these for up-to-date values (e.g. after tests patch os.environ).
get_llm_url = _resolve_llm_url
get_llm_model = _resolve_llm_model

LLM_URL = _resolve_llm_url()
LLM_MODEL = _resolve_llm_model()
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "120"))


def get_ollama_headers() -> dict[str, str]:
    """Optional Bearer token for RunPod (or other) proxies that require Authorization."""
    token = (os.getenv("OLLAMA_API_TOKEN") or "").strip()
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def call_llm(
    prompt: str,
    temperature: float | None = None,
    *,
    model: str | None = None,
) -> str:
    if temperature is None:
        temperature = float(os.getenv("LLM_TEMPERATURE", "0.1"))
    use_model = (model or get_llm_model()).strip()
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "1024"))
    req_timeout = float(os.getenv("LLM_TIMEOUT", "120"))
    payload = {
        "model": use_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    headers = get_ollama_headers()
    timeout = httpx.Timeout(req_timeout, connect=min(30.0, req_timeout))
    with httpx.Client(timeout=timeout) as client:
        for attempt in range(3):
            try:
                response = client.post(get_llm_url(), json=payload, headers=headers)
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
