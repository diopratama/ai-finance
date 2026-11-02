export interface Wallet {
  id: string;
  name: string;
  type: "CASH" | "BANK" | "EWALLET" | "INVESTMENT" | "CREDIT";
  balance: number;
  currency: string;
  color: string;
  is_default: boolean;
  created_at: string;
}

export interface Category {
  id: string;
  name: string;
  icon: string;
  color: string;
  type: "EXPENSE" | "INCOME";
  is_system: boolean;
}

export interface Transaction {
  id: string;
  type: "EXPENSE" | "INCOME" | "TRANSFER";
  amount: number;
  currency: string;
  amount_in_base: number;
  description: string;
  merchant?: string | null;
  wallet?: { id: string; name: string; color: string } | null;
  category?: { id: string; name: string; icon: string; color: string } | null;
  raw_source: string;
  transaction_date: string;
}

export interface Budget {
  id: string;
  category: {
    id: string;
    name: string;
    icon: string;
    color: string;
  } | null;
  limit_amount: number;
  spent_amount: number;
  remaining_amount: number;
  percent_used: number;
  is_over_budget: boolean;
  period: string;
}

export interface TransactionSummary {
  currency: string;
  total_income: number;
  total_expense: number;
  net_savings: number;
  category_breakdown: Array<{ name: string; color: string; total: number }>;
}

export interface BotPlatformStatus {
  connected: boolean;
  username: string | null;
}

export interface BotStatusMap {
  TELEGRAM: BotPlatformStatus;
  WHATSAPP: BotPlatformStatus;
}

export interface FIREMetrics {
  fire_number: number;
  coast_fire_number?: number;
  is_coast_fire_achieved?: boolean;
  annual_expenses: number;
  withdrawal_rate: number;
  current_net_worth: number;
  progress_percentage: number;
  years_to_target_age: number;
  projected_net_worth_at_fire_age: number;
  is_on_track: boolean;
  actual_years_needed: number | null;
}

export interface AssetAllocation {
  profile: string;
  description: string;
  expected_cagr: string;
  allocations: Array<{
    asset: string;
    percentage: number;
    color: string;
  }>;
}

export interface PlannerHealthContext {
  base_currency: string;
  net_worth_formatted: string;
  total_wallet_balance_formatted: string;
  liquid_balance_formatted?: string;
  monthly_income_formatted?: string;
  monthly_expenses_formatted: string;
  monthly_debt_formatted?: string;
  dsr_percentage?: number;
  savings_margin_percentage?: number;
  household_summary?: string;
  emergency_fund_months: number;
  emergency_target_months: number;
  emergency_fund_status: string;
  current_age: number;
  target_fire_age: number;
  fire_target_formatted: string;
  coast_fire_formatted?: string;
  is_coast_fire_achieved?: boolean;
  risk_profile: string;
  sharia_preference?: boolean;
  health_score: number;
  health_status: string;
  profile_completeness_pct?: number;
  missing_profile_hints?: string[];
}

export interface PersonalProfile {
  current_age: number;
  target_fire_age: number;
  monthly_income: number;
  monthly_living_expense: number;
  monthly_debt_payment: number;
  marital_status: "SINGLE" | "MARRIED";
  dependents_count: number;
  risk_tolerance: "CONSERVATIVE" | "MODERATE" | "AGGRESSIVE";
  sharia_preference: boolean;
  memory_notes: string;
  memory_notes_list: string[];
  confirmed_fields: string[];
  profile_completeness_pct: number;
  missing_profile_hints: string[];
}

export interface PlannerStreamMeta {
  active_skills: string[];
  skill_ids: string[];
  profile_updated: boolean;
  updated_fields: string[];
  profile_completeness_pct: number;
}

export interface PlannerMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
}
