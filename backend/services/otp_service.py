import random
import time
import os

otp_store = {}

OTP_EXPIRY = 120
MAX_ATTEMPTS = 3
RESEND_COOLDOWN = 30


def generate_otp(phone: str, background_tasks=None) -> dict:
    now = time.time()

    if phone in otp_store:
        entry = otp_store[phone]
        elapsed = now - entry["last_sent"]
        if elapsed < RESEND_COOLDOWN:
            remaining = int(RESEND_COOLDOWN - elapsed)
            return {"error": f"Resend cooldown active. Wait {remaining} seconds."}

    otp = str(random.randint(100000, 999999))
    otp_store[phone] = {
        "otp": otp,
        "created_at": now,
        "attempts": 0,
        "last_sent": now,
    }

    # Try sending via Twilio asynchronously if background_tasks provided
    if background_tasks:
        background_tasks.add_task(send_via_twilio, phone, otp)
    else:
        send_via_twilio(phone, otp)

    return {"otp": otp}


def verify_otp(phone: str, otp: str) -> dict:
    if phone not in otp_store:
        return {"error": "No OTP found for this number. Request a new one."}

    entry = otp_store[phone]
    now = time.time()

    if now - entry["created_at"] > OTP_EXPIRY:
        del otp_store[phone]
        return {"error": "OTP expired. Request a new one."}

    if entry["attempts"] >= MAX_ATTEMPTS:
        del otp_store[phone]
        return {"error": "Max attempts reached. Request a new OTP."}

    entry["attempts"] += 1

    if entry["otp"] != otp:
        remaining = MAX_ATTEMPTS - entry["attempts"]
        return {"error": f"Incorrect OTP. {remaining} attempt{'s' if remaining != 1 else ''} remaining."}

    del otp_store[phone]
    return {"success": True}


def send_via_twilio(phone: str, otp: str):
    try:
        from twilio.rest import Client
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_number = os.getenv("TWILIO_PHONE_NUMBER")
        if not all([account_sid, auth_token, from_number]):
            print(f"[TWILIO] Missing credentials, falling back to console")
            print(f"[DEV OTP] {phone}: {otp}")
            return
        client = Client(account_sid, auth_token)
        client.messages.create(
            body=f"Your Astra 360 OTP is: {otp}",
            from_=from_number,
            to=f"+91{phone}",
        )
        print(f"[TWILIO] OTP sent to +91{phone}")
    except Exception as e:
        print(f"[TWILIO ERROR] {e}")
        print(f"[DEV OTP] {phone}: {otp}")
