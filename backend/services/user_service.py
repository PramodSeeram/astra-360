from typing import Dict, Any, Optional

user_store: Dict[str, Dict[str, Any]] = {}
user_counter = 0

def create_user(phone: str) -> str:
    global user_counter
    user_counter += 1
    user_id = f"user_{user_counter:03d}"
    user_store[user_id] = {
        'phone': phone,
        'kyc': {},
        'financial_data': {}
    }
    return user_id

def save_kyc(user_id: str, data: Dict[str, Any]) -> None:
    if user_id in user_store:
        user_store[user_id]['kyc'] = data

def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    return user_store.get(user_id)