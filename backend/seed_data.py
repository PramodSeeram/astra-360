from database import SessionLocal
from services.dev_data import seed_demo_data
from services.dev_state import set_active_user_id


def seed() -> None:
    db = SessionLocal()
    try:
        result = seed_demo_data(db)
        set_active_user_id(result["active_user_id"])
        print(f"Seeded demo users: {', '.join(result['seeded_users'])}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
