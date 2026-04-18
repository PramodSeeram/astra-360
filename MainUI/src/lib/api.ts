/**
 * Dev: empty → same origin; Vite proxies to FastAPI (see vite.config.ts).
 * Prod: set VITE_API_BASE to your API origin if the UI is served separately.
 */
function apiBase(): string {
  const raw = import.meta.env.VITE_API_BASE;
  if (typeof raw === "string" && raw.length > 0) {
    return raw.replace(/\/$/, "");
  }
  if (import.meta.env.DEV) {
    return "";
  }
  return "http://127.0.0.1:8000";
}

const API_BASE = apiBase();

/** Strip +91 / spaces; keep last 10 digits for Indian numbers (backend expects [6-9]##########). */
export function normalizeIndianPhone(raw: string): string {
  const d = raw.replace(/\D/g, "");
  if (d.length >= 12 && d.startsWith("91")) return d.slice(-10);
  if (d.length === 11 && d.startsWith("0")) return d.slice(1);
  if (d.length > 10) return d.slice(-10);
  return d;
}

function messageFromErrorBody(data: Record<string, unknown>): string {
  const detail = data.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((x) =>
        typeof x === "object" && x !== null && "msg" in x ? String((x as { msg: unknown }).msg) : String(x),
      )
      .join(", ");
  }
  if (typeof data.error === "string") return data.error;
  return "Something went wrong";
}

/** Avoid `Unexpected end of JSON input` when the body is empty (API down, proxy 502, etc.). */
async function parseResponseBody(res: Response): Promise<Record<string, unknown>> {
  const text = await res.text();
  if (!text.trim()) {
    if (!res.ok) {
      if (res.status === 502 || res.status === 503 || res.status === 504) {
        throw new Error("Could not reach the API. Is the backend running? (502/503)");
      }
      throw new Error(`Request failed (${res.status}). Empty response from server.`);
    }
    return {};
  }
  try {
    return JSON.parse(text) as Record<string, unknown>;
  } catch {
    throw new Error(`Invalid response (${res.status}): ${text.slice(0, 120)}`);
  }
}

async function request<T>(endpoint: string, body: Record<string, unknown>): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const data = await parseResponseBody(res);

  if (!res.ok) {
    throw new Error(messageFromErrorBody(data));
  }

  return data as T;
}

async function get<T>(endpoint: string): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });

  const data = await parseResponseBody(res);

  if (!res.ok) {
    throw new Error(messageFromErrorBody(data));
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

export interface RagUploadResponse {
  status: string;
  chunks_processed: number;
}

// ── Dashboard Types ──

export interface BrainInsight {
  id: string;
  type: "income" | "spending" | "risk" | "behavior" | "optimization" | "system";
  title: string;
  text: string;
  suggestion?: string | null;
  action?: string | null;
  time: string;
}

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
  insights: BrainInsight[];
  has_data: boolean;
  source: string;
  last_updated: string | null;
  data_sources: string[];
  message: string | null;
}

export interface LatestInsightsResponse {
  insights: BrainInsight[];
}

export interface BillItem {
  name: string;
  amount: number;
  avg?: number;
  provider?: string;
  due_date?: string;
  next_billing?: string;
  status?: string;
  category?: string;
}

export interface BillsData {
  month: string;
  year: number;
  month_number: number;
  bills: BillItem[];
  total_outflow: number;
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
  type: "bill" | "insurance" | "investment" | "income";
  tag: string;
  title: string;
  subtitle: string;
  amount?: string;
}

export interface CalendarData {
  month: string;
  year: number;
  month_number: number;
  events: CalendarEvent[];
  daily_spend: Record<string, number>;
  total_month_spend: number;
  has_data: boolean;
  source: string;
  last_updated: string | null;
  data_sources: string[];
  message: string | null;
}

export interface ChatThread {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  preview?: string | null;
}

export interface ChatHistoryMessage {
  id: number;
  role: string;
  content: string;
  timestamp: string;
  thread_id: number;
}

export interface ChatResponseData {
  thread_id?: number;
  thread_title?: string;
  agent_used?: string;
  agent_trace?: Array<Record<string, unknown>>;
  structured_output?: Record<string, unknown>;
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
  // Auth & Onboarding (phone normalized to 10 digits for FastAPI validators)
  sendOtp: (phone: string) =>
    request<SendOtpResponse>("/api/auth/send-otp", { phone: normalizeIndianPhone(phone) }),

  verifyOtp: (phone: string, otp: string) =>
    request<VerifyOtpResponse>("/api/auth/verify-otp", { phone: normalizeIndianPhone(phone), otp }),

  demoLogin: (phone: string) =>
    request<{ user_id: string; name: string; status: string }>("/api/auth/demo-login", {
      phone: normalizeIndianPhone(phone),
    }),

  submitKyc: (data: {
    user_id: string;
    first_name: string;
    last_name: string;
    email?: string;
    pan: string;
  }) => request<KycResponse>("/api/user/kyc", data as Record<string, unknown>),

  startScan: (userId: string) =>
    request<ScanResponse>("/api/onboarding/scan", { user_id: userId }),

  uploadDocument: async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);

    const res = await fetch(`${API_BASE}/rag/upload`, {
      method: "POST",
      body: formData,
    });

    const data = await parseResponseBody(res);

    if (!res.ok) {
      throw new Error(messageFromErrorBody(data));
    }

    return data as RagUploadResponse;
  },

  activateData: async (userId: string, file: File) => {
    const formData = new FormData();
    formData.append("user_id", userId);
    formData.append("file", file);

    const res = await fetch(`${API_BASE}/data/upload`, {
      method: "POST",
      body: formData,
    });

    const data = await parseResponseBody(res);
    if (!res.ok) {
      throw new Error(messageFromErrorBody(data));
    }
    return data;
  },

  getActivationStatus: (userId: string) =>
    get<{ status: string; progress: number; stage: string; error?: string }>(`/api/data/status?user_id=${encodeURIComponent(userId)}`),

  // Dashboard APIs
  getHomeSummary: (userId: string) =>
    get<HomeSummary>(`/api/dashboard/home?user_id=${encodeURIComponent(userId)}`),

  getLatestInsights: (userId: string) =>
    get<LatestInsightsResponse>(`/api/insights/latest?user_id=${encodeURIComponent(userId)}`),

  getBills: (userId: string, year?: number, month?: number) => {
    const params = new URLSearchParams({ user_id: userId });
    if (year) params.set("year", String(year));
    if (month) params.set("month", String(month));
    return get<BillsData>(`/api/dashboard/bills?${params.toString()}`);
  },

  getCards: (userId: string) =>
    get<CardsData>(`/api/dashboard/cards?user_id=${encodeURIComponent(userId)}`),

  getCalendar: (userId: string, year: number, month: number) =>
    get<CalendarData>(
      `/api/dashboard/calendar?user_id=${encodeURIComponent(userId)}&year=${year}&month=${month}`,
    ),

  getChatThreads: (userId: string) =>
    get<ChatThread[]>(`/chat/threads?user_id=${encodeURIComponent(userId)}`),

  getChatHistory: (userId: string, threadId: number) =>
    get<ChatHistoryMessage[]>(`/chat/history?user_id=${encodeURIComponent(userId)}&thread_id=${threadId}`),

  getProfile: (userId: string) =>
    get<ProfileData>(`/api/dashboard/profile?user_id=${encodeURIComponent(userId)}`),

  // Agent Chat
  chat: (userId: string, message: string, threadId?: number, agentHint?: string) =>
    request<{ response: string; sources: string[]; data?: ChatResponseData }>(
      "/chat",
      { user_id: userId, message, thread_id: threadId, agent_hint: agentHint },
    ),
};
