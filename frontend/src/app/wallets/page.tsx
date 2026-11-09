"use client";

import { useEffect, useState } from "react";
import {
  Plus,
  ArrowLeftRight,
  Trash2,
  Wallet as WalletIcon,
  Edit2,
  Users,
  UserPlus,
  LogOut,
  ShieldCheck,
  Eye,
  Check,
  Share2,
  TrendingUp,
  RotateCcw,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
  Lock,
} from "lucide-react";
import {
  getWallets,
  createWallet,
  updateWallet,
  transferFunds,
  deleteWallet,
  addWalletMember,
  updateWalletMemberRole,
  removeWalletMember,
  resetAccountData,
} from "@/lib/api";
import { Wallet, WalletMember, PortfolioReview } from "@/lib/types";
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

const ASSET_CLASS_OPTIONS = [
  { value: "", label: "Otomatis Deteksi dari Nama/Tipe (Atau Bukan Investasi)" },
  { value: "EQUITY", label: "Saham & Ekuitas (Reksa Dana Saham / RDN / ETF)" },
  { value: "BOND", label: "Obligasi / SBN / Sukuk Negara" },
  { value: "MONEY_MARKET", label: "Pasar Uang & Deposito" },
  { value: "GOLD", label: "Emas & Logam Mulia" },
  { value: "CRYPTO", label: "Crypto & Aset Alternatif" },
];

export default function WalletsPage() {
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [totalBalance, setTotalBalance] = useState<number>(0);
  const [personalBalance, setPersonalBalance] = useState<number>(0);
  const [sharedBalance, setSharedBalance] = useState<number>(0);
  const [portfolioReview, setPortfolioReview] = useState<PortfolioReview | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [filterTab, setFilterTab] = useState<"ALL" | "PERSONAL" | "SHARED" | "INVESTMENT">("ALL");

  // Modals state
  const [showAddModal, setShowAddModal] = useState<boolean>(false);
  const [editingWallet, setEditingWallet] = useState<Wallet | null>(null);
  const [showTransferModal, setShowTransferModal] = useState<boolean>(false);
  const [managingMembersWallet, setManagingMembersWallet] = useState<Wallet | null>(null);

  // Reset Modal state
  const [showResetModal, setShowResetModal] = useState<boolean>(false);
  const [resetTargetWalletId, setResetTargetWalletId] = useState<string>("ALL");
  const [resetClearTx, setResetClearTx] = useState<boolean>(false);
  const [resetPassword, setResetPassword] = useState<string>("");
  const [resetLoading, setResetLoading] = useState<boolean>(false);
  const [resetError, setResetError] = useState<string>("");
  const [resetSuccessMsg, setResetSuccessMsg] = useState<string>("");

  // Form states
  const [name, setName] = useState("");
  const [type, setType] = useState("BANK");
  const [assetClass, setAssetClass] = useState("");
  const [balance, setBalance] = useState("0");
  const [currency, setCurrency] = useState("IDR");
  const [color, setColor] = useState("#f0b000");
  const [isDefault, setIsDefault] = useState(false);

  // Transfer form
  const [fromWalletId, setFromWalletId] = useState("");
  const [toWalletId, setToWalletId] = useState("");
  const [transferAmount, setTransferAmount] = useState("");
  const [transferDesc, setTransferDesc] = useState("");

  // Member invite form
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"EDITOR" | "VIEWER">("EDITOR");
  const [inviteLoading, setInviteLoading] = useState(false);
  const [inviteError, setInviteError] = useState("");
  const [inviteSuccess, setInviteSuccess] = useState("");

  const refreshWallets = async () => {
    setLoading(true);
    try {
      const res = await getWallets();
      setWallets(res.wallets);
      setTotalBalance(res.total_balance);
      setPersonalBalance(res.personal_balance ?? res.total_balance);
      setSharedBalance(res.shared_balance ?? 0);
      if (res.portfolio_review) {
        setPortfolioReview(res.portfolio_review);
      }

      const editorWallets = res.wallets.filter((w) => w.access_role !== "VIEWER");
      if (editorWallets.length >= 2) {
        setFromWalletId((prev) => (prev ? prev : editorWallets[0].id));
        setToWalletId((prev) => (prev ? prev : editorWallets[1].id));
      } else if (editorWallets.length === 1) {
        setFromWalletId(editorWallets[0].id);
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
    setAssetClass("");
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
    setAssetClass(w.asset_class || "");
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
        asset_class: assetClass || null,
        balance: parseFloat(balance) || 0,
        color,
        is_default: isDefault,
      });
    } else {
      await createWallet({
        name: name.trim(),
        type: type.trim().toUpperCase(),
        asset_class: assetClass || null,
        balance: parseFloat(balance) || 0,
        currency,
        color,
        is_default: isDefault,
      });
    }

    setShowAddModal(false);
    refreshWallets();
  };

  const handleOpenReset = (walletId: string = "ALL") => {
    setResetTargetWalletId(walletId);
    setResetClearTx(false);
    setResetPassword("");
    setResetError("");
    setResetSuccessMsg("");
    setShowResetModal(true);
  };

  const handleExecuteReset = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resetPassword) {
      setResetError("Silakan masukkan kata sandi akun Anda.");
      return;
    }
    setResetLoading(true);
    setResetError("");
    setResetSuccessMsg("");
    try {
      const res = await resetAccountData({
        password: resetPassword,
        mode: "ZERO_WALLETS",
        wallet_ids: resetTargetWalletId === "ALL" ? undefined : [resetTargetWalletId],
        clear_transactions: resetClearTx,
      });
      setResetSuccessMsg(res.message);
      setResetPassword("");
      await refreshWallets();
    } catch (err: any) {
      setResetError(err.message || "Gagal mereset saldo dompet.");
    } finally {
      setResetLoading(false);
    }
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

  const handleOpenManageMembers = (w: Wallet) => {
    setManagingMembersWallet(w);
    setInviteEmail("");
    setInviteRole("EDITOR");
    setInviteError("");
    setInviteSuccess("");
  };

  const handleInviteMember = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!managingMembersWallet || !inviteEmail.trim()) return;
    setInviteLoading(true);
    setInviteError("");
    setInviteSuccess("");
    try {
      const res = await addWalletMember(managingMembersWallet.id, {
        email: inviteEmail.trim(),
        role: inviteRole,
      });
      setInviteSuccess(res.message);
      setInviteEmail("");
      await refreshWallets();
      // Update local wallet in modal
      const updated = await getWallets();
      const updatedW = updated.wallets.find((w) => w.id === managingMembersWallet.id);
      if (updatedW) setManagingMembersWallet(updatedW);
    } catch (err: any) {
      setInviteError(err.message || "Gagal mengundang anggota");
    } finally {
      setInviteLoading(false);
    }
  };

  const handleUpdateRole = async (memberUserId: string, newRole: "EDITOR" | "VIEWER") => {
    if (!managingMembersWallet) return;
    try {
      await updateWalletMemberRole(managingMembersWallet.id, memberUserId, newRole);
      const updated = await getWallets();
      const updatedW = updated.wallets.find((w) => w.id === managingMembersWallet.id);
      if (updatedW) setManagingMembersWallet(updatedW);
      await refreshWallets();
    } catch (err: any) {
      alert(err.message || "Gagal mengubah role anggota");
    }
  };

  const handleRemoveMember = async (memberUserId: string) => {
    if (!managingMembersWallet) return;
    if (!confirm("Hapus akses anggota ini dari dompet bersama?")) return;
    try {
      await removeWalletMember(managingMembersWallet.id, memberUserId);
      const updated = await getWallets();
      const updatedW = updated.wallets.find((w) => w.id === managingMembersWallet.id);
      if (updatedW) setManagingMembersWallet(updatedW);
      await refreshWallets();
    } catch (err: any) {
      alert(err.message || "Gagal menghapus anggota");
    }
  };

  const handleLeaveWallet = async (walletId: string, memberUserId: string) => {
    if (!confirm("Apakah Anda yakin ingin keluar dari dompet bersama ini?")) return;
    try {
      await removeWalletMember(walletId, memberUserId);
      await refreshWallets();
    } catch (err: any) {
      alert(err.message || "Gagal keluar dari dompet bersama");
    }
  };

  const displayedWallets = wallets.filter((w) => {
    if (filterTab === "PERSONAL") return !w.is_shared;
    if (filterTab === "SHARED") return w.is_shared;
    if (filterTab === "INVESTMENT") return Boolean(w.is_investment);
    return true;
  });

  const investmentCount = wallets.filter((w) => w.is_investment).length;

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Dompet &amp; Akun Finansial</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Kelola saldo riil (Gajian, Kas, Investasi, Dompet Bersama) lengkap dengan evaluasi portofolio &amp; kontrol saldo.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <button
            onClick={() => handleOpenReset("ALL")}
            className="flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold bg-card border border-rose-500/30 hover:bg-rose-500/10 text-rose-600 dark:text-rose-400 transition-colors shadow-sm"
            title="Nolkan Saldo Dompet (Wajib Password)"
          >
            <RotateCcw className="w-4 h-4" />
            <span>Reset Saldo</span>
          </button>
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

      {/* Balance Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Balance Card */}
        <div className="p-5 rounded-3xl bg-card border border-border shadow-sm flex flex-col justify-between">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Total Saldo Seluruh Dompet
          </span>
          <div className="text-2xl font-extrabold text-foreground mt-2">
            {formatCurrency(totalBalance, "IDR")}
          </div>
          <div className="text-xs text-muted-foreground mt-2 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[#f0b000]" />
            <span>{wallets.length} dompet aktif</span>
          </div>
        </div>

        {/* Personal Balance Card */}
        <div className="p-5 rounded-3xl bg-card border border-border shadow-sm flex flex-col justify-between">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Saldo Dompet Pribadi
          </span>
          <div className="text-2xl font-bold text-foreground mt-2">
            {formatCurrency(personalBalance, "IDR")}
          </div>
          <div className="text-xs text-muted-foreground mt-2">
            {wallets.filter((w) => !w.is_shared).length} dompet milik pribadi
          </div>
        </div>

        {/* Shared Balance Card */}
        <div className="p-5 rounded-3xl bg-card border border-border shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Saldo Dompet Bersama
            </span>
            <Users className="w-4 h-4 text-primary" />
          </div>
          <div className="text-2xl font-bold text-[#8a6300] dark:text-[#f0b000] mt-2">
            {formatCurrency(sharedBalance, "IDR")}
          </div>
          <div className="text-xs text-muted-foreground mt-2">
            {wallets.filter((w) => w.is_shared).length} dompet bersama terhubung
          </div>
        </div>

        {/* Investment Portfolio Card */}
        <div className="p-5 rounded-3xl bg-card border border-border shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Portofolio Investasi
            </span>
            <TrendingUp className="w-4 h-4 text-violet-600 dark:text-violet-400" />
          </div>
          <div className="text-2xl font-bold text-violet-600 dark:text-violet-400 mt-2">
            {formatCurrency(portfolioReview?.total_investment_balance || 0, "IDR")}
          </div>
          <div className="text-xs text-muted-foreground mt-2 flex items-center justify-between">
            <span>{investmentCount} dompet investasi</span>
            {portfolioReview && portfolioReview.has_investment_wallets && (
              <span className="font-bold text-foreground">Skor {portfolioReview.alignment_score}/100</span>
            )}
          </div>
        </div>
      </div>

      {/* Investment Portfolio Review & Best Practice Comparison Panel */}
      {portfolioReview && (portfolioReview.has_investment_wallets || filterTab === "INVESTMENT") && (
        <div className="p-6 rounded-3xl bg-card border border-border shadow-sm space-y-6">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-border pb-4">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-2xl bg-violet-500/10 border border-violet-500/30 text-violet-600 dark:text-violet-400 flex items-center justify-center shrink-0 mt-0.5">
                <TrendingUp className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <h2 className="text-base font-bold text-foreground">
                    Review Portofolio Investasi vs Referensi Best Practice
                  </h2>
                  <span
                    className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold border ${
                      portfolioReview.status === "OPTIMAL"
                        ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
                        : portfolioReview.status === "PERLU_REBALANCING"
                        ? "bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400"
                        : "bg-rose-500/10 border-rose-500/30 text-rose-600 dark:text-rose-400"
                    }`}
                  >
                    {portfolioReview.status_label} ({portfolioReview.alignment_score}/100)
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  Referensi Acuan: <strong className="text-foreground">{portfolioReview.reference_profile_name}</strong>{" "}
                  &bull; Estimasi CAGR <strong className="text-[#8a6300] dark:text-[#f0b000]">{portfolioReview.expected_cagr}</strong>{" "}
                  &bull; Porsi Investasi: <strong className="text-foreground">{portfolioReview.invested_ratio_pct}%</strong> dari Kekayaan Bersih
                </p>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left 2 Columns: Asset Class Comparison Bars */}
            <div className="lg:col-span-2 space-y-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                Perbandingan Komposisi Kelas Aset (Aktual vs Target Ideal)
              </h3>
              <div className="space-y-3.5">
                {portfolioReview.allocations_comparison.map((comp) => (
                  <div key={comp.asset_class} className="p-3.5 rounded-2xl bg-secondary/50 border border-border space-y-2">
                    <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                      <div className="flex items-center gap-2">
                        <span
                          className="w-3 h-3 rounded-full shrink-0"
                          style={{ backgroundColor: comp.color }}
                        />
                        <span className="font-bold text-foreground">{comp.asset_class_label}</span>
                        <span className="text-[11px] text-muted-foreground">({comp.reference_name})</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-foreground">
                          {formatCurrency(comp.actual_amount, "IDR")}
                        </span>
                        <span
                          className={`px-2 py-0.5 rounded-md text-[10px] font-bold ${
                            comp.action === "IDEAL"
                              ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                              : comp.action === "UNDERWEIGHT"
                              ? "bg-sky-500/10 text-sky-600 dark:text-sky-400"
                              : "bg-amber-500/10 text-amber-600 dark:text-amber-400"
                          }`}
                        >
                          {comp.action === "IDEAL"
                            ? "Ideal"
                            : comp.action === "UNDERWEIGHT"
                            ? `+ Tambah ${formatCurrency(comp.delta_amount)}`
                            : `- Kurangi ${formatCurrency(Math.abs(comp.delta_amount))}`}
                        </span>
                      </div>
                    </div>

                    {/* Dual Progress Bar: Actual vs Target */}
                    <div className="space-y-1">
                      <div className="flex justify-between text-[11px] text-muted-foreground">
                        <span>
                          Aktual Anda: <strong className="text-foreground">{comp.actual_pct}%</strong>
                        </span>
                        <span>
                          Target Referensi: <strong className="text-foreground">{comp.target_pct}%</strong> ({formatCurrency(comp.ideal_amount)})
                        </span>
                      </div>
                      <div className="relative w-full bg-card h-2.5 rounded-full overflow-hidden border border-border">
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{
                            width: `${Math.min(100, comp.actual_pct)}%`,
                            backgroundColor: comp.color,
                          }}
                        />
                        {comp.target_pct > 0 && (
                          <div
                            className="absolute top-0 bottom-0 w-0.5 bg-foreground"
                            style={{ left: `${Math.min(99, comp.target_pct)}%` }}
                            title={`Target Ideal: ${comp.target_pct}%`}
                          />
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Right Column: Financial Best Practice Checklist & Recommendations */}
            <div className="space-y-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                Audit Best Practice Finansial
              </h3>
              <div className="space-y-2.5">
                {portfolioReview.best_practices.map((bp) => (
                  <div
                    key={bp.key}
                    className={`p-3 rounded-2xl border text-xs space-y-1 ${
                      bp.passed
                        ? "bg-emerald-500/5 border-emerald-500/20"
                        : "bg-amber-500/5 border-amber-500/20"
                    }`}
                  >
                    <div className="flex items-center gap-2 font-bold text-foreground">
                      {bp.passed ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
                      ) : (
                        <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
                      )}
                      <span>{bp.title}</span>
                    </div>
                    <p className="text-[11px] text-muted-foreground leading-relaxed pl-6">{bp.detail}</p>
                  </div>
                ))}
              </div>

              {portfolioReview.recommendations.length > 0 && (
                <div className="p-3.5 rounded-2xl bg-accent/60 border border-[#f0b000]/30 space-y-2">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-[#8a6300] dark:text-[#f0b000]">
                    <Sparkles className="w-3.5 h-3.5" />
                    <span>Rekomendasi Rebalancing</span>
                  </div>
                  <ul className="space-y-1.5 text-[11px] text-foreground list-disc pl-4">
                    {portfolioReview.recommendations.map((rec, i) => (
                      <li key={i}>{rec}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Filter Tabs */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border pb-3">
        <button
          onClick={() => setFilterTab("ALL")}
          className={`px-4 py-1.5 rounded-xl text-xs font-bold transition-all ${
            filterTab === "ALL"
              ? "bg-primary text-primary-foreground shadow-sm"
              : "bg-secondary text-muted-foreground hover:text-foreground"
          }`}
        >
          Semua Dompet ({wallets.length})
        </button>
        <button
          onClick={() => setFilterTab("PERSONAL")}
          className={`px-4 py-1.5 rounded-xl text-xs font-bold transition-all ${
            filterTab === "PERSONAL"
              ? "bg-primary text-primary-foreground shadow-sm"
              : "bg-secondary text-muted-foreground hover:text-foreground"
          }`}
        >
          Dompet Pribadi ({wallets.filter((w) => !w.is_shared).length})
        </button>
        <button
          onClick={() => setFilterTab("SHARED")}
          className={`px-4 py-1.5 rounded-xl text-xs font-bold transition-all ${
            filterTab === "SHARED"
              ? "bg-primary text-primary-foreground shadow-sm"
              : "bg-secondary text-muted-foreground hover:text-foreground"
          }`}
        >
          Dompet Bersama ({wallets.filter((w) => w.is_shared).length})
        </button>
        <button
          onClick={() => setFilterTab("INVESTMENT")}
          className={`px-4 py-1.5 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 ${
            filterTab === "INVESTMENT"
              ? "bg-violet-600 text-white shadow-sm"
              : "bg-secondary text-muted-foreground hover:text-foreground"
          }`}
        >
          <TrendingUp className="w-3.5 h-3.5" />
          <span>Dompet Investasi ({investmentCount})</span>
        </button>
      </div>

      {/* Wallets Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {displayedWallets.map((w) => {
          const hasCommitment = (w.allocated_budget || 0) > 0;
          const isShortfall = (w.shortfall_amount || 0) > 0;
          const isOwner = w.access_role === "OWNER" || !w.is_shared;

          return (
            <div
              key={w.id}
              className="p-6 rounded-3xl bg-card border border-border shadow-sm flex flex-col justify-between min-h-[16rem] group hover:border-[#f0b000]/40 transition-all relative overflow-hidden"
            >
              <div>
                {/* Header: Icon, Name & Badges */}
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div
                      className="w-11 h-11 rounded-2xl flex items-center justify-center font-bold text-primary-foreground shadow-sm shrink-0"
                      style={{ backgroundColor: w.color || "#f0b000" }}
                    >
                      <WalletIcon className="w-5 h-5" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="font-bold text-foreground text-base">{w.name}</h3>
                        {w.is_default && (
                          <span className="px-2 py-0.5 rounded-md bg-[#f0b000]/20 border border-[#f0b000]/40 text-[#8a6300] dark:text-[#f0b000] text-[10px] font-bold">
                            ⭐ Rekening Gajian
                          </span>
                        )}
                        {w.is_investment && (
                          <span className="px-2 py-0.5 rounded-md bg-violet-500/10 border border-violet-500/30 text-violet-600 dark:text-violet-400 text-[10px] font-bold flex items-center gap-1">
                            <TrendingUp className="w-3 h-3" />
                            {w.asset_class_label || "Investasi"}
                          </span>
                        )}
                        {w.is_shared && (
                          <span className="px-2 py-0.5 rounded-md bg-indigo-500/10 border border-indigo-500/30 text-indigo-600 dark:text-indigo-400 text-[10px] font-bold flex items-center gap-1">
                            <Users className="w-3 h-3" />
                            {w.access_role === "OWNER" ? "Pemilik" : w.access_role}
                          </span>
                        )}
                      </div>
                      <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mt-0.5">
                        {w.type} &bull; {w.currency}
                        {!isOwner && w.owner && ` &bull; Milik: ${w.owner.name}`}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-1">
                    {isOwner && (
                      <button
                        onClick={() => handleOpenReset(w.id)}
                        className="text-muted-foreground hover:text-amber-500 transition-colors p-1"
                        title="Reset Saldo Dompet Ini ke Rp 0"
                      >
                        <RotateCcw className="w-3.5 h-3.5" />
                      </button>
                    )}
                    {/* Share / Member button */}
                    {isOwner ? (
                      <button
                        onClick={() => handleOpenManageMembers(w)}
                        className="text-muted-foreground hover:text-primary transition-colors p-1"
                        title="Bagikan / Kelola Anggota"
                      >
                        <Share2 className="w-4 h-4" />
                      </button>
                    ) : (
                      <button
                        onClick={() => handleLeaveWallet(w.id, w.owner?.id || "")}
                        className="text-muted-foreground hover:text-rose-500 transition-colors p-1"
                        title="Keluar dari Dompet Bersama"
                      >
                        <LogOut className="w-4 h-4" />
                      </button>
                    )}

                    {isOwner && (
                      <>
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
                      </>
                    )}
                  </div>
                </div>

                {/* Balance & Budget Commitment */}
                <div className="mt-4 space-y-1">
                  <span className="text-xs text-muted-foreground">Saldo Aktual</span>
                  <div className="text-2xl font-extrabold text-foreground tracking-tight">
                    {formatCurrency(w.balance, w.currency)}
                  </div>

                  {hasCommitment && (
                    <div className="space-y-1 pt-1.5 border-t border-border/50 text-[11px] text-muted-foreground">
                      <div className="flex justify-between items-center">
                        <span>Komitmen Pos Anggaran:</span>
                        <strong className="text-foreground">{formatCurrency(w.remaining_commitment || 0)}</strong>
                      </div>
                      <div className="flex justify-between items-center">
                        <span>Saldo Bebas (Unallocated):</span>
                        <strong className="text-emerald-600 dark:text-emerald-400 font-bold">
                          {formatCurrency(w.free_balance || 0)}
                        </strong>
                      </div>
                      <div className="flex justify-between items-center pt-0.5">
                        <span>Status Pendanaan:</span>
                        <span
                          className={
                            isShortfall
                              ? "text-rose-600 dark:text-rose-400 font-bold"
                              : "text-emerald-600 dark:text-emerald-400 font-bold"
                          }
                        >
                          {isShortfall ? `Kurang ${formatCurrency(w.shortfall_amount || 0)}` : "Terdanai Penuh"}
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Card Footer: Members summary & metadata */}
              <div className="pt-3 border-t border-border text-[11px] text-muted-foreground flex items-center justify-between mt-3">
                {w.is_shared && w.members && w.members.length > 0 ? (
                  <div className="flex items-center gap-1.5">
                    <Users className="w-3.5 h-3.5 text-primary" />
                    <span>{w.members.length} anggota diundang</span>
                  </div>
                ) : (
                  <span>{w.assigned_items_count ? `${w.assigned_items_count} pos alokasi` : "Akun Aktif"}</span>
                )}
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
                  placeholder="Contoh: Mandiri, Jago, Tabungan Keluarga..."
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

              {/* Asset Class Selector for Investment Wallets */}
              <div>
                <label className="font-semibold text-foreground block mb-1">
                  Kelas Aset Portofolio Investasi (Opsional / Untuk Review Portofolio)
                </label>
                <select
                  value={assetClass}
                  onChange={(e) => setAssetClass(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground font-medium"
                >
                  {ASSET_CLASS_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
                <p className="text-[10px] text-muted-foreground mt-1">
                  Pilih kelas aset jika dompet ini merupakan instrumen investasi agar dibandingkan dengan referensi portofolio ideal Anda.
                </p>
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
                  Jadikan Rekening Gajian Utama (default saat transaksi tanpa menyebut bank).
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
                  {wallets
                    .filter((w) => w.access_role !== "VIEWER")
                    .map((w) => (
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
                  {wallets
                    .filter((w) => w.access_role !== "VIEWER")
                    .map((w) => (
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

      {/* Manage Members (Sharing) Modal */}
      {managingMembersWallet && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-5 text-xs">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-bold text-foreground flex items-center gap-2">
                  <Users className="w-5 h-5 text-primary" />
                  <span>Sharing &amp; Anggota: {managingMembersWallet.name}</span>
                </h2>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  Undang pengguna lain menggunakan email terdaftar untuk mengelola atau memonitor saldo dompet ini.
                </p>
              </div>
            </div>

            {/* Invite Form */}
            <form onSubmit={handleInviteMember} className="p-4 rounded-2xl bg-secondary/60 border border-border space-y-3">
              <h3 className="font-bold text-foreground flex items-center gap-1.5">
                <UserPlus className="w-4 h-4 text-primary" />
                <span>Undang Pengguna Baru</span>
              </h3>

              {inviteError && (
                <div className="p-2.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-600 dark:text-rose-400 font-semibold text-[11px]">
                  {inviteError}
                </div>
              )}
              {inviteSuccess && (
                <div className="p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-600 dark:text-emerald-400 font-semibold text-[11px] flex items-center gap-1.5">
                  <Check className="w-3.5 h-3.5" />
                  {inviteSuccess}
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                <div className="sm:col-span-2">
                  <label className="font-semibold text-foreground block mb-1">Email Terdaftar</label>
                  <input
                    type="email"
                    placeholder="email.pasangan@gmail.com"
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-card border border-border text-foreground font-medium"
                    required
                  />
                </div>
                <div>
                  <label className="font-semibold text-foreground block mb-1">Role / Hak Akses</label>
                  <select
                    value={inviteRole}
                    onChange={(e) => setInviteRole(e.target.value as "EDITOR" | "VIEWER")}
                    className="w-full px-3 py-2 rounded-xl bg-card border border-border text-foreground font-semibold"
                  >
                    <option value="EDITOR">Editor (Catat &amp; Belanja)</option>
                    <option value="VIEWER">Viewer (Hanya Lihat)</option>
                  </select>
                </div>
              </div>

              <div className="flex justify-end pt-1">
                <button
                  type="submit"
                  disabled={inviteLoading}
                  className="px-4 py-2 rounded-xl bg-primary text-primary-foreground font-bold shadow-sm shadow-[#f0b000]/20 hover:bg-primary/90 transition-colors disabled:opacity-50"
                >
                  {inviteLoading ? "Mengundang..." : "+ Tambahkan Anggota"}
                </button>
              </div>
            </form>

            {/* Current Members List */}
            <div className="space-y-2">
              <h3 className="font-bold text-foreground">Daftar Anggota Dompet Bersama</h3>
              {(!managingMembersWallet.members || managingMembersWallet.members.length === 0) ? (
                <div className="p-4 rounded-xl border border-dashed border-border text-center text-muted-foreground text-[11px]">
                  Belum ada anggota yang diundang. Masukkan email di atas untuk membagikan dompet ini.
                </div>
              ) : (
                <div className="divide-y divide-border rounded-xl border border-border overflow-hidden">
                  {managingMembersWallet.members.map((m) => (
                    <div key={m.user_id} className="p-3 bg-card flex items-center justify-between gap-3">
                      <div>
                        <div className="font-bold text-foreground">{m.name}</div>
                        <div className="text-[11px] text-muted-foreground">{m.email}</div>
                      </div>

                      <div className="flex items-center gap-2">
                        <select
                          value={m.role}
                          onChange={(e) => handleUpdateRole(m.user_id, e.target.value as "EDITOR" | "VIEWER")}
                          className="px-2.5 py-1 rounded-lg bg-secondary border border-border text-[11px] font-semibold text-foreground"
                        >
                          <option value="EDITOR">Editor</option>
                          <option value="VIEWER">Viewer</option>
                        </select>
                        <button
                          type="button"
                          onClick={() => handleRemoveMember(m.user_id)}
                          className="p-1.5 rounded-lg text-muted-foreground hover:text-rose-500 hover:bg-rose-500/10 transition-colors"
                          title="Hapus Anggota"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="flex justify-end pt-2 border-t border-border">
              <button
                type="button"
                onClick={() => setManagingMembersWallet(null)}
                className="px-4 py-2 rounded-xl text-muted-foreground hover:text-foreground font-medium"
              >
                Tutup
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Password-Protected Reset Wallet Balance Modal */}
      {showResetModal && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4 text-xs">
            <div className="flex items-center gap-2.5 text-rose-600 dark:text-rose-400">
              <div className="w-9 h-9 rounded-xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-center shrink-0">
                <RotateCcw className="w-4 h-4" />
              </div>
              <div>
                <h2 className="text-base font-bold text-foreground">Reset Saldo Dompet ke Rp 0</h2>
                <p className="text-[11px] text-muted-foreground">
                  Sistem akan otomatis menyimpan Snapshot Backup sebelum saldo di-reset.
                </p>
              </div>
            </div>

            {resetError && (
              <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-600 dark:text-rose-400 font-semibold">
                {resetError}
              </div>
            )}

            {resetSuccessMsg ? (
              <div className="space-y-4">
                <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-600 dark:text-emerald-400 font-semibold flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
                  <span>{resetSuccessMsg}</span>
                </div>
                <div className="flex justify-end">
                  <button
                    type="button"
                    onClick={() => setShowResetModal(false)}
                    className="px-4 py-2 rounded-xl bg-primary text-primary-foreground font-bold"
                  >
                    Selesai
                  </button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleExecuteReset} className="space-y-4">
                <div>
                  <label className="font-semibold text-foreground block mb-1">Pilih Dompet yang Akan Di-reset</label>
                  <select
                    value={resetTargetWalletId}
                    onChange={(e) => setResetTargetWalletId(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground font-semibold"
                  >
                    <option value="ALL">Semua Dompet Milik Saya ({wallets.filter((w) => !w.is_shared || w.access_role === "OWNER").length} dompet)</option>
                    {wallets
                      .filter((w) => !w.is_shared || w.access_role === "OWNER")
                      .map((w) => (
                        <option key={w.id} value={w.id}>
                          {w.name} ({formatCurrency(w.balance, w.currency)})
                        </option>
                      ))}
                  </select>
                </div>

                <div className="flex items-start gap-2 pt-1">
                  <input
                    type="checkbox"
                    id="clearTxCheck"
                    checked={resetClearTx}
                    onChange={(e) => setResetClearTx(e.target.checked)}
                    className="accent-rose-500 w-4 h-4 rounded cursor-pointer mt-0.5"
                  />
                  <label htmlFor="clearTxCheck" className="text-foreground cursor-pointer leading-relaxed">
                    Hapus juga seluruh riwayat transaksi &amp; realisasi anggaran pada dompet tersebut.
                  </label>
                </div>

                <div>
                  <label className="font-semibold text-foreground flex items-center gap-1.5 mb-1">
                    <Lock className="w-3.5 h-3.5 text-rose-500" />
                    <span>Konfirmasi Kata Sandi Akun Anda (Wajib)</span>
                  </label>
                  <input
                    type="password"
                    placeholder="Masukkan password login Anda..."
                    value={resetPassword}
                    onChange={(e) => setResetPassword(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground font-medium"
                    required
                  />
                </div>

                <div className="flex items-center justify-end gap-3 pt-3 border-t border-border">
                  <button
                    type="button"
                    onClick={() => setShowResetModal(false)}
                    className="px-4 py-2 rounded-xl text-muted-foreground hover:text-foreground"
                  >
                    Batal
                  </button>
                  <button
                    type="submit"
                    disabled={resetLoading}
                    className="px-5 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white font-bold shadow-sm disabled:opacity-50"
                  >
                    {resetLoading ? "Memproses Reset..." : "Konfirmasi Reset ke Rp 0"}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
