import {
  Wallet,
  Transaction,
  Category,
  Budget,
  TransactionSummary,
  BotStatusMap,
  FIREMetrics,
  AssetAllocation,
  PlannerHealthContext,
  PersonalProfile,
  PlannerMessage,
  PlannerStreamMeta,
} from "./types";

const API_BASE = (
  typeof window !== "undefined"
    ? ""
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
).replace(/\/+$/, "");

function getAuthHeader(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("ai_finance_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export interface AuthUser {
  id: string;
  email: string;
  full_name: string | null;
  base_currency: string;
  role: string;
}

export function getStoredUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem("ai_finance_user");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function hasAuthToken(): boolean {
  if (typeof window === "undefined") return false;
  return Boolean(localStorage.getItem("ai_finance_token"));
}

export function logoutUser(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem("ai_finance_token");
  localStorage.removeItem("ai_finance_user");
  window.location.href = "/login";
}

export async function apiFetch<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}/api/v1${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;
  const headers = {
    "Content-Type": "application/json",
    ...getAuthHeader(),
    ...(options.headers || {}),
  };

  const res = await fetch(url, { ...options, headers });
  if (res.status === 401 && typeof window !== "undefined" && !endpoint.startsWith("/auth/")) {
    localStorage.removeItem("ai_finance_token");
    localStorage.removeItem("ai_finance_user");
    if (!window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    let errMessage = `API error: ${res.status} ${res.statusText}`;
    try {
      const errJson = await res.json();
      if (errJson.detail) errMessage = errJson.detail;
    } catch {}
    throw new Error(errMessage);
  }
  return res.json();
}

// ----------------- AUTH -----------------
export async function loginUser(email: string, password: string): Promise<{ access_token: string; user: AuthUser }> {
  const res = await apiFetch<{ access_token: string; user: AuthUser }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  if (typeof window !== "undefined") {
    localStorage.setItem("ai_finance_token", res.access_token);
    localStorage.setItem("ai_finance_user", JSON.stringify(res.user));
  }
  return res;
}

export async function registerUser(data: { email: string; password: string; full_name?: string; base_currency?: string }): Promise<{ access_token: string; user: AuthUser }> {
  const res = await apiFetch<{ access_token: string; user: AuthUser }>("/auth/register", {
    method: "POST",
    body: JSON.stringify(data),
  });
  if (typeof window !== "undefined") {
    localStorage.setItem("ai_finance_token", res.access_token);
    localStorage.setItem("ai_finance_user", JSON.stringify(res.user));
  }
  return res;
}

// ----------------- WALLETS -----------------
export async function getWallets(): Promise<{ total_balance: number; currency: string; wallets: Wallet[] }> {
  try {
    return await apiFetch("/wallets");
  } catch {
    return {
      total_balance: 16250000,
      currency: "IDR",
      wallets: [
        { id: "1", name: "Bank BCA", type: "BANK", balance: 15000000, currency: "IDR", color: "#3b82f6", is_default: false, created_at: new Date().toISOString() },
        { id: "2", name: "GoPay", type: "EWALLET", balance: 750000, currency: "IDR", color: "#06b6d4", is_default: false, created_at: new Date().toISOString() },
        { id: "3", name: "Cash Dompet", type: "CASH", balance: 500000, currency: "IDR", color: "#10b981", is_default: true, created_at: new Date().toISOString() },
      ],
    };
  }
}

export async function createWallet(data: { name: string; type: string; balance: number; currency?: string; color?: string; is_default?: boolean }): Promise<Wallet> {
  return apiFetch("/wallets", { method: "POST", body: JSON.stringify(data) });
}

export async function transferFunds(data: { from_wallet_id: string; to_wallet_id: string; amount: number; description?: string }) {
  return apiFetch("/wallets/transfer", { method: "POST", body: JSON.stringify(data) });
}

export async function deleteWallet(walletId: string) {
  return apiFetch(`/wallets/${walletId}`, { method: "DELETE" });
}

// ----------------- TRANSACTIONS -----------------
export async function getTransactions(params?: { wallet_id?: string; category_id?: string; type?: string; search?: string; limit?: number; offset?: number }): Promise<{ total: number; items: Transaction[] }> {
  try {
    const q = new URLSearchParams();
    if (params?.wallet_id) q.append("wallet_id", params.wallet_id);
    if (params?.category_id) q.append("category_id", params.category_id);
    if (params?.type) q.append("type", params.type);
    if (params?.search) q.append("search", params.search);
    if (params?.limit) q.append("limit", params.limit.toString());
    const queryStr = q.toString() ? `?${q.toString()}` : "";
    return await apiFetch(`/transactions${queryStr}`);
  } catch {
    return {
      total: 3,
      items: [
        { id: "1", type: "EXPENSE", amount: 28000, currency: "IDR", amount_in_base: 28000, description: "Kopi Kenangan", merchant: "Kopi Kenangan", wallet: { id: "2", name: "GoPay", color: "#06b6d4" }, category: { id: "c1", name: "Makanan & Minuman", icon: "utensils", color: "#ef4444" }, raw_source: "TELEGRAM", transaction_date: new Date().toISOString() },
        { id: "2", type: "EXPENSE", amount: 50000, currency: "IDR", amount_in_base: 50000, description: "Bensin Pertamax", merchant: "SPBU Pertamina", wallet: { id: "3", name: "Cash Dompet", color: "#10b981" }, category: { id: "c2", name: "Transportasi", icon: "car", color: "#f97316" }, raw_source: "WEB", transaction_date: new Date(Date.now() - 86400000).toISOString() },
        { id: "3", type: "INCOME", amount: 12000000, currency: "IDR", amount_in_base: 12000000, description: "Gaji Bulanan", merchant: null, wallet: { id: "1", name: "Bank BCA", color: "#3b82f6" }, category: { id: "c3", name: "Gaji & Pendapatan", icon: "wallet", color: "#22c55e" }, raw_source: "WEB", transaction_date: new Date(Date.now() - 172800000).toISOString() },
      ],
    };
  }
}

export async function createTransaction(data: { wallet_id: string; category_id?: string; type: string; amount: number; description: string; merchant?: string; raw_source?: string; transaction_date?: string }): Promise<Transaction> {
  return apiFetch("/transactions", { method: "POST", body: JSON.stringify(data) });
}

export async function deleteTransaction(txId: string) {
  return apiFetch(`/transactions/${txId}`, { method: "DELETE" });
}

export async function getTransactionSummary(): Promise<TransactionSummary> {
  try {
    return await apiFetch("/transactions/summary");
  } catch {
    return {
      currency: "IDR",
      total_income: 12000000,
      total_expense: 78000,
      net_savings: 11922000,
      category_breakdown: [
        { name: "Makanan & Minuman", color: "#ef4444", total: 28000 },
        { name: "Transportasi", color: "#f97316", total: 50000 },
      ],
    };
  }
}

// ----------------- BUDGETS & CATEGORIES -----------------
export async function getBudgets(): Promise<Budget[]> {
  try {
    return await apiFetch("/budgets");
  } catch {
    return [
      { id: "b1", category: { id: "c1", name: "Makanan & Minuman", icon: "utensils", color: "#ef4444" }, limit_amount: 3000000, spent_amount: 1450000, remaining_amount: 1550000, percent_used: 48.3, is_over_budget: false, period: "MONTHLY" },
      { id: "b2", category: { id: "c2", name: "Transportasi", icon: "car", color: "#f97316" }, limit_amount: 1000000, spent_amount: 350000, remaining_amount: 650000, percent_used: 35.0, is_over_budget: false, period: "MONTHLY" },
      { id: "b3", category: { id: "c4", name: "Hiburan & Rekreasi", icon: "film", color: "#8b5cf6" }, limit_amount: 750000, spent_amount: 680000, remaining_amount: 70000, percent_used: 90.7, is_over_budget: false, period: "MONTHLY" },
    ];
  }
}

export async function getCategories(): Promise<Category[]> {
  try {
    return await apiFetch("/budgets/categories");
  } catch {
    return [
      { id: "c1", name: "Makanan & Minuman", icon: "utensils", color: "#ef4444", type: "EXPENSE", is_system: true },
      { id: "c2", name: "Transportasi", icon: "car", color: "#f97316", type: "EXPENSE", is_system: true },
      { id: "c3", name: "Belanja", icon: "shopping-bag", color: "#eab308", type: "EXPENSE", is_system: true },
      { id: "c4", name: "Tagihan & Utilitas", icon: "receipt", color: "#06b6d4", type: "EXPENSE", is_system: true },
      { id: "c5", name: "Hiburan & Rekreasi", icon: "film", color: "#8b5cf6", type: "EXPENSE", is_system: true },
      { id: "c6", name: "Gaji & Pendapatan", icon: "wallet", color: "#22c55e", type: "INCOME", is_system: true },
      { id: "c7", name: "Lain-lain", icon: "more-horizontal", color: "#64748b", type: "EXPENSE", is_system: true },
    ];
  }
}

export async function createBudget(data: { category_id: string; limit_amount: number; period?: string }): Promise<Budget> {
  return apiFetch("/budgets", { method: "POST", body: JSON.stringify(data) });
}

export async function deleteBudget(budgetId: string) {
  return apiFetch(`/budgets/${budgetId}`, { method: "DELETE" });
}

// ----------------- BOT PAIRING & SIMULATION -----------------
export async function generatePairingCode(platform: "TELEGRAM" | "WHATSAPP"): Promise<{ platform: string; pairing_code: string; expires_in_minutes: number; instruction: string }> {
  return apiFetch("/bot/generate-code", { method: "POST", body: JSON.stringify({ platform }) });
}

export async function getBotStatus(): Promise<BotStatusMap> {
  try {
    return await apiFetch("/bot/status");
  } catch {
    return {
      TELEGRAM: { connected: false, username: null },
      WHATSAPP: { connected: false, username: null },
    };
  }
}

export async function unlinkBot(platform: "telegram" | "whatsapp") {
  return apiFetch(`/bot/unlink/${platform}`, { method: "DELETE" });
}

export async function simulateChatMessage(message: string, source: string = "TELEGRAM", receipt_data?: any) {
  return apiFetch<{ success: boolean; message: string; transaction_id?: string; parsed?: any; wallet?: any }>("/webhooks/simulate-chat", {
    method: "POST",
    body: JSON.stringify({ message, source, receipt_data }),
  });
}

// ----------------- AI FINANCIAL PLANNER -----------------
export async function getPlannerOverview(): Promise<{
  context: PlannerHealthContext;
  allocations: AssetAllocation;
  personal_profile?: PersonalProfile;
}> {
  try {
    return await apiFetch("/planner/health-score");
  } catch {
    return {
      context: {
        base_currency: "IDR",
        net_worth_formatted: "Rp 16.250.000",
        total_wallet_balance_formatted: "Rp 16.250.000",
        liquid_balance_formatted: "Rp 16.250.000",
        monthly_income_formatted: "Rp 15.000.000",
        monthly_expenses_formatted: "Rp 8.000.000",
        monthly_debt_formatted: "Rp 0",
        dsr_percentage: 0,
        savings_margin_percentage: 46.7,
        household_summary: "Lajang, 0 tanggungan",
        emergency_fund_months: 2.0,
        emergency_target_months: 3,
        emergency_fund_status: "Perlu Ditingkatkan",
        current_age: 28,
        target_fire_age: 45,
        fire_target_formatted: "Rp 2.400.000.000",
        coast_fire_formatted: "Rp 760.000.000",
        is_coast_fire_achieved: false,
        risk_profile: "MODERATE",
        sharia_preference: false,
        health_score: 65,
        health_status: "HEALTHY",
        profile_completeness_pct: 20,
        missing_profile_hints: [
          "Penghasilan bersih bulanan",
          "Status pernikahan & jumlah tanggungan",
        ],
      },
      allocations: {
        profile: "Moderat (Balanced Growth)",
        description: "Keseimbangan ideal antara apresiasi modal jangka panjang dan stabilitas arus kas.",
        expected_cagr: "8.5% - 10.5%",
        allocations: [
          { asset: "Saham & Reksa Dana Saham", percentage: 40, color: "#8b5cf6" },
          { asset: "Obligasi Negara / SBN", percentage: 30, color: "#3b82f6" },
          { asset: "Reksa Dana Pendapatan Tetap & Pasar Uang", percentage: 15, color: "#10b981" },
          { asset: "Emas Fisik / Antam", percentage: 10, color: "#eab308" },
          { asset: "Aset Alternatif / Crypto", percentage: 5, color: "#f97316" },
        ],
      },
    };
  }
}

export async function updatePersonalProfile(data: Partial<{
  monthly_income: number;
  monthly_living_expense: number;
  monthly_debt_payment: number;
  marital_status: "SINGLE" | "MARRIED";
  dependents_count: number;
  current_age: number;
  target_fire_age: number;
  risk_tolerance: "CONSERVATIVE" | "MODERATE" | "AGGRESSIVE";
  sharia_preference: boolean;
  memory_notes: string;
}>): Promise<{
  context: PlannerHealthContext;
  allocations: AssetAllocation;
  personal_profile: PersonalProfile;
}> {
  return apiFetch("/planner/personal-profile", {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function getPlannerChatHistory(): Promise<PlannerMessage[]> {
  try {
    return await apiFetch("/planner/history");
  } catch {
    return [];
  }
}

export async function clearPlannerChatHistory(): Promise<{ cleared: boolean; deleted_count: number }> {
  return apiFetch("/planner/history", { method: "DELETE" });
}

export async function sendPlannerMessageStream(
  message: string,
  onChunk: (chunk: string) => void,
  onMeta?: (meta: PlannerStreamMeta) => void,
): Promise<void> {
  const url = `${API_BASE}/api/v1/planner/chat`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeader(),
    },
    body: JSON.stringify({ message }),
  });

  if (!res.ok) {
    throw new Error(`Chat error: ${res.statusText}`);
  }

  const reader = res.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  let buffer = "";
  let done = false;

  while (!done) {
    const { value, done: streamDone } = await reader.read();
    done = streamDone;
    if (value) {
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const rawLine of lines) {
        const line = rawLine.trim();
        if (!line.startsWith("data:")) continue;
        const dataStr = line.slice(5).trim();
        if (dataStr === "[DONE]") {
          return;
        }
        try {
          const parsed = JSON.parse(dataStr);
          if (parsed.meta && onMeta) {
            onMeta(parsed.meta as PlannerStreamMeta);
          }
          if (parsed.chunk) {
            onChunk(parsed.chunk);
          }
        } catch {}
      }
    }
  }
}

// ----------------- FIRE & FINANCIAL FREEDOM -----------------
export async function getFIREProfile(): Promise<{ profile: any; metrics: FIREMetrics; allocations: AssetAllocation }> {
  try {
    return await apiFetch("/fire/profile");
  } catch {
    return {
      profile: { current_age: 28, target_fire_age: 45, monthly_living_expense: 8000000, risk_tolerance: "MODERATE" },
      metrics: {
        fire_number: 2400000000,
        annual_expenses: 96000000,
        withdrawal_rate: 0.04,
        current_net_worth: 16250000,
        progress_percentage: 0.7,
        years_to_target_age: 17,
        projected_net_worth_at_fire_age: 450000000,
        is_on_track: false,
        actual_years_needed: 24.5,
      },
      allocations: {
        profile: "Moderat",
        description: "Alokasi berimbang untuk akselerasi pertumbuhan modal menuju FIRE.",
        expected_cagr: "9.0%",
        allocations: [
          { asset: "Saham IDX & US ETF", percentage: 40, color: "#8b5cf6" },
          { asset: "Obligasi Negara / SBN", percentage: 30, color: "#3b82f6" },
          { asset: "Pasar Uang & Likuid", percentage: 15, color: "#10b981" },
          { asset: "Emas", percentage: 10, color: "#eab308" },
          { asset: "Crypto / Alternatif", percentage: 5, color: "#f97316" },
        ],
      },
    };
  }
}

export async function calculateCustomFIRE(params: {
  current_age: number;
  target_fire_age: number;
  monthly_expenses: number;
  current_net_worth: number;
  monthly_savings: number;
  annual_return_rate: number;
}): Promise<FIREMetrics> {
  return apiFetch("/fire/calculate", { method: "POST", body: JSON.stringify(params) });
}
