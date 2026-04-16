import json
import os
from typing import Dict, Any

def load_persona_data() -> Dict[str, Any]:
    file_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'persona.json')
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            return json.load(f)
    return {}

def prepare_user_data(user_id: str) -> Dict[str, Any]:
    persona = load_persona_data()
    return {
        'balance': persona.get('balance', 0),
        'savings': persona.get('savings', 0),
        'investments': persona.get('investments', 0),
        'credit_due': persona.get('credit_due', 0),
        'transactions': persona.get('transactions', []),
        'subscriptions': persona.get('subscriptions', []),
        'bills': persona.get('bills', []),
        'insights': persona.get('insights', []),
        'calendar': persona.get('calendar', [])
    }