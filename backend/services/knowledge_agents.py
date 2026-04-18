"""Knowledge agents (scam / insurance / tax) with safe-RAG fallback.

The previous implementation returned a bare ``"Not found in knowledge
base"`` string whenever retrieval missed — which is why every off-topic
or slightly-worded question looked hardcoded. We now apply a tiered
policy driven by retrieval confidence (``grade``) and we always pass
the live user context into the LLM prompt so answers feel personal.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.llm_service import call_llm


_AGENT_PERSONAS: Dict[str, str] = {
    "scam_agent": (
        "You are Astra's scam and fraud safety assistant for Indian banking "
        "customers. Be concrete, cite red flags, and never tell the user to "
        "share OTPs, passwords, or card numbers."
    ),
    "insurance_agent": (
        "You are Astra's insurance assistant. Explain policies, claim steps, "
        "and exclusions in plain language grounded ONLY in the supplied "
        "knowledge context."
    ),
    "tax_agent": (
        "You are Astra's Indian tax assistant. Explain deductions, ITR steps, "
        "and regime differences grounded ONLY in the supplied knowledge "
        "context. Mention the assessment year whenever relevant."
    ),
}

_GROUNDED_PROMPT = """{persona}

STRICT RULES:
- Use ONLY the knowledge base context below for factual claims.
- You MAY personalize using the USER SNAPSHOT (for example, referencing their
  monthly commitments or top spend category) but never invent numbers.
- If the context truly does not cover the question, say so and propose the
  next helpful step — do not hallucinate.
- Keep the answer under 180 words, in Markdown with short bullet points.

{user_context}

CONVERSATION (most recent last):
{memory_block}

KNOWLEDGE BASE CONTEXT:
{retrieved_chunks}

USER QUESTION:
{user_query}

ANSWER:"""


_CLARIFY_PROMPT = """{persona}

The knowledge base did not return a confident match for this question.
Using the USER SNAPSHOT and the (possibly weak) context below, reply with
ONE short clarifying question that would let Astra answer precisely.
Never fabricate facts. Respond in under 60 words.

{user_context}

WEAK CONTEXT (may be tangential):
{retrieved_chunks}

USER QUESTION:
{user_query}

CLARIFYING QUESTION:"""


def _fallback_response(agent_name: str, category: str) -> str:
    domain = {
        "scam_agent": "scam / fraud",
        "insurance_agent": "insurance",
        "tax_agent": "tax",
    }.get(agent_name, category or "this topic")
    return (
        f"I do not have verified information on that specific {domain} "
        "question yet. Could you share a bit more context (for example the "
        "product name, policy type, or the exact scenario) so I can pull the "
        "right guidance?"
    )


def _format_memory(memory: Optional[List[Dict[str, Any]]]) -> str:
    if not memory:
        return "(no prior messages)"
    lines = []
    for msg in memory[-4:]:
        role = (msg.get("role") or "user").upper()
        content = (msg.get("content") or "").strip().replace("\n", " ")
        if not content:
            continue
        lines.append(f"{role}: {content[:240]}")
    return "\n".join(lines) if lines else "(no prior messages)"


def _format_user_context(user_context: Optional[Dict[str, Any]]) -> str:
    if not user_context:
        return "USER SNAPSHOT: (none available)"
    text = (user_context.get("prompt_text") or "").strip()
    return text or "USER SNAPSHOT: (none available)"


def answer_with_knowledge(
    agent_name: str,
    user_query: str,
    retrieval: Dict[str, Any],
    memory: Optional[List[Dict[str, Any]]] = None,
    user_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a tiered response for a non-finance agent.

    The shape matches what ``chat_service`` expects: ``response``,
    ``sources``, ``type``, ``reason``, ``confidence`` and optional
    ``actions`` / ``ui_action``.
    """

    persona = _AGENT_PERSONAS.get(agent_name, _AGENT_PERSONAS["insurance_agent"])
    grade = retrieval.get("grade", "none")
    category = retrieval.get("category") or ""
    retrieved_chunks = retrieval.get("context") or ""
    memory_block = _format_memory(memory)
    context_block = _format_user_context(user_context)
    sources = retrieval.get("sources") or (["qdrant"] if retrieved_chunks else [])

    if grade == "good":
        prompt = _GROUNDED_PROMPT.format(
            persona=persona,
            user_context=context_block,
            memory_block=memory_block,
            retrieved_chunks=retrieved_chunks,
            user_query=user_query,
        )
        try:
            response = call_llm(prompt, temperature=0.1)
        except Exception:
            response = ""
        if not response:
            return {
                "response": _fallback_response(agent_name, category),
                "sources": [],
                "type": agent_name,
                "reason": "llm_unavailable",
                "confidence": 0.2,
            }
        return {
            "response": response,
            "sources": sources,
            "type": agent_name,
            "reason": "rag_grounded",
            "confidence": round(min(1.0, float(retrieval.get("top_score") or 0.0)), 2),
        }

    if grade == "weak":
        prompt = _CLARIFY_PROMPT.format(
            persona=persona,
            user_context=context_block,
            retrieved_chunks=retrieved_chunks or "(no strong matches)",
            user_query=user_query,
        )
        try:
            response = call_llm(prompt, temperature=0.2)
        except Exception:
            response = ""
        if not response:
            response = _fallback_response(agent_name, category)
        return {
            "response": response,
            "sources": sources,
            "type": agent_name,
            "reason": "rag_weak_clarify",
            "confidence": round(float(retrieval.get("top_score") or 0.0), 2),
            "actions": ["rephrase", "upload_document"],
        }

    return {
        "response": _fallback_response(agent_name, category),
        "sources": [],
        "type": agent_name,
        "reason": "rag_no_context",
        "confidence": 0.15,
        "actions": ["rephrase", "upload_document"],
    }
