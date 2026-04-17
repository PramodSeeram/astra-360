import os
import json
import logging
import datetime
import hashlib
import re
from sqlalchemy.orm import Session
from database import SessionLocal
from models import User, Transaction, Bill, Loan, UserFinancialSummary, UserProcessingStatus, get_user_by_external_id
from rag.document_processor import parse_document
from agents.wealth_agent import client, LLM_MODEL

logger = logging.getLogger(__name__)

MIN_THRESHOLD = 5

def _normalize_description(desc: str) -> str:
    return re.sub(r'[^a-zA-Z0-9]', '', desc).lower()

def _generate_tx_hash(date: str, amount: float, description: str, index: int) -> str:
    norm_desc = _normalize_description(description)
    raw = f"{date}-{amount}-{norm_desc}-{index}"
    return hashlib.md5(raw.encode()).hexdigest()

def process_upload_safe(user_id: str, file_path: str, filename: str):
    """Wrapper to catch errors in background tasks."""
    db = SessionLocal()
    try:
        data_activation_pipeline(db, user_id, file_path, filename)
    except Exception as e:
        logger.error(f"Activation Error for {user_id}: {e}")
        status = db.query(UserProcessingStatus).filter_by(user_id=user_id).first()
        if status:
            status.status = "failed"
            status.error_message = str(e)
            db.commit()
    finally:
        db.close()

def data_activation_pipeline(db: Session, external_id: str, file_path: str, filename: str):
    user = get_user_by_external_id(db, external_id)
    if not user:
        raise ValueError("User not found")

    # 1. Initialize Status
    status = db.query(UserProcessingStatus).filter_by(user_id=user.id).first()
    if not status:
        status = UserProcessingStatus(user_id=user.id)
        db.add(status)
    
    status.status = "processing"
    status.progress = 10
    status.stage = "Parsing document..."
    db.commit()

    # 2. Parse Document
    text = parse_document(file_path, filename)
    status.progress = 30
    status.stage = "Extracting transactions..."
    db.commit()

    # 3. Hybrid Ingestion (LLM for Extraction & Categorization)
    # We use LLM to extract structured data from the text.
    # In a real production system, we'd also use Regex for common patterns.
    # Here we'll use a strong LLM prompt as requested.
    
    prompt = f"""
    You are a professional financial data extractor. I will provide you with bank statement text.
    Your task is to extract EVERY SINGLE transaction listed in the text. Do not summarize. 
    Do not skip rows.
    
    TEXT:
    \"\"\"{text[:5000]}\"\"\"
    
    INSTRUCTIONS:
    - Return a JSON list of ALL transactions.
    - Each object must have: "date" (YYYY-MM-DD), "amount" (float), "type" ("credit" or "debit"), "description", and "category".
    - If a row has a '+' it is a "credit", if it has a '-' it is a "debit".
    - Clean up descriptions (e.g., remove transaction IDs if they clutter the name).
    - If you find no transactions, return [].

    OUTPUT ONLY THE JSON LIST:
    """

    try:
        completion = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        content = completion.choices[0].message.content
        logger.info(f"DEBUG LLM CONTENT: {content}")
        print(f"DEBUG LLM CONTENT: {content}")
        start = content.find('[')
        end = content.rfind(']') + 1
        raw_txs = json.loads(content[start:end]) if start != -1 else []
    except Exception as e:
        logger.error(f"LLM Extraction failed: {e}")
        raw_txs = []

    status.progress = 60
    status.stage = "Categorizing and deduplicating..."
    db.commit()

    # 4. Save Transactions with Deduplication
    valid_count = 0
    total_txs = len(raw_txs)
    
    # Simple Deduplication: Hash of (date, amount, desc, index) 
    # to allow multiple txs on same day but avoid re-uploads.
    # For this demo, we'll check against existing txs in DB.
    
    existing_hashes = set() # Ideally we'd have a 'hash' column in Transaction table, but we'll use a simple check here
    
    for i, tx in enumerate(raw_txs):
        try:
            # 1. Basic Validation
            amt = float(tx.get('amount', 0))
            dt_str = tx.get('date')
            desc = tx.get('description', '')
            if abs(amt) == 0 or not dt_str or not desc:
                continue
            
            # Use absolute amount for storage as 'type' handles the sign
            amt = abs(amt)
                
            # 2. Generate Hash & Check Deduplication
            tx_h = _generate_tx_hash(dt_str, amt, desc, i)
            existing = db.query(Transaction).filter(Transaction.tx_hash == tx_h).first()
            if existing:
                continue # Skip duplicate

            # 3. Create Transaction
            new_tx = Transaction(
                user_id=user.id,
                amount=amt,
                type=tx.get('type', 'debit').lower(),
                category=tx.get('category', 'Miscellaneous'),
                description=desc,
                date=datetime.datetime.strptime(dt_str, '%Y-%m-%d'),
                tx_hash=tx_h
            )
            db.add(new_tx)
            valid_count += 1
            
            # Detect Bills (Utilities/Subscriptions)
            if tx.get('category') in ['Utilities', 'Rent'] or 'subscription' in tx.get('description', '').lower():
                bill = Bill(
                    user_id=user.id,
                    name=tx.get('description'),
                    amount=amt,
                    due_date=new_tx.date + datetime.timedelta(days=30),
                    status="paid"
                )
                db.add(bill)
                
            # Detect Loans (EMI)
            if tx.get('category') == 'EMI' or 'emi' in tx.get('description', '').lower():
                loan = Loan(
                    user_id=user.id,
                    loan_type="Detected Loan",
                    total_amount=amt * 12, # Rough estimate
                    remaining_amount=amt * 6,
                    emi=amt,
                    interest_rate=12.0,
                    status="active"
                )
                db.add(loan)
                
        except Exception as e:
            logger.warning(f"Skipping bad transaction row {i}: {e}")

    # 5. Calculate Quality Score & Summary
    quality_score = valid_count / total_txs if total_txs > 0 else 0.0
    
    status.progress = 90
    status.stage = "Finalizing summary..."
    db.commit()

    if valid_count < MIN_THRESHOLD:
        status.status = "failed"
        status.error_message = f"Insufficient data: only {valid_count} valid transactions found. Need at least {MIN_THRESHOLD}."
        db.commit()
    else:
        # Update User Stats
        user.monthly_income = sum(tx.get('amount', 0) for tx in raw_txs if tx.get('type') == 'credit' and tx.get('category') == 'Salary')
        
        # Create/Update Summary
        summary = db.query(UserFinancialSummary).filter_by(user_id=user.id).first()
        if not summary:
            summary = UserFinancialSummary(user_id=user.id)
            db.add(summary)
        
        summary.total_balance = sum(tx.get('amount', 0) * (1 if tx.get('type') == 'credit' else -1) for tx in raw_txs)
        summary.monthly_spend = sum(tx.get('amount', 0) for tx in raw_txs if tx.get('type') == 'debit')
        summary.emi_total = sum(tx.get('amount', 0) for tx in raw_txs if tx.get('category') == 'EMI')
        summary.data_quality_score = quality_score
        summary.income_detected = user.monthly_income
        summary.last_upload_date = datetime.datetime.utcnow()
        summary.last_updated = datetime.datetime.utcnow()
        
        status.status = "completed"
        status.progress = 100
        status.stage = "Activation complete"
        db.commit()

    db.commit()
