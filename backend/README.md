# Astra 360 Backend

FastAPI backend for AI financial app onboarding system.

## Setup

1. Install dependencies:
   pip install -r requirements.txt

2. Run the server:
   uvicorn main:app --reload

## Endpoints

- GET / : Health check
- POST /api/auth/send-otp : Send OTP
- POST /api/auth/verify-otp : Verify OTP
- POST /api/user/kyc : Submit KYC
- POST /api/onboarding/scan : Trigger scan

## Notes

- Uses in-memory storage
- OTP returned in response for dev mode
- No authentication required