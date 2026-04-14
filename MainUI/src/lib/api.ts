const API_BASE = "http://localhost:8000";

async function request<T>(endpoint: string, body: Record<string, unknown>): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const data = await res.json();

  if (!res.ok) {
    throw new Error(data.detail || "Something went wrong");
  }

  return data as T;
}

export interface SendOtpResponse {
  status: string;
  dev_otp?: string;
}

export interface VerifyOtpResponse {
  status: string;
  user_id: string;
}

export interface KycResponse {
  status: string;
  pan_type: string;
}

export interface ScanResponse {
  status: string;
}

export const api = {
  sendOtp: (phone: string) =>
    request<SendOtpResponse>("/api/auth/send-otp", { phone }),

  verifyOtp: (phone: string, otp: string) =>
    request<VerifyOtpResponse>("/api/auth/verify-otp", { phone, otp }),

  submitKyc: (data: {
    user_id: string;
    first_name: string;
    last_name: string;
    email?: string;
    pan: string;
  }) => request<KycResponse>("/api/user/kyc", data as Record<string, unknown>),

  startScan: (userId: string) =>
    request<ScanResponse>("/api/onboarding/scan", { user_id: userId }),
};
