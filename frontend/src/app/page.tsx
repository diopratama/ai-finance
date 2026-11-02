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
} from "lucide-react";
import {
  getWallets,
  getTransactions,
  getTransactionSummary,
  getFIREProfile,
  getPlannerOverview,
} from "@/lib/api";
import { Wallet, Transaction, TransactionSummary, FIREMetrics, PlannerHealthContext } from "@/lib/types";
import { formatCurrency, formatDate } from "@/lib/utils";

export default function DashboardOverviewPage() {
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [totalBalance, setTotalBalance] = useState<number>(0);
  const [summary, setSummary] = useState<TransactionSummary | null>(null);
  const [recentTransactions, setRecentTransactions] = useState<Transaction[]>([]);
  const [fireMetrics, setFireMetrics] = useState<FIREMetrics | null>(null);
  const [healthContext, setHealthContext] = useState<PlannerHealthContext | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    async function loadData() {
      try {
        const [wRes, txRes, sumRes, fireRes, healthRes] = await Promise.all([
          getWallets(),
          getTransactions({ limit: 5 }),
          getTransactionSummary(),
          getFIREProfile(),
          getPlannerOverview(),
        ]);
        setWallets(wRes.wallets);
        setTotalBalance(wRes.total_balance);
        setRecentTransactions(txRes.items);
        setSummary(sumRes);
        setFireMetrics(fireRes.metrics);
        setHealthContext(healthRes.context);
      } catch (err) {
        console.error("Error loading dashboard data", err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Dashboard Finansial</h1>
          <p className="text-sm text-slate-400 mt-1">
            Ringkasan kekayaan bersih, anggaran, dan perkembangan peta jalan menuju Financial Freedom.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/bot-pairing"
            className="flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-semibold bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-200 transition-colors"
          >
            <Bot className="w-4 h-4 text-sky-400" />
            <span>Hubungkan Telegram / WA</span>
          </Link>
          <Link
            href="/planner"
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold bg-gradient-to-r from-emerald-500 to-teal-500 text-slate-950 font-bold hover:opacity-90 transition-opacity shadow-lg shadow-emerald-500/10"
          >
            <Sparkles className="w-4 h-4" />
            <span>Diskusi AI Planner</span>
          </Link>
        </div>
      </div>

      {/* Top 4 Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Net Worth */}
        <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-sm relative overflow-hidden">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>Total Kekayaan Bersih</span>
            <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center">
              <WalletIcon className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-white mt-3">
            {formatCurrency(totalBalance, "IDR")}
          </div>
          <div className="text-[11px] text-slate-400 mt-2 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            <span>Tersebar di {wallets.length} dompet aktif</span>
          </div>
        </div>

        {/* Total Income */}
        <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-sm relative overflow-hidden">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>Pemasukan Terdata</span>
            <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center">
              <TrendingUp className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-emerald-400 mt-3">
            +{formatCurrency(summary?.total_income || 0, "IDR")}
          </div>
          <div className="text-[11px] text-slate-400 mt-2">Gaji & pendapatan lainnya</div>
        </div>

        {/* Total Expense */}
        <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-sm relative overflow-hidden">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>Pengeluaran Terdata</span>
            <div className="w-8 h-8 rounded-lg bg-rose-500/10 text-rose-400 flex items-center justify-center">
              <TrendingDown className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-rose-400 mt-3">
            -{formatCurrency(summary?.total_expense || 0, "IDR")}
          </div>
          <div className="text-[11px] text-slate-400 mt-2">Termasuk log dari WhatsApp & Telegram</div>
        </div>

        {/* Net Savings */}
        <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-sm relative overflow-hidden">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>Arus Kas Bersih (Net Savings)</span>
            <div className="w-8 h-8 rounded-lg bg-sky-500/10 text-sky-400 flex items-center justify-center">
              <PiggyBank className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-white mt-3">
            {formatCurrency(summary?.net_savings || 0, "IDR")}
          </div>
          <div className="text-[11px] text-emerald-400 mt-2 font-medium">Surplus tabungan siap diinvestasikan</div>
        </div>
      </div>

      {/* Middle Section: Financial Health & FIRE Progress */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* FIRE Roadmap Progress */}
        <div className="lg:col-span-2 p-6 rounded-2xl bg-slate-900 border border-slate-800 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-amber-500/10 text-amber-400 flex items-center justify-center">
                  <Flame className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white">FIRE Roadmap (Kebebasan Finansial)</h3>
                  <p className="text-xs text-slate-400">Target akumulasi pensiun dini berbasis Rule of 25</p>
                </div>
              </div>
              <Link href="/fire" className="text-xs font-semibold text-emerald-400 hover:text-emerald-300 flex items-center gap-1">
                <span>Detail Simulasi</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>

            {/* Progress Bar */}
            <div className="mt-6 space-y-2">
              <div className="flex justify-between text-xs">
                <span className="text-slate-400">Terkumpul: <strong className="text-slate-200">{formatCurrency(totalBalance, "IDR")}</strong></span>
                <span className="text-emerald-400 font-semibold">{fireMetrics?.progress_percentage || 0.7}% dari target</span>
              </div>
              <div className="w-full bg-slate-800 h-3 rounded-full overflow-hidden p-0.5 border border-slate-700/50">
                <div
                  className="bg-gradient-to-r from-emerald-500 via-teal-400 to-sky-400 h-full rounded-full transition-all duration-500"
                  style={{ width: `${Math.max(2, Math.min(100, fireMetrics?.progress_percentage || 1))}%` }}
                />
              </div>
              <div className="flex justify-between text-[11px] text-slate-400">
                <span>Usia Sekarang: <strong>28 th</strong></span>
                <span>Target FIRE: <strong>{formatCurrency(fireMetrics?.fire_number || 2400000000, "IDR")}</strong> (Usia 45 th)</span>
              </div>
            </div>
          </div>

          <div className="mt-6 pt-4 border-t border-slate-800/80 flex items-center justify-between text-xs">
            <span className="text-slate-400">Estimasi waktu bebas finansial:</span>
            <span className="font-semibold text-slate-200">
              {fireMetrics?.actual_years_needed ? `Sekitar ${fireMetrics.actual_years_needed} tahun lagi` : "Perlu disiplin investasi rutin"}
            </span>
          </div>
        </div>

        {/* Financial Health Score Card */}
        <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-sky-500/10 text-sky-400 flex items-center justify-center">
                <ShieldCheck className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white">Financial Health Score</h3>
                <p className="text-xs text-slate-400">Evaluasi kesehatan arus kas, cicilan & dana darurat</p>
              </div>
            </div>

            <div className="mt-6 flex items-center justify-center">
              <div className="relative w-28 h-28 rounded-full border-4 border-emerald-500/20 flex flex-col items-center justify-center bg-slate-950/40">
                <span className="text-3xl font-extrabold text-emerald-400 tracking-tight">
                  {healthContext?.health_score || 65}
                </span>
                <span className="text-[10px] uppercase font-semibold text-slate-400 tracking-wider">
                  {healthContext?.health_status || "SEHAT"}
                </span>
              </div>
            </div>

            <div className="mt-6 space-y-2 text-xs">
              <div className="flex justify-between py-1 border-b border-slate-800 text-slate-400">
                <span>Dana Darurat:</span>
                <span className="text-slate-200 font-medium">
                  {healthContext?.emergency_fund_months ?? 2} / {healthContext?.emergency_target_months ?? 3} bulan
                </span>
              </div>
              <div className="flex justify-between py-1 text-slate-400">
                <span>Profil Risiko:</span>
                <span className="text-emerald-400 font-semibold">{healthContext?.risk_profile || "MODERAT"}</span>
              </div>
            </div>
          </div>

          <Link
            href="/planner"
            className="mt-4 w-full py-2 px-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold text-center transition-colors border border-slate-700"
          >
            Optimasi Skor Bersama AI Planner
          </Link>
        </div>
      </div>

      {/* Bottom Section: Wallets List & Recent Transactions */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Wallets Quick View */}
        <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-bold text-white">Dompet Statis Anda</h3>
            <Link href="/wallets" className="text-xs font-semibold text-emerald-400 hover:text-emerald-300">
              Kelola
            </Link>
          </div>
          <div className="space-y-3">
            {wallets.map((w) => (
              <div
                key={w.id}
                className="p-3.5 rounded-xl bg-slate-800/60 border border-slate-800 flex items-center justify-between"
              >
                <div className="flex items-center gap-3">
                  <div
                    className="w-3.5 h-3.5 rounded-full shrink-0"
                    style={{ backgroundColor: w.color }}
                  />
                  <div>
                    <div className="text-sm font-semibold text-white">{w.name}</div>
                    <div className="text-[11px] text-slate-400">{w.type}</div>
                  </div>
                </div>
                <div className="text-sm font-bold text-slate-200">
                  {formatCurrency(w.balance, w.currency)}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Recent Transactions */}
        <div className="lg:col-span-2 p-6 rounded-2xl bg-slate-900 border border-slate-800 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-bold text-white">Transaksi Terbaru</h3>
            <Link href="/transactions" className="text-xs font-semibold text-emerald-400 hover:text-emerald-300 flex items-center gap-1">
              <span>Semua Transaksi</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          <div className="divide-y divide-slate-800">
            {recentTransactions.map((tx) => (
              <div key={tx.id} className="py-3 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-xl bg-slate-800 flex items-center justify-center text-xs font-bold text-slate-300">
                    {tx.type === "EXPENSE" ? "💸" : (tx.type === "INCOME" ? "💰" : "🔄")}
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-white">{tx.description}</div>
                    <div className="text-xs text-slate-400 flex items-center gap-2">
                      <span>{tx.category?.name || "Lain-lain"}</span>
                      <span>•</span>
                      <span>{tx.wallet?.name || "Dompet"}</span>
                      <span>•</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                        {tx.raw_source}
                      </span>
                    </div>
                  </div>
                </div>
                <div className="text-right">
                  <div className={`text-sm font-bold ${tx.type === "EXPENSE" ? "text-rose-400" : "text-emerald-400"}`}>
                    {tx.type === "EXPENSE" ? "-" : "+"}{formatCurrency(tx.amount, tx.currency)}
                  </div>
                  <div className="text-[11px] text-slate-400">{formatDate(tx.transaction_date)}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

