from sqlalchemy.orm import Session
from models import User, Transaction

MIN_THRESHOLD = 10

def get_user_state(db: Session, user: User) -> str:
    """
    Determines user state based on data availability.
    - ACTIVE: user.transactions count >= MIN_THRESHOLD
    - PARTIAL: No transactions or < MIN_THRESHOLD, but user.credit_score > 0
    - NEW: No transactions and user.credit_score == 0
    """
    tx_count = db.query(Transaction).filter(Transaction.user_id == user.id).count()
    
    if tx_count >= MIN_THRESHOLD:
        return "ACTIVE"
    
    if user.credit_score > 0:
        return "PARTIAL"
    
    return "NEW"
