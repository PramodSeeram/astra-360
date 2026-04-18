import os
import logging
import json
import httpx
import time
import re
from typing import Dict, Any, List, Optional
from rag.embeddings import generate_single_embedding
from rag.vector_store import (
    search_knowledge,
    COLLECTION_TRANSACTIONS,
    COLLECTION_INSIGHTS,
    COLLECTION_DOCUMENTS,
    create_category_filter
)

logger = logging.getLogger(__name__)

# Configure LLM Client (RunPod GPU - Ollama)
LLM_URL = os.getenv("LLM_URL", "https://0ruool8gerdycr-11434.proxy.runpod.net/api/generate")
LLM_MODEL = os.getenv("LLM_MODEL", "mistral")
OLLAMA_ROOT_URL = LLM_URL.replace("/api/generate", "")

SYSTEM_PROMPT = """
You are Astra 360, a smart financial co-pilot.

You help users:
- Understand finances
- Optimize spending and credit usage
- Detect fraud risks
- Handle insurance situations

----------------------------------

BEHAVIOR MODE

You operate in 3 modes:
1. Wealth Advisor
2. Fraud Protection Agent
3. Insurance Advisor

----------------------------------

CONVERSATIONAL INTELLIGENCE

- If information is missing, ask questions instead of guessing
- Ask 1-2 focused questions at a time
- Be natural and human-like
- Do not overwhelm the user

Examples:

Instead of:
"I don't have enough data"

Say:
"I can help with that. Could you tell me your monthly income or approximate spending?"

----------------------------------

MEMORY RULE

- Use previous conversation inputs if available
- Do not ask the same question again
- Build on user answers

STRICT RULES:
- Never hallucinate missing values
- Only use available data
- If still insufficient, ask the user
- Be concise and clear
- Ignore transfers when analyzing spending unless explicitly asked

----------------------------------

TONE

- Human, friendly, confident
- Like a financial advisor
- No robotic phrases

----------------------------------

FINAL RESPONSE STRUCTURE (WHEN READY)

Summary:
(1-2 lines)

Key Insights:
(2-4 bullets)

Recommended Actions:

High Priority:
- ...

Medium Priority:
- ...

Low Priority:
- ...

Impact (optional):
- ...

----------------------------------

INTERACTIVE MODE (WHEN DATA IS MISSING)

Respond like:

"I can help you plan this better. Just a quick question:
- What is your monthly income?
- Do you have any EMIs?"

Then wait for the user response.
"""

STANDARD_CATEGORIES = ("Food", "Shopping", "Transport", "Utilities", "Bills", "Entertainment", "Other")

SMALLTALK_RESPONSES = {
    "hi": "Hi, I’m here. What would you like help with in your money life today?",
    "hello": "Hello. Tell me what you want to check, improve, or understand.",
    "hey": "Hey. I can help with spending, bills, credit, and planning.",
}


def call_llm(prompt: str, temperature: float = 0.1) -> str:
    """Calls Ollama generate API with retries and timeout."""
    logger.debug("LLM prompt:\n%s", prompt)
    payload = {
        "model": LLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature
        }
    }

    with httpx.Client() as client:
        # Check health first
        try:
            client.get(OLLAMA_ROOT_URL, timeout=5.0, headers={"Authorization": "Bearer runpod"})
        except Exception:
            pass  # ignore and try actual POST

        for attempt in range(1, 4):
            try:
                response = client.post(
                    LLM_URL,
                    json=payload,
                    timeout=120.0,
                    headers={"Authorization": "Bearer runpod"}
                )
                response.raise_for_status()
                data = response.json()
                return data.get("response", "")
            except Exception as e:
                logger.warning(f"LLM API Error on attempt {attempt}: {e}")
                if attempt == 3:
                    raise RuntimeError(f"Failed to fetch from LLM: {e}")
                time.sleep(2)
    return ""

def detect_agent(query: str) -> str:
    """Deterministic routing for the conversational financial agents."""
    q = (query or "").lower()
    if any(x in q for x in ["fraud", "scam", "otp", "phishing"]):
        return "fraud"
    if any(x in q for x in ["insurance", "claim", "accident", "hospital", "damage", "crash", "policy"]):
        return "insurance"
    return "wealth"


def detect_intent(query: str) -> str:
    """Classify the conversational response shape separately from agent routing."""
    q = (query or "").lower().strip()
    if q in SMALLTALK_RESPONSES or len(q) < 5:
        return "smalltalk"
    if any(term in q for term in ["rate", "score my", "review my", "evaluate", "evaluation"]):
        return "evaluation"
    if any(term in q for term in ["plan", "budget", "save", "sip", "should i", "can i afford", "decision"]):
        return "decision"
    if any(term in q for term in ["where", "how much", "what is", "what's", "when", "which"]):
        return "factual"
    return "default"


def _intent_payload(intent_data: Any, query: str) -> Dict[str, Any]:
    if isinstance(intent_data, dict):
        payload = dict(intent_data)
        payload.setdefault("agent", detect_agent(query))
        payload.setdefault("intent", detect_intent(query))
        payload.setdefault("confidence", 1.0)
        payload.setdefault("filter_category", _detect_filter_category(query))
        return payload

    agent = intent_data if isinstance(intent_data, str) else detect_agent(query)
    return {
        "agent": agent,
        "intent": detect_intent(query),
        "confidence": 1.0,
        "filter_category": _detect_filter_category(query),
    }


def _detect_filter_category(query: str) -> Optional[str]:
    q = (query or "").lower()
    category_aliases = {
        "Food": ("food", "dining", "restaurant", "zomato", "swiggy"),
        "Shopping": ("shopping", "shop", "amazon", "flipkart"),
        "Transport": ("transport", "uber", "ola", "cab", "travel"),
        "Utilities": ("utility", "utilities", "electricity", "water", "gas", "broadband"),
        "Bills": ("bill", "emi", "loan", "rent", "insurance"),
        "Entertainment": ("entertainment", "netflix", "ott", "movie", "subscription"),
        "Transfers": ("transfer", "upi", "neft", "imps", "rtgs"),
    }
    for category, aliases in category_aliases.items():
        if any(alias in q for alias in aliases):
            return category
    return None


def _mentions_transfer(query: str) -> bool:
    q = (query or "").lower()
    return any(term in q for term in ("transfer", "upi", "neft", "imps", "rtgs"))


def _format_money(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return f"₹{float(value):,.0f}"
    except (TypeError, ValueError):
        return None


def _add_line(lines: List[str], label: str, value: Any, suffix: str = "") -> None:
    if value is None or value == "":
        return
    lines.append(f"- {label}: {value}{suffix}")


def _number(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_structured_context(
    user_context: Dict[str, Any],
    retrieved_transactions: Optional[List[Dict[str, Any]]] = None,
    retrieved_insights: Optional[List[Dict[str, Any]]] = None,
    retrieved_docs: Optional[List[str]] = None,
    intent: str = "rag",
    image_analysis: Optional[str] = None,
) -> str:
    user_context = user_context or {}
    profile = user_context.get("profile", {})
    financial = user_context.get("financial_profile", {})
    breakdown = user_context.get("spending_breakdown", {})
    credit = user_context.get("credit_summary", {})
    cards = user_context.get("cards", [])
    insights = user_context.get("insights", [])
    actions = user_context.get("recommended_actions", [])
    total_limit = _number(credit.get("total_limit"))
    used_credit = _number(credit.get("used"))
    shopping = _number(breakdown.get("Shopping"))
    savings = _number(user_context.get("spending_summary", {}).get("savings"))

    lines = ["Transactions Summary:"]
    _add_line(lines, "Total Spending", _format_money(financial.get("total_spending")))
    _add_line(lines, "Monthly Income", _format_money(profile.get("income")))
    _add_line(lines, "EMI", _format_money(financial.get("emi")))
    _add_line(lines, "Estimated Savings", _format_money(user_context.get("spending_summary", {}).get("savings")))
    if len(lines) == 1:
        lines.append("- I don't have enough data")

    lines.append("")
    lines.append("Spending Breakdown:")
    for category in STANDARD_CATEGORIES:
        amount = breakdown.get(category)
        if amount:
            lines.append(f"- {category}: {_format_money(amount)}")
    if lines[-1] == "Spending Breakdown:":
        lines.append("- I don't have enough data")

    lines.append("")
    lines.append("Credit Summary:")
    _add_line(lines, "Score", credit.get("score"))
    _add_line(lines, "Utilization", credit.get("utilization"), "%")
    _add_line(lines, "Total Limit", _format_money(credit.get("total_limit")))
    _add_line(lines, "Used Credit", _format_money(credit.get("used")))
    _add_line(lines, "Risk Level", credit.get("risk"))
    if lines[-1] == "Credit Summary:":
        lines.append("- I don't have enough data")

    lines.append("")
    lines.append("Card Usage Summary:")
    for card in cards[:4]:
        bank = card.get("bank") or "Card"
        card_type = card.get("type") or "unknown type"
        used = _format_money(card.get("used")) or "unknown usage"
        limit = _format_money(card.get("limit")) or "unknown limit"
        utilization = card.get("utilization_pct")
        rewards = card.get("key_offers") or "No reward data available"
        lines.append(
            f"- {bank} {card_type}: used {used} of {limit}; "
            f"utilization {utilization if utilization is not None else 'unknown'}%; rewards: {rewards}"
        )
    if lines[-1] == "Card Usage Summary:":
        lines.append("- I don't have enough data")

    lines.append("")
    lines.append("Insights:")
    for insight in insights[:4]:
        if insight:
            lines.append(f"- {insight}")
    if lines[-1] == "Insights:":
        lines.append("- I don't have enough data")

    lines.append("")
    lines.append("Recommended Actions:")
    for action in actions[:4]:
        if action:
            lines.append(f"- {action}")
    if lines[-1] == "Recommended Actions:":
        lines.append("- Upload more recent transactions to unlock specific recommendations.")

    lines.append("")
    lines.append("Priority Guidance Inputs:")
    if total_limit and used_credit is not None:
        target_balance = total_limit * 0.30
        reduction_needed = max(0.0, used_credit - target_balance)
        if reduction_needed > 0:
            lines.append(f"- Credit target: reduce usage by {_format_money(reduction_needed)} to reach 30% utilization")
    if shopping and shopping > 0:
        lines.append(f"- Shopping cap target: {_format_money(shopping * 0.85)} per month")
    if savings is not None:
        lines.append(f"- Savings target: increase monthly savings by {_format_money(max(1000.0, savings * 0.10))}")
    if lines[-1] == "Priority Guidance Inputs:":
        lines.append("- I don't have enough data")

    if image_analysis:
        lines.append("")
        lines.append("Image Analysis:")
        lines.append(f"- {image_analysis}")

    if intent == "wealth":
        lines.append("")
        lines.append("Qdrant Retrieval Context:")
        if retrieved_transactions:
            lines.append(f"- Transactions: {json.dumps(retrieved_transactions[:5], ensure_ascii=False)}")
        if retrieved_insights:
            lines.append(f"- Retrieved Insights: {json.dumps(retrieved_insights[:3], ensure_ascii=False)}")
        if retrieved_docs:
            lines.append(f"- Documents: {json.dumps(retrieved_docs[:2], ensure_ascii=False)}")
        if not retrieved_transactions and not retrieved_insights and not retrieved_docs:
            lines.append("- I don't have enough data")

    return "\n".join(lines)


def _format_memory(memory: Any) -> str:
    if not memory:
        return "- No previous answers yet."
    if isinstance(memory, str):
        return memory.strip() or "- No previous answers yet."
    if isinstance(memory, list):
        lines = []
        for item in memory[-8:]:
            if isinstance(item, dict):
                role = item.get("role", "user")
                content = item.get("content", "")
                if content:
                    lines.append(f"- {role}: {content}")
        return "\n".join(lines) if lines else "- No previous answers yet."
    return str(memory)


def _build_final_prompt(query: str, context: str, memory: Any = None, response_intent: str = "decision") -> str:
    intent_instruction = (
        "Provide a decision-ready financial plan with tradeoffs."
        if response_intent == "decision"
        else "Provide an evaluation with a clear rating, reasons, and next steps."
    )
    final_prompt = f"""
{SYSTEM_PROMPT}

User Financial Data:
{context}

Conversation Memory:
{_format_memory(memory)}

User Question:
{query}

Instructions:
- Answer based only on context
- Use conversation memory when it contains previous user answers
- Do not ask for information already present in memory
- Prioritize clarity over length
- {intent_instruction}
- Give practical steps the user can follow immediately when enough data is present
- Use exactly these headings: Summary:, Key Insights:, Recommended Actions:, Impact:
- Under Recommended Actions, use High Priority:, Medium Priority:, and Low Priority:
- Make every action direct, specific, and measurable when context provides numbers
- Avoid these phrases: "Based on the data provided", "It appears that", "You may consider"

Answer:
"""
    logger.debug("Final LLM prompt:\n%s", final_prompt)
    return final_prompt


def _build_natural_prompt(query: str, context: str, memory: Any = None, style: str = "default") -> str:
    style_instruction = {
        "smalltalk": "Reply naturally in 1-2 friendly sentences. Do not use headings.",
        "factual": "Reply directly and naturally. Do not use headings unless needed.",
        "default": "Reply naturally and clearly. Use brief prose unless structure is necessary.",
    }.get(style, "Reply naturally and clearly.")
    prompt = f"""
{SYSTEM_PROMPT}

User Financial Data:
{context}

Conversation Memory:
{_format_memory(memory)}

User Question:
{query}

Instructions:
- Answer based only on context and memory
- If information is missing, ask only one focused follow-up question
- {style_instruction}
- Never use the structured finance template unless the question clearly needs planning or evaluation

Answer:
"""
    logger.debug("Natural LLM prompt:\n%s", prompt)
    return prompt


def _ensure_response_format(text: str) -> str:
    clean = (text or "").strip()
    if not clean:
        return "I don’t have enough financial data yet. Please upload a statement."

    clean = _remove_generic_language(clean)
    if all(header in clean for header in ("Summary:", "Key Insights:", "Recommended Actions:")):
        if "Impact:" not in clean:
            clean = f"{clean}\n\nImpact:\n- Not enough data to estimate impact yet."
        return clean
    return (
        "Summary:\n"
        f"{clean}\n\n"
        "Key Insights:\n"
        "- I don’t have enough data beyond the available financial context.\n\n"
        "Recommended Actions:\n"
        "High Priority:\n"
        "- Upload a recent bank statement.\n\n"
        "Medium Priority:\n"
        "- Add active card and EMI details.\n\n"
        "Low Priority:\n"
        "- Review the dashboard once the data refresh is complete.\n\n"
        "Impact:\n"
        "- A complete statement unlocks specific savings and credit targets."
    )


def _remove_generic_language(text: str) -> str:
    replacements = {
        "Based on the data provided, ": "",
        "Based on the provided data, ": "",
        "Based on your data, ": "",
        "It appears that ": "",
        "It seems that ": "",
        "You may consider ": "",
        "You should consider ": "",
        "I recommend that you ": "",
    }
    cleaned = text
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)
        cleaned = cleaned.replace(old.lower(), new)
    return cleaned.strip()


def _has_financial_data(
    user_context: Dict[str, Any],
    retrieved_transactions: List[Dict[str, Any]],
    retrieved_insights: List[Dict[str, Any]],
    retrieved_docs: List[str],
) -> bool:
    user_context = user_context or {}
    financial = user_context.get("financial_profile", {})
    credit = user_context.get("credit_summary", {})
    breakdown = user_context.get("spending_breakdown", {})

    numeric_values = [
        financial.get("total_spending"),
        financial.get("emi"),
        credit.get("score"),
        credit.get("utilization"),
        credit.get("total_limit"),
        credit.get("used"),
        *breakdown.values(),
    ]
    return any(_number(value) and _number(value) > 0 for value in numeric_values) or bool(
        retrieved_transactions or retrieved_insights or retrieved_docs
    )


def _has_card_data(user_context: Dict[str, Any]) -> bool:
    return bool((user_context or {}).get("cards"))


def _has_income_or_spending_text(text: str) -> bool:
    text = (text or "").lower()
    money_pattern = r"(?:₹|rs\.?|inr)?\s*\d+(?:,\d{2,3})*(?:\.\d+)?\s*(?:k|lakh|lac|cr|crore)?"
    has_amount = bool(re.search(money_pattern, text))
    has_finance_word = any(
        word in text
        for word in ["income", "salary", "earn", "spend", "expense", "emi", "rent", "budget", "50k", "₹"]
    )
    return has_amount and has_finance_word


def _has_fraud_scenario(query: str, memory: Any = None) -> bool:
    text = f"{query}\n{_format_memory(memory)}".lower()
    detail_words = [
        "received", "message", "link", "call", "otp", "password", "upi", "bank",
        "clicked", "shared", "asked", "payment", "account", "card", "number"
    ]
    return any(word in text for word in detail_words)


def _has_insurance_description(query: str, memory: Any = None, image_analysis: Optional[str] = None) -> bool:
    if image_analysis:
        return True
    query_text = (query or "").lower().strip()
    if query_text in {"insurance", "claim", "insurance claim", "help with insurance"}:
        return False
    text = f"{query}\n{_format_memory(memory)}".lower()
    detail_words = [
        "car", "bike", "vehicle", "bumper", "scratch", "damage", "accident", "crash",
        "hospital", "medical", "doctor", "bill", "policy", "claim", "injury"
    ]
    return any(word in text for word in detail_words)


def _interactive_response(
    intent: str,
    response: str,
    actions: Optional[List[str]] = None,
    ui_action: Optional[str] = None,
    sources: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "type": f"{intent}_follow_up",
        "response": response,
        "ui_action": ui_action,
        "actions": actions or [],
        "sources": sources or [],
    }


def _fallback_response(intent: str, sources: Optional[List[str]] = None) -> Dict[str, Any]:
    if intent == "fraud":
        return _interactive_response(
            intent,
            "I can help you check this quickly. What exactly did you receive?\n- Was it a message, call, link, or OTP request?\n- Did you click anything or share any details?",
            actions=["describe_message", "block_card", "call_bank"],
            sources=sources,
        )
    if intent == "insurance":
        return _interactive_response(
            intent,
            "I can help with the claim steps. Just a quick question:\n- Was this a car accident or a medical case?\n- Do you have a photo, bill, or short description of what happened?",
            actions=["upload_photo", "describe_incident"],
            ui_action="open_camera",
            sources=sources,
        )
    return _interactive_response(
        intent,
        "I can help you plan this better. Just a quick question:\n- What is your monthly income?\n- Do you have any EMIs or major fixed expenses?",
        actions=["share_income", "upload_statement"],
        sources=sources,
    )


def _was_question_already_asked(memory: Any, phrase: str) -> bool:
    text = _format_memory(memory).lower()
    return phrase.lower() in text


def _credit_follow_up_response(user_context: Dict[str, Any], memory: Any, sources: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    credit = (user_context or {}).get("credit_summary") or {}
    total_limit = _number(credit.get("total_limit")) or 0.0
    used_credit = _number(credit.get("used"))
    emi = _number(((user_context or {}).get("loan_summary") or {}).get("total_emi")) or 0.0

    if total_limit > 0 and used_credit is not None:
        return None

    if not _was_question_already_asked(memory, "credit card limit") and not _was_question_already_asked(memory, "limit and current outstanding"):
        return _interactive_response(
            "wealth",
            "I can assess your credit health. What is your credit card limit and current outstanding amount?",
            actions=["share_card_limit", "share_outstanding"],
            sources=sources,
        )

    if emi <= 0 and not _was_question_already_asked(memory, "emi"):
        return _interactive_response(
            "wealth",
            "I can finish the credit assessment once I know your monthly EMI amount. What is it?",
            actions=["share_emi"],
            sources=sources,
        )

    return {
        "type": "wealth_follow_up",
        "response": "I need your credit card limit and outstanding amount to assess your credit health.",
        "actions": ["share_card_limit", "share_outstanding"],
        "sources": sources or [],
    }


def _smalltalk_response(query: str) -> str:
    q = (query or "").strip().lower()
    return SMALLTALK_RESPONSES.get(q, "I’m here with you. Ask me about spending, bills, credit, or planning.")


def _direct_factual_response(query: str, user_context: Dict[str, Any]) -> Optional[str]:
    q = (query or "").lower()
    spending = _number(((user_context or {}).get("financial_profile") or {}).get("total_spending"))
    income = _number(((user_context or {}).get("profile") or {}).get("income"))
    credit = (user_context or {}).get("credit_summary") or {}
    utilization = _number(credit.get("utilization"))

    if "how much" in q and "spend" in q and spending is not None:
        return f"You’ve spent {_format_money(spending)} in the recent 30-day window I can see."
    if "how much" in q and ("income" in q or "salary" in q) and income is not None:
        return f"Your detected monthly income is {_format_money(income)}."
    if "where" in q and "credit" in q and utilization is not None:
        return f"Your current credit utilization is {utilization:.1f}%."
    return None


def _build_budget_plan_context(user_context: Dict[str, Any]) -> Optional[Dict[str, float]]:
    profile = (user_context or {}).get("profile") or {}
    spending = (user_context or {}).get("spending_summary") or {}
    loan_summary = (user_context or {}).get("loan_summary") or {}

    income = _number(profile.get("income"))
    monthly_spend = _number(spending.get("monthly_spend"))
    emi = _number(loan_summary.get("total_emi")) or 0.0
    if income is None or monthly_spend is None:
        return None

    savings = max(0.0, income - monthly_spend - emi)
    needs = round(income * 0.5, 2)
    wants = round(income * 0.3, 2)
    savings_target = round(income * 0.2, 2)
    sip_low = round(savings * 0.2, 2)
    sip_high = round(savings * 0.3, 2)

    return {
        "income": round(income, 2),
        "spend": round(monthly_spend, 2),
        "emi": round(emi, 2),
        "savings": round(savings, 2),
        "needs": needs,
        "wants": wants,
        "savings_target": savings_target,
        "sip_low": sip_low,
        "sip_high": sip_high,
    }


def _credit_assessment_response(user_context: Dict[str, Any]) -> Optional[str]:
    credit = (user_context or {}).get("credit_summary") or {}
    total_limit = _number(credit.get("total_limit"))
    used_credit = _number(credit.get("used_credit"))
    emi = _number(credit.get("emi"))
    score = credit.get("credit_score") or credit.get("score")

    if total_limit in (None, 0) or used_credit is None or emi is None:
        return None

    utilization = round((used_credit / total_limit) * 100, 1) if total_limit > 0 else None
    if utilization is None:
        return None

    if utilization <= 30:
        why = f"Your utilization is a healthy {utilization:.1f}% of your total credit limit."
        fix = "Keep card usage under 30% and pay before the statement date to protect your score."
        outlook = "good"
    elif utilization <= 50:
        why = f"Your utilization is {utilization:.1f}%, which is above the ideal range."
        fix = "Bring balances below 30% of limit over the next billing cycle."
        outlook = "mixed"
    else:
        why = f"Your utilization is high at {utilization:.1f}%, which can drag your score down."
        fix = "Pay down revolving balances aggressively and avoid new card spends until utilization improves."
        outlook = "bad"

    emi_note = f" Monthly EMI outflow is {_format_money(emi)}."
    score_note = f" Reported credit score: {score}." if score else ""
    return (
        f"Your credit picture is {outlook}. {why}{emi_note}{score_note} "
        f"Actionable fix: {fix}"
    )


def _missing_required_response(
    agent: str,
    response_intent: str,
    query: str,
    user_context: Dict[str, Any],
    memory: Any,
    image_analysis: Optional[str],
    retrieved_transactions: List[Dict[str, Any]],
    retrieved_insights: List[Dict[str, Any]],
    retrieved_docs: List[str],
    sources: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    combined_text = f"{query}\n{_format_memory(memory)}"
    if agent == "fraud":
        if not _has_fraud_scenario(query, memory):
            return _fallback_response(agent, sources=sources)
        return None

    if agent == "insurance":
        if not _has_insurance_description(query, memory, image_analysis):
            return _fallback_response(agent, sources=sources)
        return None

    if any(word in query.lower() for word in ["credit", "card", "utilization", "utilisation", "score"]):
        credit_follow_up = _credit_follow_up_response(user_context, memory, sources=sources)
        if credit_follow_up:
            return credit_follow_up

    has_context_data = _has_financial_data(user_context, retrieved_transactions, retrieved_insights, retrieved_docs)
    has_memory_data = _has_income_or_spending_text(combined_text)
    has_cards = _has_card_data(user_context)
    asks_card_usage = any(word in query.lower() for word in ["card", "credit usage", "utilization", "utilisation"])

    if asks_card_usage and not (has_cards or (user_context.get("credit_summary") or {}).get("utilization")):
        return _interactive_response(
            agent,
            "I can help you optimize card usage. Just a quick question:\n- Which card do you want to review?\n- Do you know its limit and current outstanding amount?",
            actions=["share_card_limit", "share_outstanding", "upload_statement"],
            sources=sources,
        )

    if has_context_data or has_memory_data or has_cards:
        return None

    if response_intent in {"decision", "evaluation"}:
        if not _was_question_already_asked(memory, "monthly income") and not _has_income_or_spending_text(combined_text):
            return _interactive_response(
                agent,
                "I can help with that. What is your monthly income?",
                actions=["share_income"],
                sources=sources,
            )
        if not _was_question_already_asked(memory, "emi") and "emi" not in combined_text.lower():
            return _interactive_response(
                agent,
                "I can help with that. Do you have any EMIs or major fixed expenses?",
                actions=["share_emi"],
                sources=sources,
            )

    return _fallback_response(agent, sources=sources)

def get_chat_response(
    query: str,
    user_context: Dict[str, Any] = None,
    intent_data: Any = None,
    intent: Optional[str] = None,
    memory: Any = None,
    image_analysis: Optional[str] = None,
) -> Dict[str, Any]:
    """Routes the query and asks the LLM with grounded, structured financial context."""
    if not query or not query.strip():
        raise ValueError("Query cannot be empty.")

    if intent_data is None and intent is not None:
        intent_data = intent

    route = _intent_payload(intent_data, query)
    agent = route.get("agent", "wealth")
    response_intent = route.get("intent", "default")
    filter_category = route.get("filter_category")

    if response_intent == "smalltalk":
        return {
            "type": "smalltalk",
            "response": _smalltalk_response(query),
            "ui_action": None,
            "actions": [],
            "sources": [],
        }

    preflight_response = _missing_required_response(
        agent,
        response_intent,
        query,
        user_context or {},
        memory,
        image_analysis,
        [],
        [],
        [],
        sources=[],
    )
    if preflight_response:
        return preflight_response

    # RAG Retrieval Layer
    retrieved_transactions = []
    retrieved_insights = []
    retrieved_docs = []
    sources = []

    if agent == "wealth":
        try:
            query_embedding = generate_single_embedding(query)

            # 1. Filter Context if applicable
            q_filter = create_category_filter(filter_category) if filter_category else None

            # 2. Retrieve Transactions
            tx_results = search_knowledge(COLLECTION_TRANSACTIONS, query_embedding, top_k=5, filter_conditions=q_filter)
            retrieved_transactions = [res["payload"] for res in tx_results]
            if not _mentions_transfer(query):
                retrieved_transactions = [
                    tx for tx in retrieved_transactions
                    if tx.get("category") != "Transfers"
                ]

            # 3. Retrieve Insights
            in_results = search_knowledge(COLLECTION_INSIGHTS, query_embedding, top_k=2)
            retrieved_insights = [res["payload"] for res in in_results]

            # 4. Retrieve General Documents
            doc_results = search_knowledge(COLLECTION_DOCUMENTS, query_embedding, top_k=2)
            for res in doc_results:
                retrieved_docs.append(res["payload"].get("text", ""))
                src = res["payload"].get("filename")
                if src and src not in sources:
                    sources.append(src)

        except Exception as e:
            logger.error(f"RAG Error: {e}")

    context = _build_structured_context(
        user_context or {},
        retrieved_transactions=retrieved_transactions,
        retrieved_insights=retrieved_insights,
        retrieved_docs=retrieved_docs,
        intent=agent,
        image_analysis=image_analysis,
    )

    missing_response = _missing_required_response(
        agent,
        response_intent,
        query,
        user_context or {},
        memory,
        image_analysis,
        retrieved_transactions,
        retrieved_insights,
        retrieved_docs,
        sources=sources,
    )
    if missing_response:
        return missing_response

    factual_response = None
    if response_intent == "factual":
        factual_response = _direct_factual_response(query, user_context or {})
        if factual_response:
            return {
                "type": "factual",
                "response": factual_response,
                "ui_action": None,
                "actions": [],
                "sources": sources,
            }

    if any(word in query.lower() for word in ["credit", "card", "utilization", "utilisation", "score"]):
        credit_response = _credit_assessment_response(user_context or {})
        if credit_response:
            return {
                "type": "evaluation" if response_intent == "evaluation" else "factual",
                "response": credit_response,
                "ui_action": "view_cards",
                "actions": ["reduce_utilization", "pay_on_time", "review_cards"],
                "sources": sources,
            }

    if response_intent == "decision" and any(word in query.lower() for word in ["plan", "budget", "save", "sip"]):
        plan_context = _build_budget_plan_context(user_context or {})
        if plan_context:
            context += (
                "\n\nBudget Plan Inputs:\n"
                f"- Avg Monthly Income: {_format_money(plan_context['income'])}\n"
                f"- Avg Monthly Spend: {_format_money(plan_context['spend'])}\n"
                f"- Monthly EMI: {_format_money(plan_context['emi'])}\n"
                f"- Estimated Savings: {_format_money(plan_context['savings'])}\n"
                f"- Needs Target: {_format_money(plan_context['needs'])}\n"
                f"- Wants Target: {_format_money(plan_context['wants'])}\n"
                f"- Savings Target: {_format_money(plan_context['savings_target'])}\n"
                f"- SIP Suggestion Range: {_format_money(plan_context['sip_low'])} to {_format_money(plan_context['sip_high'])}"
            )

    prompt = (
        _build_final_prompt(query, context, memory=memory, response_intent=response_intent)
        if response_intent in {"decision", "evaluation"}
        else _build_natural_prompt(query, context, memory=memory, style=response_intent)
    )

    try:
        raw_output = call_llm(prompt, temperature=0.1)

        parts = raw_output.split("FOLLOW_UP:")
        if response_intent in {"decision", "evaluation"}:
            response_text = _ensure_response_format(parts[0])
        else:
            response_text = _remove_generic_language((parts[0] or "").strip()) or _smalltalk_response(query)
        follow_ups = []
        if len(parts) > 1:
            follow_ups = [tag.strip().strip('[]"') for tag in parts[1].split(",") if tag.strip()]

        ui_action = None
        if agent == "wealth" and any(word in query.lower() for word in ["budget", "plan"]):
            ui_action = "show_budget_chart"
        elif agent == "wealth" and any(word in query.lower() for word in ["credit", "card", "usage", "utilization"]):
            ui_action = "view_cards"
        elif agent == "insurance":
            ui_action = "open_camera" if not image_analysis else None
        elif any(kw in query.lower() for kw in ["upload", "statement"]):
            ui_action = "open_file_upload"

        return {
            "type": "upload_required" if ui_action == "open_file_upload" else response_intent,
            "response": response_text,
            "ui_action": ui_action,
            "actions": follow_ups[:3] or _default_actions(agent),
            "sources": sources
        }
    except Exception as e:
        logger.error(f"LLM Error: {e}")
        return _fallback_response(agent, sources=sources)


def _default_actions(intent: str) -> List[str]:
    if intent == "fraud":
        return ["block_card", "change_password", "call_bank"]
    if intent == "insurance":
        return ["upload_photo", "collect_documents", "contact_insurer"]
    if intent == "wealth":
        return ["set_budget", "reduce_top_category", "increase_savings"]
    return ["view_transactions", "upload_statement"]
