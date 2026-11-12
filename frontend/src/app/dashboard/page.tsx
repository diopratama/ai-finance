"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Wallet as WalletIcon,
  TrendingUp,
  TrendingDown,
  PiggyBank,
  ArrowRight,
  Flame,
  ShieldCheck,
  Bot,
  Sparkles,
  Target,
  BarChart3,
  ChevronLeft,
  ChevronRight,
  Calendar,
  CheckCircle2,
  AlertTriangle,
  Eye,
  EyeOff,
  ArrowUpRight,
  ArrowDownLeft,
  ArrowLeftRight,
} from "lucide-react";
import {
  getWallets,
  getTransactions,
  getTransactionSummary,
  getFIREProfile,
  getPlannerOverview,
  getBudgetAllocation,
} from "@/lib/api";
import {
  Wallet,
  Transaction,
  TransactionSummary,
  FIREMetrics,
  PlannerHealthContext,
  MonthlyAllocationResponse,
  PortfolioReview,
} from "@/lib/types";
import { formatCurrency, formatDate, formatMaskedCurrency } from "@/lib/utils";
import { useBalanceVisibility } from "@/lib/useBalanceVisibility";

function shiftMonthKey(mk: string, delta: number): string {
  const parts = mk.split("-");
  if (parts.length !== 2) return mk;
  const y = parseInt(parts[0], 10);
  const m = parseInt(parts[1], 10);
  const total = y * 12 + (m - 1) + delta;
  const ny = Math.floor(total / 12);
  const nm = (total % 12) + 1;
  return `${ny}-${String(nm).padStart(2, "0")}`;
}

export default function DashboardOverviewPage() {
  const [selectedMonth, setSelectedMonth] = useState<string>(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  });
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [totalBalance, setTotalBalance] = useState<number>(0);
  const [portfolioReview, setPortfolioReview] = useState<PortfolioReview | null>(null);
  const [summary, setSummary] = useState<TransactionSummary | null>(null);
  const [recentTransactions, setRecentTransactions] = useState<Transaction[]>([]);
  const [fireMetrics, setFireMetrics] = useState<FIREMetrics | null>(null);
  const [healthContext, setHealthContext] = useState<PlannerHealthContext | null>(null);
  const [allocation, setAllocation] = useState<MonthlyAllocationResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const { hideAll, isWalletHidden, toggleHideAll, toggleWalletVisibility } = useBalanceVisibility();

  useEffect(() => {
    let active = true;
    async function loadData() {
      setLoading(true);
      try {
        const [wRes, txRes, sumRes, fireRes, healthRes, allocRes] = await Promise.all([
          getWallets(selectedMonth),
          getTransactions({ limit: 6, month: selectedMonth }),
          getTransactionSummary(selectedMonth),
          getFIREProfile(),
          getPlannerOverview(),
          getBudgetAllocation(selectedMonth).catch(() => null),
        ]);
        if (!active) return;
        setWallets(wRes.wallets);
        setTotalBalance(wRes.total_balance);
        if (wRes.portfolio_review) {
          setPortfolioReview(wRes.portfolio_review);
        }
        setRecentTransactions(txRes.items);
        setSummary(sumRes);
        setFireMetrics(fireRes.metrics);
        setHealthContext(healthRes.context);
        setAllocation(allocRes);
      } catch (err) {
        console.error("Error loading dashboard data", err);
      } finally {
        if (active) setLoading(false);
      }
    }
    loadData();
    return () => {
      active = false;
    };
  }, [selectedMonth]);

  const monthly = summary?.monthly;
  const trendList = summary?.monthly_trend || [];
  const maxTrendVal = Math.max(
    1,
    ...trendList.map((t) => Math.max(t.income || 0, t.expense || 0))
  );

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Dashboard Finansial</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Ringkasan saldo, arus kas bulanan, portofolio, dan progres FIRE.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* Month Selector */}
          <div className="flex items-center gap-1 p-1 rounded-xl bg-card border border-border shadow-sm">
            <button
              type="button"
              onClick={() => setSelectedMonth((m) => shiftMonthKey(m, -1))}
              className="p-2 min-h-[36px] min-w-[36px] flex items-center justify-center rounded-lg hover:bg-secondary text-muted-foreground hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              title="Bulan Sebelumnya"
              aria-label="Bulan Sebelumnya"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <div className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-bold text-foreground">
              <Calendar className="w-3.5 h-3.5 text-[#8a6300] dark:text-[#f0b000]" />
              <span>{monthly?.month_label || selectedMonth}</span>
            </div>
            <button
              type="button"
              onClick={() => setSelectedMonth((m) => shiftMonthKey(m, 1))}
              className="p-2 min-h-[36px] min-w-[36px] flex items-center justify-center rounded-lg hover:bg-secondary text-muted-foreground hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              title="Bulan Berikutnya"
              aria-label="Bulan Berikutnya"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          <button
            type="button"
            onClick={toggleHideAll}
            className={`flex items-center gap-2 px-3.5 py-2 min-h-[40px] rounded-xl text-xs font-semibold border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
              hideAll
                ? "bg-accent border-[#f0b000]/40 text-[#8a6300] dark:text-[#f0b000]"
                : "bg-card border-border hover:bg-accent text-foreground"
            }`}
            title={hideAll ? "Tampilkan semua saldo dompet" : "Sembunyikan semua saldo dompet"}
            aria-pressed={hideAll}
          >
            {hideAll ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
            <span>{hideAll ? "Tampilkan Saldo" : "Sembunyikan Saldo"}</span>
          </button>

          <Link
            href="/budgets"
            className="flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold bg-card border border-border hover:bg-accent text-foreground transition-colors"
          >
            <Target className="w-4 h-4 text-[#8a6300] dark:text-[#f0b000]" />
            <span>Alokasi Gajian</span>
          </Link>
          <Link
            href="/bot-pairing"
            className="flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold bg-card border border-border hover:bg-accent text-foreground transition-colors"
          >
            <Bot className="w-4 h-4 text-sky-600 dark:text-sky-400" />
            <span>WA / Telegram Bot</span>
          </Link>
          <Link
            href="/planner"
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold bg-primary text-primary-foreground hover:bg-primary/90 transition-colors shadow-md shadow-[#f0b000]/20"
          >
            <Sparkles className="w-4 h-4" />
            <span>Diskusi AI Planner</span>
          </Link>
        </div>
      </div>

      {/* Top 4 Metric Cards */}
      {loading && wallets.length === 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4" aria-label="Memuat ringkasan dashboard">
          {[1, 2, 3, 4].map((idx) => (
            <div key={idx} className="p-5 rounded-2xl bg-card border border-border shadow-sm space-y-3 animate-pulse">
              <div className="h-4 w-28 rounded bg-secondary" />
              <div className="h-8 w-40 rounded bg-secondary" />
              <div className="h-3 w-24 rounded bg-secondary" />
            </div>
          ))}
        </div>
      ) : (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Net Worth */}
        <div className="p-5 rounded-2xl bg-card border border-border shadow-sm">
          <div className="flex items-center justify-between text-muted-foreground text-xs font-medium">
            <span>Total Kekayaan Bersih</span>
            <div className="w-8 h-8 rounded-lg bg-accent text-[#8a6300] dark:text-[#f0b000] flex items-center justify-center">
              <WalletIcon className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-foreground mt-3">
            {hideAll ? formatMaskedCurrency("IDR") : formatCurrency(totalBalance, "IDR")}
          </div>
          <div className="text-[11px] text-muted-foreground mt-2 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-[#f0b000]" />
            <span>Tersebar di {wallets.length} dompet aktif</span>
          </div>
        </div>

        {/* Monthly Income */}
        <div className="p-5 rounded-2xl bg-card border border-border shadow-sm">
          <div className="flex items-center justify-between text-muted-foreground text-xs font-medium">
            <span>Pemasukan ({monthly?.month_label || selectedMonth})</span>
            <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center">
              <TrendingUp className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400 mt-3">
            +{formatCurrency(monthly ? monthly.income : summary?.total_income || 0, "IDR")}
          </div>
          <div className="text-[11px] text-muted-foreground mt-2 flex items-center justify-between">
            <span>Total historis: {formatCurrency(summary?.total_income || 0, "IDR")}</span>
            {monthly?.income_mom_pct !== null && monthly?.income_mom_pct !== undefined && (
              <span
                className={`font-bold ${
                  monthly.income_mom_pct >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-500"
                }`}
              >
                {monthly.income_mom_pct >= 0 ? `+${monthly.income_mom_pct}%` : `${monthly.income_mom_pct}%`} MoM
              </span>
            )}
          </div>
        </div>

        {/* Monthly Expense */}
        <div className="p-5 rounded-2xl bg-card border border-border shadow-sm">
          <div className="flex items-center justify-between text-muted-foreground text-xs font-medium">
            <span>Pengeluaran ({monthly?.month_label || selectedMonth})</span>
            <div className="w-8 h-8 rounded-lg bg-rose-500/10 text-rose-600 dark:text-rose-400 flex items-center justify-center">
              <TrendingDown className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-rose-600 dark:text-rose-400 mt-3">
            -{formatCurrency(monthly ? monthly.expense : summary?.total_expense || 0, "IDR")}
          </div>
          <div className="text-[11px] text-muted-foreground mt-2 flex items-center justify-between">
            <span>Total historis: {formatCurrency(summary?.total_expense || 0, "IDR")}</span>
            {monthly?.expense_mom_pct !== null && monthly?.expense_mom_pct !== undefined && (
              <span
                className={`font-bold ${
                  monthly.expense_mom_pct <= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-500"
                }`}
              >
                {monthly.expense_mom_pct >= 0 ? `+${monthly.expense_mom_pct}%` : `${monthly.expense_mom_pct}%`} MoM
              </span>
            )}
          </div>
        </div>

        {/* Monthly Net Cashflow & Savings Rate */}
        <div className="p-5 rounded-2xl bg-card border border-border shadow-sm">
          <div className="flex items-center justify-between text-muted-foreground text-xs font-medium">
            <span>Net Cashflow &amp; Savings Rate</span>
            <div className="w-8 h-8 rounded-lg bg-accent text-[#8a6300] dark:text-[#f0b000] flex items-center justify-center">
              <PiggyBank className="w-4 h-4" />
            </div>
          </div>
          <div
            className={`text-2xl font-bold mt-3 ${
              (monthly?.net_cashflow ?? summary?.net_savings ?? 0) >= 0
                ? "text-foreground"
                : "text-rose-600 dark:text-rose-400"
            }`}
          >
            {formatCurrency(monthly ? monthly.net_cashflow : summary?.net_savings || 0, "IDR")}
          </div>
          <div className="text-xs text-[#8a6300] dark:text-[#f0b000] mt-2 font-semibold flex items-center justify-between">
            <span>Rasio Tabungan: {monthly ? `${monthly.savings_rate}%` : "0%"}</span>
            <span>{monthly?.tx_count || 0} transaksi</span>
          </div>
        </div>
      </div>
      )}

      {/* Monthly Reporting Summary Section (6-Month Cashflow Trend + Category Breakdown) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 6-Month Cashflow Trend Bar Chart */}
        <div className="lg:col-span-2 p-6 rounded-2xl bg-card border border-border shadow-sm space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-accent text-[#8a6300] dark:text-[#f0b000] flex items-center justify-center">
                <BarChart3 className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-base font-bold text-foreground">
                  Laporan Tren Arus Kas 6 Bulan Terakhir
                </h3>
                <p className="text-xs text-muted-foreground">
                  Perbandingan pemasukan vs pengeluaran bulanan dan rasio tabungan
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3 text-[11px] font-semibold">
              <span className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400">
                <span className="w-2.5 h-2.5 rounded-sm bg-emerald-500" />
                Pemasukan
              </span>
              <span className="flex items-center gap-1.5 text-rose-600 dark:text-rose-400">
                <span className="w-2.5 h-2.5 rounded-sm bg-rose-500" />
                Pengeluaran
              </span>
            </div>
          </div>

          <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 sm:gap-3 pt-4 items-end border-b border-border pb-3">
            {trendList.map((item) => {
              const incHeight = Math.max(4, Math.round(((item.income || 0) / maxTrendVal) * 120));
              const expHeight = Math.max(4, Math.round(((item.expense || 0) / maxTrendVal) * 120));
              const isSelected = item.month_key === selectedMonth;
              return (
                <button
                  key={item.month_key}
                  type="button"
                  onClick={() => setSelectedMonth(item.month_key)}
                  className={`flex flex-col items-center gap-2 p-2 rounded-xl transition-all ${
                    isSelected
                      ? "bg-accent/70 ring-1 ring-[#f0b000]/50"
                      : "hover:bg-secondary/60"
                  }`}
                  title={`${item.label}: Masuk ${formatCurrency(item.income)} | Keluar ${formatCurrency(item.expense)}`}
                >
                  <div className="flex items-end justify-center gap-1.5 h-32 w-full">
                    <div
                      className="w-3 sm:w-4 rounded-t-md bg-emerald-500 transition-all duration-300"
                      style={{ height: `${incHeight}px` }}
                    />
                    <div
                      className="w-3 sm:w-4 rounded-t-md bg-rose-500 transition-all duration-300"
                      style={{ height: `${expHeight}px` }}
                    />
                  </div>
                  <div className="text-[11px] font-bold text-foreground">{item.label}</div>
                  <div
                    className={`text-[10px] font-semibold ${
                      item.savings_rate >= 20
                        ? "text-emerald-600 dark:text-emerald-400"
                        : item.savings_rate >= 0
                        ? "text-[#8a6300] dark:text-[#f0b000]"
                        : "text-rose-500"
                    }`}
                  >
                    {item.savings_rate}% SR
                  </div>
                </button>
              );
            })}
          </div>

          {/* Wallet Cashflow Breakdown for Selected Month */}
          {summary?.wallet_breakdown && summary.wallet_breakdown.length > 0 && (
            <div className="space-y-2 pt-1">
              <div className="text-xs font-bold text-foreground">
                Mutasi Arus Kas per Dompet ({monthly?.month_label || selectedMonth})
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                {summary.wallet_breakdown.slice(0, 4).map((wb) => (
                  <div
                    key={wb.wallet_id}
                    className="p-2.5 rounded-xl bg-secondary/50 border border-border flex items-center justify-between text-xs"
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className="w-2.5 h-2.5 rounded-full shrink-0"
                        style={{ backgroundColor: wb.wallet_color }}
                      />
                      <span className="font-semibold text-foreground">{wb.wallet_name}</span>
                    </div>
                    <div className="flex items-center gap-2 font-mono text-[11px]">
                      <span className="text-emerald-600 dark:text-emerald-400">
                        +{formatCurrency(wb.income)}
                      </span>
                      <span className="text-muted-foreground">/</span>
                      <span className="text-rose-600 dark:text-rose-400">
                        -{formatCurrency(wb.expense)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Monthly Expense Category Breakdown */}
        <div className="p-6 rounded-2xl bg-card border border-border shadow-sm flex flex-col justify-between space-y-4">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-foreground">Distribusi Pengeluaran</h3>
                <p className="text-xs text-muted-foreground">
                  Periode {monthly?.month_label || selectedMonth}
                </p>
              </div>
              <Link
                href="/transactions"
                className="text-xs font-semibold text-[#8a6300] dark:text-[#f0b000] hover:underline"
              >
                Detail
              </Link>
            </div>

            {(!summary?.expense_categories || summary.expense_categories.length === 0) ? (
              <div className="py-10 text-center text-xs text-muted-foreground">
                Belum ada pengeluaran tercatat pada periode {monthly?.month_label || selectedMonth}.
              </div>
            ) : (
              <div className="space-y-3">
                {summary.expense_categories.slice(0, 6).map((cat, idx) => (
                  <div key={idx} className="space-y-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-foreground flex items-center gap-1.5">
                        <span
                          className="w-2.5 h-2.5 rounded-full shrink-0"
                          style={{ backgroundColor: cat.color || "#f0b000" }}
                        />
                        <span>{cat.name}</span>
                      </span>
                      <span className="font-mono font-bold text-foreground">
                        {formatCurrency(cat.total)}{" "}
                        <span className="text-muted-foreground font-normal">({cat.percentage}%)</span>
                      </span>
                    </div>
                    <div className="w-full h-2 rounded-full bg-secondary overflow-hidden border border-border">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${Math.min(100, Math.max(4, cat.percentage || 0))}%`,
                          backgroundColor: cat.color || "#f0b000",
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="pt-3 border-t border-border flex items-center justify-between text-xs">
            <span className="text-muted-foreground">Total Pengeluaran Bulan Ini:</span>
            <span className="font-bold text-rose-600 dark:text-rose-400">
              {formatCurrency(monthly?.expense || 0, "IDR")}
            </span>
          </div>
        </div>
      </div>

      {/* Investment Portfolio Review & Best Practice Summary Card */}
      {portfolioReview && (
        <div className="p-6 rounded-2xl bg-card border border-border shadow-sm space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-400 flex items-center justify-center">
                <TrendingUp className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="text-base font-bold text-foreground">
                    Review Portofolio Investasi vs Best Practice ({portfolioReview.reference_profile_name})
                  </h3>
                  <span
                    className={`text-[10px] font-extrabold px-2.5 py-0.5 rounded-full border ${
                      portfolioReview.status === "OPTIMAL"
                        ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30"
                        : portfolioReview.status === "PERLU_REBALANCING"
                        ? "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30"
                        : "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/30"
                    }`}
                  >
                    {portfolioReview.status_label} • Skor {portfolioReview.alignment_score}/100
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Total Aset Investasi:{" "}
                  <strong className="text-foreground">
                    {hideAll ? formatMaskedCurrency("IDR") : formatCurrency(portfolioReview.total_investment_balance, "IDR")}
                  </strong>{" "}
                  ({portfolioReview.invested_ratio_pct}% dari kekayaan bersih • Target Return{" "}
                  {portfolioReview.expected_cagr})
                </p>
              </div>
            </div>
            <Link
              href="/wallets"
              className="text-xs font-bold text-[#8a6300] dark:text-[#f0b000] hover:underline flex items-center gap-1 self-start sm:self-center"
            >
              <span>Lihat Detail &amp; Rebalancing</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
            {portfolioReview.best_practices.slice(0, 2).map((chk) => (
              <div
                key={chk.key}
                className="p-3 rounded-xl bg-secondary/50 border border-border flex items-start gap-2.5 text-xs"
              >
                {chk.passed ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
                ) : (
                  <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
                )}
                <div>
                  <div className="font-bold text-foreground">{chk.title}</div>
                  <div className="text-muted-foreground text-[11px] mt-0.5">{chk.detail}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Middle Section: Financial Health & FIRE Progress */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* FIRE Roadmap Progress */}
        <div className="lg:col-span-2 p-6 rounded-2xl bg-card border border-border flex flex-col justify-between shadow-sm">
          <div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-accent text-[#8a6300] dark:text-[#f0b000] flex items-center justify-center">
                  <Flame className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-foreground">FIRE Roadmap (Kebebasan Finansial)</h3>
                  <p className="text-xs text-muted-foreground">Target akumulasi pensiun dini berbasis Rule of 25</p>
                </div>
              </div>
              <Link
                href="/fire"
                className="text-xs font-semibold text-[#8a6300] dark:text-[#f0b000] hover:underline flex items-center gap-1"
              >
                <span>Detail Simulasi</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>

            {/* Progress Bar */}
            <div className="mt-6 space-y-2">
              <div className="flex justify-between text-xs">
                <span className="text-muted-foreground">
                  Terkumpul:{" "}
                  <strong className="text-foreground">
                    {hideAll ? formatMaskedCurrency("IDR") : formatCurrency(totalBalance, "IDR")}
                  </strong>
                </span>
                <span className="text-[#8a6300] dark:text-[#f0b000] font-bold">
                  {fireMetrics?.progress_percentage || 0.7}% dari target
                </span>
              </div>
              <div className="w-full bg-secondary h-3 rounded-full overflow-hidden p-0.5 border border-border">
                <div
                  className="bg-gradient-to-r from-[#8a6300] via-[#f0b000] to-amber-300 h-full rounded-full transition-all duration-500"
                  style={{ width: `${Math.max(2, Math.min(100, fireMetrics?.progress_percentage || 1))}%` }}
                />
              </div>
              <div className="flex justify-between text-[11px] text-muted-foreground">
                <span>
                  Usia Sekarang: <strong>{healthContext?.current_age || 28} th</strong>
                </span>
                <span>
                  Target FIRE:{" "}
                  <strong>{formatCurrency(fireMetrics?.fire_number || 2400000000, "IDR")}</strong> (Usia{" "}
                  {healthContext?.target_fire_age || 45} th)
                </span>
              </div>
            </div>
          </div>

          <div className="mt-6 pt-4 border-t border-border flex items-center justify-between text-xs">
            <span className="text-muted-foreground">Estimasi waktu bebas finansial:</span>
            <span className="font-semibold text-foreground">
              {fireMetrics?.actual_years_needed
                ? `Sekitar ${fireMetrics.actual_years_needed} tahun lagi`
                : "Perlu disiplin investasi rutin"}
            </span>
          </div>
        </div>

        {/* Financial Health Score Card */}
        <div className="p-6 rounded-2xl bg-card border border-border flex flex-col justify-between shadow-sm">
          <div>
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-accent text-[#8a6300] dark:text-[#f0b000] flex items-center justify-center">
                <ShieldCheck className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-base font-bold text-foreground">Financial Health Score</h3>
                <p className="text-xs text-muted-foreground">Evaluasi arus kas, cicilan & dana darurat</p>
              </div>
            </div>

            <div className="mt-6 flex items-center justify-center">
              <div className="relative w-28 h-28 rounded-full border-4 border-[#f0b000]/35 flex flex-col items-center justify-center bg-secondary/60">
                <span className="text-3xl font-extrabold text-[#8a6300] dark:text-[#f0b000] tracking-tight">
                  {healthContext?.health_score || 65}
                </span>
                <span className="text-[10px] uppercase font-semibold text-muted-foreground tracking-wider">
                  {healthContext?.health_status || "SEHAT"}
                </span>
              </div>
            </div>

            <div className="mt-6 space-y-2 text-xs">
              <div className="flex justify-between py-1 border-b border-border text-muted-foreground">
                <span>Dana Darurat:</span>
                <span className="text-foreground font-semibold">
                  {healthContext?.emergency_fund_months ?? 2} / {healthContext?.emergency_target_months ?? 3} bulan
                </span>
              </div>
              <div className="flex justify-between py-1 text-muted-foreground">
                <span>Profil Risiko:</span>
                <span className="text-[#8a6300] dark:text-[#f0b000] font-bold">
                  {healthContext?.risk_profile || "MODERATE"}
                </span>
              </div>
            </div>
          </div>

          <Link
            href="/planner"
            className="mt-4 w-full py-2 px-3 rounded-xl bg-secondary hover:bg-accent text-foreground text-xs font-semibold text-center transition-colors border border-border"
          >
            Optimasi Skor Bersama AI Planner
          </Link>
        </div>
      </div>

      {/* Bottom Section: Wallets List & Recent Transactions */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Wallets Quick View */}
        <div className="p-6 rounded-2xl bg-card border border-border space-y-4 shadow-sm">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-bold text-foreground">Dompet & Akun Anda</h3>
            <Link href="/wallets" className="text-xs font-semibold text-[#8a6300] dark:text-[#f0b000] hover:underline">
              Kelola
            </Link>
          </div>
          <div className="space-y-3">
            {wallets.map((w) => {
              const walletHidden = isWalletHidden(w.id);
              return (
                <div
                  key={w.id}
                  className="p-3.5 rounded-xl bg-secondary/70 border border-border flex items-center justify-between gap-2"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div
                      className="w-3.5 h-3.5 rounded-full shrink-0"
                      style={{ backgroundColor: w.color }}
                    />
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-foreground truncate">{w.name}</div>
                      <div className="text-[11px] text-muted-foreground">{w.type}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <div className="text-right">
                      <div className="text-sm font-bold text-foreground">
                        {walletHidden ? formatMaskedCurrency(w.currency) : formatCurrency(w.balance, w.currency)}
                      </div>
                      {(w.assigned_items_count || 0) > 0 && (
                        <div className="text-[10px] text-[#8a6300] dark:text-[#f0b000] font-medium">
                          {w.assigned_items_count} pos anggaran
                        </div>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => toggleWalletVisibility(w.id)}
                      className={`p-2 min-h-[36px] min-w-[36px] flex items-center justify-center rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                        walletHidden
                          ? "text-[#8a6300] dark:text-[#f0b000] bg-accent/60 hover:bg-accent"
                          : "text-muted-foreground hover:text-foreground hover:bg-card"
                      }`}
                      title={walletHidden ? "Tampilkan saldo dompet ini" : "Sembunyikan saldo dompet ini"}
                      aria-label={walletHidden ? `Tampilkan saldo ${w.name}` : `Sembunyikan saldo ${w.name}`}
                      aria-pressed={walletHidden}
                    >
                      {walletHidden ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Recent Transactions */}
        <div className="lg:col-span-2 p-6 rounded-2xl bg-card border border-border space-y-4 shadow-sm">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-bold text-foreground">Transaksi Terbaru</h3>
            <Link
              href="/transactions"
              className="text-xs font-semibold text-[#8a6300] dark:text-[#f0b000] hover:underline flex items-center gap-1"
            >
              <span>Semua Transaksi</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          {recentTransactions.length === 0 ? (
            <div className="py-10 text-center text-xs text-muted-foreground">
              Belum ada transaksi tercatat. Tambahkan dari menu Transaksi atau chat via Simulator Bot.
            </div>
          ) : (
            <div className="divide-y divide-border">
              {recentTransactions.map((tx) => (
                <div key={tx.id} className="py-3 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-9 h-9 rounded-xl border flex items-center justify-center shrink-0 ${
                        tx.type === "EXPENSE"
                          ? "bg-rose-500/10 border-rose-500/20 text-rose-600 dark:text-rose-400"
                          : tx.type === "INCOME"
                          ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-600 dark:text-emerald-400"
                          : "bg-accent border-[#f0b000]/30 text-[#8a6300] dark:text-[#f0b000]"
                      }`}
                    >
                      {tx.type === "EXPENSE" ? (
                        <ArrowUpRight className="w-4 h-4" />
                      ) : tx.type === "INCOME" ? (
                        <ArrowDownLeft className="w-4 h-4" />
                      ) : (
                        <ArrowLeftRight className="w-4 h-4" />
                      )}
                    </div>
                    <div>
                      <div className="text-sm font-semibold text-foreground">{tx.description}</div>
                      <div className="text-xs text-muted-foreground flex flex-wrap items-center gap-1.5">
                        <span>{tx.budget?.name || tx.category?.name || "Lain-lain"}</span>
                        <span>•</span>
                        <span>{tx.wallet?.name || "Dompet"}</span>
                        <span>•</span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-secondary text-muted-foreground border border-border">
                          {tx.raw_source}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div
                      className={`text-sm font-bold ${
                        tx.type === "EXPENSE"
                          ? "text-rose-600 dark:text-rose-400"
                          : tx.type === "INCOME"
                          ? "text-emerald-600 dark:text-emerald-400"
                          : "text-[#8a6300] dark:text-[#f0b000]"
                      }`}
                    >
                      {tx.type === "EXPENSE" ? "-" : tx.type === "INCOME" ? "+" : ""}
                      {formatCurrency(tx.amount, tx.currency)}
                    </div>
                    <div className="text-[11px] text-muted-foreground">{formatDate(tx.transaction_date)}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

