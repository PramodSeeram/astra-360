from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from models import Card, Transaction, User
from services.financial_engine import canonical_year_month, transactions_in_month
from services.budget_engine import compute_monthly_budget
from services.spending_engine import compute_spending, normalize_merchant, parse_query_month_window

from services.llm_service import call_llm, extract_json_object

from .agent_tools import get_card_data, get_credit_data, get_fraud_signals
from .prompts import (
    SUPERVISOR_ROUTER_PROMPT,
    WEALTH_AGENT_PROMPT,
    TELLER_AGENT_PROMPT,
    SCAM_AGENT_PROMPT,
    CLAIMS_AGENT_PROMPT,
    LLM_REWRITE_PROMPT,
)
from .state import AgentTraceEntry, AstraAgentState
from services.chat_tools import (
    tool_get_financial_summary,
    tool_get_recent_transactions,
)

logger = logging.getLogger(__name__)

VALID_AGENTS = {
    "wealth_agent",
    "teller_agent",
    "scam_agent",
    "claims_agent",
    "spending_agent",
    "budget_agent",
    "default_agent",
}

INSUFFICIENT_DATA = "I don't have enough data to answer this accurately."


def _format_inr(value: float) -> str:
    return f"₹{round(float(value), 2):,.2f}"


def _normalize_merchant_key(description: Optional[str]) -> str:
    """Legacy key for missed-savings card logic (raw-ish line)."""
    line = (description or "").strip().split("\n")[0].strip()
    line = re.sub(r"\s+", " ", line)
    return line.lower()[:120] if line else "unknown"


def _is_spending_query(message: str) -> bool:
    m = (message or "").lower()
    keys = (
        "spend",
        "spent",
        "expense",
        "expenses",
        "swiggy",
        "zomato",
        "food",
        "where did i spend",
        "where is my money going",
        "money going",
        "outflow",
        "cash flow",
        "breakdown",
        "analysis",
    )
    if any(k in m for k in keys):
        return True
    if "how much" in m or "total" in m:
        if any(
            k in m
            for k in (
                "spend",
                "spent",
                "pay",
                "cost",
                "debit",
                "expense",
                "swiggy",
                "zomato",
                "food",
            )
        ):
            return True
    return False


def _has_narrow_wealth_intent(message: str) -> bool:
    m = (message or "").lower()
    if "cibil" in m or "credit score" in m:
        return True
    if (
        "which card" in m
        or "best card" in m
        or "card benefit" in m
        or "credit card" in m
        or "which credit card" in m
        or "best credit card" in m
        or ("best" in m and "card" in m)
    ):
        return True
    return False


def _is_budget_query(message: str) -> bool:
    m = (message or "").lower()
    if not m.strip():
        return False
    if any(k in m for k in ("budget", "income", "salary", "payroll", "savings")):
        return True
    if re.search(r"\bsaving\b", m):
        return True
    if re.search(r"\bsave\b", m):
        return True
    return False


def _is_teller_query(message: str) -> bool:
    m = (message or "").lower()
    if any(kw in m for kw in ("balance", "account", "transaction", "statement")):
        return True
    if "how much money" in m and any(
        phrase in m for phrase in ("do i have", "in my account", "left in my account")
    ):
        return True
    if "my balance" in m or "current balance" in m:
        return True
    return False


_MIN_ACTIONABLE_AMOUNT = 500.0   # below this, skip "trim X%" nudges
_STRONG_SAVINGS_RATE = 30        # above this %, user is doing well — praise, don't push


def _build_savings_insight(computed: Dict[str, Any]) -> str:
    """Generate actionable savings advice grounded in the user's actual numbers."""
    cats = computed.get("category_breakdown") or {}
    income = float(computed.get("income") or 0.0)
    expenses = float(computed.get("expenses") or 0.0)
    savings = float(computed.get("savings") or 0.0)
    tips: List[str] = []

    # --- category tips (only when amounts are meaningful) ---
    if cats and expenses > 0:
        sorted_cats = sorted(cats.items(), key=lambda x: -x[1])
        top_name, top_amt = sorted_cats[0]
        top_pct = round((top_amt / expenses) * 100)

        if top_amt >= _MIN_ACTIONABLE_AMOUNT:
            saving_20 = top_amt * 0.2
            tips.append(
                f"**{top_name}** is your biggest spend — {_format_inr(top_amt)} ({top_pct}% of expenses). "
                f"Cutting it by 20% frees up {_format_inr(saving_20)}/month."
            )
        else:
            tips.append(
                f"Your spending is distributed across small categories. "
                f"Based on your recent transactions, **{top_name}** is the largest at {_format_inr(top_amt)}."
            )

        food_cats = {"Food", "Food & Dining", "Food Delivery"}
        food_amt = sum(v for k, v in cats.items() if k in food_cats or "food" in k.lower())
        if food_amt >= _MIN_ACTIONABLE_AMOUNT and top_name not in food_cats:
            tips.append(
                f"Food delivery adds up to {_format_inr(food_amt)}/month. "
                "Even cooking at home 3 extra days a week makes a noticeable difference."
            )

    # --- savings rate feedback ---
    if income > 0:
        savings_rate = round((savings / income) * 100)
        if savings_rate >= _STRONG_SAVINGS_RATE:
            tips.append(
                f"Your savings rate is strong at {savings_rate}% of income — well above the recommended 20%. "
                "Consider channelling the surplus into a SIP or liquid fund to put it to work."
            )
        elif savings_rate >= 20:
            tips.append(
                f"You're saving {savings_rate}% of income — right on track with the 50/30/20 rule. "
                "Small reductions in discretionary spend could push this higher."
            )
        else:
            target_savings = income * 0.20
            gap = target_savings - savings
            tips.append(
                f"Your current savings rate is {savings_rate}%. "
                f"The 50/30/20 rule targets 20% ({_format_inr(target_savings)}/month) — "
                f"you're {_format_inr(gap)} away from that goal."
            )

    # --- fallback when data is thin ---
    if not tips:
        return (
            "\n\n**How to save more:**\n"
            "- Based on your recent transactions, upload a full statement to get specific category-level savings targets."
        )
    return "\n\n**How to save more:**\n" + "\n".join(f"- {t}" for t in tips)


def _build_budget_answer(computed: Dict[str, Any], user_message: str = "") -> str:
    if not computed.get("transactions_found"):
        return INSUFFICIENT_DATA
    hm = computed.get("headline_month") or "latest month"
    lines = [
        f"**Budget snapshot · {hm}** (from your bank transactions)",
        f"- Estimated monthly income: {_format_inr(float(computed.get('income') or 0.0))}",
        f"- Expenses (debits in month): {_format_inr(float(computed.get('expenses') or 0.0))}",
        f"- Savings (income − expenses): {_format_inr(float(computed.get('savings') or 0.0))}",
        f"- Latest statement balance: {_format_inr(float(computed.get('total_balance') or 0.0))}",
        "",
    ]
    if computed.get("top_category"):
        lines.append(
            f"- Top spend category: **{computed['top_category']}** "
            f"({_format_inr(float(computed.get('top_category_amount') or 0.0))})"
        )
    cats = computed.get("category_breakdown") or {}
    if cats:
        lines.append("")
        lines.append("**Category breakdown (headline month)**")
        for name, amt in sorted(cats.items(), key=lambda x: -x[1])[:8]:
            lines.append(f"- {name}: {_format_inr(float(amt))}")
    by_month = computed.get("by_month") or []
    if len(by_month) > 1:
        lines.append("")
        lines.append("**Recent months (salary vs expenses)**")
        for row in by_month[-4:]:
            lines.append(
                f"- {row.get('month', '?')}: income {_format_inr(float(row.get('salary') or 0))}, "
                f"expenses {_format_inr(float(row.get('expenses') or 0))}, "
                f"savings {_format_inr(float(row.get('savings') or 0))}"
            )
    msg_l = (user_message or "").lower()
    if any(k in msg_l for k in ("save more", "reduce spending", "cut expenses", "save money", "increase savings", "how to save", "how can i save")):
        insight = _build_savings_insight(computed)
        if insight:
            lines.append(insight)
    return "\n".join(lines).strip()


def _compute_spending_metrics(db: Session, user: User) -> Dict[str, Any]:
    txs = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .order_by(Transaction.date.asc(), Transaction.id.asc())
        .all()
    )
    cy = canonical_year_month(txs)
    if not cy:
        return {
            "headline_month": None,
            "total_spend": 0.0,
            "category_totals": {},
            "top_category": None,
            "subscriptions": [],
        }
    year, month = cy
    comp = compute_spending(txs, [(year, month)])
    month_key = f"{year:04d}-{month:02d}"
    mon = comp["monthly"].get(month_key, {})
    category_totals: Dict[str, float] = dict(mon.get("by_category") or {})
    total_spend = float(mon.get("total_debit") or 0.0)
    top_category = None
    if category_totals:
        top_category = max(category_totals.keys(), key=lambda c: category_totals[c])

    month_txs = transactions_in_month(txs, year, month)
    debits = [tx for tx in month_txs if (tx.type or "").lower() == "debit"]
    merchant_counts: Dict[str, int] = defaultdict(int)
    merchant_amounts: Dict[str, float] = defaultdict(float)
    for tx in debits:
        amt = abs(float(tx.amount or 0.0))
        mkey = normalize_merchant(tx.description)
        merchant_counts[mkey] += 1
        merchant_amounts[mkey] += amt
    subscriptions: List[Dict[str, Any]] = []
    for mkey, count in merchant_counts.items():
        if count < 2:
            continue
        label = mkey if mkey != "unknown" else "Unknown merchant"
        subscriptions.append(
            {
                "merchant_key": mkey,
                "label": label[:80],
                "transactions": count,
                "total": round(merchant_amounts[mkey], 2),
            }
        )
    return {
        "headline_month": month_key,
        "total_spend": total_spend,
        "category_totals": category_totals,
        "top_category": top_category,
        "subscriptions": subscriptions,
    }


def _spending_narrative(user_message: str, computed: Dict[str, Any]) -> str:
    msg_l = (user_message or "").lower()
    windows = computed.get("windows") or []
    monthly = computed.get("monthly") or {}
    if not windows:
        return ""

    if len(windows) == 2:
        first = monthly.get(windows[0]) or {}
        second = monthly.get(windows[1]) or {}
        t1 = float(first.get("total_debit") or 0.0)
        t2 = float(second.get("total_debit") or 0.0)
        if t2 > t1:
            return f"Your spending increased in {windows[1]} compared to {windows[0]}."
        if t2 < t1:
            return f"Your spending decreased in {windows[1]} compared to {windows[0]}."
        return f"Your overall spending stayed flat between {windows[0]} and {windows[1]}."

    wk = windows[0]
    mon = monthly.get(wk) or {}
    by_cat = mon.get("by_category") or {}
    top_category = None
    if by_cat:
        top_category = max(by_cat.keys(), key=lambda c: by_cat[c])

    if "swiggy" in msg_l:
        return f"You spent {_format_inr(float(computed.get('swiggy_total') or 0.0))} on Swiggy in {wk}."
    if "zomato" in msg_l:
        return f"You spent {_format_inr(float(computed.get('zomato_total') or 0.0))} on Zomato in {wk}."
    if top_category and (
        float(mon.get("swiggy_total") or 0.0) > 0 or float(mon.get("zomato_total") or 0.0) > 0
    ):
        return (
            f"Your largest spend category in {wk} is {top_category}, with food delivery "
            "contributing materially to that total."
        )
    if top_category:
        return f"Your largest spend category in {wk} is {top_category}."
    return f"Your spending summary for {wk} is based on the transactions in your bank statement."


def _build_spending_answer(user_message: str, computed: Dict[str, Any]) -> str:
    msg_l = (user_message or "").lower()
    lines: List[str] = []
    windows = computed.get("windows") or []
    for wk in windows:
        mon = (computed.get("monthly") or {}).get(wk) or {}
        lines.append(f"**{wk}**")
        lines.append(f"- Total debits: {_format_inr(float(mon.get('total_debit') or 0.0))}")
        by_cat = mon.get("by_category") or {}
        if by_cat:
            top_c = max(by_cat.keys(), key=lambda c: by_cat[c])
            lines.append(f"- Top category: **{top_c}** ({_format_inr(float(by_cat[top_c]))})")
        if float(mon.get("swiggy_total") or 0.0) > 0:
            lines.append(f"- Swiggy: {_format_inr(float(mon['swiggy_total']))}")
        if float(mon.get("zomato_total") or 0.0) > 0:
            lines.append(f"- Zomato: {_format_inr(float(mon['zomato_total']))}")
        lines.append("")

    if "swiggy" in msg_l:
        lines.append(
            f"**Swiggy (selected period):** {_format_inr(float(computed.get('swiggy_total') or 0.0))}"
        )
    if "zomato" in msg_l:
        lines.append(
            f"**Zomato (selected period):** {_format_inr(float(computed.get('zomato_total') or 0.0))}"
        )

    if len(windows) == 2:
        m1, m2 = windows[0], windows[1]
        t1 = float(((computed.get("monthly") or {}).get(m1) or {}).get("total_debit") or 0.0)
        t2 = float(((computed.get("monthly") or {}).get(m2) or {}).get("total_debit") or 0.0)
        diff = t2 - t1
        trend = "increase" if diff > 0 else "decrease" if diff < 0 else "flat"
        lines.append(
            f"**Compare {m1} → {m2}:** {_format_inr(t1)} vs {_format_inr(t2)} "
            f"({trend}, {_format_inr(abs(diff))} difference)."
        )

    narrative = _spending_narrative(user_message, computed)
    if narrative:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(narrative)

    msg_l = (user_message or "").lower()
    if any(k in msg_l for k in ("where is my money", "money going", "where did i spend", "where am i spending")):
        if windows:
            wk = windows[-1]
            mon = (computed.get("monthly") or {}).get(wk) or {}
            by_cat = mon.get("by_category") or {}
            lines.append("")
            if by_cat:
                top_c = max(by_cat.keys(), key=lambda c: by_cat[c])
                top_amt = by_cat[top_c]
                total = float(mon.get("total_debit") or 1.0)
                pct = round((top_amt / total) * 100) if total > 0 else 0
                lines.append(
                    f"**Insight:** {pct}% of your spending in {wk} went to **{top_c}** — "
                    "that's your biggest lever if you want to cut back."
                )
            else:
                lines.append(
                    f"**Insight:** Based on your recent transactions in {wk}, "
                    "upload a full statement to see a complete category breakdown."
                )

    if not lines:
        return INSUFFICIENT_DATA
    return "\n".join(lines).strip()


def _card_label(card: Card) -> str:
    return f"{card.bank_name} *{card.last4_digits}"


def _merchant_bucket(description: Optional[str]) -> Optional[str]:
    d = (description or "").lower()
    if "uber" in d: return "uber"
    if "swiggy" in d: return "swiggy"
    if "zomato" in d: return "zomato"
    if "amazon" in d or "amzn" in d: return "amazon"
    return None


def _is_hdfc(card: Card) -> bool:
    return "hdfc" in (card.bank_name or "").lower()


def _is_icici_amazon_card(card: Card) -> bool:
    b = (card.bank_name or "").lower()
    t = (card.card_type or "").lower()
    return "icici" in b and "amazon" in (t + b)


def _analyze_card_missed_savings(db: Session, user: User) -> Dict[str, Any]:
    cards = {c.id: c for c in db.query(Card).filter(Card.user_id == user.id).all()}
    txs = db.query(Transaction).filter(Transaction.user_id == user.id).all()
    cy = canonical_year_month(txs)
    if not cy: return {"optimal": True, "suggestions": []}
    year, month = cy
    month_txs = transactions_in_month(txs, year, month)
    suggestions = []
    for tx in month_txs:
        if (tx.type or "").lower() != "debit" or not tx.card_id: continue
        card = cards.get(tx.card_id)
        if not card: continue
        amt = abs(float(tx.amount or 0.0))
        bucket = _merchant_bucket(tx.description)
        if bucket in ("swiggy", "zomato") and not _is_hdfc(card):
            suggestions.append({"merchant": bucket.title(), "better_card": "HDFC Swiggy (10%)", "savings": _format_inr(amt * 0.1)})
        elif bucket == "amazon" and not _is_icici_amazon_card(card):
            suggestions.append({"merchant": "Amazon", "better_card": "ICICI Amazon (5%)", "savings": _format_inr(amt * 0.05)})
    return {"optimal": len(suggestions) == 0, "suggestions": suggestions[:3]}


def _append_trace(state: AstraAgentState, entry: AgentTraceEntry) -> List[AgentTraceEntry]:
    # Parallel nodes will have their traces merged by the operator.add reducer
    return [entry]


def _build_unified_context(
    user_query: str,
    data: Dict[str, Any],
    computed_metrics: Dict[str, Any],
    insights: Dict[str, Any],
    derived: Dict[str, Any] = None,
) -> Dict[str, Any]:
    return {
        "user_query": user_query.strip(),
        "data": data,
        "computed_metrics": computed_metrics,
        "insights": insights,
        "derived": derived or {},
    }


def _compute_derived_signals(db: Session, user: User) -> Dict[str, Any]:
    credit_data = get_credit_data(db, user)
    spending_metrics = _compute_spending_metrics(db, user)
    txs = db.query(Transaction).filter(Transaction.user_id == user.id).all()
    insurance_keywords = ["lic", "insurance", "premium", "policy", "mediclaim", "hdfc ergo", "tata aig"]
    detected_insurance_txs = []
    for tx in txs:
        desc = (tx.description or "").lower()
        if any(kw in desc for kw in insurance_keywords):
            detected_insurance_txs.append({"date": str(tx.date), "desc": tx.description, "amount": float(tx.amount or 0)})
    return {
        "credit_utilization": credit_data.get("credit_utilization_pct"),
        "has_low_cibil": (credit_data.get("credit_score") or 900) < 700,
        "detected_insurance_patterns": detected_insurance_txs,
        "is_insured": len(detected_insurance_txs) > 0,
        "total_spend_month": spending_metrics.get("total_spend"),
        "top_category": spending_metrics.get("top_category"),
    }


def _render_prompt(template: str, user_message: str, input_json: Dict[str, Any]) -> str:
    return (
        template.replace("{{USER_MESSAGE}}", user_message.strip())
        .replace("{{INPUT_JSON}}", json.dumps(input_json, indent=2, ensure_ascii=False))
    )


def supervisor_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    raw_message = state.get("message", "") or ""
    message = raw_message.lower()
    agents = set()
    spending_hit = _is_spending_query(raw_message)
    budget_hit = _is_budget_query(raw_message)

    if any(kw in message for kw in ["insurance", "policy", "premium", "lic", "claim"]):
        agents.add("claims_agent")
    if spending_hit:
        agents.add("spending_agent")
    if budget_hit:
        agents.add("budget_agent")

    if _has_narrow_wealth_intent(raw_message) or (
        not spending_hit
        and not budget_hit
        and any(kw in message for kw in ["cibil", "credit", "score", "loan", "card"])
    ):
        agents.add("wealth_agent")

    if _is_teller_query(raw_message) and not spending_hit:
        agents.add("teller_agent")
    if any(kw in message for kw in ["fraud", "scam", "suspicious", "otp"]):
        agents.add("scam_agent")

    if (
        ("spending_agent" in agents or "budget_agent" in agents)
        and not _has_narrow_wealth_intent(raw_message)
    ):
        agents.discard("wealth_agent")

    prompt = _render_prompt(SUPERVISOR_ROUTER_PROMPT, state.get("message", ""), {})
    try:
        raw = call_llm(prompt, temperature=0.0)
        parsed = extract_json_object(raw) or {}
        for a in (parsed.get("agents") or []):
            name = a.lower() if a else ""
            if name in VALID_AGENTS:
                agents.add(name)
    except Exception:
        pass

    if (
        ("spending_agent" in agents or "budget_agent" in agents)
        and not _has_narrow_wealth_intent(raw_message)
    ):
        agents.discard("wealth_agent")

    if not agents:
        agents.add("default_agent")
    agents_to_run = list(agents)
    logger.info("supervisor.agents_to_run=%s user_id=%s", agents_to_run, getattr(user, "id", None))
    derived = _compute_derived_signals(db, user)

    return {
        "agents_to_run": agents_to_run,
        "agent_trace": _append_trace(state, {"step": "supervisor", "agent": "supervisor", "detail": f"parallel_intents: {agents_to_run}"}),
        "derived_data": derived,
        "agent_responses": {}, 
    }


def budget_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    logger.info("multi_agent.node budget_agent user_id=%s", getattr(user, "id", None))
    user_message = state.get("message", "")
    txs = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .order_by(Transaction.date.asc(), Transaction.id.asc())
        .all()
    )
    computed = compute_monthly_budget(txs)
    if not computed.get("transactions_found"):
        structured = {
            "answer": INSUFFICIENT_DATA,
            "deterministic": True,
            "confidence": 0.4,
            "computed": computed,
        }
    else:
        structured = {
            "answer": _build_budget_answer(computed, user_message),
            "deterministic": True,
            "confidence": 1.0,
            "computed": computed,
        }
    return {
        "agent_responses": {"budget_agent": structured},
        "agent_trace": _append_trace(
            state,
            {"step": "budget_agent", "agent": "budget_agent", "detail": "deterministic_budget"},
        ),
    }


def spending_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    logger.info("multi_agent.node spending_agent user_id=%s", getattr(user, "id", None))
    user_message = state.get("message", "")
    txs = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .order_by(Transaction.date.asc(), Transaction.id.asc())
        .all()
    )
    windows = parse_query_month_window(user_message, txs)
    if not txs or not windows:
        structured = {
            "answer": INSUFFICIENT_DATA,
            "deterministic": True,
            "confidence": 0.4,
            "computed": {},
        }
    else:
        computed = compute_spending(txs, windows)
        structured = {
            "answer": _build_spending_answer(user_message, computed),
            "deterministic": True,
            "confidence": 1.0,
            "computed": computed,
        }
    return {
        "agent_responses": {"spending_agent": structured},
        "agent_trace": _append_trace(
            state,
            {"step": "spending_agent", "agent": "spending_agent", "detail": "deterministic_spend"},
        ),
    }


def wealth_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    logger.info("multi_agent.node wealth_agent user_id=%s", getattr(user, "id", None))
    user_message = state.get("message", "")
    derived = state.get("derived_data") or {}
    payload = {
        "credit": get_credit_data(db, user),
        "cards": {**get_card_data(db, user), "missed_savings": _analyze_card_missed_savings(db, user)}
    }
    prompt = _render_prompt(WEALTH_AGENT_PROMPT, user_message, {"payload": payload, "derived": derived})
    raw = call_llm(prompt)
    structured = extract_json_object(raw) or {"answer": raw, "confidence": 0.7}
    return {
        "agent_responses": {"wealth_agent": structured},
        "agent_trace": _append_trace(state, {"step": "wealth_agent", "agent": "wealth_agent", "detail": "parallel_wealth_analysis"})
    }


def teller_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    logger.info("multi_agent.node teller_agent user_id=%s", getattr(user, "id", None))
    user_message = state.get("message", "")
    payload = {"summary": tool_get_financial_summary(db, user), "recent": tool_get_recent_transactions(db, user, 10)}
    prompt = _render_prompt(TELLER_AGENT_PROMPT, user_message, payload)
    raw = call_llm(prompt)
    structured = extract_json_object(raw) or {"answer": raw, "confidence": 0.9}
    return {
        "agent_responses": {"teller_agent": structured},
        "agent_trace": _append_trace(state, {"step": "teller_agent", "agent": "teller_agent", "detail": "parallel_teller_analysis"})
    }


def claims_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    logger.info("multi_agent.node claims_agent user_id=%s", getattr(user, "id", None))
    user_message = state.get("message", "")
    derived = state.get("derived_data") or {}
    prompt = _render_prompt(CLAIMS_AGENT_PROMPT, user_message, {"derived": derived})
    raw = call_llm(prompt)
    structured = extract_json_object(raw) or {"answer": raw, "confidence": 0.6}
    return {
        "agent_responses": {"claims_agent": structured},
        "agent_trace": _append_trace(state, {"step": "claims_agent", "agent": "claims_agent", "detail": "parallel_claims_analysis"})
    }


def scam_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    logger.info("multi_agent.node scam_agent user_id=%s", getattr(user, "id", None))
    user_message = state.get("message", "")
    prompt = _render_prompt(SCAM_AGENT_PROMPT, user_message, {"signals": get_fraud_signals(db, user, user_message)})
    raw = call_llm(prompt)
    structured = extract_json_object(raw) or {"answer": raw, "confidence": 0.8}
    return {
        "agent_responses": {"scam_agent": structured},
        "agent_trace": _append_trace(state, {"step": "scam_agent", "agent": "scam_agent", "detail": "parallel_scam_analysis"})
    }


def synthesizer_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    logger.info("multi_agent.node synthesizer user_id=%s", getattr(user, "id", None))
    logger.info(f"[TEST] Query: {state.get('message')}")
    logger.info(f"[TEST] Agents selected: {state.get('agents_to_run')}")
    logger.info(f"[TEST] Agent responses: {state.get('agent_responses')}")

    user_message = state.get("message", "")
    responses = state.get("agent_responses") or {}
    use_llm_rewrite = os.getenv("USE_LLM_REWRITE", "true").strip().lower() != "false"

    _AGENT_LABELS: Dict[str, str] = {
        "spending_agent": "Spending",
        "budget_agent": "Budget",
        "wealth_agent": "Card & Credit",
        "teller_agent": "Account",
        "scam_agent": "Fraud & Security",
        "claims_agent": "Insurance",
        "default_agent": "General",
    }

    # Build merged deterministic text and collect computed JSON from all agents.
    raw_answer_parts: List[str] = []
    computed_payload: Dict[str, Any] = {}
    for agent, data in responses.items():
        if not data:
            continue
        ans = (data.get("answer") if isinstance(data, dict) else str(data) or "").strip()
        if ans:
            label = _AGENT_LABELS.get(agent, agent.replace("_", " ").title())
            raw_answer_parts.append(f"[{label}]\n{ans}")
        if isinstance(data, dict) and data.get("computed"):
            computed_payload[agent] = data["computed"]

    raw_answer_text = "\n\n".join(raw_answer_parts).strip() or INSUFFICIENT_DATA

    # Short-circuit if toggle is off or there is nothing to rewrite.
    if not use_llm_rewrite or not raw_answer_parts:
        detail = "fast_path_env_disabled" if not use_llm_rewrite else "no_agent_responses"
        logger.info(f"[TEST] Final answer: {raw_answer_text}")
        return {
            "final_answer": raw_answer_text,
            "agent_trace": _append_trace(
                state,
                {"step": "synthesizer", "agent": "supervisor", "detail": detail},
            ),
        }

    # Render the rewrite prompt with authoritative computed data.
    prompt = (
        LLM_REWRITE_PROMPT
        .replace("{{USER_MESSAGE}}", user_message)
        .replace("{{COMPUTED_JSON}}", json.dumps(computed_payload, ensure_ascii=False, indent=2))
        .replace("{{RAW_ANSWER}}", raw_answer_text)
    )

    try:
        rewritten = call_llm(prompt, temperature=0.2)
    except Exception as exc:
        logger.warning("synthesizer LLM rewrite failed, falling back to deterministic: %s", exc)
        rewritten = ""

    rewritten_clean = rewritten.strip()
    if len(rewritten_clean) >= 10:
        final_answer = rewritten_clean
        trace_detail = "llm_rewrite"
    else:
        final_answer = raw_answer_text
        trace_detail = "llm_rewrite_fallback"

    logger.info(f"[TEST] Final answer: {final_answer}")
    return {
        "final_answer": final_answer,
        "agent_trace": _append_trace(
            state,
            {"step": "synthesizer", "agent": "supervisor", "detail": trace_detail},
        ),
    }


def default_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    logger.info("multi_agent.node default_agent user_id=%s", getattr(user, "id", None))
    logger.info(f"[TEST] Query: {state.get('message')}")
    logger.info(f"[TEST] Agents selected: {state.get('agents_to_run')}")
    logger.info(f"[TEST] Agent responses: {state.get('agent_responses')}")
    final_answer = "I'm sorry, I couldn't find a specialized agent to handle your request. Could you please clarify your financial question?"
    logger.info(f"[TEST] Final answer: {final_answer}")
    return {
        "final_answer": final_answer,
        "agent_trace": _append_trace(state, {"step": "default_agent", "agent": "default_agent", "detail": "unsupported_query"})
    }
