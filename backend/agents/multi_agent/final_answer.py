from __future__ import annotations

import json
from typing import Any, Dict

from services.llm_service import call_llm

from .prompts import FINAL_ANSWER_AGENT_HINTS, FINAL_ANSWER_SYSTEM_PROMPT

INSUFFICIENT_DATA = "I don't have enough data to answer this accurately."


def _build_final_answer_prompt(user_query: str, context: Dict[str, Any], agent_name: str) -> str:
    agent_hint = FINAL_ANSWER_AGENT_HINTS.get(agent_name, "")
    return (
        f"{FINAL_ANSWER_SYSTEM_PROMPT}\n\n"
        f"Agent type: {agent_name}\n"
        f"Agent guidance: {agent_hint}\n\n"
        f"User query:\n{user_query.strip()}\n\n"
        "Structured context JSON:\n"
        f"{json.dumps(context, indent=2, ensure_ascii=False)}\n\n"
        "Write the final response for the user as plain text."
    )


def generate_final_answer(user_query: str, context: Dict[str, Any], *, agent_name: str) -> str:
    try:
        response = call_llm(
            _build_final_answer_prompt(user_query, context, agent_name),
            temperature=0.2,
        )
    except Exception:
        return INSUFFICIENT_DATA

    text = (response or "").strip()
    return text or INSUFFICIENT_DATA
