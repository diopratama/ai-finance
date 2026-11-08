"use client";

import { useEffect, useState } from "react";
import {
  Plus,
  ArrowLeftRight,
  Trash2,
  Wallet as WalletIcon,
  Edit2,
  ShieldAlert,
  Sparkles,
  Check,
} from "lucide-react";
import { getWallets, createWallet, updateWallet, transferFunds, deleteWallet } from "@/lib/api";
import { Wallet } from "@/lib/types";
import { formatCurrency, formatDate } from "@/lib/utils";

const TYPE_PRESETS = [
  "BANK",
  "KANTONG DIGITAL",
  "BANK SYARIAH",
  "EWALLET",
  "CASH",
  "INVESTMENT",
  "RDN",
  "CREDIT",
];

export default function WalletsPage() {
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [totalBalance, setTotalBalance] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);

  // Modals state
  const [showAddModal, setShowAddModal] = useState<boolean>(false);
  const [editingWallet, setEditingWallet] = useState<Wallet | null>(null);
  const [showTransferModal, setShowTransferModal] = useState<boolean>(false);

  // Form states
  const [name, setName] = useState("");
  const [type, setType] = useState("BANK");
  const [balance, setBalance] = useState("0");
  const [currency, setCurrency] = useState("IDR");
  const [color, setColor] = useState("#f0b000");
  const [isDefault, setIsDefault] = useState(false);

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

  const handleOpenAdd = () => {
    setEditingWallet(null);
    setName("");
    setType("BANK");
    setBalance("0");
    setCurrency("IDR");
    setColor("#f0b000");
    setIsDefault(false);
    setShowAddModal(true);
  };

  const handleOpenEdit = (w: Wallet) => {
    setEditingWallet(w);
    setName(w.name);
    setType(w.type);
    setBalance(w.balance.toString());
    setColor(w.color || "#f0b000");
    setIsDefault(w.is_default);
    setShowAddModal(true);
  };

  const handleSaveWallet = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    if (editingWallet) {
      await updateWallet(editingWallet.id, {
        name: name.trim(),
        type: type.trim().toUpperCase(),
        balance: parseFloat(balance) || 0,
        color,
        is_default: isDefault,
      });
    } else {
      await createWallet({
        name: name.trim(),
        type: type.trim().toUpperCase(),
        balance: parseFloat(balance) || 0,
        currency,
        color,
        is_default: isDefault,
      });
    }

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
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Dompet &amp; Akun Finansial</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Kelola saldo riil (Mandiri, Jago, Danamon, Cash, RDN, Tabungan Emas) dengan kustomisasi nama dan tipe bebas tanpa batas.
          </p>
        </div>
        <div className="flex items-center gap-2.5">
          <button
            onClick={() => setShowTransferModal(true)}
            className="flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold bg-card border border-border hover:bg-accent text-foreground transition-colors shadow-sm"
          >
            <ArrowLeftRight className="w-4 h-4 text-[#8a6300] dark:text-[#f0b000]" />
            <span>Transfer Antar-Dompet</span>
          </button>
          <button
            onClick={handleOpenAdd}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold bg-primary hover:bg-primary/90 text-primary-foreground transition-colors shadow-md shadow-[#f0b000]/20"
          >
            <Plus className="w-4 h-4" />
            <span>+ Tambah Dompet</span>
          </button>
        </div>
      </div>

      {/* Total Balance Card */}
      <div className="p-6 rounded-3xl bg-card border border-border shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Total Saldo Seluruh Dompet
          </span>
          <div className="text-3xl font-extrabold text-foreground mt-1">
            {formatCurrency(totalBalance, "IDR")}
          </div>
          <div className="text-xs text-muted-foreground mt-1 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[#f0b000]" />
            <span>{wallets.length} dompet aktif terhubung ke sistem anggaran bulanan</span>
          </div>
        </div>
        <div className="p-3.5 rounded-2xl bg-secondary/70 border border-border text-xs text-muted-foreground max-w-sm leading-relaxed">
          💡 <strong>Fund Location:</strong> Setiap dompet dapat dihubungkan ke pos anggaran di menu Alokasi Anggaran, dan Chatbot WA/Telegram otomatis mendeteksi dompet tujuan saat Anda mencatat transaksi!
        </div>
      </div>

      {/* Wallets Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {wallets.map((w) => {
          const hasCommitment = (w.allocated_budget || 0) > 0;
          const isShortfall = (w.shortfall_amount || 0) > 0;

          return (
            <div
              key={w.id}
              className="p-6 rounded-3xl bg-card border border-border shadow-sm flex flex-col justify-between h-56 group hover:border-[#f0b000]/40 transition-all relative overflow-hidden"
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div
                    className="w-11 h-11 rounded-2xl flex items-center justify-center font-bold text-primary-foreground shadow-sm shrink-0"
                    style={{ backgroundColor: w.color || "#f0b000" }}
                  >
                    <WalletIcon className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="font-bold text-foreground text-base">{w.name}</h3>
                    <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                      {w.type} &bull; {w.currency}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-1">
                  <button
                    onClick={() => handleOpenEdit(w)}
                    className="text-muted-foreground hover:text-foreground transition-colors p-1"
                    title="Edit Dompet & Tipe"
                  >
                    <Edit2 className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleDelete(w.id)}
                    className="text-muted-foreground hover:text-rose-500 transition-colors p-1"
                    title="Arsipkan Dompet"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {/* Balance & Budget Commitment */}
              <div className="mt-2 space-y-1">
                <span className="text-xs text-muted-foreground">Saldo Aktual</span>
                <div className="text-2xl font-extrabold text-foreground tracking-tight">
                  {formatCurrency(w.balance, w.currency)}
                </div>

                {hasCommitment && (
                  <div className="flex justify-between items-center text-[11px] pt-1 text-muted-foreground">
                    <span>
                      Komitmen Anggaran: <strong className="text-foreground">{formatCurrency(w.remaining_commitment || 0)}</strong>
                    </span>
                    <span className={isShortfall ? "text-rose-600 dark:text-rose-400 font-bold" : "text-emerald-600 dark:text-emerald-400 font-bold"}>
                      {isShortfall ? `Kurang ${formatCurrency(w.shortfall_amount || 0)}` : "Aman / Funded"}
                    </span>
                  </div>
                )}
              </div>

              <div className="flex items-center justify-between pt-3 border-t border-border text-[11px] text-muted-foreground">
                <span>{w.is_default ? "⭐ Dompet Utama" : (w.assigned_items_count ? `${w.assigned_items_count} pos alokasi` : "Akun Aktif")}</span>
                <span>Dibuat: {formatDate(w.created_at)}</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Add / Edit Wallet Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <h2 className="text-lg font-bold text-foreground">
              {editingWallet ? "Edit Dompet & Tipe Akun" : "Tambah Dompet / Rekening Baru"}
            </h2>
            <form onSubmit={handleSaveWallet} className="space-y-4 text-xs">
              <div>
                <label className="font-semibold text-foreground block mb-1">Nama Dompet (Bebas Ketik)</label>
                <input
                  type="text"
                  placeholder="Contoh: Mandiri, Jago, Danamon, Kantong Umrah Jago..."
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground font-medium text-sm"
                  required
                />
              </div>

              {/* Custom Free-Text Wallet Type with Presets */}
              <div>
                <label className="font-semibold text-foreground block mb-1">
                  Tipe Akun (Bebas Ketik atau Pilih Preset)
                </label>
                <input
                  type="text"
                  placeholder="Contoh: BANK, KANTONG DIGITAL, BANK SYARIAH, RDN, TABUNGAN EMAS..."
                  value={type}
                  onChange={(e) => setType(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground uppercase font-semibold"
                  required
                />
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {TYPE_PRESETS.map((p) => (
                    <button
                      key={p}
                      type="button"
                      onClick={() => setType(p)}
                      className={`px-2 py-0.5 rounded-lg border text-[10px] font-semibold transition-colors ${
                        type.toUpperCase() === p
                          ? "bg-accent border-[#f0b000]/50 text-[#8a6300] dark:text-[#f0b000]"
                          : "bg-secondary border-border text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-foreground block mb-1">Saldo</label>
                  <input
                    type="number"
                    placeholder="0"
                    value={balance}
                    onChange={(e) => setBalance(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground font-mono"
                  />
                </div>
                <div>
                  <label className="font-semibold text-foreground block mb-1">Mata Uang</label>
                  <select
                    value={currency}
                    onChange={(e) => setCurrency(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground"
                  >
                    <option value="IDR">IDR (Rp)</option>
                    <option value="USD">USD ($)</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="font-semibold text-foreground block mb-1">Warna Label</label>
                <div className="flex items-center gap-2">
                  {["#f0b000", "#3b82f6", "#10b981", "#06b6d4", "#f97316", "#8b5cf6", "#ec4899"].map((c) => (
                    <button
                      key={c}
                      type="button"
                      onClick={() => setColor(c)}
                      className={`w-7 h-7 rounded-full transition-transform ${
                        color === c ? "ring-2 ring-foreground scale-110" : ""
                      }`}
                      style={{ backgroundColor: c }}
                    />
                  ))}
                </div>
              </div>

              <div className="flex items-center gap-2 pt-1">
                <input
                  type="checkbox"
                  id="walletDefault"
                  checked={isDefault}
                  onChange={(e) => setIsDefault(e.target.checked)}
                  className="accent-[#f0b000] w-4 h-4 rounded cursor-pointer"
                />
                <label htmlFor="walletDefault" className="text-foreground cursor-pointer">
                  Jadikan dompet utama (default saat transaksi tanpa menyebut bank).
                </label>
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
                  className="px-5 py-2 rounded-xl bg-primary text-primary-foreground font-bold shadow-sm shadow-[#f0b000]/20"
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
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4 text-xs">
            <h2 className="text-base font-bold text-foreground">Transfer Antar-Dompet</h2>
            <form onSubmit={handleTransfer} className="space-y-4">
              <div>
                <label className="font-semibold text-foreground block mb-1">Dari Dompet Asal</label>
                <select
                  value={fromWalletId}
                  onChange={(e) => setFromWalletId(e.target.value)}
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
                <label className="font-semibold text-foreground block mb-1">Ke Dompet Tujuan</label>
                <select
                  value={toWalletId}
                  onChange={(e) => setToWalletId(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground"
                >
                  {wallets.map((w) => (
                    <option key={w.id} value={w.id} disabled={w.id === fromWalletId}>
                      {w.name} ({formatCurrency(w.balance, w.currency)})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="font-semibold text-foreground block mb-1">Nominal Transfer (Rp)</label>
                <input
                  type="number"
                  placeholder="Contoh: 1000000"
                  value={transferAmount}
                  onChange={(e) => setTransferAmount(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground font-mono font-bold"
                  required
                />
              </div>

              <div>
                <label className="font-semibold text-foreground block mb-1">Catatan</label>
                <input
                  type="text"
                  placeholder="Contoh: Distribusi gajian / top up"
                  value={transferDesc}
                  onChange={(e) => setTransferDesc(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground"
                />
              </div>

              <div className="flex items-center justify-end gap-3 mt-6 pt-4 border-t border-border">
                <button
                  type="button"
                  onClick={() => setShowTransferModal(false)}
                  className="px-4 py-2 rounded-xl text-muted-foreground hover:text-foreground"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl bg-primary text-primary-foreground font-bold shadow-sm shadow-[#f0b000]/20"
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
