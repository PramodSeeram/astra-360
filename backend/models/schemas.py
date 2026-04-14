from pydantic import BaseModel
from typing import Optional


class SendOtpRequest(BaseModel):
    phone: str


class SendOtpResponse(BaseModel):
    status: str
    dev_otp: Optional[str] = None


class VerifyOtpRequest(BaseModel):
    phone: str
    otp: str


class VerifyOtpResponse(BaseModel):
    status: str
    user_id: str


class KycRequest(BaseModel):
    user_id: str
    first_name: str
    last_name: str
    email: Optional[str] = None
    pan: str


class KycResponse(BaseModel):
    status: str
    pan_type: str


class ScanRequest(BaseModel):
    user_id: str


class ScanResponse(BaseModel):
    status: str


class ErrorResponse(BaseModel):
    detail: str
