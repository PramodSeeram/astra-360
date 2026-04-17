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
        "balance": 125430.50,
        "savings": 85000.00,
        "investments": 240500.25,
        "credit_due": 12500.00,
        "credit_score": 782,
        "transactions": [
            {"name": "Starbucks Coffee", "amount": "- ₹450", "time": "10:30 AM", "emoji": "☕"},
            {"name": "Salary Credit", "amount": "+ ₹85,000", "time": "Yesterday", "emoji": "💰"},
            {"name": "Amazon India", "amount": "- ₹2,400", "time": "2 days ago", "emoji": "📦"},
            {"name": "HDFC Netflix Pay", "amount": "- ₹649", "time": "3 days ago", "emoji": "📺"},
        ],
        "subscriptions": [
            {"name": "Netflix Premium", "amount": 649, "provider": "Netflix", "next_billing": "24 Oct 2024", "status": "Active"},
            {"name": "Spotify Family", "amount": 199, "provider": "Spotify", "next_billing": "12 Oct 2024", "status": "Active"},
            {"name": "Amazon Prime", "amount": 1499, "provider": "Amazon", "next_billing": "05 Jan 2025", "status": "Yearly"},
        ],
        "bills": [
            {"name": "Electricity Bill", "amount": 2450, "provider": "BESCOM", "due_date": "20 Oct 2024", "status": "Pending"},
            {"name": "Airtel Fiber", "amount": 1179, "provider": "Airtel", "due_date": "18 Oct 2024", "status": "Pending"},
        ],
        "cards": [
            {"id": 1, "bank": "SBI Card", "type": "Visa Signature", "number": "•••• 4242", "name": "DHANUSH V M", "network": "visa", "expiry": "12/28", "color1": "#1A2980", "color2": "#26D0CE", "limit": "₹2,50,000", "used": "₹12,450"},
            {"id": 2, "bank": "HDFC Bank", "type": "Diners Club", "number": "•••• 1005", "name": "DHANUSH V M", "network": "diners", "expiry": "09/27", "color1": "#EB3349", "color2": "#F45C43", "limit": "₹5,00,000", "used": "₹45,200"},
        ],
        "insights": [
            {"id": 1, "type": "warning", "text": "Unusually high spending on Dining this week.", "time": "2h ago"},
            {"id": 2, "type": "info", "text": "You can save ₹1,200 by switching to a yearly plan for Netflix.", "action": "View", "time": "5h ago"},
            {"id": 3, "type": "success", "text": "Credit score increased by 12 points! Great job.", "time": "1d ago"},
        ],
        "calendar": [
            {"id": 1, "date": 18, "type": "bill", "tag": "AIRTEL", "title": "Airtel Postpaid", "subtitle": "Monthly Bill", "amount": "₹1,179"},
            {"id": 2, "date": 20, "type": "bill", "tag": "BESCOM", "title": "Electricity", "subtitle": "Utilities", "amount": "₹2,450"},
            {"id": 3, "date": 24, "type": "bill", "tag": "NETFLIX", "title": "Subscription", "subtitle": "Entertainment", "amount": "₹649"},
        ],
        "linked_accounts": [
            {"bank": "SBI Bank", "short_name": "SBI", "type": "Savings", "acc_no": "•••• 8821"},
            {"bank": "HDFC Bank", "short_name": "HDFC", "type": "Current", "acc_no": "•••• 4432"},
        ],
        "data_sources": ["SMS Inbound", "Email Scraper", "Account Aggregator"],
        "has_data": True,
        "initialized_at": time.time(),
    }
    user_store[user_id]["has_data"] = True
    user_store[user_id]["is_onboarded"] = True
    user_store[user_id]["is_new_user"] = False
    return True

# Seed demo user for immediate dashboard visibility
demo_user_id = create_or_get_user("9876543210")
init_financial_data(demo_user_id)
# Ensure the first user is always user_001 and has data
if "user_001" not in user_store:
    user_store["user_001"] = user_store[demo_user_id]
else:
    init_financial_data("user_001")
    user_store["user_001"]["kyc"] = {
        "first_name": "Dhanush",
        "last_name": "V M",
        "email": "dhanush@example.com",
        "pan": "ABCDE1234F",
        "pan_type": "Individual"
    }
