from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from models import Card, Transaction, User
from services.financial_engine import canonical_year_month, transactions_in_month
from services.agent_router import AgentRoute, route_query
from services.chat_tools import (
    tool_get_financial_summary,
    tool_get_recent_transactions,
    tool_get_top_categories,
    tool_search_knowledge,
)
from services.llm_service import call_llm, extract_json_object

from services.canonical_cards import ensure_canonical_cards
from services.card_knowledge import get_inline_card_knowledge

from .agent_tools import get_card_data, get_credit_data, get_fraud_signals
from .final_answer import generate_final_answer
from .prompts import SUPERVISOR_ROUTER_PROMPT
from .state import AgentTraceEntry, AstraAgentState

VALID_AGENTS = {
    "spending_agent",
    "credit_agent",
    "card_agent",
    "fraud_agent",
    "default_agent",
}

INSUFFICIENT_DATA = "I don't have enough data to answer this accurately."
FALLBACK_INSIGHT = "I need more transaction data to provide detailed insights."


def _spending_has_data(summary: Dict[str, Any], metrics: Dict[str, Any]) -> bool:
    if summary.get("has_data"):
        return True
    if float(metrics.get("total_spend") or 0) > 0:
        return True
    return bool(metrics.get("category_totals"))


def _insufficient_spending_output() -> Dict[str, Any]:
    return {
        "summary": INSUFFICIENT_DATA,
        "top_category": INSUFFICIENT_DATA,
        "insights": [],
        "subscriptions_detected": [],
        "predicted_next_month_spend": None,
    }


def _insufficient_card_output() -> Dict[str, Any]:
    return {
        "card_usage_summary": INSUFFICIENT_DATA,
        "missed_savings_total": _format_inr(0.0),
        "impact": "",
        "suggestions": [],
    }


def _insufficient_fraud_output() -> Dict[str, Any]:
    return {
        "risk_level": "LOW",
        "reason": INSUFFICIENT_DATA,
        "recommended_action": INSUFFICIENT_DATA,
        "confidence": "40%",
        "urgency": "Low risk",
    }


def _append_trace(state: AstraAgentState, entry: AgentTraceEntry) -> List[AgentTraceEntry]:
    trace = list(state.get("agent_trace") or [])
    trace.append(entry)
    return trace


def _build_unified_context(
    user_query: str,
    data: Dict[str, Any],
    computed_metrics: Dict[str, Any],
    insights: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "user_query": user_query.strip(),
        "data": data,
        "computed_metrics": computed_metrics,
        "insights": insights,
    }


def _retrieve_card_rag(user_message: str) -> Dict[str, Any]:
    """Optional Qdrant retrieval (category ``cards``); safe if Qdrant is down."""
    try:
        from services.knowledge_base_service import retrieve_context

        q = f"{user_message} credit card benefits cashback Swiggy Zomato compare cards"
        return retrieve_context(q, category="cards", top_k=4)
    except Exception:
        return {
            "grade": "none",
            "context": "",
            "hit_count": 0,
            "sources": [],
            "top_score": 0.0,
            "category": "cards",
        }


def _append_final_answer_trace(state: AstraAgentState, agent: str) -> List[AgentTraceEntry]:
    return _append_trace(
        state,
        {
            "step": "final_answer",
            "agent": agent,
            "detail": "llm_generated_final_response",
        },
    )


def _render_prompt(template: str, user_message: str, input_json: Dict[str, Any], route_hint: Dict[str, Any] | None = None) -> str:
    return (
        template.replace("{{USER_MESSAGE}}", user_message.strip())
        .replace("{{INPUT_JSON}}", json.dumps(input_json, indent=2, ensure_ascii=False))
        .replace("{{ROUTE_HINT}}", json.dumps(route_hint or {}, indent=2, ensure_ascii=False))
    )


def _run_tool(
    state: AstraAgentState,
    agent: str,
    tool_name: str,
    fn: Callable[..., Dict[str, Any]],
    *args: Any,
    **kwargs: Any,
) -> tuple[Dict[str, Any], List[AgentTraceEntry]]:
    started = time.perf_counter()
    result = fn(*args, **kwargs)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    trace = _append_trace(
        state,
        {
            "step": "tool",
            "agent": agent,
            "tool": tool_name,
            "detail": "tool_executed",
            "duration_ms": elapsed_ms,
        },
    )
    return result, trace


def _fallback_agent_from_route(message: str, route_hint: Dict[str, Any] | None) -> str:
    if route_hint:
        hinted_agent = route_hint.get("agent")
        if hinted_agent == "scam_agent":
            return "fraud_agent"
    routed = route_query(message)
    if routed.agent == "scam_agent":
        return "fraud_agent"
    return "default_agent"


def _call_structured_llm(prompt: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    try:
        raw = call_llm(prompt, temperature=0.1)
    except Exception:
        return fallback
    parsed = extract_json_object(raw)
    return parsed if parsed else fallback


def _format_inr(value: float) -> str:
    return f"₹{round(float(value), 2):,.2f}"


def _normalize_merchant_key(description: Optional[str]) -> str:
    line = (description or "").strip().split("\n")[0].strip()
    line = re.sub(r"\s+", " ", line)
    return line.lower()[:120] if line else "unknown"


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
    month_txs = transactions_in_month(txs, year, month)
    debits = [tx for tx in month_txs if (tx.type or "").lower() == "debit"]
    category_totals: Dict[str, float] = defaultdict(float)
    merchant_counts: Dict[str, int] = defaultdict(int)
    merchant_amounts: Dict[str, float] = defaultdict(float)
    for tx in debits:
        amt = abs(float(tx.amount or 0.0))
        cat = (tx.category or "Other").strip() or "Other"
        category_totals[cat] += amt
        mkey = _normalize_merchant_key(tx.description)
        merchant_counts[mkey] += 1
        merchant_amounts[mkey] += amt
    total_spend = round(sum(category_totals.values()), 2)
    top_category = None
    if category_totals:
        top_category = max(category_totals.keys(), key=lambda c: category_totals[c])
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
    subscriptions.sort(key=lambda row: row["total"], reverse=True)
    return {
        "headline_month": f"{year:04d}-{month:02d}",
        "total_spend": total_spend,
        "category_totals": {k: round(v, 2) for k, v in sorted(category_totals.items(), key=lambda x: -x[1])},
        "top_category": top_category,
        "subscriptions": subscriptions,
    }


def _card_label(card: Card) -> str:
    return f"{card.bank_name} *{card.last4_digits}"


def _is_hdfc(card: Card) -> bool:
    return "hdfc" in (card.bank_name or "").lower()


def _is_icici_amazon_card(card: Card) -> bool:
    b = (card.bank_name or "").lower()
    t = (card.card_type or "").lower()
    return "icici" in b and "amazon" in (t + b)


def _merchant_bucket(description: Optional[str]) -> Optional[str]:
    d = (description or "").lower()
    if "uber" in d:
        return "uber"
    if "swiggy" in d:
        return "swiggy"
    if "zomato" in d:
        return "zomato"
    if "amazon" in d or "amzn" in d:
        return "amazon"
    return None


def _analyze_card_missed_savings(db: Session, user: User) -> Dict[str, Any]:
    cards = {
        c.id: c
        for c in db.query(Card).filter(Card.user_id == user.id).order_by(Card.id.asc()).all()
    }
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
            "optimal": True,
            "missed_savings_total_value": 0.0,
            "total_card_spend_value": 0.0,
            "missed_savings_total": _format_inr(0.0),
            "suggestions": [],
        }
    year, month = cy
    month_txs = transactions_in_month(txs, year, month)
    raw_suggestions: List[Dict[str, Any]] = []
    total_missed = 0.0
    total_card_spend = 0.0
    for tx in month_txs:
        if (tx.type or "").lower() != "debit" or not tx.card_id:
            continue
        card = cards.get(tx.card_id)
        if not card:
            continue
        amt = abs(float(tx.amount or 0.0))
        if amt <= 0:
            continue
        total_card_spend += amt
        bucket = _merchant_bucket(tx.description)
        if bucket == "uber":
            continue
        used = _card_label(card)
        if bucket in ("swiggy", "zomato"):
            if _is_hdfc(card):
                continue
            sav = round(amt * 0.10, 2)
            total_missed += sav
            raw_suggestions.append(
                {
                    "merchant": "Swiggy" if bucket == "swiggy" else "Zomato",
                    "used_card": used,
                    "better_card": "HDFC (10% food-delivery cashback rule)",
                    "savings": _format_inr(sav),
                    "savings_value": sav,
                }
            )
            continue
        if bucket == "amazon":
            if _is_icici_amazon_card(card):
                continue
            sav = round(amt * 0.05, 2)
            total_missed += sav
            raw_suggestions.append(
                {
                    "merchant": "Amazon",
                    "used_card": used,
                    "better_card": "ICICI Amazon card (5% rule)",
                    "savings": _format_inr(sav),
                    "savings_value": sav,
                }
            )
    raw_suggestions.sort(key=lambda row: float(row.get("savings_value") or 0.0), reverse=True)
    suggestions: List[Dict[str, str]] = [
        {k: v for k, v in row.items() if k != "savings_value"} for row in raw_suggestions
    ]
    optimal = total_missed <= 0.0
    return {
        "headline_month": f"{year:04d}-{month:02d}",
        "optimal": optimal,
        "missed_savings_total_value": round(total_missed, 2),
        "total_card_spend_value": round(total_card_spend, 2),
        "missed_savings_total": _format_inr(total_missed),
        "suggestions": suggestions,
    }


def _extract_primary_amount_from_text(text: str) -> Optional[float]:
    if not (text or "").strip():
        return None
    amounts: List[float] = []
    for m in re.finditer(r"₹\s*([\d,]+(?:\.\d+)?)", text):
        try:
            amounts.append(float(m.group(1).replace(",", "")))
        except ValueError:
            continue
    for m in re.finditer(r"\b([\d,]+(?:\.\d+)?)\b", text.replace(",", "")):
        try:
            v = float(m.group(1))
            if v >= 100.0:
                amounts.append(v)
        except ValueError:
            continue
    return max(amounts) if amounts else None


def _unknown_merchant_case(message: str, fraud_signals: Dict[str, Any]) -> bool:
    m = (message or "").lower()
    if "unknown merchant" in m or "unrecognized merchant" in m:
        return True
    if ("not me" in m or "didn't authorize" in m or "did not authorize" in m) and not (
        fraud_signals.get("matched_recent_transactions") or []
    ):
        return True
    return False


def _merge_risk_levels(*levels: str) -> str:
    rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    best = "LOW"
    for lvl in levels:
        if rank.get(lvl, 0) > rank.get(best, 0):
            best = lvl
    return best


def _fraud_rule_enrichment(message: str, fraud_signals: Dict[str, Any]) -> Dict[str, Any]:
    lowered = (message or "").lower()
    amt = _extract_primary_amount_from_text(message or "")
    indicators = list(fraud_signals.get("indicators") or [])
    otp_like = (
        "otp" in lowered
        or "one time password" in lowered
        or "otp_request" in indicators
        or "pin_request" in indicators
    )
    urgent_like = "urgent" in lowered or "urgent_language" in indicators
    payment_like = "payment" in lowered or "pay" in lowered

    reason_parts: List[str] = []
    if otp_like:
        reason_parts.append("OTP-based transaction")
    if amt is not None:
        reason_parts.append(f"high amount ₹{amt:,.2f}" if amt > 10000 else f"amount ₹{amt:,.2f}")
    if urgent_like:
        reason_parts.append("urgent language")
    if payment_like:
        reason_parts.append("payment-related wording")

    if otp_like and amt is not None and amt > 10000:
        return {
            "risk_level": "HIGH",
            "reason": f"OTP-based request with high transaction amount (₹{amt:,.2f})",
            "reason_parts": reason_parts + ["OTP with amount above ₹10,000"],
            "recommended_action": "Do not share OTP. Consider blocking the transaction and verify with your bank using an official number.",
            "amount_in_message": amt,
        }
    if _unknown_merchant_case(message, fraud_signals):
        return {
            "risk_level": "MEDIUM",
            "reason": "Unknown or unrecognized merchant context; verify before paying",
            "reason_parts": reason_parts + ["unusual request"],
            "recommended_action": "Pause and verify the sender through your bank's official channel before acting.",
            "amount_in_message": amt,
        }
    return {
        "risk_level": "LOW",
        "reason": "No OTP+high-amount pattern or unknown-merchant signal from rules; still review tool indicators.",
        "reason_parts": reason_parts or ["no strong rule-based trigger"],
        "recommended_action": "Stay alert; confirm unusual payment requests through official channels.",
        "amount_in_message": amt,
    }


def _has_numeric_content(obj: Any) -> bool:
    if isinstance(obj, (int, float)) and not isinstance(obj, bool):
        return True
    if isinstance(obj, str):
        return bool(re.search(r"\d", obj))
    if isinstance(obj, dict):
        return any(_has_numeric_content(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_has_numeric_content(v) for v in obj)
    return False


def _ensure_numeric_visibility(agent: str, structured: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(structured)
    if _has_numeric_content(out):
        return out
    if agent == "spending_agent":
        ins = list(out.get("insights") or [])
        if isinstance(ins, str):
            ins = [ins] if ins.strip() else []
        ins.append(FALLBACK_INSIGHT)
        out["insights"] = ins
    elif agent == "card_agent":
        cur = str(out.get("card_usage_summary") or "").strip()
        out["card_usage_summary"] = (cur + " " + FALLBACK_INSIGHT).strip() if cur else FALLBACK_INSIGHT
    elif agent == "fraud_agent":
        out["reason"] = (str(out.get("reason") or "") + " " + FALLBACK_INSIGHT).strip()
    elif agent == "credit_agent":
        out["score_analysis"] = (str(out.get("score_analysis") or "") + " " + FALLBACK_INSIGHT).strip()
    return out


def _append_agent_trace_node(
    state: AstraAgentState,
    agent: str,
    tools_used: List[str],
    key_metrics: Dict[str, Any],
) -> List[AgentTraceEntry]:
    return _append_trace(
        state,
        {
            "step": "agent_metrics",
            "agent": agent,
            "tools_used": tools_used,
            "key_metrics": key_metrics,
        },
    )


def _build_spending_insights(metrics: Dict[str, Any], financial_summary: Dict[str, Any]) -> Dict[str, Any]:
    total = float(metrics.get("total_spend") or 0.0)
    category_totals = dict(metrics.get("category_totals") or {})
    top_category_name = metrics.get("top_category")
    top_category_amount = float(category_totals.get(top_category_name, 0.0)) if top_category_name else 0.0
    top_category_share = round((top_category_amount / total) * 100.0, 1) if total > 0 else None

    overspending_categories: List[Dict[str, Any]] = []
    for category, amount in category_totals.items():
        if total <= 0:
            continue
        share_pct = round((float(amount) / total) * 100.0, 1)
        if share_pct > 40.0:
            overspending_categories.append(
                {
                    "category": category,
                    "amount": round(float(amount), 2),
                    "share_pct": share_pct,
                    "threshold_pct": 40.0,
                }
            )

    recurring_subscriptions = [
        {
            "merchant": row.get("label") or row.get("merchant_key") or "Unknown merchant",
            "transactions": int(row.get("transactions") or 0),
            "total": round(float(row.get("total") or 0.0), 2),
        }
        for row in list(metrics.get("subscriptions") or [])
    ]

    estimated_savings = None
    if top_category_name and top_category_amount > 0:
        estimated_savings = {
            "category": top_category_name,
            "reduce_pct": 15.0,
            "estimated_monthly_savings": round(top_category_amount * 0.15, 2),
        }

    return {
        "has_spending_data": bool(financial_summary.get("has_data") or total > 0 or category_totals),
        "top_category_signal": (
            {
                "category": top_category_name,
                "amount": round(top_category_amount, 2),
                "share_pct": top_category_share,
            }
            if top_category_name
            else None
        ),
        "overspending_categories": overspending_categories,
        "recurring_subscriptions": recurring_subscriptions,
        "projected_next_month_spend": round(total, 2) if total > 0 else None,
        "estimated_savings_if_top_category_reduced": estimated_savings,
        "salary_reference_available": bool(financial_summary.get("salary_3mo_avg")),
    }


def _build_credit_insights(credit_data: Dict[str, Any]) -> Dict[str, Any]:
    utilization = credit_data.get("credit_utilization_pct")
    score = credit_data.get("credit_score")
    monthly_emi_total = round(float(credit_data.get("monthly_emi_total") or 0.0), 2)

    risk_factors: List[Dict[str, Any]] = []
    positive_factors: List[Dict[str, Any]] = []
    improvement_actions: List[Dict[str, Any]] = []

    if utilization is not None and utilization > 30:
        risk_factors.append(
            {
                "type": "high_utilization",
                "utilization_pct": utilization,
                "ideal_pct": 30.0,
            }
        )
        improvement_actions.append(
            {
                "type": "reduce_utilization",
                "target_pct": 30.0,
            }
        )
    elif utilization is not None:
        positive_factors.append(
            {
                "type": "healthy_utilization",
                "utilization_pct": utilization,
                "ideal_pct": 30.0,
            }
        )

    if score is not None and score < 700:
        risk_factors.append(
            {
                "type": "low_credit_score",
                "credit_score": score,
                "strong_range_min": 700,
            }
        )
        improvement_actions.append(
            {
                "type": "improve_credit_score",
                "credit_score": score,
            }
        )
    elif score is not None and score >= 750:
        positive_factors.append(
            {
                "type": "strong_credit_score",
                "credit_score": score,
                "strong_range_min": 750,
            }
        )

    if monthly_emi_total > 0:
        risk_factors.append(
            {
                "type": "loan_commitment",
                "monthly_emi_total": monthly_emi_total,
            }
        )

    return {
        "risk_factors": risk_factors,
        "positive_factors": positive_factors,
        "improvement_actions": improvement_actions,
        "missing_fields": list(credit_data.get("missing_fields") or []),
    }


def _build_card_insights(card_data: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
    cards = list(card_data.get("cards") or [])
    high_utilization_cards = [
        {
            "bank_name": card.get("bank_name"),
            "last4_digits": card.get("last4_digits"),
            "utilization_pct": card.get("utilization_pct"),
        }
        for card in cards
        if (card.get("utilization_pct") or 0) > 30
    ]
    return {
        "optimization_status": "optimal"
        if analysis.get("optimal") or not analysis.get("suggestions")
        else "opportunities_found",
        "missed_savings_opportunities": list(analysis.get("suggestions") or []),
        "high_utilization_cards": high_utilization_cards,
        "offers_dataset_available": bool(card_data.get("offers_dataset_available")),
        "missing_fields": list(card_data.get("missing_fields") or []),
    }


def _build_fraud_insights(
    fraud_signals: Dict[str, Any],
    fraud_rule_analysis: Dict[str, Any],
    knowledge_result: Dict[str, Any],
    merged_risk: str,
) -> Dict[str, Any]:
    return {
        "final_risk_level": merged_risk,
        "tool_risk_level": fraud_signals.get("risk_level"),
        "rule_risk_level": fraud_rule_analysis.get("risk_level"),
        "matched_patterns": list(fraud_signals.get("indicators") or []),
        "amount_in_message": fraud_rule_analysis.get("amount_in_message"),
        "knowledge_hit_count": int(knowledge_result.get("hit_count") or 0),
        "matches_banking_scam_patterns": bool(
            (knowledge_result.get("context") or "").strip() or int(knowledge_result.get("hit_count") or 0) > 0
        ),
        "recommended_action": fraud_rule_analysis.get("recommended_action"),
        "matched_recent_transactions_count": len(fraud_signals.get("matched_recent_transactions") or []),
    }


def _build_spending_actionable_insights(metrics: Dict[str, Any], financial_summary: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic 'so what' layer: percentages, flags, savings math, projection."""
    total = float(metrics.get("total_spend") or 0.0)
    category_totals = dict(metrics.get("category_totals") or {})
    top_cat = metrics.get("top_category")
    sub_rows = list(metrics.get("subscriptions") or [])
    headline = metrics.get("headline_month") or "this month"

    subscriptions_detected: List[str] = [
        f"{row.get('label') or row.get('merchant_key') or 'merchant'} (₹{float(row.get('total') or 0):,.2f})"
        for row in sub_rows
    ]

    if total <= 0 and not category_totals:
        return {
            "insights": [INSUFFICIENT_DATA],
            "subscriptions_detected": [],
            "top_category": INSUFFICIENT_DATA,
            "summary_tail": "",
            "predicted_next_month_spend": None,
        }

    insights: List[str] = []
    insights.append(f"You spent ₹{total:,.2f} total in {headline}.")

    top_amount = float(category_totals.get(top_cat, 0)) if top_cat else 0.0
    pct_top = (top_amount / total * 100.0) if total > 0 else 0.0
    if top_cat:
        insights.append(
            f"Your highest spending is ₹{top_amount:,.2f} on {top_cat} ({pct_top:.1f}% of total)."
        )

    overspent: List[Tuple[str, float]] = []
    for cat, amt in category_totals.items():
        if total <= 0:
            continue
        share = float(amt) / total * 100.0
        if share > 40.0:
            overspent.append((cat, share))
    overspent.sort(key=lambda x: -x[1])
    for cat, share in overspent[:3]:
        insights.append(
            f"This indicates possible overspending in {cat}: {share:.1f}% of total spend (above 40%)."
        )

    if len(sub_rows) >= 3:
        insights.append(
            f"You have {len(sub_rows)} recurring merchant patterns (2+ debits) — review subscription load."
        )

    reduce_pct = 15.0
    if top_cat and top_amount > 0:
        n_saved = round(top_amount * (reduce_pct / 100.0), 2)
        insights.append(
            f"Reducing {top_cat} by {reduce_pct:.0f}% could save about ₹{n_saved:,.2f} next month."
        )

    projected = round(total, 2)
    insights.append(
        f"At your current pace, next month's spend may be around ₹{projected:,.2f} (projection based on this month)."
    )

    top_category_line = (
        f"{top_cat} — ₹{top_amount:,.2f} ({pct_top:.1f}% of total)" if top_cat else INSUFFICIENT_DATA
    )
    summary_tail = f" Estimated next month at current pace: ₹{projected:,.2f}."
    return {
        "insights": insights,
        "subscriptions_detected": subscriptions_detected,
        "top_category": top_category_line,
        "summary_tail": summary_tail,
        "predicted_next_month_spend": projected,
    }


def _apply_spending_postprocess(
    structured: Dict[str, Any],
    metrics: Dict[str, Any],
    financial_summary: Dict[str, Any],
) -> Dict[str, Any]:
    built = _build_spending_actionable_insights(metrics, financial_summary)
    out = dict(structured)
    out["insights"] = built["insights"]
    out["subscriptions_detected"] = built["subscriptions_detected"]
    out["top_category"] = built["top_category"]
    out["predicted_next_month_spend"] = built.get("predicted_next_month_spend")
    base = (out.get("summary") or "").strip()
    tail = built.get("summary_tail") or ""
    if tail and tail.strip() not in base:
        out["summary"] = (base + " " + tail).strip() if base else tail.strip()
    elif not base:
        out["summary"] = (
            f"Spending overview for {metrics.get('headline_month') or 'the period'}: ₹{float(metrics.get('total_spend') or 0):,.2f} total."
            + (tail or "")
        ).strip()
    return out


def _fraud_confidence_and_urgency(risk_level: str) -> tuple[str, str]:
    m = {
        "HIGH": ("90%", "Immediate action required"),
        "MEDIUM": ("70%", "Review recommended"),
        "LOW": ("40%", "Low risk"),
    }
    return m.get((risk_level or "MEDIUM").upper(), ("70%", "Review recommended"))


def _apply_fraud_polish(
    structured: Dict[str, Any],
    rule: Dict[str, Any],
    fraud_signals: Dict[str, Any],
    knowledge_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    out = dict(structured)
    rl = str(out.get("risk_level") or "MEDIUM").upper()
    conf, urgency = _fraud_confidence_and_urgency(rl)
    out["confidence"] = conf
    out["urgency"] = urgency
    reason = str(out.get("reason") or "").strip()
    amt = rule.get("amount_in_message")
    if amt is not None:
        amt_s = f"₹{float(amt):,.2f}"
        if amt_s not in reason and str(int(amt)) not in reason.replace(",", ""):
            reason = f"{reason} Amount referenced: {amt_s}." if reason else f"Amount referenced: {amt_s}."
    msg_lower = str(fraud_signals.get("message_text") or "").lower()
    patterns: List[str] = []
    if "otp" in msg_lower or "otp_request" in (fraud_signals.get("indicators") or []):
        patterns.append("OTP pattern")
    if _unknown_merchant_case(str(fraud_signals.get("message_text") or ""), fraud_signals):
        patterns.append("unknown merchant")
    rlow = reason.lower()
    if patterns and "patterns:" not in rlow:
        reason = f"{reason} Patterns: {', '.join(patterns)}." if reason else f"Patterns: {', '.join(patterns)}."
    out["reason"] = reason.strip()
    if knowledge_result and (
        (knowledge_result.get("context") or "").strip() or int(knowledge_result.get("hit_count") or 0) > 0
    ):
        out["matches_banking_scam_patterns"] = True
    return out


def _finalize_card_structured(structured: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(structured)
    missed = float(analysis.get("missed_savings_total_value") or 0.0)
    total_card = float(analysis.get("total_card_spend_value") or 0.0)
    out["missed_savings_total"] = analysis.get("missed_savings_total") or _format_inr(missed)
    suggestions = list(analysis.get("suggestions") or [])
    out["suggestions"] = suggestions
    if total_card > 0:
        pct_impact = round((missed / total_card) * 100.0, 1)
        out["impact"] = (
            f"You could have saved {out['missed_savings_total']} ({pct_impact}% of your card spending this month)."
        )
    else:
        out["impact"] = (
            f"You could have saved {out['missed_savings_total']} this month by optimizing card usage."
            if missed > 0
            else "No missed rule-based savings on card-tagged debits this month."
        )
    return out


def _route_from_state(state: AstraAgentState) -> AgentRoute:
    route_hint = state.get("route_hint") or {}
    agent = route_hint.get("agent")
    category = route_hint.get("category")
    if agent and category:
        return AgentRoute(
            agent=agent,
            category=category,
            confidence=float(route_hint.get("confidence") or 0.0),
            reason=str(route_hint.get("reason") or "multi_agent_fallback"),
            keywords_matched=tuple(route_hint.get("keywords_matched") or ()),
        )
    return route_query(state.get("message", ""))


def _spending_fallback(payload: Dict[str, Any]) -> Dict[str, Any]:
    summary = payload.get("financial_summary") or {}
    metrics = payload.get("computed_metrics") or {}
    category_totals = metrics.get("category_totals") or {}

    if not summary.get("has_data") and not category_totals:
        return {
            "summary": INSUFFICIENT_DATA,
            "top_category": INSUFFICIENT_DATA,
            "subscriptions_detected": [],
            "insights": [INSUFFICIENT_DATA],
            "predicted_next_month_spend": None,
        }

    built = _build_spending_actionable_insights(metrics, summary)
    headline_month = metrics.get("headline_month") or summary.get("headline_month") or "the latest month"
    total_spend = float(metrics.get("total_spend") or 0.0)

    summary_text = (
        f"In {headline_month}, total debit spend from categorized transactions is ₹{total_spend:,.2f}."
    )
    if summary.get("expenses_canonical_month") is not None:
        summary_text += f" Snapshot expenses: ₹{float(summary['expenses_canonical_month']):,.2f}."
    if summary.get("savings_canonical_month") is not None:
        summary_text += f" Savings: ₹{float(summary['savings_canonical_month']):,.2f}."
    if summary.get("salary_3mo_avg"):
        summary_text += f" Average income (3 mo): ₹{float(summary['salary_3mo_avg']):,.2f}."
    summary_text += built.get("summary_tail") or ""

    return {
        "summary": summary_text.strip(),
        "top_category": built["top_category"],
        "subscriptions_detected": built["subscriptions_detected"],
        "insights": built["insights"],
        "predicted_next_month_spend": built.get("predicted_next_month_spend"),
    }


def _credit_fallback(payload: Dict[str, Any]) -> Dict[str, Any]:
    credit = payload.get("credit_data") or {}
    if not credit.get("has_data"):
        return {
            "score_analysis": INSUFFICIENT_DATA,
            "risk_factors": [INSUFFICIENT_DATA],
            "positive_factors": [INSUFFICIENT_DATA],
            "improvement_actions": [INSUFFICIENT_DATA],
            "predicted_impact": INSUFFICIENT_DATA,
        }

    score = credit.get("credit_score")
    utilization = credit.get("credit_utilization_pct")
    risk_factors: List[str] = []
    positive_factors: List[str] = []
    improvements: List[str] = []

    if utilization is not None and utilization > 30:
        risk_factors.append(f"Credit utilization is {utilization}%, above the ideal 30% level.")
        improvements.append("Reduce utilization below 30% before adding new card spend.")
    if score is not None and score < 700:
        risk_factors.append(f"Credit score is {score}, which is below a strong-credit range.")
        improvements.append("Focus on lowering balances before applying for new credit.")
    if utilization is not None and utilization <= 30:
        positive_factors.append(f"Utilization is {utilization}%, which is within the ideal range.")
    if score is not None and score >= 750:
        positive_factors.append(f"Credit score is {score}, which is already strong.")
    if credit.get("monthly_emi_total", 0) > 0:
        risk_factors.append(
            f"Monthly EMI commitments are ₹{credit['monthly_emi_total']:,.2f}, which can limit flexibility."
        )
    if not positive_factors:
        positive_factors.append("The available data does not show a strong positive credit signal yet.")
    if not improvements:
        improvements.append(INSUFFICIENT_DATA)

    score_analysis = (
        f"Your current credit score is {score}."
        if score is not None
        else INSUFFICIENT_DATA
    )
    if utilization is not None:
        score_analysis += f" Total utilization is {utilization}% across ₹{credit['total_credit_limit']:,.2f} of limit."

    return {
        "score_analysis": score_analysis,
        "risk_factors": risk_factors or [INSUFFICIENT_DATA],
        "positive_factors": positive_factors,
        "improvement_actions": improvements,
        "predicted_impact": (
            "Lower utilization should have the clearest near-term impact because that metric is present in your data."
            if utilization is not None
            else INSUFFICIENT_DATA
        ),
    }


def _card_fallback(payload: Dict[str, Any]) -> Dict[str, Any]:
    card_data = payload.get("card_data") or {}
    analysis = payload.get("missed_savings_analysis") or {}
    cards = card_data.get("cards") or []
    if not card_data.get("has_data"):
        return {
            "card_usage_summary": INSUFFICIENT_DATA,
            "missed_savings_total": _format_inr(0.0),
            "suggestions": [],
        }

    summary_bits = []
    for card in cards[:3]:
        summary_bits.append(
            f"{card['bank_name']} {card.get('card_type') or 'card'} ending {card['last4_digits']} was used for "
            f"₹{card['monthly_spend']:,.2f} in {card_data.get('headline_month') or 'the latest month'}."
        )
    missed_total = analysis.get("missed_savings_total") or _format_inr(0.0)
    suggestions = list(analysis.get("suggestions") or [])
    if analysis.get("optimal") or not suggestions:
        summary_line = (" ".join(summary_bits) if summary_bits else "Card usage from data.") + " Optimal usage detected."
    else:
        summary_line = " ".join(summary_bits) if summary_bits else "Card usage from data."

    return {
        "card_usage_summary": summary_line,
        "missed_savings_total": missed_total,
        "suggestions": suggestions,
    }


def _fraud_fallback(payload: Dict[str, Any]) -> Dict[str, Any]:
    fraud = payload.get("fraud_signals") or {}
    kb = payload.get("knowledge_result") or {}
    rule = payload.get("fraud_rule_analysis") or {}
    if not fraud.get("has_data"):
        return {
            "risk_level": "MEDIUM",
            "reason": INSUFFICIENT_DATA,
            "recommended_action": INSUFFICIENT_DATA,
        }

    indicators = fraud.get("indicators") or []
    tool_level = fraud.get("risk_level") or "LOW"
    rule_level = rule.get("risk_level") or "LOW"
    risk_level = _merge_risk_levels(tool_level, rule_level)

    reason_parts = list(rule.get("reason_parts") or [])
    if indicators:
        reason_parts.append(f"tool indicators: {', '.join(indicators)}")
    amt = rule.get("amount_in_message")
    reason = rule.get("reason") or ""
    if amt is not None:
        reason = f"{reason} (amount in message: ₹{float(amt):,.2f})"
    if indicators:
        reason += (
            f" Signals detected: {', '.join(indicators)}."
            if reason
            else f"Signals detected: {', '.join(indicators)}."
        )
    if kb.get("context"):
        reason += f" Knowledge base: {kb.get('hit_count', 0)} scam document(s)."

    if risk_level == "HIGH":
        action = rule.get("recommended_action") or (
            "Do not share OTP, PIN, CVV, or click the link. Contact your bank immediately."
        )
    elif risk_level == "MEDIUM":
        action = rule.get("recommended_action") or (
            "Pause and verify the sender through your bank's official channel before acting."
        )
    else:
        action = rule.get("recommended_action") or (
            "No immediate fraud pattern is confirmed, but continue monitoring the transaction."
        )

    return {
        "risk_level": risk_level,
        "reason": reason.strip() or INSUFFICIENT_DATA,
        "recommended_action": action,
    }


def supervisor_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    agent_hint = state.get("agent_hint")
    if agent_hint in VALID_AGENTS and agent_hint != "default_agent":
        trace = _append_trace(
            state,
            {
                "step": "supervisor",
                "agent": agent_hint,
                "reason": "agent_hint",
                "detail": "using_explicit_agent_hint",
            },
        )
        return {"next_agent": agent_hint, "agent_trace": trace}

    prompt = _render_prompt(
        SUPERVISOR_ROUTER_PROMPT,
        state.get("message", ""),
        {},
        state.get("route_hint"),
    )
    try:
        raw = call_llm(prompt, temperature=0.0)
        parsed = extract_json_object(raw) or {}
        agent = parsed.get("agent")
    except Exception:
        agent = None

    if agent not in VALID_AGENTS:
        agent = _fallback_agent_from_route(state.get("message", ""), state.get("route_hint"))
        reason = "supervisor_fallback"
    else:
        reason = "supervisor_llm"

    trace = _append_trace(
        state,
        {
            "step": "supervisor",
            "agent": str(agent),
            "reason": reason,
            "detail": "query_classified",
        },
    )
    return {"next_agent": str(agent), "agent_trace": trace}


def spending_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    user_message = state.get("message", "")
    computed_metrics = _compute_spending_metrics(db, user)
    summary, trace = _run_tool(state, "spending_agent", "get_financial_summary", tool_get_financial_summary, db, user)
    working_state = dict(state)
    working_state["agent_trace"] = trace
    categories, trace = _run_tool(working_state, "spending_agent", "get_top_categories", tool_get_top_categories, db, user, 5)
    working_state["agent_trace"] = trace
    recent, trace = _run_tool(working_state, "spending_agent", "get_recent_transactions", tool_get_recent_transactions, db, user, 10, "debit")

    budget_reference = None
    salary = summary.get("salary_3mo_avg")
    if salary:
        budget_reference = {
            "needs_50_pct": round(float(salary) * 0.5, 2),
            "wants_30_pct": round(float(salary) * 0.3, 2),
            "savings_20_pct": round(float(salary) * 0.2, 2),
        }

    payload = {
        "financial_summary": summary,
        "category_breakdown": categories.get("categories", []),
        "recent_debits": recent.get("transactions", []),
        "subscription_summary": summary.get("subscription_line_items", []),
        "budget_reference": budget_reference,
        "computed_metrics": computed_metrics,
        "structured_spending_input": {
            "total_spend": computed_metrics["total_spend"],
            "category_totals": computed_metrics["category_totals"],
            "top_category": computed_metrics["top_category"],
            "subscriptions": computed_metrics["subscriptions"],
        },
    }
    spending_insights = _build_spending_insights(computed_metrics, summary)
    computed_metrics_block = {
        "headline_month": computed_metrics.get("headline_month"),
        "total_spend": computed_metrics.get("total_spend"),
        "category_totals": computed_metrics.get("category_totals"),
        "top_category": computed_metrics.get("top_category"),
        "subscriptions": computed_metrics.get("subscriptions"),
        "budget_reference": budget_reference,
    }

    if not _spending_has_data(summary, computed_metrics):
        trace = _append_agent_trace_node(
            {"agent_trace": trace},
            "spending_agent",
            ["get_financial_summary", "get_top_categories", "get_recent_transactions"],
            {"data_ok": False, "reason": "no_transaction_grounding"},
        )
        unified_context = _build_unified_context(
            user_message,
            payload,
            computed_metrics_block,
            {
                "status": "insufficient_data",
                "reason": "no_transaction_grounding",
            },
        )
        return {
            "structured_output": unified_context,
            "unified_context": unified_context,
            "tool_results": payload,
            "final_answer": INSUFFICIENT_DATA,
            "sources": [],
            "confidence": 0.25,
            "reason": "multi_agent_spending_no_data",
            "agent_trace": trace,
        }

    unified_context = _build_unified_context(
        user_message,
        payload,
        computed_metrics_block,
        spending_insights,
    )
    final_answer = generate_final_answer(user_message, unified_context, agent_name="spending_agent")
    trace = _append_agent_trace_node(
        {"agent_trace": trace},
        "spending_agent",
        ["get_financial_summary", "get_top_categories", "get_recent_transactions"],
        {
            "total_spend": computed_metrics["total_spend"],
            "top_category": computed_metrics["top_category"] or "",
            "subscriptions_merchants": len(computed_metrics["subscriptions"]),
        },
    )
    trace = _append_final_answer_trace({"agent_trace": trace}, "spending_agent")
    return {
        "structured_output": unified_context,
        "unified_context": unified_context,
        "tool_results": payload,
        "final_answer": final_answer,
        "sources": ["db"],
        "confidence": 0.9 if summary.get("has_data") else 0.4,
        "reason": "multi_agent_spending",
        "agent_trace": trace,
    }


def credit_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    user_message = state.get("message", "")
    credit_data, trace = _run_tool(state, "credit_agent", "get_credit_data", get_credit_data, db, user)
    computed_metrics = {
        "credit_score": credit_data.get("credit_score"),
        "credit_utilization_pct": credit_data.get("credit_utilization_pct"),
        "total_credit_limit": credit_data.get("total_credit_limit"),
        "total_used_credit": credit_data.get("total_used_credit"),
        "monthly_emi_total": credit_data.get("monthly_emi_total"),
        "number_of_accounts": credit_data.get("number_of_accounts"),
    }
    credit_insights = _build_credit_insights(credit_data)
    if not credit_data.get("has_data"):
        trace = _append_agent_trace_node(
            {"agent_trace": trace},
            "credit_agent",
            ["get_credit_data"],
            {"data_ok": False, "reason": "no_credit_grounding"},
        )
        unified_context = _build_unified_context(
            user_message,
            {"credit_data": credit_data},
            computed_metrics,
            {
                "status": "insufficient_data",
                "reason": "no_credit_grounding",
                **credit_insights,
            },
        )
        return {
            "structured_output": unified_context,
            "unified_context": unified_context,
            "tool_results": {"credit_data": credit_data},
            "final_answer": INSUFFICIENT_DATA,
            "sources": [],
            "confidence": 0.25,
            "reason": "multi_agent_credit_no_data",
            "agent_trace": trace,
        }

    unified_context = _build_unified_context(
        user_message,
        {"credit_data": credit_data},
        computed_metrics,
        credit_insights,
    )
    final_answer = generate_final_answer(user_message, unified_context, agent_name="credit_agent")
    trace = _append_agent_trace_node(
        {"agent_trace": trace},
        "credit_agent",
        ["get_credit_data"],
        {
            "credit_score": credit_data.get("credit_score"),
            "credit_utilization_pct": credit_data.get("credit_utilization_pct"),
        },
    )
    trace = _append_final_answer_trace({"agent_trace": trace}, "credit_agent")
    return {
        "structured_output": unified_context,
        "unified_context": unified_context,
        "tool_results": {"credit_data": credit_data},
        "final_answer": final_answer,
        "sources": ["db"],
        "confidence": 0.88 if credit_data.get("has_data") else 0.4,
        "reason": "multi_agent_credit",
        "agent_trace": trace,
    }


def card_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    user_message = state.get("message", "")
    ensure_canonical_cards(db, user)
    missed_savings_analysis = _analyze_card_missed_savings(db, user)
    card_data, trace = _run_tool(state, "card_agent", "get_card_data", get_card_data, db, user)
    payload = {
        "card_data": card_data,
        "missed_savings_analysis": missed_savings_analysis,
        "card_knowledge_base": get_inline_card_knowledge(),
    }
    computed_metrics = {
        "headline_month": card_data.get("headline_month"),
        "card_count": len(card_data.get("cards") or []),
        "missed_savings_total_value": missed_savings_analysis.get("missed_savings_total_value"),
        "missed_savings_total": missed_savings_analysis.get("missed_savings_total"),
        "total_card_spend_value": missed_savings_analysis.get("total_card_spend_value"),
        "unassigned_debit_spend": card_data.get("unassigned_debit_spend"),
    }
    card_insights = _build_card_insights(card_data, missed_savings_analysis)
    if not card_data.get("has_data"):
        trace = _append_agent_trace_node(
            {"agent_trace": trace},
            "card_agent",
            ["get_card_data"],
            {"data_ok": False, "reason": "no_card_or_card_tx_grounding"},
        )
        unified_context = _build_unified_context(
            user_message,
            payload,
            computed_metrics,
            {
                "status": "insufficient_data",
                "reason": "no_card_or_card_tx_grounding",
                **card_insights,
            },
        )
        return {
            "structured_output": unified_context,
            "unified_context": unified_context,
            "tool_results": payload,
            "final_answer": INSUFFICIENT_DATA,
            "sources": [],
            "confidence": 0.25,
            "reason": "multi_agent_card_no_data",
            "agent_trace": trace,
        }
    rag_raw = _retrieve_card_rag(user_message)
    payload["rag_context"] = {
        "grade": rag_raw.get("grade"),
        "top_score": rag_raw.get("top_score"),
        "hit_count": rag_raw.get("hit_count"),
        "sources": rag_raw.get("sources", []),
        "context": (rag_raw.get("context") or "")[:8000],
    }
    trace = _append_trace(
        {"agent_trace": trace},
        {
            "step": "card_rag",
            "agent": "card_agent",
            "detail": "qdrant_cards_category",
            "reason": str(rag_raw.get("grade") or "none"),
        },
    )
    unified_context = _build_unified_context(
        user_message,
        payload,
        computed_metrics,
        card_insights,
    )
    final_answer = generate_final_answer(user_message, unified_context, agent_name="card_agent")
    trace = _append_agent_trace_node(
        {"agent_trace": trace},
        "card_agent",
        ["get_card_data"],
        {
            "missed_savings_total_value": missed_savings_analysis.get("missed_savings_total_value"),
            "total_card_spend_value": missed_savings_analysis.get("total_card_spend_value"),
            "suggestions_count": len(missed_savings_analysis.get("suggestions") or []),
        },
    )
    trace = _append_final_answer_trace({"agent_trace": trace}, "card_agent")
    sources = ["db"]
    if (payload.get("rag_context") or {}).get("context"):
        sources.append("rag")
    return {
        "structured_output": unified_context,
        "unified_context": unified_context,
        "tool_results": payload,
        "final_answer": final_answer,
        "sources": sources,
        "confidence": 0.85 if card_data.get("has_data") else 0.4,
        "reason": "multi_agent_card",
        "agent_trace": trace,
    }


def fraud_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    user_message = (state.get("message") or "").strip()
    if not user_message:
        trace = _append_trace(
            state,
            {
                "step": "fraud_agent",
                "agent": "fraud_agent",
                "detail": "no_message",
            },
        )
        unified_context = _build_unified_context(
            "",
            {"fraud_signals": {"has_data": False}, "knowledge_result": {}},
            {},
            {"status": "insufficient_data", "reason": "no_message"},
        )
        return {
            "structured_output": unified_context,
            "unified_context": unified_context,
            "tool_results": {"fraud_signals": {"has_data": False}, "knowledge_result": {}},
            "final_answer": INSUFFICIENT_DATA,
            "sources": [],
            "confidence": 0.25,
            "reason": "multi_agent_fraud_no_message",
            "agent_trace": trace,
        }

    fraud_signals, trace = _run_tool(
        state,
        "fraud_agent",
        "get_fraud_signals",
        get_fraud_signals,
        db,
        user,
        user_message,
    )
    working_state = dict(state)
    working_state["agent_trace"] = trace
    knowledge_result, trace = _run_tool(
        working_state,
        "fraud_agent",
        "search_knowledge",
        tool_search_knowledge,
        user_message,
        "scam",
        3,
    )
    fraud_rule_analysis = _fraud_rule_enrichment(user_message, fraud_signals)
    payload = {
        "fraud_signals": fraud_signals,
        "knowledge_result": knowledge_result,
        "fraud_rule_analysis": fraud_rule_analysis,
    }
    merged_risk = _merge_risk_levels(
        str(fraud_rule_analysis.get("risk_level") or "LOW"),
        str(fraud_signals.get("risk_level") or "LOW"),
    )
    computed_metrics = {
        "risk_level": merged_risk,
        "tool_risk_level": fraud_signals.get("risk_level"),
        "rule_risk_level": fraud_rule_analysis.get("risk_level"),
        "knowledge_hit_count": int(knowledge_result.get("hit_count") or 0),
    }
    fraud_insights = _build_fraud_insights(
        fraud_signals,
        fraud_rule_analysis,
        knowledge_result,
        merged_risk,
    )
    unified_context = _build_unified_context(
        user_message,
        payload,
        computed_metrics,
        fraud_insights,
    )
    final_answer = generate_final_answer(user_message, unified_context, agent_name="fraud_agent")
    trace = _append_agent_trace_node(
        {"agent_trace": trace},
        "fraud_agent",
        ["get_fraud_signals", "search_knowledge"],
        {
            "risk_level": merged_risk,
            "amount_in_message": fraud_rule_analysis.get("amount_in_message"),
        },
    )
    trace = _append_final_answer_trace({"agent_trace": trace}, "fraud_agent")

    sources = ["db"]
    if knowledge_result.get("context"):
        sources.append("rag")

    return {
        "structured_output": unified_context,
        "unified_context": unified_context,
        "tool_results": payload,
        "final_answer": final_answer,
        "sources": sources,
        "confidence": 0.92 if merged_risk == "HIGH" else 0.8,
        "reason": "multi_agent_fraud",
        "agent_trace": trace,
    }


def default_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    unified_context = _build_unified_context(
        state.get("message", ""),
        {},
        {},
        {
            "status": "insufficient_data",
            "reason": "unsupported_query_for_multi_agent",
        },
    )
    trace = _append_trace(
        state,
        {
            "step": "default_agent",
            "agent": "default_agent",
            "reason": "insufficient_data",
            "detail": "unsupported_query_in_multi_agent",
        },
    )
    return {
        "structured_output": unified_context,
        "unified_context": unified_context,
        "tool_results": {},
        "final_answer": INSUFFICIENT_DATA,
        "sources": [],
        "confidence": 0.2,
        "reason": "multi_agent_default_no_data",
        "agent_trace": trace,
    }
