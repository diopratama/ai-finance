"use client";

import { useEffect, useState } from "react";
import { Plus, Search, Filter, Trash2, ArrowUpRight, ArrowDownLeft, RefreshCw } from "lucide-react";
import { getTransactions, getWallets, getCategories, createTransaction, deleteTransaction } from "@/lib/api";
import { Transaction, Wallet, Category } from "@/lib/types";
import { formatCurrency, formatDate } from "@/lib/utils";

export default function TransactionsPage() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);

  // Filters
  const [selectedType, setSelectedType] = useState<string>("");
  const [selectedWallet, setSelectedWallet] = useState<string>("");
  const [selectedCategory, setSelectedCategory] = useState<string>("");
  const [search, setSearch] = useState<string>("");

  // Add Transaction Modal
  const [showAddModal, setShowAddModal] = useState<boolean>(false);
  const [txType, setTxType] = useState<string>("EXPENSE");
  const [amount, setAmount] = useState<string>("");
  const [description, setDescription] = useState<string>("");
  const [walletId, setWalletId] = useState<string>("");
  const [categoryId, setCategoryId] = useState<string>("");

  const refreshData = async () => {
    setLoading(true);
    try {
      const [txRes, wRes, catRes] = await Promise.all([
        getTransactions({
          type: selectedType || undefined,
          wallet_id: selectedWallet || undefined,
          category_id: selectedCategory || undefined,
          search: search || undefined,
        }),
        getWallets(),
        getCategories(),
      ]);
      setTransactions(txRes.items);
      setTotalCount(txRes.total);
      setWallets(wRes.wallets);
      setCategories(catRes);
      if (wRes.wallets.length > 0 && !walletId) {
        setWalletId(wRes.wallets[0].id);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshData();
  }, [selectedType, selectedWallet, selectedCategory, search]);

  const handleCreateTx = async (e: React.FormEvent) => {
    e.preventDefault();
    const amt = parseFloat(amount);
    if (!amt || amt <= 0 || !walletId || !description.trim()) return;

    await createTransaction({
      wallet_id: walletId,
      category_id: categoryId || undefined,
      type: txType,
      amount: amt,
      description,
      raw_source: "WEB",
    });

    setAmount("");
    setDescription("");
    setShowAddModal(false);
    refreshData();
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
          <h1 className="text-2xl font-bold tracking-tight text-white">Daftar Transaksi</h1>
          <p className="text-sm text-slate-400 mt-1">
            Semua catatan pemasukan, pengeluaran, dan transfer yang dicatat via Web, Telegram, maupun WhatsApp.
          </p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold transition-colors shadow-sm self-start sm:self-auto"
        >
          <Plus className="w-4 h-4" />
          <span>+ Catat Transaksi Baru</span>
        </button>
      </div>

      {/* Filter Bar */}
      <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3 flex-1 min-w-[280px]">
          {/* Search */}
          <div className="relative flex-1 min-w-[200px]">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Cari transaksi atau merchant..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2 rounded-xl bg-slate-800 border border-slate-700 text-white text-xs focus:outline-none focus:border-emerald-500"
            />
          </div>

          {/* Type Filter */}
          <select
            value={selectedType}
            onChange={(e) => setSelectedType(e.target.value)}
            className="px-3 py-2 rounded-xl bg-slate-800 border border-slate-700 text-slate-200 text-xs focus:outline-none"
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
            className="px-3 py-2 rounded-xl bg-slate-800 border border-slate-700 text-slate-200 text-xs focus:outline-none"
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
            className="px-3 py-2 rounded-xl bg-slate-800 border border-slate-700 text-slate-200 text-xs focus:outline-none"
          >
            <option value="">Semua Kategori</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>

        <button
          onClick={refreshData}
          className="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
          title="Muat Ulang"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* Transactions Table */}
      <div className="rounded-2xl bg-slate-900 border border-slate-800 overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-800/60 text-slate-400 uppercase font-semibold border-b border-slate-800">
              <tr>
                <th className="py-3.5 px-4">Deskripsi & Sumber</th>
                <th className="py-3.5 px-4">Kategori</th>
                <th className="py-3.5 px-4">Dompet</th>
                <th className="py-3.5 px-4">Tanggal</th>
                <th className="py-3.5 px-4 text-right">Nominal</th>
                <th className="py-3.5 px-4 text-center">Aksi</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800 text-slate-300">
              {transactions.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-slate-500">
                    Belum ada transaksi yang sesuai dengan filter.
                  </td>
                </tr>
              ) : (
                transactions.map((tx) => (
                  <tr key={tx.id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="py-3.5 px-4">
                      <div className="flex items-center gap-3">
                        <div className={`w-8 h-8 rounded-lg flex items-center justify-center font-bold ${
                          tx.type === "EXPENSE" ? "bg-rose-500/10 text-rose-400" : (tx.type === "INCOME" ? "bg-emerald-500/10 text-emerald-400" : "bg-sky-500/10 text-sky-400")
                        }`}>
                          {tx.type === "EXPENSE" ? <ArrowDownLeft className="w-4 h-4" /> : <ArrowUpRight className="w-4 h-4" />}
                        </div>
                        <div>
                          <div className="font-semibold text-white">{tx.description}</div>
                          {tx.merchant && <div className="text-[11px] text-slate-400">Toko: {tx.merchant}</div>}
                          <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-400 border border-slate-700">
                            {tx.raw_source}
                          </span>
                        </div>
                      </div>
                    </td>
                    <td className="py-3.5 px-4">
                      <span className="px-2.5 py-1 rounded-full bg-slate-800 text-slate-200 border border-slate-700">
                        {tx.category?.name || "Lain-lain"}
                      </span>
                    </td>
                    <td className="py-3.5 px-4">
                      <div className="flex items-center gap-2">
                        <span
                          className="w-2.5 h-2.5 rounded-full"
                          style={{ backgroundColor: tx.wallet?.color || "#3b82f6" }}
                        />
                        <span>{tx.wallet?.name || "Dompet"}</span>
                      </div>
                    </td>
                    <td className="py-3.5 px-4 text-slate-400">{formatDate(tx.transaction_date)}</td>
                    <td className="py-3.5 px-4 text-right font-bold">
                      <span className={tx.type === "EXPENSE" ? "text-rose-400" : "text-emerald-400"}>
                        {tx.type === "EXPENSE" ? "-" : "+"}{formatCurrency(tx.amount, tx.currency)}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-center">
                      <button
                        onClick={() => handleDelete(tx.id)}
                        className="text-slate-500 hover:text-rose-400 transition-colors p-1"
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
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full p-6 shadow-2xl">
            <h2 className="text-lg font-bold text-white mb-4">Catat Transaksi Baru</h2>
            <form onSubmit={handleCreateTx} className="space-y-4">
              {/* Type Switcher */}
              <div className="grid grid-cols-2 gap-2 p-1 rounded-xl bg-slate-800">
                <button
                  type="button"
                  onClick={() => setTxType("EXPENSE")}
                  className={`py-2 text-xs font-bold rounded-lg transition-colors ${
                    txType === "EXPENSE" ? "bg-rose-500 text-white" : "text-slate-400"
                  }`}
                >
                  Pengeluaran (Expense)
                </button>
                <button
                  type="button"
                  onClick={() => setTxType("INCOME")}
                  className={`py-2 text-xs font-bold rounded-lg transition-colors ${
                    txType === "INCOME" ? "bg-emerald-500 text-slate-950" : "text-slate-400"
                  }`}
                >
                  Pemasukan (Income)
                </button>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">Nominal (Rp)</label>
                <input
                  type="number"
                  placeholder="Contoh: 35000"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-800 border border-slate-700 text-white text-sm focus:outline-none focus:border-emerald-500"
                  required
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">Deskripsi Transaksi</label>
                <input
                  type="text"
                  placeholder="Contoh: Makan siang nasi padang"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-800 border border-slate-700 text-white text-sm focus:outline-none focus:border-emerald-500"
                  required
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">Dompet / Rekening</label>
                <select
                  value={walletId}
                  onChange={(e) => setWalletId(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-800 border border-slate-700 text-white text-sm focus:outline-none focus:border-emerald-500"
                >
                  {wallets.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name} ({formatCurrency(w.balance, w.currency)})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">Kategori</label>
                <select
                  value={categoryId}
                  onChange={(e) => setCategoryId(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-800 border border-slate-700 text-white text-sm focus:outline-none focus:border-emerald-500"
                >
                  <option value="">Pilih Kategori</option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
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
                  Simpan Transaksi
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

