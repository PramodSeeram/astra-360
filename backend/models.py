from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from database import Base
import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String(50), unique=True, index=True, nullable=False) # e.g. user_001
    name = Column(String(255), nullable=False)
    phone_number = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(255))
    credit_score = Column(Integer, default=0)
    monthly_income = Column(Float, default=0.0)
    risk_level = Column(String(50)) # low, medium, high
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    cards = relationship("Card", back_populates="user", cascade="all, delete-orphan")
    loans = relationship("Loan", back_populates="user", cascade="all, delete-orphan")
    bills = relationship("Bill", back_populates="user", cascade="all, delete-orphan")
    chat_threads = relationship("ChatThread", back_populates="user", cascade="all, delete-orphan")
    financial_summary = relationship("UserFinancialSummary", back_populates="user", uselist=False, cascade="all, delete-orphan")
    processing_status = relationship("UserProcessingStatus", back_populates="user", uselist=False, cascade="all, delete-orphan")

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    type = Column(String(50), nullable=False) # credit/debit
    category = Column(String(100))
    description = Column(String(255))
    date = Column(DateTime, default=datetime.datetime.utcnow)
    tx_hash = Column(String(64), unique=True, index=True) # For deduplication

    user = relationship("User", back_populates="transactions")

class Card(Base):
    __tablename__ = "cards"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    bank_name = Column(String(100), nullable=False)
    card_type = Column(String(100)) # Visa Signature, etc.
    last4_digits = Column(String(4), nullable=False)
    limit = Column(Float, default=0.0)
    balance = Column(Float, default=0.0)

    user = relationship("User", back_populates="cards")

class Loan(Base):
    __tablename__ = "loans"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    loan_type = Column(String(100), nullable=False)
    total_amount = Column(Float, nullable=False)
    remaining_amount = Column(Float, nullable=False)
    emi = Column(Float, nullable=False)
    interest_rate = Column(Float, nullable=False)
    status = Column(String(50), nullable=False) # active, closed

    user = relationship("User", back_populates="loans")

class Bill(Base):
    __tablename__ = "bills"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    amount = Column(Float, nullable=False)
    due_date = Column(DateTime, nullable=False)
    status = Column(String(50), nullable=False) # paid, unpaid, pending

    user = relationship("User", back_populates="bills")

class ChatThread(Base):
    __tablename__ = "chat_threads"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), default="Main Chat")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="chat_threads")
    messages = relationship("ChatMessage", back_populates="thread", cascade="all, delete-orphan")

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(Integer, ForeignKey("chat_threads.id"), nullable=False)
    role = Column(String(50), nullable=False) # user, assistant
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    thread = relationship("ChatThread", back_populates="messages")

class UserFinancialSummary(Base):
    __tablename__ = "user_financial_summary"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    total_balance = Column(Float, default=0.0)
    monthly_income = Column(Float, default=0.0)
    monthly_spend = Column(Float, default=0.0)
    emi_total = Column(Float, default=0.0)
    savings = Column(Float, default=0.0)
    category_distribution = Column(Text) # JSON string
    income_detected = Column(Float, default=0.0)
    expense_trend = Column(Text)
    data_quality_score = Column(Float, default=0.0)
    last_upload_date = Column(DateTime)
    last_updated = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    user = relationship("User", back_populates="financial_summary")

class UserProcessingStatus(Base):
    __tablename__ = "user_processing_status"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(50), default="idle") # idle, processing, completed, failed
    progress = Column(Integer, default=0) # 0-100
    stage = Column(String(255))
    error_message = Column(Text)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    user = relationship("User", back_populates="processing_status")

# Helper functions
def get_user_by_external_id(db, external_id):
    return db.query(User).filter(User.external_id == external_id).first()

def get_or_create_thread(db, user):
    from models import ChatThread
    thread = db.query(ChatThread).filter_by(user_id=user.id).first()
    if not thread:
        thread = ChatThread(user_id=user.id, title="Main Chat")
        db.add(thread)
        db.commit()
        db.refresh(thread)
    return thread
