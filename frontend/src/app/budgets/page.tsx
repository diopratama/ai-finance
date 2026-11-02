"use client";

import { useEffect, useState } from "react";
import { Plus, Target, AlertTriangle, CheckCircle2, Trash2 } from "lucide-react";
import { getBudgets, getCategories, createBudget, deleteBudget } from "@/lib/api";
import { Budget, Category } from "@/lib/types";
import { formatCurrency } from "@/lib/utils";

export default function BudgetsPage() {
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  // Add Budget Modal
  const [showAddModal, setShowAddModal] = useState<boolean>(false);
  const [categoryId, setCategoryId] = useState<string>("");
  const [limitAmount, setLimitAmount] = useState<string>("");

  const refreshBudgets = async () => {
    setLoading(true);
    try {
      const [bRes, cRes] = await Promise.all([getBudgets(), getCategories()]);
      setBudgets(bRes);
      setCategories(cRes.filter((c) => c.type === "EXPENSE"));
      if (cRes.length > 0 && !categoryId) {
        setCategoryId(cRes[0].id);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshBudgets();
  }, []);

  const handleCreateBudget = async (e: React.FormEvent) => {
    e.preventDefault();
    const limit = parseFloat(limitAmount);
    if (!categoryId || !limit || limit <= 0) return;

    await createBudget({
      category_id: categoryId,
      limit_amount: limit,
      period: "MONTHLY",
    });

    setLimitAmount("");
    setShowAddModal(false);
    refreshBudgets();
  };

  const handleDelete = async (id: string) => {
    if (confirm("Hapus batasan anggaran ini?")) {
      await deleteBudget(id);
      refreshBudgets();
    }
  };

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Anggaran Bulanan (Budgeting)</h1>
          <p className="text-sm text-slate-400 mt-1">
            Kendalikan batas pengeluaran per kategori. Dapatkan peringatan otomatis ketika pengeluaran mendekati batas limit.
          </p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold transition-colors shadow-sm self-start sm:self-auto"
        >
          <Plus className="w-4 h-4" />
          <span>+ Buat Batas Anggaran</span>
        </button>
      </div>

      {/* Budgets Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {budgets.map((b) => {
          const isDanger = b.percent_used >= 90;
          const isWarning = b.percent_used >= 70 && b.percent_used < 90;

          return (
            <div
              key={b.id}
              className="p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-sm flex flex-col justify-between space-y-4 relative overflow-hidden"
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div
                    className="w-10 h-10 rounded-xl flex items-center justify-center font-bold text-white shadow-sm"
                    style={{ backgroundColor: b.category?.color || "#64748b" }}
                  >
                    <Target className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="font-bold text-white text-base">{b.category?.name || "Kategori"}</h3>
                    <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">
                      Periode: {b.period}
                    </span>
                  </div>
                </div>

                <button
                  onClick={() => handleDelete(b.id)}
                  className="text-slate-500 hover:text-rose-400 transition-colors p-1"
                  title="Hapus Budget"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>

              {/* Progress and status */}
              <div className="space-y-2">
                <div className="flex justify-between text-xs">
                  <span className="text-slate-400">
                    Terpakai: <strong className="text-white">{formatCurrency(b.spent_amount)}</strong>
                  </span>
                  <span className={`font-semibold ${isDanger ? "text-rose-400" : (isWarning ? "text-amber-400" : "text-emerald-400")}`}>
                    {b.percent_used}%
                  </span>
                </div>

                <div className="w-full bg-slate-800 h-2.5 rounded-full overflow-hidden p-0.5 border border-slate-700/50">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      isDanger
                        ? "bg-rose-500"
                        : (isWarning ? "bg-amber-400" : "bg-emerald-500")
                    }`}
                    style={{ width: `${Math.min(100, b.percent_used)}%` }}
                  />
                </div>

                <div className="flex justify-between text-[11px] text-slate-400 pt-1">
                  <span>Limit: {formatCurrency(b.limit_amount)}</span>
                  <span>Sisa: <strong className="text-slate-200">{formatCurrency(b.remaining_amount)}</strong></span>
                </div>
              </div>

              {/* Status Alert Badge */}
              <div className="pt-3 border-t border-slate-800">
                {b.is_over_budget ? (
                  <div className="flex items-center gap-2 text-rose-400 text-xs font-semibold">
                    <AlertTriangle className="w-4 h-4 shrink-0" />
                    <span>Melebihi Anggaran! Harap rem pengeluaran.</span>
                  </div>
                ) : (
                  <div className="flex items-center gap-2 text-emerald-400 text-xs font-medium">
                    <CheckCircle2 className="w-4 h-4 shrink-0" />
                    <span>Anggaran terkontrol dengan baik.</span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Add Budget Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full p-6 shadow-2xl">
            <h2 className="text-lg font-bold text-white mb-4">Buat Batas Anggaran Bulanan</h2>
            <form onSubmit={handleCreateBudget} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">Kategori Pengeluaran</label>
                <select
                  value={categoryId}
                  onChange={(e) => setCategoryId(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-800 border border-slate-700 text-white text-sm focus:outline-none focus:border-emerald-500"
                >
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">Batas Maksimal Bulanan (Rp)</label>
                <input
                  type="number"
                  placeholder="Contoh: 3000000"
                  value={limitAmount}
                  onChange={(e) => setLimitAmount(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-800 border border-slate-700 text-white text-sm focus:outline-none focus:border-emerald-500"
                  required
                />
              </div>

              <div className="flex items-center justify-end gap-3 mt-6 pt-4 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:text-white"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl text-xs font-bold bg-emerald-500 hover:bg-emerald-600 text-slate-950 shadow-sm"
                >
                  Pasang Budget
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

