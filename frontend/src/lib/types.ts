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

export interface PortfolioStrategyPreset {
  key: string;
  label: string;
  description: string;
}

export interface PortfolioReview {
  has_investment_wallets: boolean;
  investment_wallets_count: number;
  investment_wallets: Array<{
    id: string;
    name: string;
    type: string;
    balance: number;
    currency?: string;
    balance_in_base?: number;
    asset_class: string;
    asset_class_label: string;
  }>;
  total_investment_balance: number;
  liquid_cash_balance: number;
  total_net_worth: number;
  invested_ratio_pct: number;
  risk_profile: string;
  sharia_preference: boolean;
  portfolio_strategy?: string;
  portfolio_strategy_label?: string;
  available_strategies?: PortfolioStrategyPreset[];
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

export interface InvestmentQuote {
  price?: number;
  change?: number;
  change_pct?: number;
  high?: number;
  low?: number;
  open?: number;
  volume?: number;
  as_of?: string;
  provider?: string;
}

export interface MultiHorizonItem {
  horizon: string;
  stance: string;
  target_range: string;
  thesis: string;
  catalysts?: string[];
  compounding_factors?: string[];
  risks?: string[];
}

export interface InvestmentRecommendation {
  symbol: string;
  market: string;
  stance: string;
  confidence_pct: number;
  confidence_basis?: string;
  fundamental_quality_score: number;
  sharia_compliance?: {
    is_sharia: boolean;
    classification: string;
    notes: string;
  };
  valuation_summary?: {
    fair_value_estimate: string;
    current_valuation_status: string;
    metric_rationale: string;
  };
  investment_price_zones?: {
    reference_price?: number;
    accumulation_zone?: {
      ideal_low?: number;
      ideal_high?: number;
      status?: string;
      guidance?: string;
    };
    fair_value_target?: {
      fair_value?: number;
      horizon_3y_upper?: number;
      margin_of_safety_pct?: number;
      valuation_status?: string;
      source?: string;
    };
    thesis_invalidation?: {
      summary?: string;
      triggers?: string[];
    };
    accumulation_zone_summary?: string;
    fair_value_target_summary?: string;
    thesis_invalidation_trigger?: string;
  };
  institutional_metrics?: {
    currency?: string;
    current_price?: number;
    dcf_fair_value?: number;
    margin_of_safety_pct?: number;
    valuation_signal?: string;
    fair_value_source?: string;
    piotroski_f_score?: number;
    altman_z_score?: number;
    roic_pct?: number;
    roe_pct?: number;
    interest_coverage?: number;
    debt_to_equity?: number;
    trailing_pe?: number;
    price_to_book?: number;
    dividend_yield_pct?: number;
    dividend_5y_avg_pct?: number;
    payout_ratio_pct?: number;
    revenue_cagr_3y_pct?: number;
    net_income_cagr_3y_pct?: number;
    eps_cagr_3y_pct?: number;
    fcf_cagr_3y_pct?: number;
    cagr_1y_pct?: number;
    cagr_3y_pct?: number;
    cagr_5y_pct?: number;
    max_drawdown_pct?: number;
    annualized_volatility_pct?: number;
    sma50_day?: number;
    sma200_day?: number;
    sma200_week?: number;
    price_vs_sma50_pct?: number;
    price_vs_sma200_pct?: number;
    price_vs_sma200w_pct?: number;
    cycle_position?: string;
    historical_provider?: string;
    fmp_used?: boolean;
    mcap_to_fdv_ratio?: number;
    supply_issued_pct?: number;
    dilution_risk?: string;
    defillama_tvl_usd?: number;
    defillama_daily_fees_usd?: number;
    defillama_daily_revenue_usd?: number;
  };
  compounding_simulation?: {
    currency: "IDR" | "USD" | string;
    current_price?: number;
    default_lump_sum: number;
    default_monthly_dca: number;
    assumed_annual_cagr_pct: number;
    assumed_dividend_yield_pct: number;
    effective_total_return_pct: number;
    cagr_basis?: string;
    horizons: Array<{
      years: number;
      total_principal: number;
      projected_value: number;
      total_gain: number;
      total_return_pct: number;
      estimated_annual_dividend: number;
      cumulative_dividends: number;
    }>;
  };
  portfolio_concentration_analysis?: {
    target_asset_class: string;
    target_asset_class_label: string;
    sector_or_category?: string;
    total_investment_balance_idr: number;
    current_class_allocation_pct: number;
    target_class_allocation_pct: number;
    drift_pct: number;
    existing_symbol_exposure_idr: number;
    matching_wallets?: string[];
    concentration_status: string;
    recommended_max_asset_pct: number;
    warning_message: string;
    proportional_allocation_advice: string;
  };
  macro_regime?: {
    usd_idr_rate?: number;
    gold_idr_per_gram?: number;
    gold_usd_per_oz?: number;
    us10y_yield_pct?: number;
    dxy_index?: number;
    interest_rate_regime: string;
    regime_label: string;
    regime_summary: string;
    implication_for_asset: string;
  };
  multi_horizon_outlook?: {
    short_term?: MultiHorizonItem;
    medium_term?: MultiHorizonItem;
    long_term?: MultiHorizonItem;
  };
  portfolio_and_dca_simulation?: {
    risk_profile_match: string;
    recommended_max_allocation_pct: number;
    suggested_monthly_dca_amount: number;
    action_plan: string;
  };
  executive_thesis: string;
  key_monitoring_metrics?: string[];
}

export type AnalysisType = "analyze" | "recommend";
export type ChatMode = "standard" | "deep_validation";

export interface RankedCandidate {
  symbol: string;
  name?: string;
  price: number;
  change_pct?: number;
  score: number;
  fundamental_score?: number;
  cycle_score?: number;
  rsi?: number;
  macd?: number;
  sma20?: number;
  sma50?: number;
  sma200?: number;
  stance?: "BUY" | "ACCUMULATE" | "HOLD" | "REDUCE" | "TAKE_PROFIT" | "AVOID" | string;
  confidence?: number;
  confidence_basis?: string;
  sharia_status?: string;
  issi_status?: string;
  piotroski_f_score?: number;
  altman_z_score?: number;
  fair_value_estimate?: number;
  margin_of_safety_pct?: number;
  valuation_status?: string;
  roic_pct?: number;
  roe_pct?: number;
  dividend_yield_pct?: number;
  revenue_cagr_3y_pct?: number;
  mcap_to_fdv_pct?: number;
  cycle_position?: string;
  accumulation_zone?: {
    ideal_low?: number;
    ideal_high?: number;
    status?: string;
    guidance?: string;
  };
  fair_value_target?: {
    fair_value?: number;
    horizon_3y_upper?: number;
    margin_of_safety_pct?: number;
    valuation_status?: string;
    source?: string;
  };
  thesis_invalidation?: {
    summary?: string;
    triggers?: string[];
  };
  investment_zones?: Record<string, any>;
  invalidation_trigger?: string;
  target_price_1?: number;
  target_price_2?: number;
  target_price_3?: number;
  support_level?: number;
  resistance_level?: number;
  atr_levels?: Record<string, any>;
  thesis_summary?: string;
}

export interface RecommendationResult {
  type: "recommendation";
  market: string;
  report: string;
  agent_reports: Record<string, string>;
  symbols_scanned: number;
  exa_news_count: number;
  status: string;
  ranked_candidates: RankedCandidate[];
  macro_regime?: Record<string, any>;
  sharia_status?: string;
}

export interface ValidationLiveSnapshot {
  symbol: string;
  price?: string | number;
  drift_pct?: number;
  rsi_1d?: number;
  macd_1d?: string;
  rsi_1w?: number;
  macd_1w?: string;
  rsi_1h?: number;
  macd_1h?: string;
  cycle_position?: string;
  flags?: string[];
  provider?: string;
}

export interface ValidationMeta {
  validated_symbols: string[];
  checked_sources: string[];
  live_snapshots: ValidationLiveSnapshot[];
  discrepancy_flags: string[];
}

export interface InvestmentChatResponse {
  reply: string;
  mode: ChatMode;
  validation_meta?: ValidationMeta | null;
}

export interface InvestmentSwarmResult {
  symbol: string;
  market: string;
  timestamp: string;
  analyst_reports: Record<string, string>;
  investment_recommendation?: InvestmentRecommendation;
  recommendation_result?: RecommendationResult;
  news_sources?: Array<{
    title: string;
    url: string;
    snippet?: string;
    published_date?: string;
    source_engine?: string;
  }>;
}

export interface InvestmentHistoryItem {
  id: string;
  run_id: string;
  market: string;
  symbol: string;
  investment_horizon: string;
  decision?: string;
  confidence?: number;
  status: string;
  report_preview?: string;
  exa_news_count: number;
  created_at?: string;
}

export interface ShariaStockIssuer {
  ticker: string;
  name: string;
  sector?: string;
  subsector?: string;
  issi_status: string;
  effective_date?: string;
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
