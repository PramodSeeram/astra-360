import random
import time
from typing import Dict, Any

otp_store: Dict[str, Dict[str, Any]] = {}

def generate_otp(phone: str) -> str:
    otp = ''.join(random.choices('0123456789', k=6))
    expires_at = time.time() + 120  # 2 minutes
    resend_available_at = time.time() + 30  # 30 seconds
    otp_store[phone] = {
        'otp': otp,
        'expires_at': expires_at,
        'attempts': 0,
        'resend_available_at': resend_available_at
    }
    return otp

def verify_otp(phone: str, otp: str) -> bool:
    if phone not in otp_store:
        return False
    data = otp_store[phone]
    if time.time() > data['expires_at']:
        del otp_store[phone]
        return False
    if data['attempts'] >= 3:
        return False
    if data['otp'] != otp:
        data['attempts'] += 1
        return False
    del otp_store[phone]
    return True

def can_resend_otp(phone: str) -> bool:
    if phone not in otp_store:
        return True
    return time.time() >= otp_store[phone]['resend_available_at']