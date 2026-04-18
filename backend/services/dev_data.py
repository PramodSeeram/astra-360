import datetime
import json
from typing import Any

from sqlalchemy.orm import Session

from models import Bill, Card, CreditAccount, Subscription, Transaction, User, UserFinancialSummary, UserProcessingStatus
from services.canonical_cards import card_id_for_debit, create_canonical_cards_for_user


ACTIVE_DEMO_USER_ID = "demo_user_1"


def _dt(value: str) -> datetime.datetime:
    return datetime.datetime.strptime(value, "%Y-%m-%d")


DEMO_USERS: list[dict[str, Any]] = [
    {
        "user_id": "demo_user_1",
        "name": "Riya Sharma",
        "phone_number": "9000000001",
        "email": "riya.sharma@example.com",
        "income": 50000,
        "emi": 8000,
        "transactions": [
            {"date": "2026-04-01", "desc": "Salary Credit", "amount": 50000, "type": "credit", "category": "income"},
            {"date": "2026-04-03", "desc": "House Rent", "amount": 15000, "type": "debit", "category": "rent"},
            {"date": "2026-04-05", "desc": "Electricity Bill", "amount": 2500, "type": "debit", "category": "utilities"},
            {"date": "2026-04-10", "desc": "Groceries", "amount": 4200, "type": "debit", "category": "food"},
            {"date": "2026-04-12", "desc": "Swiggy", "amount": 800, "type": "debit", "category": "food"},
            {"date": "2026-04-15", "desc": "Freelance Payment", "amount": 10000, "type": "credit", "category": "income"},
            {"date": "2026-04-18", "desc": "Internet Bill", "amount": 1200, "type": "debit", "category": "utilities"},
        ],
        "bills": [
            {"name": "Rent", "amount": 15000, "due_date": "2026-04-03", "status": "paid"},
            {"name": "Electricity Bill", "amount": 2500, "due_date": "2026-04-05", "status": "paid"},
        ],
    },
    {
        "user_id": "demo_user_2",
        "name": "Arjun Mehta",
        "phone_number": "9000000002",
        "email": "arjun.mehta@example.com",
        "income": 60000,
        "emi": 12000,
        "transactions": [
            {"date": "2026-02-01", "desc": "Salary", "amount": 60000, "type": "credit", "category": "income"},
            {"date": "2026-02-10", "desc": "Shopping", "amount": 15000, "type": "debit", "category": "lifestyle"},
            {"date": "2026-03-01", "desc": "Salary", "amount": 60000, "type": "credit", "category": "income"},
            {"date": "2026-03-12", "desc": "Travel", "amount": 20000, "type": "debit", "category": "travel"},
            {"date": "2026-04-01", "desc": "Salary", "amount": 60000, "type": "credit", "category": "income"},
            {"date": "2026-04-14", "desc": "Utilities", "amount": 10000, "type": "debit", "category": "utilities"},
        ],
    },
    {
        "user_id": "demo_user_3",
        "name": "Neha Verma",
        "phone_number": "9000000003",
        "email": "neha.verma@example.com",
        "income": 90000,
        "emi": 0,
        "credit": {
            "provider": "Astra Demo Card",
            "limit": 100000,
            "used": 85000,
        },
        "transactions": [
            {"date": "2026-04-05", "desc": "Amazon Purchase", "amount": 25000, "type": "debit", "category": "lifestyle"},
            {"date": "2026-04-08", "desc": "Flight Booking", "amount": 30000, "type": "debit", "category": "travel"},
            {"date": "2026-04-12", "desc": "Dining", "amount": 15000, "type": "debit", "category": "food"},
        ],
    },
    {
        "user_id": "demo_user_4",
        "name": "Kabir Nair",
        "phone_number": "9000000004",
        "email": "kabir.nair@example.com",
        "income": 70000,
        "emi": 0,
        "subscriptions": [
            {"name": "Netflix", "amount": 649},
            {"name": "Amazon Prime", "amount": 1499},
            {"name": "Spotify", "amount": 179},
            {"name": "Xbox Pass", "amount": 499},
        ],
    },
    {
        "user_id": "demo_user_5",
        "name": "Maya Iyer",
        "phone_number": "9000000005",
        "email": "maya.iyer@example.com",
        "income": 0,
        "emi": 0,
        "transactions": [
            {"date": "2026-04-10", "desc": "Tea", "amount": 50, "type": "debit", "category": "food"},
        ],
    },
]


def _demo_cards_for_user(db: Session, user: User) -> dict[str, int]:
    """Create the three canonical cards; return map keys sbi, federal, hdfc -> card id."""
    return create_canonical_cards_for_user(db, user)


def normalize_category(category: str | None) -> str | None:
    if not category:
        return None
    mapping = {
        "income": "Salary",
        "rent": "Bills",
        "utilities": "Utilities",
        "food": "Food",
        "travel": "Travel",
        "lifestyle": "Shopping",
    }
    return mapping.get(category.lower(), category.title())


def seed_demo_data(db: Session) -> dict[str, Any]:
    seeded_ids: list[str] = []

    for payload in DEMO_USERS:
        external_id = payload["user_id"]
        user = db.query(User).filter(User.external_id == external_id).first()
        if not user:
            user = User(
                external_id=external_id,
                name=payload["name"],
                phone_number=payload["phone_number"],
                email=payload["email"],
            )
            db.add(user)
            db.flush()

        user.name = payload["name"]
        user.phone_number = payload["phone_number"]
        user.email = payload["email"]
        user.monthly_income = float(payload.get("income", 0) or 0)
        user.credit_score = 760 if external_id != "demo_user_3" else 680
        user.risk_level = "medium" if external_id in {"demo_user_1", "demo_user_2", "demo_user_3"} else "low"

        db.query(Transaction).filter(Transaction.user_id == user.id).delete()
        db.query(Card).filter(Card.user_id == user.id).delete()
        db.query(Bill).filter(Bill.user_id == user.id).delete()
        db.query(CreditAccount).filter(CreditAccount.user_id == user.id).delete()
        db.query(Subscription).filter(Subscription.user_id == user.id).delete()
        db.query(UserFinancialSummary).filter(UserFinancialSummary.user_id == user.id).delete()
        db.query(UserProcessingStatus).filter(UserProcessingStatus.user_id == user.id).delete()

        card_ids = _demo_cards_for_user(db, user)

        transactions = payload.get("transactions", [])
        monthly_spend = 0.0
        category_distribution: dict[str, float] = {}

        for index, item in enumerate(transactions):
            category = normalize_category(item.get("category"))
            amount = float(item["amount"])
            cid = None
            if item["type"] == "debit":
                cid = card_id_for_debit(card_ids, item.get("desc") or "", item.get("category"))
            tx = Transaction(
                user_id=user.id,
                amount=amount,
                type=item["type"],
                category=category,
                description=item["desc"],
                date=_dt(item["date"]),
                tx_hash=f"{external_id}_{index}",
                card_id=cid,
            )
            db.add(tx)
            if item["type"] == "debit":
                monthly_spend += amount
                key = category or "Other"
                category_distribution[key] = round(category_distribution.get(key, 0.0) + amount, 2)

        for bill in payload.get("bills", []):
            db.add(
                Bill(
                    user_id=user.id,
                    name=bill["name"],
                    amount=float(bill["amount"]),
                    due_date=_dt(bill["due_date"]),
                    status=bill.get("status", "pending"),
                )
            )

        credit_data = payload.get("credit")
        if credit_data:
            db.add(
                CreditAccount(
                    user_id=user.id,
                    provider=credit_data.get("provider", "Credit Line"),
                    credit_limit=float(credit_data["limit"]),
                    used_amount=float(credit_data["used"]),
                    last_updated=_dt("2026-04-12"),
                )
            )

        for sub in payload.get("subscriptions", []):
            db.add(
                Subscription(
                    user_id=user.id,
                    name=sub["name"],
                    amount=float(sub["amount"]),
                    billing_cycle="monthly",
                    status="active",
                    next_billing_date=_dt("2026-04-25"),
                )
            )

        db.add(
            UserFinancialSummary(
                user_id=user.id,
                total_balance=max(0.0, float(payload.get("income", 0) or 0) - monthly_spend),
                monthly_income=float(payload.get("income", 0) or 0),
                monthly_spend=monthly_spend,
                emi_total=float(payload.get("emi", 0) or 0),
                savings=max(0.0, float(payload.get("income", 0) or 0) - monthly_spend - float(payload.get("emi", 0) or 0)),
                category_distribution=json.dumps(category_distribution),
                income_detected=float(payload.get("income", 0) or 0),
                expense_trend="stable",
                data_quality_score=0.95 if transactions else 0.6,
                last_upload_date=_dt("2026-04-17"),
            )
        )
        db.add(
            UserProcessingStatus(
                user_id=user.id,
                status="completed",
                progress=100,
                stage="Demo data available",
            )
        )
        seeded_ids.append(external_id)

    db.commit()
    return {
        "status": "ok",
        "seeded_users": seeded_ids,
        "active_user_id": ACTIVE_DEMO_USER_ID,
    }
