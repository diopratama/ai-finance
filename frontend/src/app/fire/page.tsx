"use client";

import { useEffect, useState } from "react";
import { Flame, Calculator, Sparkles, TrendingUp, CheckCircle2, AlertTriangle } from "lucide-react";
import { getFIREProfile, calculateCustomFIRE } from "@/lib/api";
import { FIREMetrics, AssetAllocation, PortfolioReview } from "@/lib/types";
import { formatCurrency } from "@/lib/utils";

export default function FIRECalculatorPage() {
  const [currentAge, setCurrentAge] = useState<number>(28);
  const [targetAge, setTargetAge] = useState<number>(45);
  const [monthlyExpense, setMonthlyExpense] = useState<number>(8000000);
  const [currentNetWorth, setCurrentNetWorth] = useState<number>(16250000);
  const [monthlySavings, setMonthlySavings] = useState<number>(4000000);
  const [expectedReturn, setExpectedReturn] = useState<number>(0.08);

  const [metrics, setMetrics] = useState<FIREMetrics | null>(null);
  const [allocations, setAllocations] = useState<AssetAllocation | null>(null);
  const [portfolioReview, setPortfolioReview] = useState<PortfolioReview | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const recalculate = async () => {
    try {
      const res = await calculateCustomFIRE({
        current_age: currentAge,
        target_fire_age: targetAge,
        monthly_expenses: monthlyExpense,
        current_net_worth: currentNetWorth,
        monthly_savings: monthlySavings,
        annual_return_rate: expectedReturn,
      });
      setMetrics(res);
    } catch (err) {
      console.error("FIRE calculation failed", err);
    }
  };

  useEffect(() => {
    async function loadInitial() {
      try {
        const init = await getFIREProfile();
        setCurrentAge(init.profile.current_age);
        setTargetAge(init.profile.target_fire_age);
        setMonthlyExpense(init.profile.monthly_living_expense);
        setCurrentNetWorth(init.metrics.current_net_worth);
        setMetrics(init.metrics);
        setAllocations(init.allocations);
        if (init.portfolio_review) {
          setPortfolioReview(init.portfolio_review);
        }
      } finally {
        setLoading(false);
      }
    }
    loadInitial();
  }, []);

  useEffect(() => {
    if (!loading) {
      recalculate();
    }
  }, [currentAge, targetAge, monthlyExpense, currentNetWorth, monthlySavings, expectedReturn]);

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
          <span>Kalkulator FIRE &amp; Pensiun Dini</span>
          <Flame className="w-6 h-6 text-[#f0b000]" />
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Simulasikan peta jalan menuju <strong>Financial Independence, Retire Early (FIRE)</strong> berbasis kaidah baku <em>Rule of 25</em> dan <em>4% Safe Withdrawal Rate</em>.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left Form: Sliders & Parameter Inputs */}
        <div className="p-6 rounded-3xl bg-card border border-border shadow-sm space-y-6">
          <div className="flex items-center gap-2 text-xs font-bold text-foreground uppercase tracking-wider">
            <Calculator className="w-4 h-4 text-[#8a6300] dark:text-[#f0b000]" />
            <span>Parameter Keuangan Anda</span>
          </div>

          {/* Age range */}
          <div className="space-y-4">
            <div>
              <div className="flex justify-between text-xs mb-1.5">
                <span className="text-foreground font-medium">Usia Saat Ini</span>
                <span className="font-bold text-foreground">{currentAge} tahun</span>
              </div>
              <input
                type="range"
                min="18"
                max="65"
                value={currentAge}
                onChange={(e) => setCurrentAge(parseInt(e.target.value))}
                className="w-full accent-[#f0b000] cursor-pointer"
              />
            </div>

            <div>
              <div className="flex justify-between text-xs mb-1.5">
                <span className="text-foreground font-medium">Target Usia Pensiun Dini</span>
                <span className="font-bold text-[#8a6300] dark:text-[#f0b000]">{targetAge} tahun</span>
              </div>
              <input
                type="range"
                min={currentAge + 1}
                max="75"
                value={targetAge}
                onChange={(e) => setTargetAge(parseInt(e.target.value))}
                className="w-full accent-[#f0b000] cursor-pointer"
              />
            </div>
          </div>

          {/* Monthly Expense */}
          <div>
            <label className="text-xs font-medium text-foreground block mb-1">
              Estimasi Pengeluaran Bulanan di Masa Pensiun (Rp)
            </label>
            <input
              type="number"
              value={monthlyExpense}
              onChange={(e) => setMonthlyExpense(parseFloat(e.target.value) || 0)}
              className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground font-mono font-medium text-sm focus:outline-none focus:border-[#f0b000]"
            />
            <span className="text-[11px] text-muted-foreground mt-1 block">
              Pengeluaran tahunan: {formatCurrency(monthlyExpense * 12)}
            </span>
          </div>

          {/* Monthly Savings */}
          <div>
            <label className="text-xs font-medium text-foreground block mb-1">
              Kemampuan Nabung &amp; Investasi Bulanan (Rp)
            </label>
            <input
              type="number"
              value={monthlySavings}
              onChange={(e) => setMonthlySavings(parseFloat(e.target.value) || 0)}
              className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground font-mono font-medium text-sm focus:outline-none focus:border-[#f0b000]"
            />
          </div>

          {/* Current Net Worth */}
          <div>
            <label className="text-xs font-medium text-foreground block mb-1">
              Total Investasi Awal Saat Ini (Rp)
            </label>
            <input
              type="number"
              value={currentNetWorth}
              onChange={(e) => setCurrentNetWorth(parseFloat(e.target.value) || 0)}
              className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground font-mono font-medium text-sm focus:outline-none focus:border-[#f0b000]"
            />
          </div>

          {/* Return Rate */}
          <div>
            <div className="flex justify-between text-xs mb-1.5">
              <span className="text-foreground font-medium">Ekspektasi Return Investasi Tahunan</span>
              <span className="font-bold text-foreground">{(expectedReturn * 100).toFixed(1)}%</span>
            </div>
            <input
              type="range"
              min="0.04"
              max="0.15"
              step="0.005"
              value={expectedReturn}
              onChange={(e) => setExpectedReturn(parseFloat(e.target.value))}
              className="w-full accent-[#f0b000] cursor-pointer"
            />
          </div>
        </div>

        {/* Right 2 Columns: Projection Results */}
        <div className="lg:col-span-2 space-y-6">
          {/* Target FIRE Hero Card */}
          <div className="p-6 rounded-3xl bg-accent border border-[#f0b000]/30 shadow-md">
            <span className="text-xs font-bold text-[#8a6300] dark:text-[#f0b000] uppercase tracking-wider">
              Target Angka FIRE Anda (Rule of 25)
            </span>
            <div className="text-3xl sm:text-4xl font-extrabold text-foreground mt-1 tracking-tight">
              {formatCurrency(metrics?.fire_number || 2400000000)}
            </div>
            <p className="text-xs text-muted-foreground mt-2 leading-relaxed">
              Dengan modal ini, Anda dapat menarik <strong>4% per tahun ({formatCurrency(monthlyExpense * 12)})</strong> atau <strong>{formatCurrency(monthlyExpense)}/bulan</strong> untuk biaya hidup tanpa menggerus modal pokok.
            </p>
          </div>

          {/* Projection Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="p-5 rounded-2xl bg-card border border-border shadow-sm">
              <span className="text-xs font-medium text-muted-foreground">Proyeksi Aset di Usia Pensiun ({targetAge} th)</span>
              <div className="text-2xl font-bold text-foreground mt-1 font-mono">
                {formatCurrency(metrics?.projected_net_worth_at_fire_age || 0)}
              </div>
              <div className="text-[11px] text-muted-foreground mt-2">
                Compound growth akumulasi selama {targetAge - currentAge} tahun.
              </div>
            </div>

            <div className="p-5 rounded-2xl bg-card border border-border shadow-sm">
              <span className="text-xs font-medium text-muted-foreground">Status Capaian Target</span>
              <div className="flex items-center gap-2 mt-2">
                {metrics?.is_on_track ? (
                  <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400 font-bold text-sm">
                    <CheckCircle2 className="w-5 h-5 shrink-0" />
                    <span>Target Tercapai Tepat Waktu!</span>
                  </div>
                ) : (
                  <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400 font-bold text-sm">
                    <AlertTriangle className="w-5 h-5 shrink-0" />
                    <span>Perlu Tambahan Tabungan / Return</span>
                  </div>
                )}
              </div>
              <div className="text-[11px] text-muted-foreground mt-2">
                {metrics?.actual_years_needed ? `Dibutuhkan sekitar ${metrics.actual_years_needed} tahun investasi` : "Target aman"}
              </div>
            </div>
          </div>

          {/* Asset Allocation Model */}
          {allocations && (
            <div className="p-6 rounded-3xl bg-card border border-border shadow-sm space-y-4">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div>
                  <h3 className="font-bold text-foreground text-base">
                    Rekomendasi vs Aktual Portofolio Menuju FIRE
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    Perbandingan komposisi dompet investasi Anda dengan model referensi ({allocations.profile})
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {portfolioReview && (
                    <span className="text-[11px] font-bold px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30">
                      Skor Keselarasan: {portfolioReview.alignment_score}/100
                    </span>
                  )}
                  <span className="text-xs font-bold px-2.5 py-1 rounded-full bg-accent text-[#8a6300] dark:text-[#f0b000] border border-[#f0b000]/30">
                    CAGR {allocations.expected_cagr}
                  </span>
                </div>
              </div>

              <div className="space-y-3 pt-2">
                {portfolioReview && portfolioReview.allocations_comparison.length > 0
                  ? portfolioReview.allocations_comparison.map((comp) => (
                      <div key={comp.asset_class} className="space-y-1.5">
                        <div className="flex justify-between text-xs">
                          <span className="text-foreground font-semibold">{comp.asset_class_label}</span>
                          <span className="text-foreground font-mono">
                            Aktual: <strong>{comp.actual_pct}%</strong> ({formatCurrency(comp.actual_amount)}) •{" "}
                            <span className="text-muted-foreground">Target: {comp.target_pct}%</span>
                          </span>
                        </div>
                        <div className="w-full bg-secondary h-2 rounded-full overflow-hidden border border-border">
                          <div
                            className="h-full rounded-full transition-all duration-300"
                            style={{ width: `${Math.min(100, comp.actual_pct)}%`, backgroundColor: comp.color }}
                          />
                        </div>
                      </div>
                    ))
                  : allocations.allocations.map((a, idx) => (
                      <div key={idx} className="space-y-1">
                        <div className="flex justify-between text-xs">
                          <span className="text-foreground font-medium">{a.asset}</span>
                          <span className="text-foreground font-bold">{a.percentage}%</span>
                        </div>
                        <div className="w-full bg-secondary h-2 rounded-full overflow-hidden border border-border">
                          <div
                            className="h-full rounded-full transition-all duration-300"
                            style={{ width: `${a.percentage}%`, backgroundColor: a.color }}
                          />
                        </div>
                      </div>
                    ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
