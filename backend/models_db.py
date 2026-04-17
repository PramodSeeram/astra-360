from sqlalchemy import Column, Integer, String, Float, DateTime, Date, ForeignKey, Enum
from sqlalchemy.orm import relationship
from database import Base
import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary key=True, index=True)
    name = Column(String(255), nullable=False)
    phone_number = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(255))

    transactions = relationship("Transaction", back_populates="user")
    cards = relationship("Card", back_populates="user")
    bills = relationship("Bill", back_populates="user")

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    type = Column(String(50), nullable=False) # credit/debit
    description = Column(String(255))
    date = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="transactions")

class Card(Base):
    __tablename__ = "cards"

    id = Column(Integer, primary key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    card_number = Column(String(255), nullable=False) # masked string
    balance = Column(Float, default=0.0)
    limit = Column(Float, default=0.0)

    user = relationship("User", back_populates="cards")

class Bill(Base):
    __tablename__ = "bills"

    id = Column(Integer, primary key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    amount = Column(Float, nullable=False)
    due_date = Column(Date, nullable=False)
    status = Column(String(50), nullable=False) # paid/unpaid

    user = relationship("User", back_populates="bills")
