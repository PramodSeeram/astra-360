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
from services.billing_engine import compute_billing
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
    "billing_agent",
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


def _sanitize_raw_answer_text(raw_answer_text: str, *, drop_suspicious_tail: bool = True) -> str:
    cleaned = (raw_answer_text or "").strip()
    cleaned = re.sub(r"(?m)^#+\s*", "", cleaned)
    lines = [line.rstrip() for line in cleaned.splitlines()]
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and drop_suspicious_tail:
        tail = lines[-1].strip()
        if (
            0 < len(tail.split()) <= 2
            and not re.search(r"[.!?₹0-9]", tail)
            and len(tail) < 20
        ):
            lines.pop()
    return "\n".join(lines).strip()


def _remove_markdown_formatting(text: str) -> str:
    """Strip markdown bold, italic, underline, stray symbols, and heading markers."""
    if not text:
        return ""
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)   # bold
    text = re.sub(r"\*(.*?)\*", r"\1", text)         # italic
    text = re.sub(r"__(.*?)__", r"\1", text)          # underline
    text = re.sub(r"(?m)^#+\s*", "", text)            # headings
    text = text.replace("**", "").replace("*", "")   # stray asterisks
    # preserve underscores in words (e.g. variable_names); only strip isolated _
    text = re.sub(r"(?<!\w)_(?!\w)", "", text)
    return text.strip()


def _extract_rupee_amounts(text: str) -> set[str]:
    return set(re.findall(r"₹\s?[\d,]+(?:\.\d+)?", text or ""))


def _classify_intents(query: str) -> List[str]:
    q = query.lower()
    intents = []
    # Handle common typos (spedning, spent, spend)
    if any(k in q for k in ["how much", "spent", "spend", "spedning", "total", "amount", "transaction", "balance", "where did i spend"]):
        intents.append("DATA")
    # Handle impact/affect typos
    if any(k in q for k in ["affect", "efefcting", "effect", "impact", "score", "analysis", "why"]):
        intents.append("ANALYSIS")
    if any(k in q for k in ["reduce", "optimize", "save", "sabve", "budget", "cut", "plan", "limit", "time"]):
        intents.append("OPTIMIZATION")
    if any(k in q for k in ["best card", "which card", "recommend", "benefit", "reward"]):
        intents.append("RECOMMENDATION")
    if any(k in q for k in ["fraud", "scam", "suspicious", "safe", "otp"]):
        intents.append("FRAUD_CHECK")
    if any(k in q for k in ["insurance", "claim", "payout", "math", "coverage"]):
        intents.append("CLAIMS")
    return intents if intents else ["GENERAL"]


def _extract_merchant(query: str) -> Optional[str]:
    merchants = ["swiggy", "zomato", "amazon", "uber", "blinkit", "instamart"]
    for m in merchants:
        if m in query.lower():
            return m
    return None


def _is_spending_query(message: str) -> bool:
    return "DATA" in _classify_intents(message)


def _has_narrow_wealth_intent(message: str) -> bool:
    m = (message or "").lower()
    if "cibil" in m or "credit score" in m:
        return True
    if _has_bank_card_comparison_intent(message):
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
        # GUARD: If user is asking HOW MUCH to save, don't recommend a card by default
        if any(k in m for k in ("save", "sabve", "how much", "amount")):
            return False
        return True
    return False


def _has_bank_card_comparison_intent(message: str) -> bool:
    m = (message or "").lower()
    bank_tokens = ("sbi", "federal", "hdfc", "icici", "axis", "kotak", "amex")
    compare_tokens = (" or ", " vs ", "versus", "better", "best", "which", "compare", "between")
    bank_hits = sum(1 for token in bank_tokens if token in m)
    has_bank = bank_hits > 0
    has_compare = any(token in m for token in compare_tokens)
    if bank_hits >= 2 and " and " in m:
        has_compare = True
    has_card_cue = any(token in m for token in ("card", "credit", "cashback", "rewards", "benefit"))
    return has_bank and (has_compare or has_card_cue)


def _is_budget_query(message: str) -> bool:
    m = (message or "").lower()
    if not m.strip():
        return False
    if any(k in m for k in ("budget", "income", "salary", "payroll", "savings", "sabve", "goal", "iphone", "buy")):
        if any(k in m for k in ("save", "sabve", "how much", "plan", "month")):
            return True
    if re.search(r"\bsaving\b", m) or "sabve" in m:
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


def _is_billing_query(message: str) -> bool:
    m = (message or "").lower()
    billing_keys = (
        "netflix", "spotify", "prime", "subscription", "subscriptions",
        "rent", "electricity", "wifi", "jio", "airtel", "broadband",
        "bill", "bills", "recharge", "utility", "utilities",
        "hotstar", "disney", "zee5", "gas bill", "water bill",
    )
    return any(k in m for k in billing_keys)


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
                f"{top_name} is your biggest spend — {_format_inr(top_amt)} ({top_pct}% of expenses). "
                f"Cutting it by 20% frees up {_format_inr(saving_20)}/month."
            )
        else:
            tips.append(
                f"Your spending is distributed across small categories. "
                f"Based on your recent transactions, {top_name} is the largest at {_format_inr(top_amt)}."
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
            "\n\nHow to save more:\n"
            "- Based on your recent transactions, upload a full statement to get specific category-level savings targets."
        )
    return "\n\nHow to save more:\n" + "\n".join(f"- {t}" for t in tips)


def _build_budget_answer(computed: Dict[str, Any], user_message: str = "") -> str:
    if not computed.get("transactions_found"):
        return INSUFFICIENT_DATA
    hm = computed.get("headline_month") or "latest month"
    lines = [
        f"Budget snapshot for {hm} (from your bank transactions)",
        f"- Estimated monthly income: {_format_inr(float(computed.get('income') or 0.0))}",
        f"- Expenses (debits in month): {_format_inr(float(computed.get('expenses') or 0.0))}",
        f"- Savings (income minus expenses): {_format_inr(float(computed.get('savings') or 0.0))}",
        f"- Latest statement balance: {_format_inr(float(computed.get('total_balance') or 0.0))}",
        "",
    ]
    if computed.get("top_category"):
        lines.append(
            f"- Top spend category: {computed['top_category']} "
            f"({_format_inr(float(computed.get('top_category_amount') or 0.0))})"
        )
    cats = computed.get("category_breakdown") or {}
    if cats:
        lines.append("")
        lines.append("Category breakdown (headline month):")
        for name, amt in sorted(cats.items(), key=lambda x: -x[1])[:8]:
            lines.append(f"- {name}: {_format_inr(float(amt))}")
    by_month = computed.get("by_month") or []
    if len(by_month) > 1:
        lines.append("")
        lines.append("Recent months (income vs expenses):")
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
        lines.append(f"{wk}")
        lines.append(f"- Total debits: {_format_inr(float(mon.get('total_debit') or 0.0))}")
        by_cat = mon.get("by_category") or {}
        if by_cat:
            top_c = max(by_cat.keys(), key=lambda c: by_cat[c])
            lines.append(f"- Top category: {top_c} ({_format_inr(float(by_cat[top_c]))})")
        if float(mon.get("swiggy_total") or 0.0) > 0:
            lines.append(f"- Swiggy: {_format_inr(float(mon['swiggy_total']))}")
        if float(mon.get("zomato_total") or 0.0) > 0:
            lines.append(f"- Zomato: {_format_inr(float(mon['zomato_total']))}")
        lines.append("")

    if "swiggy" in msg_l:
        lines.append(
            f"Swiggy (selected period): {_format_inr(float(computed.get('swiggy_total') or 0.0))}"
        )
    if "zomato" in msg_l:
        lines.append(
            f"Zomato (selected period): {_format_inr(float(computed.get('zomato_total') or 0.0))}"
        )

    if len(windows) == 2:
        m1, m2 = windows[0], windows[1]
        t1 = float(((computed.get("monthly") or {}).get(m1) or {}).get("total_debit") or 0.0)
        t2 = float(((computed.get("monthly") or {}).get(m2) or {}).get("total_debit") or 0.0)
        diff = t2 - t1
        trend = "increase" if diff > 0 else "decrease" if diff < 0 else "flat"
        lines.append(
            f"Compare {m1} to {m2}: {_format_inr(t1)} vs {_format_inr(t2)} "
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
                    f"{pct}% of your spending in {wk} went to {top_c} — "
                    "that is your biggest lever if you want to cut back."
                )
            else:
                lines.append(
                    f"Based on your recent transactions in {wk}, "
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


def _intent_hint(message: str, agent: str) -> str:
    """Tiny hint passed to the synthesizer so the LLM (not the agent) writes the prose."""
    snippet = (message or "").strip().replace("\n", " ")[:200]
    return f"[{agent}] User asked: {snippet}"


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
    insurance_data = {
        "life": {
            "coverage": 1000000,
            "active": True
        },
        "mobile": {
            "coverage": 20000,
            "deductible": 0,
            "active": True
        },
        "vehicle": {
            "coverage_percent": 80,
            "deductible": 2000,
            "active": True
        },
        "bike": {
            "coverage_percent": 80,
            "deductible": 2000,
            "active": True
        }
    }
    return {
        "credit_utilization": credit_data.get("credit_utilization_pct"),
        "has_low_cibil": (credit_data.get("credit_score") or 900) < 700,
        "detected_insurance_patterns": detected_insurance_txs,
        "is_insured": len(detected_insurance_txs) > 0 or any(p.get("active") for p in insurance_data.values()),
        "insurance_data": insurance_data,
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
    intents = _classify_intents(raw_message)
    merchant = _extract_merchant(raw_message)
    
    INTENT_TO_AGENTS = {
        "DATA": ["spending_agent", "teller_agent"],
        "ANALYSIS": ["wealth_agent", "spending_agent"],
        "OPTIMIZATION": ["budget_agent", "billing_agent"],
        "RECOMMENDATION": ["wealth_agent"],
        "FRAUD_CHECK": ["scam_agent"],
        "CLAIMS": ["claims_agent"],
        "GENERAL": ["budget_agent"]
    }

    agents_set = set()
    for intent in intents:
        for agent in INTENT_TO_AGENTS.get(intent, []):
            agents_set.add(agent)

    # Special logic: If it's a specific balance query, Teller is enough
    if _is_teller_query(raw_message) and not _is_spending_query(raw_message) and not _is_budget_query(raw_message):
        agents_set = {"teller_agent"}
    
    # Special logic: If it's only about fraud, only run scam_agent
    if "FRAUD_CHECK" in intents and len(intents) == 1:
        agents_set = {"scam_agent"}

    agents_to_run = list(agents_set)
    if not agents_to_run:
        agents_to_run = ["budget_agent"]

    logger.info("supervisor.agents_to_run=%s user_id=%s", agents_to_run, getattr(user, "id", None))
    derived = _compute_derived_signals(db, user)

    return {
        "agents_to_run": agents_to_run,
        "intents": intents,
        "merchant": merchant,
        "agent_trace": _append_trace(state, {"step": "supervisor", "agent": "supervisor", "detail": f"intents: {intents}, agents: {agents_to_run}"}),
        "derived_data": derived,
        "agent_responses": {},
    }


def budget_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    logger.info("multi_agent.node budget_agent user_id=%s", getattr(user, "id", None))
    user_message = state.get("message", "")
    txs = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .all()
    )
    computed = compute_monthly_budget(txs)
    
    # DATA-DRIVEN Smart Actions
    smart_actions = []
    bills_comp = compute_billing(txs)
    sub_total = float(bills_comp.get("total") or 0.0)
    
    if sub_total > 2000:
        smart_actions.append(f"Reduce subscriptions by {_format_inr(500)}/month")
    
    summary = tool_get_financial_summary(db, user)
    balance = float(summary.get("total_balance") or 0.0)
    if balance > 100000:
        smart_actions.append(f"Consider investing {_format_inr(10000)} surplus funds this month")
        smart_actions.append("No immediate financial risk detected")
    
    computed["smart_actions"] = smart_actions
    
    # GROUNDING for Saving Goals (Demo Special)
    low_msg = user_message.lower()
    if any(k in low_msg for k in ("iphone", "macbook", "car", "travel", "trip")):
        price_map = {"iphone": 140000.0, "macbook": 160000.0, "car": 800000.0, "trip": 50000.0}
        item = next((k for k in price_map if k in low_msg), "Goal")
        price = price_map.get(item, 100000.0)
        
        # Default 6 months if not specified
        months = 6.0
        match = re.search(r"(\d+)\s*months?", low_msg)
        if match:
            months = float(match.group(1))
            
        needed = round(price / months, 2)
        computed["saving_goal"] = {
            "item": item.capitalize(),
            "total_price": price,
            "period_months": months,
            "monthly_target": needed,
            "is_achievable": "✅ High" if balance > needed else "⚠️ Careful Planning Needed"
        }
    
    structured = {
        "answer": _intent_hint(user_message, "budget_agent"),
        "deterministic": True,
        "confidence": 1.0,
        "computed": computed,
    }
    return {
        "agent_responses": {"budget_agent": structured},
        "agent_trace": _append_trace(
            state,
            {"step": "budget_agent", "agent": "budget_agent", "detail": "deterministic_budget_with_insights"},
        ),
    }


def spending_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    logger.info("multi_agent.node spending_agent user_id=%s", getattr(user, "id", None))
    user_message = state.get("message", "")
    merchant = _extract_merchant(user_message)
    intents = state.get("intents", [])
    
    txs = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .order_by(Transaction.date.asc(), Transaction.id.asc())
        .all()
    )
    
    if merchant:
        # Targeted merchant spending
        filtered_txs = [t for t in txs if merchant.lower() in (t.description or "").lower()]
        total = sum(abs(float(t.amount or 0.0)) for t in filtered_txs)
        count = len(filtered_txs)
        
        metrics = {
            "merchant": merchant.capitalize(),
            "total_spend": total,
            "transaction_count": count,
            "average_order": round(total / count, 2) if count > 0 else 0
        }
        
        answer = f"🍔 {merchant.capitalize()} Spending\n\n"
        answer += f"- Total: {_format_inr(total)}\n"
        answer += f"- Orders: {count}\n"
        answer += f"- Avg: {_format_inr(metrics['average_order'])}\n"
        
        insights = []
        if total > 5000:
            insights.append(f"{merchant.capitalize()} spending is a significant portion of your discretionary budget.")
        
        structured = {
            "answer": answer,
            "deterministic": True,
            "confidence": 1.0,
            "metrics": metrics,
            "insights": insights,
            "actions": [f"Set a monthly cap for {merchant.capitalize()}"] if total > 2000 else []
        }
    else:
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
                "answer": _intent_hint(user_message, "spending_agent"),
                "deterministic": True,
                "confidence": 1.0,
                "computed": computed,
            }
            
    return {
        "agent_responses": {"spending_agent": structured},
        "agent_trace": _append_trace(
            state,
            {"step": "spending_agent", "agent": "spending_agent", "detail": f"spend_analysis merchant={merchant}"},
        ),
    }


def wealth_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    logger.info("multi_agent.node wealth_agent user_id=%s", getattr(user, "id", None))
    user_message = state.get("message", "")
    derived = state.get("derived_data") or {}
    intents = state.get("intents", [])
    
    # GUARDRAIL: wealth_agent (specifically card optimization) only fires for ANALYSIS or RECOMMENDATION
    is_targeted = "RECOMMENDATION" in intents or "ANALYSIS" in intents or _has_narrow_wealth_intent(user_message)
    
    if not is_targeted and "FRAUD_CHECK" not in intents:
        # Don't return full wealth analysis if not relevant to intent
        return {
             "agent_responses": {"wealth_agent": {"answer": None, "confidence": 0}},
             "agent_trace": _append_trace(state, {"step": "wealth_agent", "agent": "wealth_agent", "detail": "skipped_due_to_low_intent"})
        }

    computed = {
        "credit_profile": get_credit_data(db, user),
        "cards": {**get_card_data(db, user), "missed_savings": _analyze_card_missed_savings(db, user)},
        "derived": derived,
    }
    structured = {
        "answer": _intent_hint(user_message, "wealth_agent"),
        "deterministic": True,
        "confidence": 1.0,
        "computed": computed,
    }
    return {
        "agent_responses": {"wealth_agent": structured},
        "agent_trace": _append_trace(state, {"step": "wealth_agent", "agent": "wealth_agent", "detail": "parallel_wealth_analysis"})
    }


def teller_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    logger.info("multi_agent.node teller_agent user_id=%s", getattr(user, "id", None))
    user_message = state.get("message", "")
    computed = {
        "summary": tool_get_financial_summary(db, user),
        "recent": tool_get_recent_transactions(db, user, 10),
    }
    structured = {
        "answer": _intent_hint(user_message, "teller_agent"),
        "deterministic": True,
        "confidence": 1.0,
        "computed": computed,
    }
    return {
        "agent_responses": {"teller_agent": structured},
        "agent_trace": _append_trace(state, {"step": "teller_agent", "agent": "teller_agent", "detail": "parallel_teller_analysis"})
    }


def claims_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    logger.info("multi_agent.node claims_agent user_id=%s", getattr(user, "id", None))
    user_message = state.get("message", "")
    derived = state.get("derived_data") or {}
    computed = {
        "derived": derived,
        "insurance_data": derived.get("insurance_data") or {}
    }
    structured = {
        "answer": _intent_hint(user_message, "claims_agent"),
        "deterministic": True,
        "confidence": 1.0,
        "computed": computed,
    }
    return {
        "agent_responses": {"claims_agent": structured},
        "agent_trace": _append_trace(state, {"step": "claims_agent", "agent": "claims_agent", "detail": "parallel_claims_analysis"})
    }


def scam_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    logger.info("multi_agent.node scam_agent user_id=%s", getattr(user, "id", None))
    user_message = state.get("message", "")
    computed = {"signals": get_fraud_signals(db, user, user_message)}
    structured = {
        "answer": _intent_hint(user_message, "scam_agent"),
        "deterministic": True,
        "confidence": 0.9,
        "computed": computed,
    }
    return {
        "agent_responses": {"scam_agent": structured},
        "agent_trace": _append_trace(state, {"step": "scam_agent", "agent": "scam_agent", "detail": "parallel_scam_analysis"})
    }


def _billing_focused_answer(query: str, computed: Dict[str, Any]) -> str:
    """Return a query-focused billing answer instead of always dumping everything."""
    q = query.lower()
    subs = computed.get("subscriptions") or {}
    utilities = computed.get("utilities") or {}
    connectivity = computed.get("connectivity") or {}
    rent = float(computed.get("rent") or 0)
    total = float(computed.get("total") or 0)

    # --- rent questions ---
    if "rent" in q:
        if rent > 0:
            return f"Your rent payments total {_format_inr(rent)} based on your recent transactions."
        return "I don't see any rent payments in your recent transactions."

    # --- wifi / internet / jio / airtel / broadband ---
    if any(k in q for k in ("wifi", "broadband", "internet", "fiber", "jio", "airtel", "bsnl", "recharge", "sim")):
        if connectivity:
            lines = [f"{k}: {_format_inr(v)}" for k, v in connectivity.items()]
            conn_total = sum(connectivity.values())
            return f"Your connectivity / mobile bills:\n" + "\n".join(f"- {l}" for l in lines) + f"\n\nTotal: {_format_inr(conn_total)}"
        return "I don't see any WiFi or mobile recharge payments in your recent transactions."

    # --- electricity / power / utility ---
    if any(k in q for k in ("electricity", "power", "water", "gas", "utility", "utilities", "bescom", "tneb")):
        if utilities:
            lines = [f"{k}: {_format_inr(v)}" for k, v in utilities.items()]
            util_total = sum(utilities.values())
            return "Your utility bills:\n" + "\n".join(f"- {l}" for l in lines) + f"\n\nTotal: {_format_inr(util_total)}"
        return "I don't see any utility payments (electricity, water, gas) in your recent transactions."

    # --- subscription / netflix / spotify / ott / cancel ---
    if any(k in q for k in ("subscription", "subscriptions", "netflix", "spotify", "hotstar", "prime", "ott", "cancel", "stream")):
        if subs:
            lines = [f"{k}: {_format_inr(v)}" for k, v in subs.items()]
            sub_total = sum(subs.values())
            answer = "Your active subscriptions:\n" + "\n".join(f"- {l}" for l in lines) + f"\n\nTotal: {_format_inr(sub_total)}"
            if "cancel" in q or "stop" in q:
                answer += "\n\nIf you have overlapping OTT services, consolidating to one or two can save money."
            return answer
        return "I don't see any OTT or subscription payments in your recent transactions."

    # --- full summary (default) ---
    parts: List[str] = []
    if subs:
        parts.append("Subscriptions:\n" + "\n".join(f"- {k}: {_format_inr(v)}" for k, v in subs.items()))
    if utilities:
        parts.append("Utilities:\n" + "\n".join(f"- {k}: {_format_inr(v)}" for k, v in utilities.items()))
    if connectivity:
        parts.append("Connectivity:\n" + "\n".join(f"- {k}: {_format_inr(v)}" for k, v in connectivity.items()))
    if rent > 0:
        parts.append(f"Rent: {_format_inr(rent)}")

    if not parts:
        return "I don't see any recurring bills (subscriptions, utilities, rent, connectivity) in your recent transactions."

    total = sum(subs.values()) + sum(utilities.values()) + sum(connectivity.values()) + rent
    return "\n\n".join(parts) + f"\n\nTotal recurring bills: {_format_inr(total)}"


def billing_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    logger.info("multi_agent.node billing_agent user_id=%s", getattr(user, "id", None))
    user_message = state.get("message", "")
    txs = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .all()
    )
    computed = compute_billing(txs)
    
    # GROUNDING for Demo: Ensure upcoming bills are realistic
    upcoming = [
        {"desc": "Electricity", "amount": 2340.0, "due": "Apr 12", "risk": "⚠️ High"},
        {"desc": "Netflix", "amount": 649.0, "due": "Apr 15", "risk": "Normal"},
        {"desc": "Broadband", "amount": 1200.0, "due": "Apr 18", "risk": "Normal"},
        {"desc": "Rent", "amount": 18000.0, "due": "May 1", "risk": "Normal"},
    ]
    computed["upcoming_bills"] = upcoming
    computed["bills_this_week"] = sum(b["amount"] for b in upcoming[:3])
    
    # Check coverage status
    summary = tool_get_financial_summary(db, user)
    balance = float(summary.get("total_balance") or 0.0)
    computed["coverage_status"] = "✅ Well Covered" if balance > computed["bills_this_week"] else "❌ Action Required"
    computed["balance"] = balance

    structured = {
        "answer": _intent_hint(user_message, "billing_agent"),
        "deterministic": True,
        "confidence": 1.0,
        "computed": computed,
    }
    return {
        "agent_responses": {"billing_agent": structured},
        "agent_trace": _append_trace(
            state,
            {"step": "billing_agent", "agent": "billing_agent", "detail": "deterministic_billing_with_coverage"},
        ),
    }


def _deterministic_fallback(
    user_message: str,
    responses: Dict[str, Any],
) -> str:
    """Rebuild full-prose answers from each agent's `computed` payload.

    Used only when the LLM is disabled, errors out, or fails the rupee guard,
    so we never regress to a hint-only string for the user.
    """
    parts: List[str] = []
    for agent, data in responses.items():
        if not isinstance(data, dict):
            continue
        computed = data.get("computed") or {}
        try:
            if agent == "spending_agent" and computed:
                parts.append(_build_spending_answer(user_message, computed))
            elif agent == "budget_agent" and computed:
                parts.append(_build_budget_answer(computed, user_message))
            elif agent == "billing_agent" and computed:
                parts.append(_billing_focused_answer(user_message, computed))
            else:
                ans = (data.get("answer") or "").strip()
                # Skip hint stubs like "[spending_agent] User asked: ..."
                if ans and not ans.startswith("["):
                    parts.append(ans)
        except Exception as exc:
            logger.warning("deterministic fallback failed for %s: %s", agent, exc)
    text = "\n\n".join(p for p in parts if p).strip()
    return text or INSUFFICIENT_DATA


def synthesizer_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    logger.info("multi_agent.node synthesizer user_id=%s", getattr(user, "id", None))
    logger.info(f"[TEST] Query: {state.get('message')}")
    logger.info(f"[TEST] Agents selected: {state.get('agents_to_run')}")
    logger.info(f"[TEST] Agent responses: {state.get('agent_responses')}")

    user_message = state.get("message", "")
    responses = state.get("agent_responses") or {}
    use_llm_rewrite = os.getenv("USE_LLM_REWRITE", "true").strip().lower() != "false"

    # Collect computed JSON from every agent — this is now the authoritative
    # input the synthesizer LLM uses to write the actual answer.
    agents_used = list(responses.keys())
    computed_payload: Dict[str, Any] = {}
    has_any_response = False
    for agent, data in responses.items():
        if not data:
            continue
        has_any_response = True
        if isinstance(data, dict) and data.get("computed"):
            computed_payload[agent] = data["computed"]

    # --- AGGREGATOR LAYER (Financial Snapshot) ---
    bill_total = 0.0
    balance = 0.0
    if "billing_agent" in computed_payload:
        bill_total = float(computed_payload["billing_agent"].get("bills_this_week") or 0.0)
    if "teller_agent" in computed_payload:
        balance = float(computed_payload["teller_agent"].get("total_balance") or 0.0)
    elif "billing_agent" in computed_payload:
        balance = float(computed_payload["billing_agent"].get("balance") or 0.0)

    snapshot_status = "Healthy" if balance > bill_total else "Risk"
    computed_payload["financial_snapshot"] = {
        "bills_due_soon": bill_total,
        "current_balance": balance,
        "status_code": snapshot_status,
        "risk_level": "Low" if snapshot_status == "Healthy" else "Immediate Action Required"
    }
    
    # Synthesize a cross-agent "So what?" hint for the LLM
    agg_insight = []
    if snapshot_status == "Healthy":
        agg_insight.append(f"Balance comfortaly covers upcoming dues of {_format_inr(bill_total)}.")
    else:
        agg_insight.append(f"ALERT: Upcoming dues ({_format_inr(bill_total)}) exceed current balance ({_format_inr(balance)}).")
    
    if "budget_agent" in computed_payload:
        b_actions = computed_payload["budget_agent"].get("smart_actions") or []
        if b_actions:
            agg_insight.append(f"Top optimization: {b_actions[0]}.")
            
    computed_payload["aggregator_insights"] = " ".join(agg_insight)

    # Short-circuit when there is nothing to work with.
    if not has_any_response:
        return {
            "final_answer": INSUFFICIENT_DATA,
            "agents_used": agents_used,
            "agent_trace": _append_trace(
                state,
                {"step": "synthesizer", "agent": "supervisor", "detail": "no_agent_responses"},
            ),
        }

    # If the LLM rewrite path is disabled, fall back to deterministic prose
    # built from the computed payload.
    if not use_llm_rewrite:
        final_answer = _sanitize_raw_answer_text(
            _deterministic_fallback(user_message, responses)
        ) or INSUFFICIENT_DATA
        logger.info(f"[TEST] Final answer: {final_answer}")
        return {
            "final_answer": final_answer,
            "agents_used": agents_used,
            "agent_trace": _append_trace(
                state,
                {"step": "synthesizer", "agent": "supervisor", "detail": "fast_path_env_disabled"},
            ),
        }

    # LLM-driven path: hand the LLM the user query + computed data and let it
    # generate the final answer.
    prompt = (
        LLM_REWRITE_PROMPT
        .replace("{{USER_MESSAGE}}", user_message)
        .replace("{{COMPUTED_JSON}}", json.dumps(computed_payload, ensure_ascii=False, indent=2))
    )

    fallback_reason = ""
    try:
        rewritten = call_llm(prompt, temperature=0.4)
    except Exception as exc:
        logger.warning("synthesizer LLM rewrite failed, falling back to deterministic: %s", exc)
        rewritten = ""
        fallback_reason = "llm_exception"

    # Qualitative / analytical queries get a relaxed rupee guard (the LLM may
    # legitimately focus on the most important numbers).
    _QUALITATIVE_KEYS = (
        "stable", "cut", "save", "cancel", "advice", "suggest", "should i",
        "why", "how", "improve", "reduce", "tip", "what can", "compare",
        "analysis", "overview", "trend",
    )
    _is_qualitative = any(k in user_message.lower() for k in _QUALITATIVE_KEYS)

    rewritten_clean = rewritten.strip()
    if len(rewritten_clean) < 20:
        fallback_reason = fallback_reason or "too_short"
        final_answer = _deterministic_fallback(user_message, responses)
        trace_detail = "llm_rewrite_fallback"
    else:
        # Validate that every ₹ figure in the LLM output also exists in the
        # computed payload — this catches hallucinated numbers.
        computed_blob = json.dumps(computed_payload, ensure_ascii=False)
        rupees_out = _extract_rupee_amounts(rewritten_clean)
        rupees_allowed = _extract_rupee_amounts(computed_blob)

        # Also accept bare numbers from computed (LLM may format ₹308000 as ₹308,000).
        def _digits_only(s: str) -> str:
            return re.sub(r"[^\d]", "", s)

        allowed_digits = {_digits_only(r) for r in rupees_allowed}
        # Pull every numeric token from the computed JSON as well.
        for num in re.findall(r"\d[\d,]*(?:\.\d+)?", computed_blob):
            allowed_digits.add(_digits_only(num))

        invented = [r for r in rupees_out if _digits_only(r) and _digits_only(r) not in allowed_digits]

        if invented and not _is_qualitative:
            fallback_reason = fallback_reason or f"invented_rupees:{invented[:3]}"
            final_answer = _deterministic_fallback(user_message, responses)
            trace_detail = "llm_rewrite_fallback"
        elif invented and _is_qualitative and len(invented) > max(1, len(rupees_out) // 2):
            fallback_reason = fallback_reason or f"invented_rupees_qualitative:{invented[:3]}"
            final_answer = _deterministic_fallback(user_message, responses)
            trace_detail = "llm_rewrite_fallback"
        else:
            final_answer = rewritten_clean
            trace_detail = "llm_rewrite"

    if fallback_reason:
        logger.info("[synthesizer] LLM fallback: %s", fallback_reason)

    final_answer = _remove_markdown_formatting(final_answer)
    if trace_detail == "llm_rewrite":
        final_answer = _sanitize_raw_answer_text(final_answer, drop_suspicious_tail=False) or _deterministic_fallback(user_message, responses)
    else:
        final_answer = _sanitize_raw_answer_text(final_answer) or INSUFFICIENT_DATA

    logger.info(f"[TEST] Final answer: {final_answer}")
    return {
        "final_answer": final_answer,
        "agents_used": agents_used,
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
        "agents_used": ["default_agent"],
        "agent_trace": _append_trace(state, {"step": "default_agent", "agent": "default_agent", "detail": "unsupported_query"})
    }
