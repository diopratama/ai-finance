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
  PortfolioReview,
  AccountBackupItem,
  InvestmentHistoryItem,
  ShariaStockIssuer,
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

// ----------------- BACKUP, RESET & RESTORE -----------------
export async function listAccountBackups(): Promise<{ items: AccountBackupItem[] }> {
  return await apiFetch<{ items: AccountBackupItem[] }>("/auth/backups");
}

export async function createAccountBackup(title?: string): Promise<AccountBackupItem & { backup_payload: any }> {
  return await apiFetch<AccountBackupItem & { backup_payload: any }>("/auth/backups", {
    method: "POST",
    body: JSON.stringify({ title: title || "Backup Manual" }),
  });
}

export async function exportAccountBackup(backupId: string): Promise<any> {
  return await apiFetch<any>(`/auth/backups/${backupId}/export`);
}

export async function deleteAccountBackup(backupId: string): Promise<{ ok: boolean; message: string }> {
  return await apiFetch<{ ok: boolean; message: string }>(`/auth/backups/${backupId}`, {
    method: "DELETE",
  });
}

export async function resetAccountData(data: {
  password: string;
  mode: "ZERO_WALLETS" | "FULL_ACCOUNT_RESET";
  wallet_ids?: string[];
  clear_transactions?: boolean;
}): Promise<{
  ok: boolean;
  mode: string;
  reset_wallets_count?: number;
  deleted_transactions_count?: number;
  auto_backup_id: string;
  message: string;
}> {
  return await apiFetch("/auth/reset-data", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function restoreAccountData(data: {
  password: string;
  backup_id?: string;
  backup_payload?: any;
}): Promise<{
  ok: boolean;
  restored_wallets_count: number;
  restored_transactions_count: number;
  restored_budgets_count: number;
  message: string;
}> {
  return await apiFetch("/auth/restore-data", {
    method: "POST",
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
  investment_balance?: number;
  currency: string;
  month_key?: string;
  wallets: Wallet[];
  portfolio_review?: PortfolioReview;
  market_rates?: import("./types").MarketRates;
}> {
  const q = month ? `?month=${encodeURIComponent(month)}` : "";
  return apiFetch(`/wallets${q}`);
}

export async function createWallet(data: {
  name: string;
  type: string;
  asset_class?: string | null;
  balance: number;
  currency?: string;
  color?: string;
  is_default?: boolean;
}): Promise<Wallet> {
  return apiFetch("/wallets", { method: "POST", body: JSON.stringify(data) });
}

export async function updateWallet(
  walletId: string,
  data: Partial<{
    name: string;
    type: string;
    asset_class: string | null;
    balance: number;
    currency: string;
    color: string;
    is_default: boolean;
    is_archived: boolean;
  }>
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
  month?: string;
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
    if (params?.month) q.append("month", params.month);
    if (params?.search) q.append("search", params.search);
    if (params?.limit) q.append("limit", params.limit.toString());
    if (params?.offset) q.append("offset", params.offset.toString());
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

export async function getTransactionSummary(month?: string): Promise<TransactionSummary> {
  try {
    const q = month ? `?month=${encodeURIComponent(month)}` : "";
    return await apiFetch(`/transactions/summary${q}`);
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
  portfolio_review?: PortfolioReview;
  personal_profile?: PersonalProfile;
}> {
  return apiFetch("/planner/health-score");
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
  onStatus?: (status: string) => void,
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
          if (parsed.status && onStatus) {
            onStatus(String(parsed.status));
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
export async function getFIREProfile(): Promise<{
  profile: any;
  metrics: FIREMetrics;
  allocations: AssetAllocation;
  portfolio_review?: PortfolioReview;
}> {
  return apiFetch("/fire/profile");
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

export async function updatePortfolioStrategy(
  strategy: string,
  custom_allocations?: Record<string, number>
): Promise<{
  success: boolean;
  portfolio_strategy: string;
  custom_allocations: Record<string, number>;
  portfolio_review: PortfolioReview;
}> {
  return apiFetch("/wallets/portfolio-strategy", {
    method: "PUT",
    body: JSON.stringify({ strategy, custom_allocations }),
  });
}

// ----------------- MULTI-AGENT INVESTMENT RESEARCH -----------------
export async function getInvestmentQuote(market: string, symbol: string, timeframe = "1D"): Promise<any> {
  return apiFetch(`/investment/quote?market=${encodeURIComponent(market)}&symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}`);
}

export async function getShariaStocksReference(query?: string): Promise<{
  total: number;
  source_name?: string;
  source_as_of?: string;
  valid_until?: string;
  counts?: { Ya: number; Tidak: number };
  issuers: ShariaStockIssuer[];
}> {
  const q = query ? `?query=${encodeURIComponent(query)}` : "";
  return apiFetch(`/investment/sharia-stocks${q}`);
}

export async function stopInvestmentTask(task_id: string): Promise<{ success: boolean; stopped: boolean; task_id: string }> {
  return apiFetch("/investment/stop", {
    method: "POST",
    body: JSON.stringify({ task_id }),
  });
}

export async function chatWithInvestmentAgent(payload: {
  symbol?: string;
  market: string;
  history: Array<{ role: string; content: string }>;
  analysis_context: any;
  user_message?: string;
  mode?: "standard" | "deep_validation";
}): Promise<{
  reply: string;
  mode: "standard" | "deep_validation";
  validation_meta?: any;
}> {
  return apiFetch("/investment/chat", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getInvestmentHistory(market?: string, limit = 20): Promise<InvestmentHistoryItem[]> {
  const m = market ? `?market=${encodeURIComponent(market)}&limit=${limit}` : `?limit=${limit}`;
  return apiFetch(`/investment/history${m}`);
}

export async function getInvestmentHistoryDetail(id: string): Promise<any> {
  return apiFetch(`/investment/history/${encodeURIComponent(id)}`);
}

export async function deleteInvestmentHistory(id: string): Promise<{ success: boolean; deleted_id: string }> {
  return apiFetch(`/investment/history/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}
