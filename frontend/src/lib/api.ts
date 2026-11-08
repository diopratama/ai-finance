import {
  Wallet,
  Transaction,
  Category,
  Budget,
  BudgetGroupItem,
  MonthlyAllocationResponse,
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
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001"
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
  is_verified?: boolean;
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
    if (!window.location.pathname.startsWith("/login") && !window.location.pathname.startsWith("/register") && window.location.pathname !== "/") {
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

export interface RegisterResult {
  status: string;
  email: string;
  full_name: string;
  message: string;
  is_verified: boolean;
}

export async function registerUser(data: {
  email: string;
  password: string;
  full_name: string;
  base_currency?: string;
}): Promise<RegisterResult> {
  return await apiFetch<RegisterResult>("/auth/register", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function verifyEmail(email: string, code: string): Promise<{ access_token: string; user: AuthUser }> {
  const res = await apiFetch<{ access_token: string; user: AuthUser }>("/auth/verify-email", {
    method: "POST",
    body: JSON.stringify({ email, code }),
  });
  if (typeof window !== "undefined") {
    localStorage.setItem("ai_finance_token", res.access_token);
    localStorage.setItem("ai_finance_user", JSON.stringify(res.user));
  }
  return res;
}

export async function resendVerification(email: string): Promise<{ ok: boolean; message: string }> {
  return await apiFetch<{ ok: boolean; message: string }>("/auth/resend-verification", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function getUserProfile(): Promise<AuthUser & { created_at: string }> {
  return await apiFetch<AuthUser & { created_at: string }>("/auth/profile");
}

export async function updateUserProfile(data: {
  full_name: string;
  email: string;
  base_currency?: string;
}): Promise<AuthUser & { created_at: string }> {
  const res = await apiFetch<AuthUser & { created_at: string }>("/auth/profile", {
    method: "PUT",
    body: JSON.stringify(data),
  });
  if (typeof window !== "undefined") {
    localStorage.setItem("ai_finance_user", JSON.stringify(res));
  }
  return res;
}

export async function changePassword(data: {
  old_password: string;
  new_password: string;
}): Promise<{ ok: boolean; message: string }> {
  return await apiFetch<{ ok: boolean; message: string }>("/auth/change-password", {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

// ----------------- ADMIN -----------------
export interface AdminStats {
  total_users: number;
  verified_users: number;
  unverified_users: number;
  active_users_30d: number;
  total_transactions: number;
  total_system_wallets: number;
  total_system_balance: number;
  bot_connected_users: number;
}

export interface AdminUserItem {
  id: string;
  full_name: string;
  email: string;
  role: string;
  is_verified: boolean;
  base_currency: string;
  created_at: string;
  wallet_count: number;
  total_balance: number;
  transaction_count: number;
  has_bot_linked: boolean;
}

export interface AdminUsersResponse {
  total: number;
  page: number;
  limit: number;
  users: AdminUserItem[];
}

export async function getAdminStats(): Promise<AdminStats> {
  return await apiFetch<AdminStats>("/admin/stats");
}

export async function getAdminUsers(params?: {
  search?: string;
  page?: number;
  limit?: number;
}): Promise<AdminUsersResponse> {
  const q = new URLSearchParams();
  if (params?.search) q.set("search", params.search);
  if (params?.page) q.set("page", String(params.page));
  if (params?.limit) q.set("limit", String(params.limit));
  const qs = q.toString() ? `?${q.toString()}` : "";
  return await apiFetch<AdminUsersResponse>(`/admin/users${qs}`);
}

// ----------------- WALLETS -----------------
export async function getWallets(month?: string): Promise<{
  total_balance: number;
  personal_balance?: number;
  shared_balance?: number;
  currency: string;
  month_key?: string;
  wallets: Wallet[];
}> {
  try {
    const q = month ? `?month=${encodeURIComponent(month)}` : "";
    return await apiFetch(`/wallets${q}`);
  } catch {
    return {
      total_balance: 16250000,
      personal_balance: 16250000,
      shared_balance: 0,
      currency: "IDR",
      wallets: [
        { id: "1", name: "Bank BCA", type: "BANK", balance: 15000000, currency: "IDR", color: "#f0b000", is_default: false, created_at: new Date().toISOString() },
        { id: "2", name: "GoPay", type: "EWALLET", balance: 750000, currency: "IDR", color: "#06b6d4", is_default: false, created_at: new Date().toISOString() },
        { id: "3", name: "Cash Dompet", type: "CASH", balance: 500000, currency: "IDR", color: "#10b981", is_default: true, created_at: new Date().toISOString() },
      ],
    };
  }
}

export async function createWallet(data: { name: string; type: string; balance: number; currency?: string; color?: string; is_default?: boolean }): Promise<Wallet> {
  return apiFetch("/wallets", { method: "POST", body: JSON.stringify(data) });
}

export async function updateWallet(
  walletId: string,
  data: Partial<{ name: string; type: string; balance: number; color: string; is_default: boolean; is_archived: boolean }>
): Promise<Wallet> {
  return apiFetch(`/wallets/${walletId}`, { method: "PUT", body: JSON.stringify(data) });
}

export async function transferFunds(data: { from_wallet_id: string; to_wallet_id: string; amount: number; description?: string }) {
  return apiFetch("/wallets/transfer", { method: "POST", body: JSON.stringify(data) });
}

export async function deleteWallet(walletId: string) {
  return apiFetch(`/wallets/${walletId}`, { method: "DELETE" });
}

export async function addWalletMember(
  walletId: string,
  data: { email: string; role?: "EDITOR" | "VIEWER" }
): Promise<{ message: string; member: { user_id: string; name: string; email: string; role: string } }> {
  return apiFetch(`/wallets/${walletId}/members`, { method: "POST", body: JSON.stringify(data) });
}

export async function updateWalletMemberRole(
  walletId: string,
  memberUserId: string,
  role: "EDITOR" | "VIEWER"
): Promise<{ message: string; role: string }> {
  return apiFetch(`/wallets/${walletId}/members/${memberUserId}`, { method: "PUT", body: JSON.stringify({ role }) });
}

export async function removeWalletMember(walletId: string, memberUserId: string): Promise<{ message: string }> {
  return apiFetch(`/wallets/${walletId}/members/${memberUserId}`, { method: "DELETE" });
}

// ----------------- TRANSACTIONS -----------------
export async function getTransactions(params?: {
  wallet_id?: string;
  category_id?: string;
  budget_id?: string;
  type?: string;
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<{ total: number; items: Transaction[] }> {
  try {
    const q = new URLSearchParams();
    if (params?.wallet_id) q.append("wallet_id", params.wallet_id);
    if (params?.category_id) q.append("category_id", params.category_id);
    if (params?.budget_id) q.append("budget_id", params.budget_id);
    if (params?.type) q.append("type", params.type);
    if (params?.search) q.append("search", params.search);
    if (params?.limit) q.append("limit", params.limit.toString());
    const queryStr = q.toString() ? `?${q.toString()}` : "";
    return await apiFetch(`/transactions${queryStr}`);
  } catch {
    return { total: 0, items: [] };
  }
}

export async function createTransaction(data: {
  wallet_id?: string;
  category_id?: string;
  budget_id?: string;
  type: string;
  amount: number;
  description: string;
  merchant?: string;
  raw_source?: string;
  transaction_date?: string;
}): Promise<Transaction> {
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
      total_income: 0,
      total_expense: 0,
      net_savings: 0,
      category_breakdown: [],
    };
  }
}

// ----------------- BUDGETS, ALLOCATIONS & CATEGORIES -----------------
export async function getBudgetAllocation(month?: string): Promise<MonthlyAllocationResponse> {
  const q = month ? `?month=${encodeURIComponent(month)}` : "";
  return apiFetch(`/budgets/allocation${q}`);
}

export async function getBudgets(month?: string): Promise<Budget[]> {
  try {
    const q = month ? `?month=${encodeURIComponent(month)}` : "";
    return await apiFetch(`/budgets${q}`);
  } catch {
    return [];
  }
}

export async function getCategories(): Promise<Category[]> {
  try {
    return await apiFetch("/budgets/categories");
  } catch {
    return [];
  }
}

export async function createCustomCategory(data: {
  name: string;
  type?: "EXPENSE" | "INCOME";
  color?: string;
  icon?: string;
}): Promise<Category> {
  return apiFetch("/budgets/categories", { method: "POST", body: JSON.stringify(data) });
}

export async function updateCustomCategory(
  categoryId: string,
  data: Partial<{ name: string; type: "EXPENSE" | "INCOME"; color: string; icon: string }>
): Promise<Category> {
  return apiFetch(`/budgets/categories/${categoryId}`, { method: "PUT", body: JSON.stringify(data) });
}

export async function deleteCustomCategory(categoryId: string) {
  return apiFetch(`/budgets/categories/${categoryId}`, { method: "DELETE" });
}

export async function createBudget(data: {
  name?: string;
  group_type?: string;
  limit_amount: number;
  remark?: string;
  wallet_id?: string | null;
  category_id?: string | null;
  month_key?: string;
  is_sinking_fund?: boolean;
  rollover_balance?: number;
  funded_this_month?: number;
  period?: string;
}): Promise<Budget> {
  return apiFetch("/budgets", { method: "POST", body: JSON.stringify(data) });
}

export async function updateBudget(
  budgetId: string,
  data: Partial<{
    name: string;
    group_type: string;
    limit_amount: number;
    remark: string;
    wallet_id: string | null;
    category_id: string | null;
    is_sinking_fund: boolean;
    rollover_balance: number;
    funded_this_month: number;
    sort_order: number;
  }>
): Promise<Budget> {
  return apiFetch(`/budgets/${budgetId}`, { method: "PUT", body: JSON.stringify(data) });
}

export async function deleteBudget(budgetId: string) {
  return apiFetch(`/budgets/${budgetId}`, { method: "DELETE" });
}

export async function getBudgetGroups(): Promise<BudgetGroupItem[]> {
  try {
    return await apiFetch("/budgets/groups");
  } catch {
    return [];
  }
}

export async function createBudgetGroup(data: {
  name: string;
  is_sinking_fund?: boolean;
  sort_order?: number;
}): Promise<BudgetGroupItem> {
  return apiFetch("/budgets/groups", { method: "POST", body: JSON.stringify(data) });
}

export async function updateBudgetGroup(
  groupId: string,
  data: Partial<{ name: string; is_sinking_fund: boolean; sort_order: number }>
): Promise<BudgetGroupItem> {
  return apiFetch(`/budgets/groups/${groupId}`, { method: "PUT", body: JSON.stringify(data) });
}

export async function deleteBudgetGroup(
  groupId: string,
  options?: { action?: "cascade" | "reassign"; reassign_to_id?: string; reassign_to_name?: string }
): Promise<{ success: boolean; deleted_group_id: string; items_affected: number; action_taken: string }> {
  const q = new URLSearchParams();
  if (options?.action) q.append("action", options.action);
  if (options?.reassign_to_id) q.append("reassign_to_id", options.reassign_to_id);
  if (options?.reassign_to_name) q.append("reassign_to_name", options.reassign_to_name);
  const qs = q.toString() ? `?${q.toString()}` : "";
  return apiFetch(`/budgets/groups/${groupId}${qs}`, { method: "DELETE" });
}

export async function renameBudgetGroup(data: {
  old_group_type: string;
  new_group_type: string;
  month_key?: string;
  is_sinking_fund?: boolean;
}) {
  return apiFetch("/budgets/groups/rename", { method: "PUT", body: JSON.stringify(data) });
}

export async function updateReferenceIncome(monthly_income: number) {
  return apiFetch<{ monthly_income: number }>("/budgets/reference-income", {
    method: "PUT",
    body: JSON.stringify({ monthly_income }),
  });
}

export async function copyPreviousMonthBudgets(data: {
  target_month: string;
  source_month?: string;
  overwrite?: boolean;
}): Promise<{ copied_count: number; source_month: string; target_month: string; allocation: MonthlyAllocationResponse }> {
  return apiFetch("/budgets/copy-month", { method: "POST", body: JSON.stringify(data) });
}

export async function distributePaydayToWallets(data: {
  source_wallet_id: string;
  month_key?: string;
  transfers?: Array<{ to_wallet_id: string; amount: number }>;
  mode?: "SHORTFALL" | "FULL_BUDGET";
  auto_fund_sinking?: boolean;
}): Promise<{ message: string; transfers_executed: Array<{ to_wallet_id: string; to_wallet_name: string; amount: number }>; allocation: MonthlyAllocationResponse }> {
  return apiFetch("/budgets/distribute-payday", { method: "POST", body: JSON.stringify(data) });
}

export async function recordBudgetAction(
  budgetId: string,
  data: {
    mode: "EXPENSE" | "FUND_SINKING" | "TRANSFER_ALLOCATION";
    amount?: number;
    wallet_id?: string;
    source_wallet_id?: string;
    description?: string;
  }
) {
  return apiFetch<{
    mode: string;
    item: Budget;
    transaction_id?: string;
    wallet_balance?: number;
    source_wallet_balance?: number;
    dest_wallet_balance?: number;
  }>(
    `/budgets/${budgetId}/record`,
    { method: "POST", body: JSON.stringify(data) }
  );
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
  return apiFetch<{ success: boolean; message: string; transaction_id?: string; parsed?: any; matched_budget?: any; wallet?: any }>("/webhooks/simulate-chat", {
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
          { asset: "Saham & Reksa Dana Saham", percentage: 40, color: "#f0b000" },
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
          { asset: "Saham IDX & US ETF", percentage: 40, color: "#f0b000" },
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
