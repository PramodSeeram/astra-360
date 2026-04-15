from pydantic import BaseModel

class SendOTPRequest(BaseModel):
    phone: str

class VerifyOTPRequest(BaseModel):
    phone: str
    otp: str

class KYCRequest(BaseModel):
    user_id: str
    first_name: str
    last_name: str
    email: str | None = None
    pan: str

class ScanRequest(BaseModel):
    user_id: str