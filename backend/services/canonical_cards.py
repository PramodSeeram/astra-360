"""Exactly three canonical credit cards for every user (demo + chat consistency).

Product rule: HDFC Swiggy, Federal Swiggy, SBI Cashback — LLM and UI always see these three.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from models import Card, Transaction, User

logger = logging.getLogger(__name__)

# (bank_name, card_type, last4, limit, balance) — stable identifiers for enforcement
CANONICAL_CARD_SPECS: List[tuple[str, str, str, float, float]] = [
    ("HDFC Bank", "Swiggy Credit Card", "2109", 350_000.0, 9_800.0),
    ("Federal Bank", "Swiggy Credit Card", "8765", 500_000.0, 42_000.0),
    ("SBI", "Cashback Credit Card", "4321", 200_000.0, 12_500.0),
]

EXPECTED_LAST4 = frozenset(spec[2] for spec in CANONICAL_CARD_SPECS)


def card_id_for_debit(card_ids: Dict[str, int], desc: str, category: Optional[str]) -> Optional[int]:
    """Route debit to HDFC (food delivery), SBI (amazon), Federal (travel), else SBI."""
    d = (desc or "").lower()
    if "swiggy" in d or "zomato" in d:
        return card_ids.get("hdfc")
    if "amazon" in d or "amzn" in d:
        return card_ids.get("sbi")
    if "flight" in d or "travel" in d or "booking" in d:
        return card_ids.get("federal")
    if "shopping" in d or "groceries" in d or "dining" in d:
        return card_ids.get("sbi")
    return card_ids.get("sbi")


def _map_card_ids_by_brand(cards: List[Card]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for c in cards:
        b = (c.bank_name or "").lower()
        last4 = c.last4_digits or ""
        if last4 == "2109" or "hdfc" in b:
            out["hdfc"] = c.id
        elif last4 == "8765" or "federal" in b:
            out["federal"] = c.id
        elif last4 == "4321" or b.startswith("sbi"):
            out["sbi"] = c.id
    return out


def _cards_match_canonical(cards: List[Card]) -> bool:
    if len(cards) != 3:
        return False
    last4s = {c.last4_digits for c in cards}
    if last4s != EXPECTED_LAST4:
        return False
    # Light sanity check on bank labels
    by_last4 = {c.last4_digits: c for c in cards}
    for bank_name, card_type, last4, _, _ in CANONICAL_CARD_SPECS:
        c = by_last4.get(last4)
        if not c:
            return False
        if (c.bank_name or "") != bank_name or (c.card_type or "") != card_type:
            return False
    return True


def create_canonical_cards_for_user(db: Session, user: User) -> Dict[str, int]:
    """Insert the three canonical cards (caller must have removed prior rows if replacing)."""
    for bank_name, card_type, last4, limit_v, balance_v in CANONICAL_CARD_SPECS:
        db.add(
            Card(
                user_id=user.id,
                bank_name=bank_name,
                card_type=card_type,
                last4_digits=last4,
                limit=limit_v,
                balance=balance_v,
            )
        )
    db.flush()
    cards = (
        db.query(Card)
        .filter(Card.user_id == user.id)
        .order_by(Card.id.asc())
        .all()
    )
    return _map_card_ids_by_brand(cards)


def _reassign_debit_card_ids(db: Session, user_id: int, card_ids: Dict[str, int]) -> None:
    txs = (
        db.query(Transaction)
        .filter(Transaction.user_id == user_id)
        .order_by(Transaction.date.asc(), Transaction.id.asc())
        .all()
    )
    for tx in txs:
        if (tx.type or "").lower() != "debit":
            continue
        cid = card_id_for_debit(card_ids, tx.description or "", tx.category)
        tx.card_id = cid


def ensure_canonical_cards(db: Session, user: User) -> None:
    """Ensure user has exactly the three canonical cards; fix DB if not.

    Reassigns debit transactions to the canonical routing rules when cards are replaced.
    """
    cards = (
        db.query(Card)
        .filter(Card.user_id == user.id)
        .order_by(Card.id.asc())
        .all()
    )
    if _cards_match_canonical(cards):
        return

    logger.info(
        "canonical_cards: replacing cards for user_id=%s (had %s rows)",
        user.id,
        len(cards),
    )

    db.execute(update(Transaction).where(Transaction.user_id == user.id).values(card_id=None))
    db.execute(delete(Card).where(Card.user_id == user.id))

    card_ids = create_canonical_cards_for_user(db, user)
    if len(card_ids) != 3:
        logger.warning("canonical_cards: expected 3 brand keys, got %s", card_ids)

    _reassign_debit_card_ids(db, user.id, card_ids)
    db.commit()
