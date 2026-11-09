export interface WalletMember {
  user_id: string;
  name: string;
  email: string;
  role: "EDITOR" | "VIEWER";
  created_at?: string;
}

export interface Wallet {
  id: string;
  name: string;
  type: string; // Custom or preset e.g. BANK, EWALLET, CASH, KANTONG DIGITAL, BANK SYARIAH, INVESTMENT, CREDIT
  asset_class?: "EQUITY" | "BOND" | "MONEY_MARKET" | "GOLD" | "CRYPTO" | string | null;
  asset_class_label?: string | null;
  is_investment?: boolean;
  balance: number;
  balance_in_base?: number;
  formatted_native?: string;
  formatted_base?: string;
  currency: string;
  color: string;
  is_default: boolean;
  is_shared?: boolean;
  access_role?: "OWNER" | "EDITOR" | "VIEWER";
  owner?: { id: string; name: string; email: string } | null;
  members?: WalletMember[];
  created_at: string;
  allocated_budget?: number;
  remaining_commitment?: number;
  sinking_fund_held?: number;
  free_balance?: number;
  shortfall_amount?: number;
  funding_status?: "FUNDED" | "SHORTFALL" | "IDLE";
  assigned_items_count?: number;
}

export interface MarketRates {
  usd_idr: number;
  usd_to_idr?: number;
  gold_idr_per_gram: number;
  gold_per_gram_idr?: number;
  gold_antam_idr?: number;
  gold_buyback_idr?: number;
  gold_spot_idr?: number;
  gold_xau_usd?: number;
  updated_at: string;
  source: string;
}

export interface WalletsResponse {
  total_balance: number;
  personal_balance?: number;
  shared_balance?: number;
  investment_balance?: number;
  currency: string;
  month_key?: string;
  wallets: Wallet[];
  portfolio_review?: PortfolioReview | null;
  market_rates?: MarketRates;
}

export interface PortfolioAllocationComparison {
  asset_class: string;
  asset_class_label: string;
  reference_name: string;
  color: string;
  actual_amount: number;
  ideal_amount: number;
  delta_amount: number;
  actual_pct: number;
  target_pct: number;
  drift_pct: number;
  action: "IDEAL" | "UNDERWEIGHT" | "OVERWEIGHT";
  status_text: string;
}

export interface PortfolioBestPracticeItem {
  key: string;
  title: string;
  passed: boolean;
  detail: string;
}

export interface PortfolioReview {
  has_investment_wallets: boolean;
  investment_wallets_count: number;
  investment_wallets: Array<{
    id: string;
    name: string;
    type: string;
    balance: number;
    asset_class: string;
    asset_class_label: string;
  }>;
  total_investment_balance: number;
  liquid_cash_balance: number;
  total_net_worth: number;
  invested_ratio_pct: number;
  risk_profile: string;
  sharia_preference: boolean;
  reference_profile_name: string;
  reference_description: string;
  expected_cagr: string;
  alignment_score: number;
  status: "OPTIMAL" | "PERLU_REBALANCING" | "PERINGATAN_RISIKO" | "BELUM_ADA_INVESTASI";
  status_label: string;
  allocations_comparison: PortfolioAllocationComparison[];
  best_practices: PortfolioBestPracticeItem[];
  recommendations: string[];
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
  to_wallet?: { id: string; name: string; color: string } | null;
  created_by?: { id: string; name: string; email: string } | null;
  is_own?: boolean;
  category?: { id: string; name: string; icon: string; color: string } | null;
  budget?: { id: string; name: string; group_type: string } | null;
  raw_source: string;
  transaction_date: string;
}

export interface Budget {
  id: string;
  name: string;
  group_type: string;
  remark: string;
  limit_amount: number;
  spent_amount: number;
  remaining_amount: number;
  percent_used: number;
  is_over_budget: boolean;
  period: string;
  month_key: string;
  is_sinking_fund: boolean;
  rollover_balance: number;
  funded_this_month: number;
  accumulated_balance: number;
  sort_order: number;
  wallet_id: string | null;
  is_same_as_payroll?: boolean;
  funding_status?: "PAYROLL_DIRECT" | "FUNDED" | "PARTIAL" | "UNFUNDED";
  unfunded_amount?: number;
  wallet: {
    id: string;
    name: string;
    type: string;
    color: string;
    balance: number;
  } | null;
  category_id: string | null;
  category: {
    id: string;
    name: string;
    icon: string;
    color: string;
  } | null;
}

export interface BudgetGroupItem {
  id: string;
  name: string;
  is_sinking_fund: boolean;
  sort_order: number;
  items_count?: number;
}

export interface BudgetGroupSummary {
  group_type: string;
  is_sinking_fund_group: boolean;
  subtotal_budget: number;
  subtotal_spent: number;
  subtotal_accumulated: number;
  income_percentage: number;
  items_count: number;
  items: Budget[];
}

export interface WalletAllocationSummary {
  wallet_id: string;
  wallet_name: string;
  wallet_type: string;
  wallet_color: string;
  current_balance: number;
  total_monthly_budget: number;
  sinking_rollover_balance: number;
  sinking_fund_held: number;
  remaining_commitment: number;
  free_unallocated_balance: number;
  shortfall_amount: number;
  status: "FUNDED" | "SHORTFALL" | "IDLE";
  items_count: number;
}

export interface MonthlyAllocationResponse {
  month_key: string;
  previous_month_key: string;
  has_previous_month_template: boolean;
  reference_income: number;
  income_source: "PROFILE" | "TRANSACTIONS" | "UNSET";
  payroll_wallet_id?: string | null;
  payroll_wallet_name?: string | null;
  group_presets: string[];
  groups: BudgetGroupSummary[];
  wallet_allocations: WalletAllocationSummary[];
  unassigned_budget_total: number;
  totals: {
    total_budget: number;
    total_spent: number;
    total_remaining: number;
    allocated_percentage: number;
    unallocated_income: number;
    items_count: number;
  };
}

export interface MonthlyTrendItem {
  month_key: string;
  label: string;
  full_label: string;
  income: number;
  expense: number;
  net_cashflow: number;
  savings_rate: number;
  tx_count: number;
}

export interface CategorySummaryItem {
  name: string;
  color: string;
  total: number;
  percentage?: number;
  count?: number;
}

export interface WalletCashflowItem {
  wallet_id: string;
  wallet_name: string;
  wallet_color: string;
  wallet_type: string;
  current_balance: number;
  income: number;
  expense: number;
  transfer_in: number;
  transfer_out: number;
  net_cashflow: number;
  tx_count: number;
}

export interface MonthlyTransactionMetrics {
  month_key: string;
  month_label: string;
  income: number;
  expense: number;
  transfer_volume: number;
  net_cashflow: number;
  savings_rate: number;
  tx_count: number;
  prev_month_key: string;
  prev_income: number;
  prev_expense: number;
  income_mom_pct: number;
  expense_mom_pct: number;
}

export interface TransactionSummary {
  currency?: string;
  total_income: number;
  total_expense: number;
  net_savings: number;
  categories?: Array<{ name: string; color: string; total: number }>;
  category_breakdown?: Array<{ name: string; color: string; total: number }>;
  month_key?: string;
  month_label?: string;
  monthly?: MonthlyTransactionMetrics;
  monthly_trend?: MonthlyTrendItem[];
  expense_categories?: CategorySummaryItem[];
  income_categories?: CategorySummaryItem[];
  wallet_breakdown?: WalletCashflowItem[];
}

export interface AccountBackupItem {
  id: string;
  title: string;
  backup_type: "MANUAL" | "AUTO_PRE_RESET" | string;
  summary: {
    wallets_count?: number;
    total_balance?: number;
    transactions_count?: number;
    budgets_count?: number;
  };
  created_at: string;
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
