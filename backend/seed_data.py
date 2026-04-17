import datetime
from sqlalchemy.orm import Session
from database import SessionLocal
from models import User, Transaction, Card, Loan, Bill

def seed():
    db = SessionLocal()
    try:
        # Clear existing data
        db.query(Bill).delete()
        db.query(Loan).delete()
        db.query(Card).delete()
        db.query(Transaction).delete()
        db.query(User).delete()
        db.commit()

        # 1. USER 1 (LOW CREDIT)
        user1 = User(
            external_id="user_001",
            name="Aman Gupta",
            phone_number="9876543210",
            email="aman.g@example.com",
            credit_score=580,
            monthly_income=35000.0,
            risk_level="high"
        )
        db.add(user1)
        db.flush()

        # Transactions for User 1
        u1_txs = [
            Transaction(user_id=user1.id, amount=12000.0, type="debit", category="Rent", description="Monthly House Rent", date=datetime.datetime.now() - datetime.timedelta(days=2)),
            Transaction(user_id=user1.id, amount=450.0, type="debit", category="Food", description="Zomato Order", date=datetime.datetime.now() - datetime.timedelta(days=1)),
            Transaction(user_id=user1.id, amount=850.0, type="debit", category="Transport", description="Uber Ride", date=datetime.datetime.now() - datetime.timedelta(hours=5)),
            Transaction(user_id=user1.id, amount=35000.0, type="credit", category="Salary", description="Monthly Salary Credit", date=datetime.datetime.now() - datetime.timedelta(days=15)),
            Transaction(user_id=user1.id, amount=5000.0, type="debit", category="EMI", description="Personal Loan EMI", date=datetime.datetime.now() - datetime.timedelta(days=5)),
            Transaction(user_id=user1.id, amount=3000.0, type="debit", category="EMI", description="Phone EMI", date=datetime.datetime.now() - datetime.timedelta(days=10)),
        ]
        db.add_all(u1_txs)

        # Cards for User 1
        db.add(Card(user_id=user1.id, bank_name="SBI", card_type="Visa Platinum", last4_digits="1234", limit=50000.0, balance=45000.0))

        # Loans for User 1
        db.add(Loan(user_id=user1.id, loan_type="Personal Loan", total_amount=100000.0, remaining_amount=85000.0, emi=5000.0, interest_rate=14.5, status="active"))
        db.add(Loan(user_id=user1.id, loan_type="Consumer Durable Loan", total_amount=30000.0, remaining_amount=15000.0, emi=3000.0, interest_rate=12.0, status="active"))

        # Bills for User 1
        db.add(Bill(user_id=user1.id, name="Electricity Bill", amount=1200.0, due_date=datetime.datetime.now() + datetime.timedelta(days=5), status="unpaid"))
        db.add(Bill(user_id=user1.id, name="Mobile Bill", amount=799.0, due_date=datetime.datetime.now() + datetime.timedelta(days=2), status="unpaid"))


        # 2. USER 2 (MEDIUM CREDIT)
        user2 = User(
            external_id="user_002",
            name="Priya Sharma",
            phone_number="8888888888",
            email="priya.s@example.com",
            credit_score=700,
            monthly_income=85000.0,
            risk_level="medium"
        )
        db.add(user2)
        db.flush()

        # Transactions for User 2
        u2_txs = [
            Transaction(user_id=user2.id, amount=85000.0, type="credit", category="Salary", description="Salary Credit", date=datetime.datetime.now() - datetime.timedelta(days=15)),
            Transaction(user_id=user2.id, amount=25000.0, type="debit", category="EMI", description="Home Loan EMI", date=datetime.datetime.now() - datetime.timedelta(days=5)),
            Transaction(user_id=user2.id, amount=4500.0, type="debit", category="Shopping", description="Amazon purchase", date=datetime.datetime.now() - datetime.timedelta(days=3)),
            Transaction(user_id=user2.id, amount=1200.0, type="debit", category="Entertainment", description="Netflix", date=datetime.datetime.now() - datetime.timedelta(days=10)),
            Transaction(user_id=user2.id, amount=3000.0, type="debit", category="Utilities", description="Gas Bill", date=datetime.datetime.now() - datetime.timedelta(days=2)),
        ]
        db.add_all(u2_txs)

        # Cards for User 2
        db.add(Card(user_id=user2.id, bank_name="HDFC", card_type="Regalia Gold", last4_digits="5678", limit=300000.0, balance=12000.0))

        # Loans for User 2
        db.add(Loan(user_id=user2.id, loan_type="Home Loan", total_amount=5000000.0, remaining_amount=4200000.0, emi=25000.0, interest_rate=8.5, status="active"))

        # Bills for User 2
        db.add(Bill(user_id=user2.id, name="Broadband", amount=999.0, due_date=datetime.datetime.now() + datetime.timedelta(days=10), status="unpaid"))
        db.add(Bill(user_id=user2.id, name="Credit Card Bill", amount=12000.0, due_date=datetime.datetime.now() + datetime.timedelta(days=15), status="unpaid"))


        # 3. USER 3 (HIGH CREDIT)
        user3 = User(
            external_id="user_003",
            name="Vikram Malhotra",
            phone_number="9999999999",
            email="vikram.m@example.com",
            credit_score=820,
            monthly_income=250000.0,
            risk_level="low"
        )
        db.add(user3)
        db.flush()

        # Transactions for User 3
        u3_txs = [
            Transaction(user_id=user3.id, amount=250000.0, type="credit", category="Salary", description="Senior Executive Salary", date=datetime.datetime.now() - datetime.timedelta(days=15)),
            Transaction(user_id=user3.id, amount=15000.0, type="debit", category="Investment", description="SIP - Mutual Fund", date=datetime.datetime.now() - datetime.timedelta(days=10)),
            Transaction(user_id=user3.id, amount=8500.0, type="debit", category="Dining", description="Fine Dining at Taj", date=datetime.datetime.now() - datetime.timedelta(days=5)),
            Transaction(user_id=user3.id, amount=45000.0, type="debit", category="Travel", description="Flight Booking", date=datetime.datetime.now() - datetime.timedelta(days=20)),
            Transaction(user_id=user3.id, amount=12000.0, type="debit", category="Shopping", description="Luxury Apparel", date=datetime.datetime.now() - datetime.timedelta(days=1)),
        ]
        db.add_all(u3_txs)

        # Cards for User 3
        db.add(Card(user_id=user3.id, bank_name="ICICI", card_type="Sapphiro", last4_digits="9012", limit=1000000.0, balance=55000.0))
        db.add(Card(user_id=user3.id, bank_name="Amex", card_type="Platinum", last4_digits="4433", limit=0.0, balance=0.0)) # No preset limit

        # Loans for User 3 (None as per instructions low debt)
        
        # Bills for User 3
        db.add(Bill(user_id=user3.id, name="Corporate Gym", amount=5000.0, due_date=datetime.datetime.now() + datetime.timedelta(days=20), status="paid"))
        db.add(Bill(user_id=user3.id, name="Property Maintenance", amount=15000.0, due_date=datetime.datetime.now() + datetime.timedelta(days=25), status="pending"))

        db.commit()
        print("Database seeded successfully with 3 users.")
    except Exception as e:
        print(f"Error seeding database: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed()
