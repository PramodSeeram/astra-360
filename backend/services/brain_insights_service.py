import datetime as dt
import hashlib
import json
import re
from collections import Counter
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from models import Transaction, User, UserInsight
from services.financial_engine import (
    compute_snapshot_from_transactions,
    snapshot_category_distribution,
    transactions_in_month,
)
from services.llm_service import call_llm, extract_json_object

INSIGHT_TYPES = [
    "income",
    "spending",
    "risk",
    "behavior",
    "optimization",
]

_RENT_KEYWORDS = ("rent", "house rent", "flat rent")
_FOOD_MERCHANTS = ("swiggy", "zomato")
_PAYLATER_KEYWORDS = ("lazypay", "lazy pay", "simpl", "slice", "paylater", "pay later", "postpe")
_CARD_BILL_KEYWORDS = ("card", "credit")
_NUMERIC_TOKEN_RE = re.compile(r"₹?[\d,]+(?:\.\d+)?%?")


def _format_inr(amount: float) -> str:
    return f"₹{amount:,.0f}"


def _month_label(month_key: Optional[str]) -> str:
    if not month_key:
        return "Latest snapshot"
    try:
        return dt.datetime.strptime(month_key, "%Y-%m").strftime("%b %Y")
    except ValueError:
        return month_key


def _insight_id(month_key: Optional[str], slug: str) -> str:
    digest = hashlib.md5(f"{month_key or 'latest'}:{slug}".encode("utf-8")).hexdigest()[:10]
    return f"{slug}-{digest}"


def _clean_suggestion(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = value.strip()
    return cleaned or None


def _contains_keyword(text: Optional[str], keywords: Iterable[str]) -> bool:
    lowered = (text or "").lower()
    return any(keyword in lowered for keyword in keywords)


def _most_common_day(transactions: list[Transaction]) -> Optional[int]:
    days = [tx.date.day for tx in transactions if tx.date]
    if not days:
        return None
    return Counter(days).most_common(1)[0][0]


def _numeric_signature(*parts: Optional[str]) -> tuple[str, ...]:
    joined = "\n".join(part or "" for part in parts)
    return tuple(_NUMERIC_TOKEN_RE.findall(joined))


def _append_insight(
    insights: list[dict],
    month_key: Optional[str],
    *,
    slug: str,
    insight_type: str,
    title: str,
    text: str,
    time_label: str,
    suggestion: Optional[str] = None,
    action: Optional[str] = None,
) -> None:
    if not text:
        return
    insights.append(
        {
            "id": _insight_id(month_key, slug),
            "type": insight_type,
            "title": title,
            "text": text,
            "suggestion": _clean_suggestion(suggestion),
            "time": time_label,
            "action": action,
        }
    )


def _salary_insight(snapshot, month_label_value: str) -> Optional[dict]:
    if snapshot.salary <= 0:
        return None
    return {
        "slug": "income-snapshot",
        "type": "income",
        "title": "Income snapshot",
        "text": f"Your monthly salary is approximately {_format_inr(snapshot.salary)}.",
        "time": month_label_value,
    }


def _cashflow_insight(snapshot, month_label_value: str, top_category: Optional[str]) -> Optional[dict]:
    if snapshot.salary <= 0 or snapshot.expenses <= snapshot.salary:
        return None
    overspend = snapshot.expenses - snapshot.salary
    suggestion = None
    if top_category:
        suggestion = f"Review {top_category.lower()} spending first to ease cash-flow pressure."
    return {
        "slug": "overspending-alert",
        "type": "risk",
        "title": "Overspending alert",
        "text": f"Your expenses exceed your income by {_format_inr(overspend)} in {month_label_value}.",
        "suggestion": suggestion,
        "time": month_label_value,
    }


def _spending_insight(snapshot, month_label_value: str, top_category: Optional[str], top_amount: float) -> Optional[dict]:
    if snapshot.expenses <= 0:
        return None
    if top_category and top_amount > 0:
        text = (
            f"You spent {_format_inr(snapshot.expenses)} in {month_label_value}, led by "
            f"{top_category} at {_format_inr(top_amount)}."
        )
    else:
        text = f"You spent {_format_inr(snapshot.expenses)} in {month_label_value}."
    return {
        "slug": "spending-summary",
        "type": "spending",
        "title": "Monthly spending",
        "text": text,
        "time": month_label_value,
    }


def _rent_insight(snapshot, month_key: Optional[str], month_transactions: list[Transaction], month_label_value: str) -> Optional[dict]:
    if snapshot.rent_total <= 0:
        return None
    rent_transactions = [
        tx
        for tx in month_transactions
        if (tx.type or "").lower() == "debit"
        and (
            _contains_keyword(tx.description, _RENT_KEYWORDS)
            or _contains_keyword(tx.category, ("rent",))
        )
    ]
    day = _most_common_day(rent_transactions)
    if day is not None:
        text = f"You pay fixed rent of {_format_inr(snapshot.rent_total)} around the {day}th of each month."
    else:
        text = f"You pay fixed rent of {_format_inr(snapshot.rent_total)} each month."
    return {
        "slug": "rent-rhythm",
        "type": "behavior",
        "title": "Rent rhythm",
        "text": text,
        "time": month_label_value if month_key else "Latest snapshot",
    }


def _food_delivery_insight(month_transactions: list[Transaction], month_label_value: str) -> Optional[dict]:
    matched = [
        tx
        for tx in month_transactions
        if (tx.type or "").lower() == "debit"
        and (
            _contains_keyword(tx.description, _FOOD_MERCHANTS)
            or (tx.category or "").strip().lower() == "food"
        )
    ]
    if len(matched) < 2:
        return None

    total = sum(abs(float(tx.amount or 0.0)) for tx in matched)
    merchants = sorted(
        {
            merchant.title()
            for merchant in _FOOD_MERCHANTS
            if any(merchant in (tx.description or "").lower() for tx in matched)
        }
    )
    merchant_text = " and ".join(merchants[:2]) if merchants else "food delivery apps"
    return {
        "slug": "food-delivery-habit",
        "type": "behavior",
        "title": "Food delivery habit",
        "text": (
            f"You used {merchant_text} {len(matched)} times in {month_label_value}, "
            f"totalling {_format_inr(total)}."
        ),
        "suggestion": "Watch repeat delivery orders if you want to improve monthly cash flow.",
        "time": month_label_value,
    }


def _subscriptions_insight(user: User, snapshot, month_label_value: str) -> Optional[dict]:
    active_names = [
        (subscription.name or "").strip()
        for subscription in user.subscriptions
        if (subscription.status or "active").lower() == "active" and (subscription.name or "").strip()
    ]
    if not active_names:
        active_names = [
            str(item.get("name", "")).strip()
            for item in (snapshot.subscriptions_items or [])
            if str(item.get("name", "")).strip()
        ]

    unique_names: list[str] = []
    for name in active_names:
        if name not in unique_names:
            unique_names.append(name)

    if len(unique_names) < 2 and snapshot.subscriptions_total <= 0:
        return None

    preview = ", ".join(unique_names[:3]) if unique_names else "multiple recurring services"
    suggestion = None
    if len(unique_names) >= 3:
        suggestion = "Review overlapping subscriptions to free up monthly budget."

    return {
        "slug": "subscription-stack",
        "type": "optimization",
        "title": "Subscription stack",
        "text": f"You maintain multiple subscriptions including {preview}.",
        "suggestion": suggestion,
        "time": month_label_value,
    }


def _card_bill_insight(user: User, month_label_value: str) -> Optional[dict]:
    card_bills = [
        bill
        for bill in user.bills
        if _contains_keyword(bill.name, _CARD_BILL_KEYWORDS)
    ]
    if not card_bills:
        return None

    days = sorted({bill.due_date.day for bill in card_bills if bill.due_date})
    if not days:
        return None

    if len(days) >= 2:
        day_text = " and ".join(str(day) for day in days[:2])
        text = f"Your credit card bills usually fall around the {day_text}th each month."
    else:
        text = f"Your credit card bill is typically due around the {days[0]}th each month."

    return {
        "slug": "card-bill-rhythm",
        "type": "behavior",
        "title": "Card bill rhythm",
        "text": text,
        "time": "Upcoming" if any((bill.status or "").lower() != "paid" for bill in card_bills) else month_label_value,
        "action": "bills",
    }


def _paylater_insight(month_transactions: list[Transaction], month_label_value: str) -> Optional[dict]:
    matched = [
        tx
        for tx in month_transactions
        if (tx.type or "").lower() == "debit"
        and _contains_keyword(tx.description, _PAYLATER_KEYWORDS)
    ]
    if len(matched) < 2:
        return None

    total = sum(abs(float(tx.amount or 0.0)) for tx in matched)
    if total < 1500:
        return None

    return {
        "slug": "paylater-usage",
        "type": "risk",
        "title": "Pay-later usage",
        "text": f"You used pay-later services {len(matched)} times in {month_label_value}, totalling {_format_inr(total)}.",
        "suggestion": "Keep pay-later usage in check so upcoming obligations do not stack up.",
        "time": month_label_value,
    }


def _polish_insights_with_llm(insights: list[dict]) -> list[dict]:
    if not insights:
        return insights

    payload = [
        {
            "index": index,
            "type": insight["type"],
            "title": insight["title"],
            "text": insight["text"],
            "suggestion": insight.get("suggestion"),
        }
        for index, insight in enumerate(insights)
    ]
    prompt = (
        "You are a financial AI editor.\n"
        "Rewrite the insight copy for clarity and polish without changing the facts.\n"
        "Rules:\n"
        "- Return JSON only in the form {\"insights\": [...]}.\n"
        "- Keep the same indexes.\n"
        "- Do not add or remove insights.\n"
        "- Do not change, add, or infer numbers.\n"
        "- Keep each text field to one sentence.\n"
        "- Keep suggestion optional and brief.\n"
        "- Never describe negative savings as debt.\n"
        f"Insights:\n{json.dumps(payload, ensure_ascii=True)}"
    )

    try:
        raw = call_llm(prompt, temperature=0.0)
        parsed = extract_json_object(raw) or {}
        rewritten = parsed.get("insights")
        if not isinstance(rewritten, list):
            return insights

        polished = list(insights)
        for item in rewritten:
            if not isinstance(item, dict):
                continue
            index = item.get("index")
            if not isinstance(index, int) or index < 0 or index >= len(insights):
                continue

            original = insights[index]
            title = str(item.get("title") or original["title"]).strip()
            text = str(item.get("text") or original["text"]).strip()
            suggestion = _clean_suggestion(str(item.get("suggestion")).strip()) if item.get("suggestion") is not None else original.get("suggestion")

            if "debt" in text.lower():
                continue
            if _numeric_signature(title, text, suggestion) != _numeric_signature(
                original["title"],
                original["text"],
                original.get("suggestion"),
            ):
                continue

            polished[index] = {
                **original,
                "title": title or original["title"],
                "text": text or original["text"],
                "suggestion": suggestion,
            }
        return polished
    except Exception:
        return insights


def generate_insights(db: Session, user: User, limit: int = 6, use_llm: bool = True) -> list[dict]:
    transactions = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .order_by(Transaction.date.asc(), Transaction.id.asc())
        .all()
    )
    snapshot = compute_snapshot_from_transactions(transactions)
    if not snapshot.transactions_found:
        return []

    month_key = snapshot.headline_month
    month_label_value = _month_label(month_key)
    month_transactions = (
        transactions_in_month(transactions, snapshot.current_year, snapshot.current_month)
        if snapshot.current_year is not None and snapshot.current_month is not None
        else []
    )
    category_dist = snapshot_category_distribution(transactions, snapshot)
    top_category = None
    top_amount = 0.0
    if category_dist:
        top_category = max(category_dist, key=category_dist.get)
        top_amount = float(category_dist[top_category])

    rule_candidates = [
        _cashflow_insight(snapshot, month_label_value, top_category),
        _salary_insight(snapshot, month_label_value),
        _spending_insight(snapshot, month_label_value, top_category, top_amount),
        _rent_insight(snapshot, month_key, month_transactions, month_label_value),
        _food_delivery_insight(month_transactions, month_label_value),
        _subscriptions_insight(user, snapshot, month_label_value),
        _card_bill_insight(user, month_label_value),
        _paylater_insight(month_transactions, month_label_value),
    ]

    insights: list[dict] = []
    seen_titles: set[str] = set()
    for candidate in rule_candidates:
        if not candidate:
            continue
        title = candidate["title"]
        if title in seen_titles:
            continue
        seen_titles.add(title)
        _append_insight(
            insights,
            month_key,
            slug=candidate["slug"],
            insight_type=candidate["type"],
            title=title,
            text=candidate["text"],
            suggestion=candidate.get("suggestion"),
            time_label=candidate["time"],
            action=candidate.get("action"),
        )
        if len(insights) >= limit:
            break

    if use_llm:
        insights = _polish_insights_with_llm(insights)
    return insights[:limit]


def prepend_processing_banner(insights: list[dict]) -> list[dict]:
    banner = {
        "id": "processing-banner",
        "type": "system",
        "title": "Processing update",
        "text": "Your data is still being processed. These insights use the latest reliable snapshot.",
        "suggestion": None,
        "time": "Now",
        "action": None,
    }
    return [banner, *insights]


def upsert_user_insights(db: Session, user: User, limit: int = 6) -> list[dict]:
    insights = generate_insights(db, user, limit=limit, use_llm=True)
    if not insights:
        db.query(UserInsight).filter(UserInsight.user_id == user.id).delete()
        db.commit()
        return []

    month_key = next((insight.get("time") for insight in insights if insight.get("time")), None)
    snapshot_month = (
        dt.datetime.strptime(month_key, "%b %Y").strftime("%Y-%m")
        if month_key and re.fullmatch(r"[A-Z][a-z]{2} \d{4}", month_key)
        else None
    )
    if snapshot_month is None:
        # Use the stable month in the generated ids if the display label is not parseable.
        snapshot_month = (
            db.query(Transaction)
            .filter(Transaction.user_id == user.id, Transaction.date.isnot(None))
            .order_by(Transaction.date.desc(), Transaction.id.desc())
            .with_entities(Transaction.date)
            .first()
        )
        snapshot_month = snapshot_month[0].strftime("%Y-%m") if snapshot_month else None

    if not snapshot_month:
        return insights

    db.query(UserInsight).filter(
        UserInsight.user_id == user.id,
        UserInsight.month == snapshot_month,
    ).delete()

    for index, insight in enumerate(insights):
        db.add(
            UserInsight(
                user_id=user.id,
                type=insight["type"],
                title=insight["title"],
                text=insight["text"],
                suggestion=insight.get("suggestion"),
                month=snapshot_month,
                time_label=insight.get("time"),
                action=insight.get("action"),
                position=index,
            )
        )
    db.commit()
    return insights


def get_latest_insights(db: Session, user: User, limit: int = 6) -> list[dict]:
    latest_month = (
        db.query(UserInsight.month)
        .filter(UserInsight.user_id == user.id)
        .order_by(UserInsight.month.desc())
        .first()
    )
    if latest_month and latest_month[0]:
        rows = (
            db.query(UserInsight)
            .filter(UserInsight.user_id == user.id, UserInsight.month == latest_month[0])
            .order_by(UserInsight.position.asc(), UserInsight.id.asc())
            .limit(limit)
            .all()
        )
        if rows:
            fallback_time = _month_label(latest_month[0])
            return [
                {
                    "id": f"stored-{row.id}",
                    "type": row.type,
                    "title": row.title,
                    "text": row.text,
                    "suggestion": row.suggestion,
                    "time": row.time_label or fallback_time,
                    "action": row.action,
                }
                for row in rows
            ]

    return generate_insights(db, user, limit=limit, use_llm=True)
