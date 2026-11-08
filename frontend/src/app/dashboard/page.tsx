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
} from "@/lib/types";
import { formatCurrency, formatDate } from "@/lib/utils";

export default function DashboardOverviewPage() {
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [totalBalance, setTotalBalance] = useState<number>(0);
  const [summary, setSummary] = useState<TransactionSummary | null>(null);
  const [recentTransactions, setRecentTransactions] = useState<Transaction[]>([]);
  const [fireMetrics, setFireMetrics] = useState<FIREMetrics | null>(null);
  const [healthContext, setHealthContext] = useState<PlannerHealthContext | null>(null);
  const [allocation, setAllocation] = useState<MonthlyAllocationResponse | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        const [wRes, txRes, sumRes, fireRes, healthRes, allocRes] = await Promise.all([
          getWallets(),
          getTransactions({ limit: 5 }),
          getTransactionSummary(),
          getFIREProfile(),
          getPlannerOverview(),
          getBudgetAllocation().catch(() => null),
        ]);
        setWallets(wRes.wallets);
        setTotalBalance(wRes.total_balance);
        setRecentTransactions(txRes.items);
        setSummary(sumRes);
        setFireMetrics(fireRes.metrics);
        setHealthContext(healthRes.context);
        setAllocation(allocRes);
      } catch (err) {
        console.error("Error loading dashboard data", err);
      }
    }
    loadData();
  }, []);

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Dashboard Finansial</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Ringkasan kekayaan bersih, alokasi gajian per dompet, dan peta jalan menuju Financial Freedom.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
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
            {formatCurrency(totalBalance, "IDR")}
          </div>
          <div className="text-[11px] text-muted-foreground mt-2 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-[#f0b000]" />
            <span>Tersebar di {wallets.length} dompet aktif</span>
          </div>
        </div>

        {/* Total Income */}
        <div className="p-5 rounded-2xl bg-card border border-border shadow-sm">
          <div className="flex items-center justify-between text-muted-foreground text-xs font-medium">
            <span>Pemasukan Terdata</span>
            <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center">
              <TrendingUp className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400 mt-3">
            +{formatCurrency(summary?.total_income || 0, "IDR")}
          </div>
          <div className="text-[11px] text-muted-foreground mt-2">Gaji & pendapatan lainnya</div>
        </div>

        {/* Total Expense */}
        <div className="p-5 rounded-2xl bg-card border border-border shadow-sm">
          <div className="flex items-center justify-between text-muted-foreground text-xs font-medium">
            <span>Pengeluaran Terdata</span>
            <div className="w-8 h-8 rounded-lg bg-rose-500/10 text-rose-600 dark:text-rose-400 flex items-center justify-center">
              <TrendingDown className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-rose-600 dark:text-rose-400 mt-3">
            -{formatCurrency(summary?.total_expense || 0, "IDR")}
          </div>
          <div className="text-[11px] text-muted-foreground mt-2">Termasuk log WhatsApp & Telegram</div>
        </div>

        {/* Monthly Budget Allocation Status */}
        <div className="p-5 rounded-2xl bg-card border border-border shadow-sm">
          <div className="flex items-center justify-between text-muted-foreground text-xs font-medium">
            <span>Alokasi Bulan Ini ({allocation?.month_key || "Aktif"})</span>
            <div className="w-8 h-8 rounded-lg bg-accent text-[#8a6300] dark:text-[#f0b000] flex items-center justify-center">
              <PiggyBank className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-foreground mt-3">
            {formatCurrency(allocation?.totals.total_budget || summary?.net_savings || 0, "IDR")}
          </div>
          <div className="text-[11px] text-[#8a6300] dark:text-[#f0b000] mt-2 font-semibold">
            {allocation && allocation.totals.items_count > 0
              ? `${allocation.totals.items_count} pos aktif (${allocation.totals.allocated_percentage}% gaji)`
              : "Klik Alokasi Gajian untuk menyusun pos"}
          </div>
        </div>
      </div>

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
                  Terkumpul: <strong className="text-foreground">{formatCurrency(totalBalance, "IDR")}</strong>
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
            {wallets.map((w) => (
              <div
                key={w.id}
                className="p-3.5 rounded-xl bg-secondary/70 border border-border flex items-center justify-between"
              >
                <div className="flex items-center gap-3">
                  <div
                    className="w-3.5 h-3.5 rounded-full shrink-0"
                    style={{ backgroundColor: w.color }}
                  />
                  <div>
                    <div className="text-sm font-semibold text-foreground">{w.name}</div>
                    <div className="text-[11px] text-muted-foreground">{w.type}</div>
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-bold text-foreground">
                    {formatCurrency(w.balance, w.currency)}
                  </div>
                  {(w.assigned_items_count || 0) > 0 && (
                    <div className="text-[10px] text-[#8a6300] dark:text-[#f0b000] font-medium">
                      {w.assigned_items_count} pos anggaran
                    </div>
                  )}
                </div>
              </div>
            ))}
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
                    <div className="w-9 h-9 rounded-xl bg-secondary border border-border flex items-center justify-center text-xs font-bold">
                      {tx.type === "EXPENSE" ? "💸" : tx.type === "INCOME" ? "💰" : "🔄"}
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

