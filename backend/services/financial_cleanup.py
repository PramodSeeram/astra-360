"""Pre-ingestion cleanup helpers.

On re-upload we wipe the user's financial surfaces (transactions, bills,
subscriptions, calendar events) so the pipeline can write a clean snapshot
without relying on tx_hash dedup — which fails across re-parses when
descriptions shift slightly.

The caller must ensure extraction succeeded (non-empty parse) before calling
``delete_user_financial_data`` so a bad file never wipes prior state.
"""

import logging
from typing import Dict

from sqlalchemy.orm import Session

from models import Bill, CalendarEvent, Subscription, Transaction

logger = logging.getLogger(__name__)


def delete_user_financial_data(db: Session, user_id: int) -> Dict[str, int]:
    """Delete all derived financial rows for ``user_id`` and return counts."""
    deleted = {
        "calendar_events": db.query(CalendarEvent).filter(CalendarEvent.user_id == user_id).delete(synchronize_session=False),
        "bills": db.query(Bill).filter(Bill.user_id == user_id).delete(synchronize_session=False),
        "subscriptions": db.query(Subscription).filter(Subscription.user_id == user_id).delete(synchronize_session=False),
        "transactions": db.query(Transaction).filter(Transaction.user_id == user_id).delete(synchronize_session=False),
    }
    db.commit()
    logger.info(
        "[Cleanup] user_id=%s cleared txs=%s bills=%s subs=%s events=%s",
        user_id,
        deleted["transactions"],
        deleted["bills"],
        deleted["subscriptions"],
        deleted["calendar_events"],
    )
    return deleted
