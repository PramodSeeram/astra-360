import time
import random

otp_store = {}

def generate_otp(phone: str) -> str:
    otp = ''.join(random.choices('0123456789', k=6))
    expires_at = time.time() + 120
    resend_available_at = time.time() + 30
    otp_store[phone] = {
        'otp': otp,
        'expires_at': expires_at,
        'attempts': 0,
        'resend_available_at': resend_available_at
    }
    return otp

def can_resend(phone: str) -> bool:
    if phone not in otp_store:
        return True
    return time.time() >= otp_store[phone]['resend_available_at']

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