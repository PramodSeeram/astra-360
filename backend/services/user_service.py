import time

user_store = {}
phone_to_user = {}
user_counter = 0


def create_or_get_user(phone: str) -> str:
    global user_counter

    if phone in phone_to_user:
        return phone_to_user[phone]

    user_counter += 1
    user_id = f"user_{str(user_counter).zfill(3)}"

    user_store[user_id] = {
        "phone": phone,
        "kyc": {},
        "financial_data": {},
        "is_onboarded": False,
        "is_new_user": True,
        "has_data": False,
        "created_at": time.time(),
    }

    phone_to_user[phone] = user_id
    return user_id


def get_user(user_id: str) -> dict | None:
    return user_store.get(user_id)


def update_kyc(user_id: str, data: dict):
    if user_id not in user_store:
        return False
    user_store[user_id]["kyc"] = data
    return True


def init_financial_data(user_id: str):
    if user_id not in user_store:
        return False

    user_store[user_id]["financial_data"] = {
        "balance": 0,
        "savings": 0,
        "investments": 0,
        "credit_due": 0,
        "credit_score": 0,
        "transactions": [],
        "subscriptions": [],
        "bills": [],
        "cards": [],
        "insights": [],
        "calendar": [],
        "linked_accounts": [],
        "data_sources": [],
        "has_data": False,
        "initialized_at": time.time(),
    }
    user_store[user_id]["is_onboarded"] = True
    user_store[user_id]["is_new_user"] = False
    return True
