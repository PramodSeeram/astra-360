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

async function get<T>(endpoint: string): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });

  const data = await res.json();

  if (!res.ok) {
    throw new Error(data.detail || "Something went wrong");
  }

  return data as T;
}

// ── Auth & Onboarding Types ──

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

// ── Dashboard Types ──

export interface HomeSummary {
  user_id: string;
  first_name: string;
  last_name: string;
  initials: string;
  balance: number;
  savings: number;
  investments: number;
  credit_due: number;
  credit_score: number;
  insights: Array<{
    id: number;
    type: "warning" | "info" | "success";
    text: string;
    action?: string;
    time: string;
  }>;
  has_data: boolean;
  source: string;
  last_updated: string | null;
  data_sources: string[];
  message: string | null;
}

export interface BillItem {
  name: string;
  amount: number;
  provider?: string;
  due_date?: string;
  next_billing?: string;
  status?: string;
  category?: string;
}

export interface BillsData {
  subscriptions: BillItem[];
  utilities: BillItem[];
  total_monthly: number;
  due_this_week: number;
  has_data: boolean;
  source: string;
  last_updated: string | null;
  data_sources: string[];
  message: string | null;
}

export interface CardItem {
  id: number;
  bank: string;
  type: string;
  number: string;
  name: string;
  network: string;
  expiry: string;
  color1: string;
  color2: string;
  limit?: string;
  used?: string;
}

export interface CardsData {
  cards: CardItem[];
  transactions: Array<{
    name: string;
    amount: string;
    time: string;
    emoji: string;
  }>;
  has_data: boolean;
  source: string;
  last_updated: string | null;
  data_sources: string[];
  message: string | null;
}

export interface CalendarEvent {
  id: number;
  date: number;
  type: "bill" | "insurance" | "investment";
  tag: string;
  title: string;
  subtitle: string;
  amount?: string;
}

export interface CalendarData {
  events: CalendarEvent[];
  has_data: boolean;
  source: string;
  last_updated: string | null;
  data_sources: string[];
  message: string | null;
}

export interface ProfileData {
  user_id: string;
  first_name: string;
  last_name: string;
  full_name: string;
  initials: string;
  phone: string;
  email: string;
  pan_masked: string;
  pan_type: string;
  is_onboarded: boolean;
  linked_accounts: Array<{
    bank: string;
    short_name: string;
    type: string;
    acc_no: string;
  }>;
  has_data: boolean;
  source: string;
  joined_at: string | null;
  data_sources: string[];
  message: string | null;
}

// ── API Client ──

export const api = {
  // Auth & Onboarding
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

  // Dashboard APIs
  getHomeSummary: (userId: string) =>
    get<HomeSummary>(`/api/dashboard/home?user_id=${encodeURIComponent(userId)}`),

  getBills: (userId: string) =>
    get<BillsData>(`/api/dashboard/bills?user_id=${encodeURIComponent(userId)}`),

  getCards: (userId: string) =>
    get<CardsData>(`/api/dashboard/cards?user_id=${encodeURIComponent(userId)}`),

  getCalendar: (userId: string) =>
    get<CalendarData>(`/api/dashboard/calendar?user_id=${encodeURIComponent(userId)}`),

  getProfile: (userId: string) =>
    get<ProfileData>(`/api/dashboard/profile?user_id=${encodeURIComponent(userId)}`),
};
