"""
User State Resolver — Astra 360

ACTIVE   → >= 10 transactions (full dashboard)
PARTIAL  → >= 1 transaction  (partial dashboard + upload banner)
NEW      → 0 transactions    (onboarding / upload prompt)
"""

from sqlalchemy.orm import Session
from models import User, Transaction

ACTIVE_THRESHOLD  = 10
PARTIAL_THRESHOLD = 1

def get_user_state(db: Session, user: User) -> str:
    """
    Determine user state purely from transaction count.
    Credit score is NOT used — file upload is the only activation gate.
    """
    tx_count = db.query(Transaction).filter(Transaction.user_id == user.id).count()

    if tx_count >= ACTIVE_THRESHOLD:
        return "ACTIVE"

    if tx_count >= PARTIAL_THRESHOLD:
        return "PARTIAL"

    return "NEW"
