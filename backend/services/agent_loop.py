"""Planner → tools → synthesizer agent loop.

The LLM decides *which* tools to call (not hardcoded per intent). Tool
outputs are authoritative; the final LLM only narrates and reasons.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from models import User
from services.agent_router import AgentRoute
from services.chat_policy import build_response_envelope, finance_snapshot_data
from services.chat_tools import (
    TOOL_REGISTRY,
    default_tool_plan,
    execute_tool,
)
from services.financial_engine import build_financial_snapshot
from services.llm_service import call_llm, extract_json_object

logger = logging.getLogger(__name__)

MAX_TOOL_CALLS = 3

USE_AGENTIC_CHAT = os.getenv("USE_AGENTIC_CHAT", "true").lower() in (
    "1",
    "true",
    "yes",
)

AGENTIC_DEBUG = os.getenv("AGENTIC_DEBUG", "false").lower() in ("1", "true", "yes")

PLANNER_PROMPT = """You are the planning brain for Astra, an Indian fintech assistant.

User message:
{message}

Router hint (do not contradict — use it to choose knowledge category):
- agent: {agent}
- category: {category}

Recent conversation (oldest first):
{memory}

Available tools (call only what you need, in order):
1. get_financial_summary — DB snapshot: salary avg, expenses, savings, balances, top categories, rent, EMI, subscriptions. Use for ANY personal money question.
2. get_top_categories — category totals for the canonical month; args: limit (default 5).
3. get_top_debit_transactions — largest debits in canonical month; args: limit (e.g. 5 for "top 5").
4. get_recent_transactions — latest rows; args: limit, tx_type: "all"|"debit"|"credit".
5. search_knowledge — RAG over policy docs; args: query (string), category (scam|insurance|tax|finance or null), top_k.
6. get_user_context_snapshot — user profile + bills + subscriptions summary text for personalization.

Rules:
- For "top N" / "biggest spends" include get_top_debit_transactions or get_top_categories with limit=N.
- For insurance/tax/scam *general* questions, prefer search_knowledge + get_user_context_snapshot.
- For hybrid questions ("overspending + what should I do"), use get_financial_summary + get_user_context_snapshot; add search_knowledge only if domain facts are needed.
- Never invent tool names.

Reply with ONLY valid JSON (no markdown outside JSON):
{{
  "tool_calls": [
    {{"name": "<tool_name>", "arguments": {{ ... }} }}
  ],
  "strategy": "one short sentence"
}}
"""


SYNTHESIZER_PROMPT = """You are Astra's voice — helpful, clear, concise (under 250 words). Use Markdown.

User question:
{message}

Router context: {agent} / {category}

AUTHORITATIVE DATA (from tools — these numbers are ground truth; never contradict or recompute them):
{tool_json}

Conversation memory (for tone only):
{memory}

Rules:
1. Base every numeric claim on the authoritative data. If a number is missing, say you don't have it.
2. Do not invent transactions, balances, or policy facts.
3. STRICT: Do not modify numeric values, do not round/recompute values, and do not introduce new calculated numbers unless a tool already provided that exact number.
4. If search_knowledge context is empty or weak, give safe general guidance and suggest uploading docs or rephrasing — do not hallucinate regulations.
5. For budgeting or "reduce expenses", use get_financial_summary / get_top_categories facts explicitly.
6. Be warm and actionable.

Answer:"""


def _memory_block(memory: List[Dict[str, Any]], max_chars: int = 1200) -> str:
    if not memory:
        return "(none)"
    lines = []
    for m in memory[-3:]:
        role = (m.get("role") or "user").upper()
        c = (m.get("content") or "").strip().replace("\n", " ")
        if c:
            lines.append(f"{role}: {c[:400]}")
    text = "\n".join(lines)
    return text[:max_chars]


def _is_vague_query(message: str) -> bool:
    text = (message or "").strip().lower()
    if not text:
        return True
    vague_phrases = (
        "help me manage money",
        "help me",
        "what should i do",
        "guide me",
        "improve finances",
        "manage money",
    )
    return len(text.split()) <= 4 or any(p in text for p in vague_phrases)


def _validate_or_repair_plan(
    plan: List[Dict[str, Any]],
    message: str,
    route: AgentRoute,
) -> List[Dict[str, Any]]:
    """Validate planner output and repair obvious misses.

    We never trust the planner blindly: enforce tool cap, known tools,
    argument shape, and explicit top-N coverage for ranking requests.
    """
    repaired: List[Dict[str, Any]] = []
    for item in plan[:MAX_TOOL_CALLS]:
        name = item.get("name")
        args = item.get("arguments") or {}
        if name not in TOOL_REGISTRY or not isinstance(args, dict):
            continue
        repaired.append({"name": name, "arguments": args})

    if not repaired:
        return default_tool_plan(route.agent, route.category, message)[:MAX_TOOL_CALLS]

    msg = (message or "").lower()
    if any(k in msg for k in ("top ", "biggest", "highest", "largest")):
        has_rank_tool = any(
            c["name"] in {"get_top_debit_transactions", "get_top_categories"}
            for c in repaired
        )
        if not has_rank_tool:
            fallback = default_tool_plan(route.agent, route.category, message)
            repaired.extend(
                c for c in fallback
                if c["name"] in {"get_top_debit_transactions", "get_top_categories"}
            )

    if _is_vague_query(message):
        if not any(c["name"] == "get_financial_summary" for c in repaired):
            repaired.insert(0, {"name": "get_financial_summary", "arguments": {}})
        if not any(c["name"] == "get_user_context_snapshot" for c in repaired):
            repaired.append({"name": "get_user_context_snapshot", "arguments": {}})

    return repaired[:MAX_TOOL_CALLS]


def _plan_tools(
    message: str,
    memory: List[Dict[str, Any]],
    route: AgentRoute,
) -> tuple[List[Dict[str, Any]], Optional[str]]:
    prompt = PLANNER_PROMPT.format(
        message=message.strip(),
        agent=route.agent,
        category=route.category,
        memory=_memory_block(memory),
    )
    try:
        raw = call_llm(prompt, temperature=0.1)
    except Exception as exc:
        logger.warning("planner LLM failed: %s", exc)
        return default_tool_plan(route.agent, route.category, message), None
    parsed = extract_json_object(raw) if raw else None
    if not parsed:
        logger.warning("planner returned non-JSON, using defaults")
        return default_tool_plan(route.agent, route.category, message), None
    calls = parsed.get("tool_calls")
    strategy = parsed.get("strategy")
    strat = strategy.strip() if isinstance(strategy, str) else None
    if not isinstance(calls, list):
        return default_tool_plan(route.agent, route.category, message), strat
    cleaned: List[Dict[str, Any]] = []
    for item in calls[:MAX_TOOL_CALLS]:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if name not in TOOL_REGISTRY:
            continue
        args = item.get("arguments")
        if args is not None and not isinstance(args, dict):
            continue
        cleaned.append({"name": name, "arguments": args or {}})
    if not cleaned:
        fallback = default_tool_plan(route.agent, route.category, message)[:MAX_TOOL_CALLS]
        return _validate_or_repair_plan(fallback, message, route), strat
    return _validate_or_repair_plan(cleaned, message, route), strat


def _synthesize(
    message: str,
    memory: List[Dict[str, Any]],
    route: AgentRoute,
    tool_results: Dict[str, Any],
) -> str:
    payload = json.dumps(tool_results, ensure_ascii=False, indent=2)[:24000]
    prompt = SYNTHESIZER_PROMPT.format(
        message=message.strip(),
        agent=route.agent,
        category=route.category,
        tool_json=payload,
        memory=_memory_block(memory),
    )
    try:
        return call_llm(prompt, temperature=0.35)
    except Exception as exc:
        logger.warning("synthesizer LLM failed: %s", exc)
        return (
            "I pulled your data but could not generate a full reply right now. "
            "Please try again in a moment."
        )


def run_agentic_chat(
    db: Session,
    user: User,
    message: str,
    memory: List[Dict[str, Any]],
    route: AgentRoute,
) -> Dict[str, Any]:
    """Run planner → tools → synthesizer; return canonical chat envelope."""

    plan, planner_strategy = _plan_tools(message, memory, route)
    plan = _validate_or_repair_plan(plan, message, route)
    for call in plan:
        if call.get("name") == "search_knowledge":
            args = call.setdefault("arguments", {})
            if not args.get("category") and route.category:
                args["category"] = route.category
            if not args.get("query"):
                args["query"] = message
    tool_results: Dict[str, Any] = {"plan": plan, "results": []}

    for idx, call in enumerate(plan):
        name = call["name"]
        args = call.get("arguments") or {}
        result = execute_tool(name, db, user, args)
        tool_results["results"].append(
            {"step": idx + 1, "tool": name, "arguments": args, "output": result}
        )

    text = _synthesize(message, memory, route, tool_results)

    snap = build_financial_snapshot(db, user)
    sources: List[str] = []
    for block in tool_results["results"]:
        t = block.get("tool")
        out = block.get("output") or {}
        if t == "search_knowledge" and out.get("sources"):
            sources.extend(str(s) for s in out["sources"][:5])
        if t in ("get_financial_summary", "get_top_categories", "get_top_debit_transactions"):
            if out.get("has_data") or out.get("ok"):
                sources.append("db")
    if not sources:
        sources = ["agentic"]
    sources = list(dict.fromkeys(sources))

    data: Dict[str, Any] = {
        "agentic": True,
        "tools_used": [c.get("name") for c in plan],
        "planner_strategy": planner_strategy,
        "explanation": (
            "Response synthesized from live tool outputs"
            + (f": {', '.join([c.get('name') for c in plan if c.get('name')])}." if plan else ".")
        ),
        "finance_snapshot": finance_snapshot_data(snap) if snap.transactions_found else {},
    }
    if AGENTIC_DEBUG:
        data["tool_results"] = tool_results

    return build_response_envelope(
        type_name=route.agent,
        response=text.strip() or "I could not produce an answer.",
        sources=sources,
        reason="agentic_tools",
        confidence=0.85,
        route=route,
        data=data,
    )
