user_store = {}
user_counter = 1

def create_user(phone: str) -> str:
    global user_counter
    user_id = f"user_{user_counter}"
    user_counter += 1
    user_store[user_id] = {
        'phone': phone,
        'kyc': {},
        'financial_data': {}
    }
    return user_id

def save_kyc(user_id: str, data: dict):
    if user_id in user_store:
        user_store[user_id]['kyc'] = data

def get_user(user_id: str) -> dict | None:
    return user_store.get(user_id)