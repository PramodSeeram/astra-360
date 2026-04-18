import sys
import os

# Add the backend directory to sys.path to import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from database import SessionLocal
from models import User

def delete_user(phone_number: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.phone_number == phone_number).first()
        if user:
            print(f"Found user: {user.name} (ID: {user.id}). Deleting...")
            db.delete(user)
            db.commit()
            print("User and all related data deleted successfully.")
        else:
            print(f"User with phone number {phone_number} not found.")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    phone = "9640222666"
    delete_user(phone)
