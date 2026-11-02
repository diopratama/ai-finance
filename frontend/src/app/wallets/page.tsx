"use client";

import { useEffect, useState } from "react";
import { Plus, ArrowLeftRight, Trash2, Wallet as WalletIcon, ShieldAlert } from "lucide-react";
import { getWallets, createWallet, transferFunds, deleteWallet } from "@/lib/api";
import { Wallet } from "@/lib/types";
import { formatCurrency, formatDate } from "@/lib/utils";

export default function WalletsPage() {
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [totalBalance, setTotalBalance] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);

  // Modals state
  const [showAddModal, setShowAddModal] = useState<boolean>(false);
  const [showTransferModal, setShowTransferModal] = useState<boolean>(false);

  // Form states
  const [name, setName] = useState("");
  const [type, setType] = useState("BANK");
  const [balance, setBalance] = useState("0");
  const [currency, setCurrency] = useState("IDR");
  const [color, setColor] = useState("#3b82f6");

  // Transfer form
  const [fromWalletId, setFromWalletId] = useState("");
  const [toWalletId, setToWalletId] = useState("");
  const [transferAmount, setTransferAmount] = useState("");
  const [transferDesc, setTransferDesc] = useState("");

  const refreshWallets = async () => {
    setLoading(true);
    try {
      const res = await getWallets();
      setWallets(res.wallets);
      setTotalBalance(res.total_balance);
      if (res.wallets.length >= 2) {
        setFromWalletId(res.wallets[0].id);
        setToWalletId(res.wallets[1].id);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshWallets();
  }, []);

  const handleCreateWallet = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    await createWallet({
      name,
      type,
      balance: parseFloat(balance) || 0,
      currency,
      color,
    });
    setName("");
    setBalance("0");
    setShowAddModal(false);
    refreshWallets();
  };

  const handleTransfer = async (e: React.FormEvent) => {
    e.preventDefault();
    const amt = parseFloat(transferAmount);
    if (!amt || amt <= 0 || !fromWalletId || !toWalletId || fromWalletId === toWalletId) return;

    await transferFunds({
      from_wallet_id: fromWalletId,
      to_wallet_id: toWalletId,
      amount: amt,
      description: transferDesc || undefined,
    });
    setTransferAmount("");
    setTransferDesc("");
    setShowTransferModal(false);
    refreshWallets();
  };

  const handleDelete = async (id: string) => {
    if (confirm("Apakah Anda yakin ingin mengarsipkan dompet ini?")) {
      await deleteWallet(id);
      refreshWallets();
    }
  };

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Dompet & Rekening Statis</h1>
          <p className="text-sm text-slate-400 mt-1">
            Kelola saldo akun riil Anda (Bank BCA, Mandiri, Cash, GoPay, OVO, dll.) tanpa butuh koneksi perbankan pihak ketiga.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowTransferModal(true)}
            className="flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-200 transition-colors"
          >
            <ArrowLeftRight className="w-4 h-4 text-sky-400" />
            <span>Transfer Antar-Dompet</span>
          </button>
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold transition-colors shadow-sm"
          >
            <Plus className="w-4 h-4" />
            <span>+ Tambah Dompet</span>
          </button>
        </div>
      </div>

      {/* Total Balance Card */}
      <div className="p-6 rounded-2xl bg-gradient-to-r from-slate-900 via-slate-900 to-slate-800 border border-slate-800 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Total Saldo Semua Akun</span>
          <div className="text-3xl font-extrabold text-white mt-1">
            {formatCurrency(totalBalance, "IDR")}
          </div>
        </div>
        <div className="text-xs text-slate-400 max-w-xs">
          💡 Bot Telegram dan WhatsApp Anda dapat mengenali nama-nama dompet ini secara otomatis saat mencatat pengeluaran.
        </div>
      </div>

      {/* Wallets Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {wallets.map((w) => (
          <div
            key={w.id}
            className="p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-sm relative overflow-hidden flex flex-col justify-between h-48 group hover:border-slate-700 transition-colors"
          >
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div
                  className="w-10 h-10 rounded-xl flex items-center justify-center font-bold text-white shadow-sm"
                  style={{ backgroundColor: w.color }}
                >
                  <WalletIcon className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-white text-base">{w.name}</h3>
                  <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">
                    {w.type} • {w.currency}
                  </span>
                </div>
              </div>
              <button
                onClick={() => handleDelete(w.id)}
                className="text-slate-500 hover:text-rose-400 transition-colors p-1"
                title="Arsipkan Wallet"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>

            <div className="mt-4">
              <span className="text-xs text-slate-400">Saldo Saat Ini</span>
              <div className="text-2xl font-extrabold text-white mt-0.5 tracking-tight">
                {formatCurrency(w.balance, w.currency)}
              </div>
            </div>

            <div className="flex items-center justify-between pt-3 border-t border-slate-800 text-[11px] text-slate-500">
              <span>{w.is_default ? "⭐ Dompet Bawaan (Default)" : "Akun Terdaftar"}</span>
              <span>Dibuat: {formatDate(w.created_at)}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Add Wallet Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full p-6 shadow-2xl">
            <h2 className="text-lg font-bold text-white mb-4">Tambah Dompet / Rekening Baru</h2>
            <form onSubmit={handleCreateWallet} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">Nama Dompet / Bank</label>
                <input
                  type="text"
                  placeholder="Contoh: Bank BCA, Mandiri Gaji, GoPay, Bibit"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-800 border border-slate-700 text-white text-sm focus:outline-none focus:border-emerald-500"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-slate-300 block mb-1">Tipe Akun</label>
                  <select
                    value={type}
                    onChange={(e) => setType(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-slate-800 border border-slate-700 text-white text-sm focus:outline-none focus:border-emerald-500"
                  >
                    <option value="BANK">Bank</option>
                    <option value="EWALLET">E-Wallet</option>
                    <option value="CASH">Uang Tunai / Cash</option>
                    <option value="INVESTMENT">Investasi</option>
                    <option value="CREDIT">Kartu Kredit / Pinjaman</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-300 block mb-1">Mata Uang</label>
                  <select
                    value={currency}
                    onChange={(e) => setCurrency(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-slate-800 border border-slate-700 text-white text-sm focus:outline-none focus:border-emerald-500"
                  >
                    <option value="IDR">IDR (Rp)</option>
                    <option value="USD">USD ($)</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">Saldo Awal</label>
                <input
                  type="number"
                  placeholder="0"
                  value={balance}
                  onChange={(e) => setBalance(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-800 border border-slate-700 text-white text-sm focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">Warna Label</label>
                <div className="flex items-center gap-2">
                  {["#3b82f6", "#10b981", "#06b6d4", "#f97316", "#8b5cf6", "#ec4899"].map((c) => (
                    <button
                      key={c}
                      type="button"
                      onClick={() => setColor(c)}
                      className={`w-7 h-7 rounded-full transition-transform ${color === c ? "ring-2 ring-white scale-110" : ""}`}
                      style={{ backgroundColor: c }}
                    />
                  ))}
                </div>
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
                  Simpan Dompet
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Transfer Funds Modal */}
      {showTransferModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full p-6 shadow-2xl">
            <h2 className="text-lg font-bold text-white mb-4">Transfer Antar-Dompet</h2>
            <form onSubmit={handleTransfer} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">Dari Dompet Asal</label>
                <select
                  value={fromWalletId}
                  onChange={(e) => setFromWalletId(e.target.value)}
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
                <label className="text-xs font-semibold text-slate-300 block mb-1">Ke Dompet Tujuan</label>
                <select
                  value={toWalletId}
                  onChange={(e) => setToWalletId(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-800 border border-slate-700 text-white text-sm focus:outline-none focus:border-emerald-500"
                >
                  {wallets.map((w) => (
                    <option key={w.id} value={w.id} disabled={w.id === fromWalletId}>
                      {w.name} ({formatCurrency(w.balance, w.currency)})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">Nominal Transfer (Rp)</label>
                <input
                  type="number"
                  placeholder="Contoh: 100000"
                  value={transferAmount}
                  onChange={(e) => setTransferAmount(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-800 border border-slate-700 text-white text-sm focus:outline-none focus:border-emerald-500"
                  required
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">Catatan (Opsional)</label>
                <input
                  type="text"
                  placeholder="Contoh: Topup GoPay dari BCA"
                  value={transferDesc}
                  onChange={(e) => setTransferDesc(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-800 border border-slate-700 text-white text-sm focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div className="flex items-center justify-end gap-3 mt-6 pt-4 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowTransferModal(false)}
                  className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:text-white"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl text-xs font-bold bg-emerald-500 hover:bg-emerald-600 text-slate-950 shadow-sm"
                >
                  Eksekusi Transfer
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

