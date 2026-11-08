"use client";

import { useEffect, useState } from "react";
import {
  Plus,
  Search,
  Filter,
  Trash2,
  ArrowUpRight,
  ArrowDownLeft,
  RefreshCw,
  Sparkles,
  Tag,
  Target,
} from "lucide-react";
import {
  getTransactions,
  getWallets,
  getCategories,
  getBudgets,
  createTransaction,
  deleteTransaction,
  createCustomCategory,
} from "@/lib/api";
import { Transaction, Wallet, Category, Budget } from "@/lib/types";
import { formatCurrency, formatDate } from "@/lib/utils";

export default function TransactionsPage() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [activeBudgets, setActiveBudgets] = useState<Budget[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);

  // Filters
  const [selectedType, setSelectedType] = useState<string>("");
  const [selectedWallet, setSelectedWallet] = useState<string>("");
  const [selectedCategory, setSelectedCategory] = useState<string>("");
  const [selectedBudget, setSelectedBudget] = useState<string>("");
  const [search, setSearch] = useState<string>("");

  // Add Transaction Modal
  const [showAddModal, setShowAddModal] = useState<boolean>(false);
  const [showCustomCatModal, setShowCustomCatModal] = useState<boolean>(false);
  const [txType, setTxType] = useState<string>("EXPENSE");
  const [amount, setAmount] = useState<string>("");
  const [description, setDescription] = useState<string>("");
  const [walletId, setWalletId] = useState<string>("");
  const [categoryId, setCategoryId] = useState<string>("");
  const [budgetId, setBudgetId] = useState<string>("");

  // Quick custom category form
  const [customCatName, setCustomCatName] = useState("");
  const [customCatType, setCustomCatType] = useState<"EXPENSE" | "INCOME">("EXPENSE");

  const refreshData = async () => {
    setLoading(true);
    try {
      const [txRes, wRes, catRes, bRes] = await Promise.all([
        getTransactions({
          type: selectedType || undefined,
          wallet_id: selectedWallet || undefined,
          category_id: selectedCategory || undefined,
          budget_id: selectedBudget || undefined,
          search: search || undefined,
        }),
        getWallets(),
        getCategories(),
        getBudgets(),
      ]);
      setTransactions(txRes.items);
      setTotalCount(txRes.total);
      setWallets(wRes.wallets);
      setCategories(catRes);
      setActiveBudgets(bRes);
      if (wRes.wallets.length > 0 && !walletId) {
        setWalletId(wRes.wallets[0].id);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshData();
  }, [selectedType, selectedWallet, selectedCategory, selectedBudget, search]);

  const handleCreateTx = async (e: React.FormEvent) => {
    e.preventDefault();
    const amt = parseFloat(amount);
    if (!amt || amt <= 0 || !description.trim()) return;

    await createTransaction({
      wallet_id: walletId || undefined,
      category_id: categoryId || undefined,
      budget_id: budgetId || undefined,
      type: txType,
      amount: amt,
      description,
      raw_source: "WEB",
    });

    setAmount("");
    setDescription("");
    setBudgetId("");
    setShowAddModal(false);
    refreshData();
  };

  const handleBudgetSelect = (selectedBudgetId: string) => {
    setBudgetId(selectedBudgetId);
    if (selectedBudgetId) {
      const matched = activeBudgets.find((b) => b.id === selectedBudgetId);
      if (matched) {
        if (matched.wallet_id) setWalletId(matched.wallet_id);
        if (matched.category_id) setCategoryId(matched.category_id);
        if (!description) setDescription(`Realisasi ${matched.name}`);
      }
    }
  };

  const handleCreateCustomCategory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customCatName.trim()) return;

    const newCat = await createCustomCategory({
      name: customCatName.trim(),
      type: customCatType,
      color: "#f0b000",
      icon: "tag",
    });

    setCategoryId(newCat.id);
    setCustomCatName("");
    setShowCustomCatModal(false);
    const updated = await getCategories();
    setCategories(updated);
  };

  const handleDelete = async (id: string) => {
    if (confirm("Hapus transaksi ini? Saldo dompet terkait akan disesuaikan kembali.")) {
      await deleteTransaction(id);
      refreshData();
    }
  };

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Daftar Transaksi</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Semua catatan pemasukan, pengeluaran, dan transfer yang dicatat via Web, Bot Telegram, maupun WhatsApp.
          </p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold bg-primary hover:bg-primary/90 text-primary-foreground transition-colors shadow-md shadow-[#f0b000]/20 self-start sm:self-auto"
        >
          <Plus className="w-4 h-4" />
          <span>+ Catat Transaksi Baru</span>
        </button>
      </div>

      {/* Filter Bar */}
      <div className="p-4 rounded-3xl bg-card border border-border shadow-sm flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3 flex-1 min-w-[280px]">
          {/* Search */}
          <div className="relative flex-1 min-w-[200px]">
            <Search className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Cari transaksi atau merchant..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2 rounded-xl bg-secondary border border-border text-foreground text-xs focus:outline-none focus:border-[#f0b000]"
            />
          </div>

          {/* Type Filter */}
          <select
            value={selectedType}
            onChange={(e) => setSelectedType(e.target.value)}
            className="px-3 py-2 rounded-xl bg-secondary border border-border text-foreground text-xs focus:outline-none"
          >
            <option value="">Semua Tipe</option>
            <option value="EXPENSE">Pengeluaran</option>
            <option value="INCOME">Pemasukan</option>
            <option value="TRANSFER">Transfer</option>
          </select>

          {/* Wallet Filter */}
          <select
            value={selectedWallet}
            onChange={(e) => setSelectedWallet(e.target.value)}
            className="px-3 py-2 rounded-xl bg-secondary border border-border text-foreground text-xs focus:outline-none"
          >
            <option value="">Semua Dompet</option>
            {wallets.map((w) => (
              <option key={w.id} value={w.id}>{w.name}</option>
            ))}
          </select>

          {/* Category Filter */}
          <select
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
            className="px-3 py-2 rounded-xl bg-secondary border border-border text-foreground text-xs focus:outline-none"
          >
            <option value="">Semua Kategori</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>

          {/* Budget Pos Filter */}
          <select
            value={selectedBudget}
            onChange={(e) => setSelectedBudget(e.target.value)}
            className="px-3 py-2 rounded-xl bg-secondary border border-border text-foreground text-xs focus:outline-none"
          >
            <option value="">Semua Pos Anggaran</option>
            {activeBudgets.map((b) => (
              <option key={b.id} value={b.id}>{b.name} ({b.group_type})</option>
            ))}
          </select>
        </div>

        <button
          onClick={refreshData}
          className="p-2 rounded-xl bg-secondary hover:bg-accent text-muted-foreground hover:text-foreground transition-colors border border-border"
          title="Muat Ulang"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* Transactions Table */}
      <div className="rounded-3xl bg-card border border-border overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-secondary/70 text-muted-foreground uppercase font-bold border-b border-border">
              <tr>
                <th className="py-3.5 px-4">Deskripsi &amp; Sumber</th>
                <th className="py-3.5 px-4">Pos Anggaran / Kategori</th>
                <th className="py-3.5 px-4">Dompet (Fund Location)</th>
                <th className="py-3.5 px-4">Tanggal</th>
                <th className="py-3.5 px-4 text-right">Nominal</th>
                <th className="py-3.5 px-4 text-center">Aksi</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {transactions.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-muted-foreground">
                    Belum ada transaksi yang sesuai dengan filter.
                  </td>
                </tr>
              ) : (
                transactions.map((tx) => (
                  <tr key={tx.id} className="hover:bg-secondary/30 transition-colors">
                    <td className="py-3.5 px-4">
                      <div className="flex items-center gap-3">
                        <div
                          className={`w-8 h-8 rounded-xl border flex items-center justify-center font-bold shrink-0 ${
                            tx.type === "EXPENSE"
                              ? "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20"
                              : tx.type === "INCOME"
                              ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20"
                              : "bg-accent text-[#8a6300] dark:text-[#f0b000] border-[#f0b000]/30"
                          }`}
                        >
                          {tx.type === "EXPENSE" ? (
                            <ArrowDownLeft className="w-4 h-4" />
                          ) : tx.type === "TRANSFER" ? (
                            <ArrowLeftRight className="w-4 h-4" />
                          ) : (
                            <ArrowUpRight className="w-4 h-4" />
                          )}
                        </div>
                        <div>
                          <div className="font-semibold text-foreground">{tx.description}</div>
                          {tx.merchant && <div className="text-[11px] text-muted-foreground">Toko: {tx.merchant}</div>}
                          <div className="flex items-center gap-1.5 mt-0.5">
                            <span className="text-[10px] px-1.5 py-0.2 rounded bg-secondary text-muted-foreground border border-border">
                              {tx.raw_source}
                            </span>
                            {tx.created_by && !tx.is_own && (
                              <span className="text-[10px] px-1.5 py-0.2 rounded bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20 font-medium">
                                Dicatat: {tx.created_by.name}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="py-3.5 px-4">
                      <div className="space-y-1">
                        {tx.budget ? (
                          <div className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-accent border border-[#f0b000]/30 text-[#8a6300] dark:text-[#f0b000] font-semibold text-[11px]">
                            <Target className="w-3 h-3" />
                            <span>{tx.budget.name}</span>
                          </div>
                        ) : (
                          <span className="px-2.5 py-0.5 rounded-full bg-secondary text-muted-foreground border border-border text-[11px]">
                            {tx.category?.name || (tx.type === "TRANSFER" ? "Transfer Saldo" : "Lain-lain")}
                          </span>
                        )}
                        {tx.budget && tx.category && (
                          <div className="text-[10px] text-muted-foreground">{tx.category.name}</div>
                        )}
                      </div>
                    </td>
                    <td className="py-3.5 px-4">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span
                          className="w-2.5 h-2.5 rounded-full"
                          style={{ backgroundColor: tx.wallet?.color || "#f0b000" }}
                        />
                        {tx.to_wallet ? (
                          <span className="font-medium text-foreground text-xs flex items-center gap-1">
                            <span>{tx.wallet?.name || "Asal"}</span>
                            <span className="text-muted-foreground">&rarr;</span>
                            <span className="text-primary font-bold">{tx.to_wallet.name}</span>
                          </span>
                        ) : (
                          <span className="font-medium text-foreground text-xs">{tx.wallet?.name || "Dompet"}</span>
                        )}
                      </div>
                    </td>
                    <td className="py-3.5 px-4 text-muted-foreground">{formatDate(tx.transaction_date)}</td>
                    <td className="py-3.5 px-4 text-right font-bold font-mono">
                      <span
                        className={
                          tx.type === "EXPENSE"
                            ? "text-rose-600 dark:text-rose-400"
                            : tx.type === "INCOME"
                            ? "text-emerald-600 dark:text-emerald-400"
                            : "text-foreground"
                        }
                      >
                        {tx.type === "EXPENSE" ? "-" : tx.type === "INCOME" ? "+" : ""}
                        {formatCurrency(tx.amount, tx.currency)}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-center">
                      <button
                        onClick={() => handleDelete(tx.id)}
                        className="text-muted-foreground hover:text-rose-500 transition-colors p-1"
                        title="Hapus Transaksi"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add Transaction Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <h2 className="text-lg font-bold text-foreground">Catat Transaksi Baru</h2>
            <form onSubmit={handleCreateTx} className="space-y-4 text-xs">
              {/* Type Switcher */}
              <div className="grid grid-cols-2 gap-2 p-1 rounded-xl bg-secondary border border-border">
                <button
                  type="button"
                  onClick={() => setTxType("EXPENSE")}
                  className={`py-2 text-xs font-bold rounded-lg transition-colors ${
                    txType === "EXPENSE"
                      ? "bg-rose-500 text-white shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  Pengeluaran (Expense)
                </button>
                <button
                  type="button"
                  onClick={() => setTxType("INCOME")}
                  className={`py-2 text-xs font-bold rounded-lg transition-colors ${
                    txType === "INCOME"
                      ? "bg-emerald-500 text-slate-950 shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  Pemasukan (Income)
                </button>
              </div>

              {/* Optional Pos Anggaran selection */}
              {txType === "EXPENSE" && (
                <div>
                  <label className="font-semibold text-foreground block mb-1">
                    Hubungkan ke Pos Anggaran (Opsional)
                  </label>
                  <select
                    value={budgetId}
                    onChange={(e) => handleBudgetSelect(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground font-medium"
                  >
                    <option value="">-- Tanpa Hubungan Pos Spesifik --</option>
                    {activeBudgets.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name} ({b.group_type}) - Limit: {formatCurrency(b.limit_amount)}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <label className="font-semibold text-foreground block mb-1">Nominal (Rp)</label>
                <input
                  type="number"
                  placeholder="Contoh: 35000"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground font-mono font-bold text-sm"
                  required
                />
              </div>

              <div>
                <label className="font-semibold text-foreground block mb-1">Deskripsi Transaksi</label>
                <input
                  type="text"
                  placeholder="Contoh: Bensin Pertamax / Makan siang"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground"
                  required
                />
              </div>

              <div>
                <label className="font-semibold text-foreground block mb-1">Dompet / Rekening</label>
                <select
                  value={walletId}
                  onChange={(e) => setWalletId(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground"
                >
                  {wallets.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name} ({formatCurrency(w.balance, w.currency)})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="font-semibold text-foreground">Kategori</label>
                  <button
                    type="button"
                    onClick={() => setShowCustomCatModal(true)}
                    className="text-[11px] text-[#8a6300] dark:text-[#f0b000] hover:underline"
                  >
                    + Buat Kategori Custom
                  </button>
                </div>
                <select
                  value={categoryId}
                  onChange={(e) => setCategoryId(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground"
                >
                  <option value="">Pilih Kategori</option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>

              <div className="flex items-center justify-end gap-3 mt-6 pt-4 border-t border-border">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 rounded-xl text-muted-foreground hover:text-foreground"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl bg-primary text-primary-foreground font-bold shadow-md shadow-[#f0b000]/20"
                >
                  Simpan Transaksi
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Quick Custom Category Modal */}
      {showCustomCatModal && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl max-w-sm w-full p-6 shadow-2xl space-y-4 text-xs">
            <h2 className="text-base font-bold text-foreground">Tambah Kategori Custom</h2>
            <form onSubmit={handleCreateCustomCategory} className="space-y-3">
              <div>
                <label className="font-semibold text-foreground block mb-1">Nama Kategori</label>
                <input
                  type="text"
                  placeholder="Contoh: Kebutuhan Bayi, Zakat..."
                  value={customCatName}
                  onChange={(e) => setCustomCatName(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground"
                  required
                />
              </div>
              <div>
                <label className="font-semibold text-foreground block mb-1">Tipe</label>
                <select
                  value={customCatType}
                  onChange={(e) => setCustomCatType(e.target.value as "EXPENSE" | "INCOME")}
                  className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground"
                >
                  <option value="EXPENSE">Pengeluaran (Expense)</option>
                  <option value="INCOME">Pemasukan (Income)</option>
                </select>
              </div>
              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCustomCatModal(false)}
                  className="px-4 py-2 rounded-xl text-muted-foreground hover:text-foreground"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl bg-primary text-primary-foreground font-bold"
                >
                  Simpan Kategori
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
