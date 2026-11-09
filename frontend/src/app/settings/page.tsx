"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  User as UserIcon,
  Mail,
  ShieldCheck,
  Lock,
  Save,
  KeyRound,
  Coins,
  Bot,
  ExternalLink,
  CheckCircle2,
  AlertCircle,
  Clock,
  SlidersHorizontal,
  MoonStar,
  Sparkles,
  HeartHandshake,
  TrendingUp,
  Database,
  Download,
  Upload,
  RotateCcw,
  Trash2,
  AlertTriangle,
} from "lucide-react";
import {
  AuthUser,
  getUserProfile,
  updateUserProfile,
  changePassword,
  getBotStatus,
  getPlannerOverview,
  updatePersonalProfile,
  listAccountBackups,
  createAccountBackup,
  exportAccountBackup,
  deleteAccountBackup,
  resetAccountData,
  restoreAccountData,
} from "@/lib/api";
import { BotStatusMap, PersonalProfile, AccountBackupItem } from "@/lib/types";
import { formatCurrency } from "@/lib/utils";

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<"account" | "financial" | "data">("account");

  // Account state
  const [profile, setProfile] = useState<(AuthUser & { created_at: string }) | null>(null);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [baseCurrency, setBaseCurrency] = useState("IDR");

  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const [botStatus, setBotStatus] = useState<BotStatusMap>({
    TELEGRAM: { connected: false, username: null },
    WHATSAPP: { connected: false, username: null },
  });

  const [profileLoading, setProfileLoading] = useState(false);
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [profileMsg, setProfileMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [passwordMsg, setPasswordMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Financial personalization state
  const [personalProfile, setPersonalProfile] = useState<PersonalProfile | null>(null);
  const [incomeInput, setIncomeInput] = useState<number>(0);
  const [expenseInput, setExpenseInput] = useState<number>(10000000);
  const [debtInput, setDebtInput] = useState<number>(0);
  const [maritalInput, setMaritalInput] = useState<"SINGLE" | "MARRIED">("SINGLE");
  const [dependentsInput, setDependentsInput] = useState<number>(0);
  const [ageInput, setAgeInput] = useState<number>(28);
  const [targetFireInput, setTargetFireInput] = useState<number>(50);
  const [riskInput, setRiskInput] = useState<"CONSERVATIVE" | "MODERATE" | "AGGRESSIVE">("MODERATE");
  const [shariaInput, setShariaInput] = useState<boolean>(false);
  const [finLoading, setFinLoading] = useState<boolean>(false);
  const [finMsg, setFinMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Backup, Restore & Reset state
  const [backups, setBackups] = useState<AccountBackupItem[]>([]);
  const [backupLabel, setBackupLabel] = useState<string>("");
  const [dataLoading, setDataLoading] = useState<boolean>(false);
  const [dataMsg, setDataMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Restore Modal / Section state
  const [restoreTargetId, setRestoreTargetId] = useState<string | null>(null);
  const [restorePassword, setRestorePassword] = useState<string>("");
  const [uploadedPayload, setUploadedPayload] = useState<Record<string, any> | null>(null);
  const [uploadedFileName, setUploadedFileName] = useState<string>("");

  // Reset Section state
  const [resetMode, setResetMode] = useState<"ZERO_WALLETS" | "FULL_ACCOUNT_RESET">("ZERO_WALLETS");
  const [resetClearTx, setResetClearTx] = useState<boolean>(false);
  const [resetPassword, setResetPassword] = useState<string>("");

  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const qTab = params.get("tab");
      if (qTab === "financial") {
        setActiveTab("financial");
      } else if (qTab === "data") {
        setActiveTab("data");
      }
    }
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const p = await getUserProfile().catch(() => null);
      if (p) {
        setProfile(p);
        setFullName(p.full_name || "");
        setEmail(p.email || "");
        setBaseCurrency(p.base_currency || "IDR");
      }

      const b = await getBotStatus().catch(() => null);
      if (b) {
        setBotStatus(b);
      }

      const overview = await getPlannerOverview().catch(() => null);
      if (overview?.personal_profile) {
        const pp = overview.personal_profile;
        setPersonalProfile(pp);
        setIncomeInput(pp.monthly_income || 0);
        setExpenseInput(pp.monthly_living_expense || 10000000);
        setDebtInput(pp.monthly_debt_payment || 0);
        setMaritalInput(pp.marital_status || "SINGLE");
        setDependentsInput(pp.dependents_count || 0);
        setAgeInput(pp.current_age || 28);
        setTargetFireInput(pp.target_fire_age || 50);
        setRiskInput(pp.risk_tolerance || "MODERATE");
        setShariaInput(pp.sharia_preference || false);
      }

      const bList = await listAccountBackups().catch(() => null);
      if (bList?.items) {
        setBackups(bList.items);
      }
    } catch (err: any) {
      setProfileMsg({ type: "error", text: "Gagal memuat profil: " + err.message });
    }
  };

  const handleCreateBackup = async (downloadAfter: boolean = false) => {
    setDataMsg(null);
    setDataLoading(true);
    try {
      const res = await createAccountBackup(backupLabel.trim() || undefined);
      setBackupLabel("");
      const bList = await listAccountBackups();
      setBackups(bList.items);
      if (downloadAfter && res?.id) {
        await handleDownloadBackup(res.id);
      }
      setDataMsg({
        type: "success",
        text: downloadAfter
          ? "Backup berhasil dibuat & diunduh sebagai file JSON!"
          : `Cloud Snapshot "${res.title}" berhasil disimpan!`,
      });
    } catch (err: any) {
      setDataMsg({ type: "error", text: err.message || "Gagal membuat backup." });
    } finally {
      setDataLoading(false);
    }
  };

  const handleDownloadBackup = async (backupId: string) => {
    try {
      const exported = await exportAccountBackup(backupId);
      const blob = new Blob([JSON.stringify(exported, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const safeLabel = (exported.title || exported.label || "aifinance-backup")
        .toLowerCase()
        .replace(/[^a-z0-9-_]+/g, "-");
      a.download = `${safeLabel}-${backupId.slice(0, 6)}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err: any) {
      setDataMsg({ type: "error", text: err.message || "Gagal mengunduh file backup JSON." });
    }
  };

  const handleDeleteBackup = async (backupId: string) => {
    if (!confirm("Hapus snapshot backup ini dari penyimpanan Cloud?")) return;
    setDataMsg(null);
    try {
      await deleteAccountBackup(backupId);
      const bList = await listAccountBackups();
      setBackups(bList.items);
      setDataMsg({ type: "success", text: "Snapshot backup berhasil dihapus." });
    } catch (err: any) {
      setDataMsg({ type: "error", text: err.message || "Gagal menghapus backup." });
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadedFileName(file.name);
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const parsed = JSON.parse(String(ev.target?.result || "{}"));
        const payload = parsed.data && parsed.data.wallets ? parsed.data : parsed;
        setUploadedPayload(payload);
        setRestoreTargetId("FILE_UPLOAD");
        setDataMsg({
          type: "success",
          text: `File "${file.name}" berhasil dibaca. Masukkan kata sandi di bawah untuk mengembalikan (Restore) data.`,
        });
      } catch {
        setUploadedPayload(null);
        setDataMsg({ type: "error", text: "Format file JSON backup tidak valid." });
      }
    };
    reader.readAsText(file);
  };

  const handleExecuteRestore = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!restorePassword.trim()) {
      setDataMsg({ type: "error", text: "Kata sandi wajib diisi untuk konfirmasi Restore." });
      return;
    }
    setDataLoading(true);
    setDataMsg(null);
    try {
      const res = await restoreAccountData({
        password: restorePassword,
        backup_id: restoreTargetId !== "FILE_UPLOAD" ? restoreTargetId || undefined : undefined,
        backup_payload: restoreTargetId === "FILE_UPLOAD" ? uploadedPayload || undefined : undefined,
      });
      setRestorePassword("");
      setRestoreTargetId(null);
      setUploadedPayload(null);
      setUploadedFileName("");
      await loadData();
      setDataMsg({
        type: "success",
        text: `${res.message} (${res.restored_wallets_count} dompet & ${res.restored_transactions_count} transaksi dipulihkan).`,
      });
    } catch (err: any) {
      setDataMsg({ type: "error", text: err.message || "Gagal memulihkan data." });
    } finally {
      setDataLoading(false);
    }
  };

  const handleExecuteReset = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resetPassword.trim()) {
      setDataMsg({ type: "error", text: "Kata sandi akun wajib diisi untuk melakukan Reset." });
      return;
    }
    setDataLoading(true);
    setDataMsg(null);
    try {
      const res = await resetAccountData({
        password: resetPassword,
        mode: resetMode,
        clear_transactions: resetClearTx,
      });
      setResetPassword("");
      await loadData();
      setDataMsg({
        type: "success",
        text: `${res.message} Snapshot otomatis telah diamankan sebelum reset.`,
      });
    } catch (err: any) {
      setDataMsg({ type: "error", text: err.message || "Gagal mereset data akun." });
    } finally {
      setDataLoading(false);
    }
  };

  const handleUpdateProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfileMsg(null);

    if (!fullName.trim() || fullName.trim().length < 2) {
      setProfileMsg({ type: "error", text: "Nama lengkap wajib diisi minimal 2 karakter." });
      return;
    }

    if (!email.trim()) {
      setProfileMsg({ type: "error", text: "Alamat email wajib diisi." });
      return;
    }

    setProfileLoading(true);
    try {
      const updated = await updateUserProfile({
        full_name: fullName.trim(),
        email: email.trim().toLowerCase(),
        base_currency: baseCurrency,
      });
      setProfile(updated);
      setProfileMsg({ type: "success", text: "Profil berhasil diperbarui!" });
    } catch (err: any) {
      setProfileMsg({ type: "error", text: err.message || "Gagal memperbarui profil." });
    } finally {
      setProfileLoading(false);
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordMsg(null);

    if (newPassword.length < 6) {
      setPasswordMsg({ type: "error", text: "Kata sandi baru minimal 6 karakter." });
      return;
    }

    if (newPassword !== confirmPassword) {
      setPasswordMsg({ type: "error", text: "Konfirmasi kata sandi baru tidak cocok." });
      return;
    }

    setPasswordLoading(true);
    try {
      await changePassword({ old_password: oldPassword, new_password: newPassword });
      setPasswordMsg({ type: "success", text: "Kata sandi berhasil diperbarui!" });
      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err: any) {
      setPasswordMsg({ type: "error", text: err.message || "Gagal mengubah kata sandi." });
    } finally {
      setPasswordLoading(false);
    }
  };

  const handleSaveFinancialProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setFinMsg(null);
    setFinLoading(true);

    try {
      const res = await updatePersonalProfile({
        monthly_income: incomeInput,
        monthly_living_expense: expenseInput,
        monthly_debt_payment: debtInput,
        marital_status: maritalInput,
        dependents_count: dependentsInput,
        current_age: ageInput,
        target_fire_age: targetFireInput,
        risk_tolerance: riskInput,
        sharia_preference: shariaInput,
      });
      setPersonalProfile(res.personal_profile);
      setFinMsg({ type: "success", text: "Data personalisasi finansial berhasil disimpan & disinkronkan ke AI Planner!" });
    } catch (err: any) {
      setFinMsg({ type: "error", text: err.message || "Gagal menyimpan data personalisasi." });
    } finally {
      setFinLoading(false);
    }
  };

  const completeness = personalProfile?.profile_completeness_pct || 0;

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-8">
      {/* Page Header */}
      <div>
        <div className="flex items-center gap-2 text-xs font-semibold text-[#8a6300] dark:text-[#f0b000] uppercase tracking-wider">
          <span>Pusat Pengaturan</span>
        </div>
        <h1 className="text-2xl font-bold text-foreground mt-1 tracking-tight">
          Pengaturan Akun &amp; Personalisasi
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Kelola nama lengkap, email terverifikasi, keamanan kata sandi, serta profil finansial terpusat untuk rekomendasi AI.
        </p>
      </div>

      {/* Tab Switcher */}
      <div className="flex items-center gap-2 border-b border-border pb-1">
        <button
          type="button"
          onClick={() => setActiveTab("account")}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all border ${
            activeTab === "account"
              ? "bg-primary text-primary-foreground border-primary shadow-sm shadow-[#f0b000]/20"
              : "border-transparent text-muted-foreground hover:text-foreground hover:bg-secondary"
          }`}
        >
          <UserIcon className="w-3.5 h-3.5" />
          <span>Akun &amp; Keamanan</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("financial")}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all border ${
            activeTab === "financial"
              ? "bg-primary text-primary-foreground border-primary shadow-sm shadow-[#f0b000]/20"
              : "border-transparent text-muted-foreground hover:text-foreground hover:bg-secondary"
          }`}
        >
          <SlidersHorizontal className="w-3.5 h-3.5" />
          <span>Personalisasi Finansial (AI)</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-accent text-[#8a6300] dark:text-[#f0b000] border border-[#f0b000]/30 font-extrabold">
            {completeness}%
          </span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("data")}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all border ${
            activeTab === "data"
              ? "bg-primary text-primary-foreground border-primary shadow-sm shadow-[#f0b000]/20"
              : "border-transparent text-muted-foreground hover:text-foreground hover:bg-secondary"
          }`}
        >
          <Database className="w-3.5 h-3.5" />
          <span>Data, Backup &amp; Reset</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-secondary text-muted-foreground border border-border font-bold">
            {backups.length}
          </span>
        </button>
      </div>

      {/* TAB 1: AKUN & KEAMANAN */}
      {activeTab === "account" && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Left Column: Profile Summary Card */}
          <div className="md:col-span-1 space-y-6">
            <div className="p-6 rounded-2xl bg-card border border-border shadow-sm flex flex-col items-center text-center">
              <div className="w-20 h-20 rounded-full bg-accent border-2 border-[#f0b000]/40 flex items-center justify-center text-2xl font-bold text-[#8a6300] dark:text-[#f0b000] shadow-md shadow-[#f0b000]/10 mb-4">
                {fullName ? fullName.charAt(0).toUpperCase() : "U"}
              </div>
              <h2 className="text-lg font-bold text-foreground">{fullName || "Pengguna"}</h2>
              <p className="text-xs text-muted-foreground mt-0.5">{email}</p>

              <div className="mt-4 inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>Email Terverifikasi (Resend)</span>
              </div>

              {profile?.created_at && (
                <div className="mt-6 pt-4 border-t border-border w-full text-left text-xs text-muted-foreground flex items-center justify-between">
                  <span className="flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    Bergabung
                  </span>
                  <span className="font-medium text-foreground">
                    {(() => {
                      try {
                        const d = new Date(profile.created_at);
                        return isNaN(d.getTime())
                          ? "-"
                          : d.toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" });
                      } catch {
                        return "-";
                      }
                    })()}
                  </span>
                </div>
              )}
            </div>

            {/* Bot Integration Widget */}
            <div className="p-5 rounded-2xl bg-secondary/50 border border-border space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs font-bold text-foreground">
                  <Bot className="w-4 h-4 text-[#8a6300] dark:text-[#f0b000]" />
                  <span>Integrasi Chatbot</span>
                </div>
                <Link
                  href="/bot-pairing"
                  className="text-xs text-[#8a6300] dark:text-[#f0b000] hover:underline flex items-center gap-1"
                >
                  <span>Kelola</span>
                  <ExternalLink className="w-3 h-3" />
                </Link>
              </div>

              <div className="space-y-2 pt-1 text-xs">
                <div className="flex items-center justify-between p-2 rounded-lg bg-card border border-border">
                  <span className="text-muted-foreground">Telegram</span>
                  <span
                    className={`font-semibold ${
                      botStatus?.TELEGRAM?.connected
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-muted-foreground"
                    }`}
                  >
                    {botStatus?.TELEGRAM?.connected ? "Terhubung ✅" : "Belum Terhubung"}
                  </span>
                </div>
                <div className="flex items-center justify-between p-2 rounded-lg bg-card border border-border">
                  <span className="text-muted-foreground">WhatsApp</span>
                  <span
                    className={`font-semibold ${
                      botStatus?.WHATSAPP?.connected
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-muted-foreground"
                    }`}
                  >
                    {botStatus?.WHATSAPP?.connected ? "Terhubung ✅" : "Belum Terhubung"}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Right Column: Forms */}
          <div className="md:col-span-2 space-y-6">
            {/* Card 1: Data Pribadi Mandatori */}
            <div className="p-6 rounded-2xl bg-card border border-border shadow-sm space-y-5">
              <div className="flex items-center gap-2 border-b border-border pb-3">
                <UserIcon className="w-4 h-4 text-[#8a6300] dark:text-[#f0b000]" />
                <h3 className="text-base font-bold text-foreground">Data Profil Pribadi (Mandatori)</h3>
              </div>

              {profileMsg && (
                <div
                  className={`p-3.5 rounded-xl text-xs font-medium flex items-start gap-2 border ${
                    profileMsg.type === "success"
                      ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
                      : "bg-rose-500/10 border-rose-500/30 text-rose-600 dark:text-rose-400"
                  }`}
                >
                  {profileMsg.type === "success" ? (
                    <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
                  ) : (
                    <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                  )}
                  <span>{profileMsg.text}</span>
                </div>
              )}

              <form onSubmit={handleUpdateProfile} className="space-y-4">
                <div>
                  <label className="text-xs font-semibold text-foreground block mb-1.5">
                    Nama Lengkap <span className="text-rose-500 font-bold">* (Wajib)</span>
                  </label>
                  <div className="relative">
                    <UserIcon className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
                    <input
                      type="text"
                      required
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      placeholder="Masukkan nama lengkap Anda"
                      className="w-full pl-9 pr-3 py-2.5 rounded-xl bg-secondary border border-border text-foreground text-sm focus:outline-none focus:border-[#f0b000]"
                    />
                  </div>
                </div>

                <div>
                  <label className="text-xs font-semibold text-foreground block mb-1.5">
                    Alamat Email <span className="text-rose-500 font-bold">* (Wajib)</span>
                  </label>
                  <div className="relative">
                    <Mail className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
                    <input
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="email@domain.com"
                      className="w-full pl-9 pr-3 py-2.5 rounded-xl bg-secondary border border-border text-foreground text-sm focus:outline-none focus:border-[#f0b000]"
                    />
                  </div>
                </div>

                <div>
                  <label className="text-xs font-semibold text-foreground block mb-1.5">
                    Mata Uang Acuan
                  </label>
                  <div className="relative">
                    <Coins className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
                    <select
                      value={baseCurrency}
                      onChange={(e) => setBaseCurrency(e.target.value)}
                      className="w-full pl-9 pr-3 py-2.5 rounded-xl bg-secondary border border-border text-foreground text-sm focus:outline-none focus:border-[#f0b000]"
                    >
                      <option value="IDR">IDR - Rupiah Indonesia</option>
                      <option value="USD">USD - United States Dollar</option>
                      <option value="SGD">SGD - Singapore Dollar</option>
                      <option value="EUR">EUR - Euro</option>
                    </select>
                  </div>
                </div>

                <div className="pt-2 flex justify-end">
                  <button
                    type="submit"
                    disabled={profileLoading}
                    className="py-2.5 px-5 rounded-xl bg-primary hover:bg-primary/90 disabled:opacity-50 text-primary-foreground font-bold text-xs flex items-center gap-2 shadow-sm shadow-[#f0b000]/20 transition-all"
                  >
                    <Save className="w-4 h-4" />
                    <span>{profileLoading ? "Menyimpan..." : "Simpan Perubahan Profil"}</span>
                  </button>
                </div>
              </form>
            </div>

            {/* Card 2: Keamanan & Kata Sandi */}
            <div className="p-6 rounded-2xl bg-card border border-border shadow-sm space-y-5">
              <div className="flex items-center gap-2 border-b border-border pb-3">
                <Lock className="w-4 h-4 text-[#8a6300] dark:text-[#f0b000]" />
                <h3 className="text-base font-bold text-foreground">Keamanan &amp; Ubah Kata Sandi</h3>
              </div>

              {passwordMsg && (
                <div
                  className={`p-3.5 rounded-xl text-xs font-medium flex items-start gap-2 border ${
                    passwordMsg.type === "success"
                      ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
                      : "bg-rose-500/10 border-rose-500/30 text-rose-600 dark:text-rose-400"
                  }`}
                >
                  {passwordMsg.type === "success" ? (
                    <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
                  ) : (
                    <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                  )}
                  <span>{passwordMsg.text}</span>
                </div>
              )}

              <form onSubmit={handleChangePassword} className="space-y-4">
                <div>
                  <label className="text-xs font-semibold text-foreground block mb-1.5">
                    Kata Sandi Saat Ini
                  </label>
                  <div className="relative">
                    <KeyRound className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
                    <input
                      type="password"
                      required
                      value={oldPassword}
                      onChange={(e) => setOldPassword(e.target.value)}
                      placeholder="••••••••"
                      className="w-full pl-9 pr-3 py-2.5 rounded-xl bg-secondary border border-border text-foreground text-sm focus:outline-none focus:border-[#f0b000]"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs font-semibold text-foreground block mb-1.5">
                      Kata Sandi Baru (Min. 6 Karakter)
                    </label>
                    <div className="relative">
                      <Lock className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
                      <input
                        type="password"
                        required
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                        placeholder="••••••••"
                        className="w-full pl-9 pr-3 py-2.5 rounded-xl bg-secondary border border-border text-foreground text-sm focus:outline-none focus:border-[#f0b000]"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="text-xs font-semibold text-foreground block mb-1.5">
                      Konfirmasi Kata Sandi Baru
                    </label>
                    <div className="relative">
                      <Lock className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
                      <input
                        type="password"
                        required
                        value={confirmPassword}
                        onChange={(e) => setConfirmPassword(e.target.value)}
                        placeholder="••••••••"
                        className="w-full pl-9 pr-3 py-2.5 rounded-xl bg-secondary border border-border text-foreground text-sm focus:outline-none focus:border-[#f0b000]"
                      />
                    </div>
                  </div>
                </div>

                <div className="pt-2 flex justify-end">
                  <button
                    type="submit"
                    disabled={passwordLoading}
                    className="py-2.5 px-5 rounded-xl bg-secondary hover:bg-accent text-foreground border border-border hover:border-[#f0b000]/40 font-bold text-xs flex items-center gap-2 transition-all"
                  >
                    <KeyRound className="w-4 h-4 text-[#8a6300] dark:text-[#f0b000]" />
                    <span>{passwordLoading ? "Memperbarui..." : "Perbarui Kata Sandi"}</span>
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: PERSONALISASI FINANSIAL (AI) */}
      {activeTab === "financial" && (
        <div className="space-y-6">
          {/* Akurasi & Context Banner */}
          <div className="p-6 rounded-2xl bg-card border border-border shadow-sm space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <SlidersHorizontal className="w-5 h-5 text-[#8a6300] dark:text-[#f0b000]" />
                <div>
                  <h2 className="text-base font-bold text-foreground">Akurasi Personalisasi Finansial AI</h2>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Data ini menjadi acuan AI Financial Planner dalam menghitung target FIRE, dana darurat, dan alokasi portofolio.
                  </p>
                </div>
              </div>
              <div className="text-right">
                <span className="text-2xl font-black text-[#8a6300] dark:text-[#f0b000]">{completeness}%</span>
                <span className="text-xs text-muted-foreground block">Kelengkapan</span>
              </div>
            </div>

            <div className="w-full bg-secondary h-2.5 rounded-full overflow-hidden border border-border">
              <div
                className="h-full rounded-full bg-gradient-to-r from-[#8a6300] via-[#f0b000] to-amber-300 transition-all duration-500"
                style={{ width: `${Math.max(5, completeness)}%` }}
              />
            </div>

            {personalProfile?.memory_notes_list && personalProfile.memory_notes_list.length > 0 && (
              <div className="pt-2 border-t border-border">
                <div className="text-[11px] font-semibold text-muted-foreground mb-1.5 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-[#8a6300] dark:text-[#f0b000]" />
                  <span>Konteks Hidup yang Diingat AI dari Percakapan:</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {personalProfile.memory_notes_list.map((note, idx) => (
                    <span
                      key={idx}
                      className="text-xs px-2.5 py-1 rounded-lg bg-secondary text-foreground border border-border"
                    >
                      {note}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {finMsg && (
            <div
              className={`p-4 rounded-xl text-xs font-medium flex items-start gap-2 border ${
                finMsg.type === "success"
                  ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
                  : "bg-rose-500/10 border-rose-500/30 text-rose-600 dark:text-rose-400"
              }`}
            >
              {finMsg.type === "success" ? (
                <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
              ) : (
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              )}
              <span>{finMsg.text}</span>
            </div>
          )}

          {/* Form Personalisasi Terpusat */}
          <form onSubmit={handleSaveFinancialProfile} className="p-6 rounded-2xl bg-card border border-border shadow-sm space-y-6">
            {/* Syariah Preference Switch */}
            <div className="flex items-center justify-between p-4 rounded-xl bg-secondary/60 border border-border">
              <div className="flex items-center gap-3">
                <MoonStar className="w-5 h-5 text-teal-600 dark:text-teal-400" />
                <div>
                  <div className="text-sm font-bold text-foreground">Preferensi Syariah</div>
                  <div className="text-xs text-muted-foreground">
                    Prioritaskan instrumen halal (Sukuk, Reksa Dana Syariah, Saham Syariah, Emas).
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShariaInput((v) => !v)}
                className={`w-12 h-6 rounded-full transition-colors p-0.5 ${
                  shariaInput ? "bg-[#f0b000]" : "bg-secondary border border-border"
                }`}
                aria-label="Toggle Preferensi Syariah"
              >
                <div
                  className={`w-5 h-5 rounded-full bg-white transition-transform ${
                    shariaInput ? "translate-x-6" : "translate-x-0"
                  }`}
                />
              </button>
            </div>

            {/* Income & Expense Section */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-semibold text-foreground mb-1.5">
                  Penghasilan Bersih / Bulan (Rp)
                </label>
                <input
                  type="number"
                  min="0"
                  value={incomeInput}
                  onChange={(e) => setIncomeInput(parseFloat(e.target.value) || 0)}
                  className="w-full px-3 py-2.5 rounded-xl bg-secondary border border-border text-foreground font-mono text-sm focus:outline-none focus:border-[#f0b000]"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-foreground mb-1.5">
                  Estimasi Pengeluaran / Bulan (Rp)
                </label>
                <input
                  type="number"
                  min="0"
                  value={expenseInput}
                  onChange={(e) => setExpenseInput(parseFloat(e.target.value) || 0)}
                  className="w-full px-3 py-2.5 rounded-xl bg-secondary border border-border text-foreground font-mono text-sm focus:outline-none focus:border-[#f0b000]"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-foreground mb-1.5">
                  Cicilan Utang / Bulan (Rp)
                </label>
                <input
                  type="number"
                  min="0"
                  value={debtInput}
                  onChange={(e) => setDebtInput(parseFloat(e.target.value) || 0)}
                  className="w-full px-3 py-2.5 rounded-xl bg-secondary border border-border text-foreground font-mono text-sm focus:outline-none focus:border-[#f0b000]"
                />
              </div>
            </div>

            {/* Demographics & FIRE Age */}
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
              <div>
                <label className="block text-xs font-semibold text-foreground mb-1.5">
                  Status Pernikahan
                </label>
                <select
                  value={maritalInput}
                  onChange={(e) => setMaritalInput(e.target.value as "SINGLE" | "MARRIED")}
                  className="w-full px-3 py-2.5 rounded-xl bg-secondary border border-border text-foreground text-sm focus:outline-none focus:border-[#f0b000]"
                >
                  <option value="SINGLE">Lajang</option>
                  <option value="MARRIED">Menikah</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-foreground mb-1.5">
                  Jumlah Tanggungan
                </label>
                <input
                  type="number"
                  min="0"
                  max="10"
                  value={dependentsInput}
                  onChange={(e) => setDependentsInput(parseInt(e.target.value) || 0)}
                  className="w-full px-3 py-2.5 rounded-xl bg-secondary border border-border text-foreground text-sm focus:outline-none focus:border-[#f0b000]"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-foreground mb-1.5">
                  Usia Saat Ini (Tahun)
                </label>
                <input
                  type="number"
                  min="15"
                  max="90"
                  value={ageInput}
                  onChange={(e) => setAgeInput(parseInt(e.target.value) || 28)}
                  className="w-full px-3 py-2.5 rounded-xl bg-secondary border border-border text-foreground text-sm focus:outline-none focus:border-[#f0b000]"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-foreground mb-1.5">
                  Target Usia FIRE / Pensiun
                </label>
                <input
                  type="number"
                  min="25"
                  max="90"
                  value={targetFireInput}
                  onChange={(e) => setTargetFireInput(parseInt(e.target.value) || 50)}
                  className="w-full px-3 py-2.5 rounded-xl bg-secondary border border-border text-foreground text-sm focus:outline-none focus:border-[#f0b000]"
                />
              </div>
            </div>

            {/* Risk Tolerance */}
            <div>
              <label className="block text-xs font-semibold text-foreground mb-1.5">
                Profil Risiko Investasi
              </label>
              <select
                value={riskInput}
                onChange={(e) => setRiskInput(e.target.value as "CONSERVATIVE" | "MODERATE" | "AGGRESSIVE")}
                className="w-full sm:w-1/2 px-3 py-2.5 rounded-xl bg-secondary border border-border text-foreground text-sm focus:outline-none focus:border-[#f0b000]"
              >
                <option value="CONSERVATIVE">Konservatif (Prioritas Pengamanan Modal)</option>
                <option value="MODERATE">Moderat (Seimbang Pertumbuhan &amp; Keamanan)</option>
                <option value="AGGRESSIVE">Agresif (Maksimalisasi Return &amp; Saham)</option>
              </select>
            </div>

            <div className="pt-4 border-t border-border flex items-center justify-between">
              <Link
                href="/planner"
                className="text-xs font-semibold text-[#8a6300] dark:text-[#f0b000] hover:underline flex items-center gap-1.5"
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>Konsultasikan dengan AI Financial Planner</span>
              </Link>

              <button
                type="submit"
                disabled={finLoading}
                className="py-2.5 px-6 rounded-xl bg-primary hover:bg-primary/90 disabled:opacity-50 text-primary-foreground font-bold text-xs flex items-center gap-2 shadow-md shadow-[#f0b000]/20 transition-all"
              >
                <Save className="w-4 h-4" />
                <span>{finLoading ? "Menyimpan Data..." : "Simpan Profil Finansial"}</span>
              </button>
            </div>
          </form>
        </div>
      )}

      {/* TAB 3: DATA, BACKUP & RESET */}
      {activeTab === "data" && (
        <div className="space-y-6">
          {dataMsg && (
            <div
              className={`p-4 rounded-xl text-xs font-medium flex items-start gap-2 border ${
                dataMsg.type === "success"
                  ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
                  : "bg-rose-500/10 border-rose-500/30 text-rose-600 dark:text-rose-400"
              }`}
            >
              {dataMsg.type === "success" ? (
                <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
              ) : (
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              )}
              <span>{dataMsg.text}</span>
            </div>
          )}

          {/* Section 1: Buat Cloud Snapshot & Export JSON */}
          <div className="p-6 rounded-2xl bg-card border border-border shadow-sm space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-border pb-3">
              <div className="flex items-center gap-2.5">
                <Database className="w-5 h-5 text-[#8a6300] dark:text-[#f0b000]" />
                <div>
                  <h2 className="text-base font-bold text-foreground">
                    Backup Pencatatan Dana, Saldo Dompet &amp; Transaksi
                  </h2>
                  <p className="text-xs text-muted-foreground">
                    Simpan snapshot penuh ke Cloud Database atau unduh sebagai file JSON lokal kapan saja.
                  </p>
                </div>
              </div>
            </div>

            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
              <input
                type="text"
                placeholder="Nama label backup (opsional, misal: Sebelum Gajian November)"
                value={backupLabel}
                onChange={(e) => setBackupLabel(e.target.value)}
                className="flex-1 px-3.5 py-2.5 rounded-xl bg-secondary border border-border text-foreground text-xs focus:outline-none focus:border-[#f0b000]"
              />
              <button
                type="button"
                disabled={dataLoading}
                onClick={() => handleCreateBackup(false)}
                className="px-4 py-2.5 rounded-xl bg-primary hover:bg-primary/90 disabled:opacity-50 text-primary-foreground font-bold text-xs flex items-center justify-center gap-2 shadow-sm shadow-[#f0b000]/20"
              >
                <Save className="w-4 h-4" />
                <span>Simpan Cloud Backup</span>
              </button>
              <button
                type="button"
                disabled={dataLoading}
                onClick={() => handleCreateBackup(true)}
                className="px-4 py-2.5 rounded-xl bg-secondary hover:bg-accent disabled:opacity-50 text-foreground border border-border font-bold text-xs flex items-center justify-center gap-2"
              >
                <Download className="w-4 h-4 text-[#8a6300] dark:text-[#f0b000]" />
                <span>Buat &amp; Unduh JSON</span>
              </button>
            </div>

            {/* Daftar Cloud Snapshots */}
            <div className="pt-2 space-y-2.5">
              <div className="flex items-center justify-between text-xs font-bold text-foreground">
                <span>Riwayat Snapshot Backup Tersimpan ({backups.length})</span>
                <label className="cursor-pointer inline-flex items-center gap-1.5 text-[#8a6300] dark:text-[#f0b000] hover:underline font-semibold">
                  <Upload className="w-3.5 h-3.5" />
                  <span>Restore dari File .JSON Lokal</span>
                  <input type="file" accept=".json" onChange={handleFileUpload} className="hidden" />
                </label>
              </div>

              {backups.length === 0 ? (
                <div className="p-6 rounded-xl bg-secondary/40 border border-border text-center text-xs text-muted-foreground">
                  Belum ada Cloud Snapshot tersimpan. Klik <strong>Simpan Cloud Backup</strong> di atas atau sistem akan otomatis membuat snapshot sebelum Anda melakukan Reset.
                </div>
              ) : (
                <div className="divide-y divide-border rounded-xl border border-border overflow-hidden bg-secondary/20">
                  {backups.map((b) => (
                    <div
                      key={b.id}
                      className="p-3.5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 hover:bg-secondary/40 transition-colors"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-xs font-bold text-foreground">{b.title}</span>
                          <span
                            className={`text-[10px] px-2 py-0.5 rounded-full font-bold border ${
                              b.backup_type === "AUTO_PRE_RESET"
                                ? "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30"
                                : "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30"
                            }`}
                          >
                            {b.backup_type === "AUTO_PRE_RESET" ? "Auto Pre-Reset" : "Manual Snapshot"}
                          </span>
                        </div>
                        <div className="text-[11px] text-muted-foreground flex flex-wrap items-center gap-2">
                          <span>
                            {new Date(b.created_at).toLocaleString("id-ID", {
                              day: "numeric",
                              month: "short",
                              year: "numeric",
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </span>
                          <span>•</span>
                          <span>{b.summary?.wallets_count || 0} dompet</span>
                          <span>•</span>
                          <span>{b.summary?.transactions_count || 0} transaksi</span>
                          <span>•</span>
                          <span className="font-mono font-semibold text-foreground">
                            Total Saldo: {formatCurrency(b.summary?.total_balance || 0, "IDR")}
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 self-end sm:self-center">
                        <button
                          type="button"
                          onClick={() => {
                            setRestoreTargetId(b.id);
                            setUploadedPayload(null);
                          }}
                          className="px-3 py-1.5 rounded-lg bg-accent hover:bg-accent/80 text-[#8a6300] dark:text-[#f0b000] border border-[#f0b000]/30 font-bold text-xs flex items-center gap-1"
                        >
                          <RotateCcw className="w-3.5 h-3.5" />
                          <span>Restore</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDownloadBackup(b.id)}
                          className="px-2.5 py-1.5 rounded-lg bg-secondary hover:bg-accent text-foreground border border-border text-xs flex items-center gap-1"
                          title="Unduh File JSON"
                        >
                          <Download className="w-3.5 h-3.5" />
                          <span>JSON</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDeleteBackup(b.id)}
                          className="p-1.5 rounded-lg text-muted-foreground hover:text-rose-500 transition-colors"
                          title="Hapus Snapshot"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Password Confirmation Box for Restore */}
            {restoreTargetId && (
              <form
                onSubmit={handleExecuteRestore}
                className="p-4 rounded-xl bg-accent/60 border border-[#f0b000]/40 space-y-3 text-xs"
              >
                <div className="flex items-center justify-between">
                  <div className="font-bold text-foreground flex items-center gap-2">
                    <RotateCcw className="w-4 h-4 text-[#8a6300] dark:text-[#f0b000]" />
                    <span>
                      Konfirmasi Restore Data{" "}
                      {restoreTargetId === "FILE_UPLOAD"
                        ? `dari File "${uploadedFileName}"`
                        : "dari Cloud Snapshot Terpilih"}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setRestoreTargetId(null);
                      setRestorePassword("");
                      setUploadedPayload(null);
                    }}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    Batal
                  </button>
                </div>
                <p className="text-muted-foreground text-[11px]">
                  Seluruh saldo dompet, riwayat transaksi, pos anggaran, dan profil finansial akan dikembalikan sesuai titik backup ini. Masukkan kata sandi akun Anda untuk melanjutkan:
                </p>
                <div className="flex flex-col sm:flex-row gap-2.5">
                  <input
                    type="password"
                    required
                    placeholder="Masukkan kata sandi akun Anda..."
                    value={restorePassword}
                    onChange={(e) => setRestorePassword(e.target.value)}
                    className="flex-1 px-3 py-2 rounded-xl bg-card border border-border text-foreground text-xs focus:outline-none focus:border-[#f0b000]"
                  />
                  <button
                    type="submit"
                    disabled={dataLoading}
                    className="px-5 py-2 rounded-xl bg-primary text-primary-foreground font-bold text-xs shadow-sm"
                  >
                    {dataLoading ? "Memulihkan..." : "Konfirmasi & Pulihkan Data"}
                  </button>
                </div>
              </form>
            )}
          </div>

          {/* Section 2: Danger Zone - Reset Dompet / Factory Reset Akun */}
          <div className="p-6 rounded-2xl bg-card border border-rose-500/30 shadow-sm space-y-5">
            <div className="flex items-center gap-2.5 border-b border-border pb-3">
              <div className="w-9 h-9 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-600 dark:text-rose-400 flex items-center justify-center">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-base font-bold text-foreground">
                  Reset Saldo Dompet &amp; Reset Pencatatan Akun (Wajib Verifikasi Password)
                </h2>
                <p className="text-xs text-muted-foreground">
                  Gunakan fitur ini jika Anda ingin me-reset seluruh saldo menjadi Rp 0 dan mengatur ulang pencatatan keuangan dari awal.
                </p>
              </div>
            </div>

            <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/25 text-[11px] text-amber-700 dark:text-amber-300 flex items-start gap-2">
              <ShieldCheck className="w-4 h-4 shrink-0 mt-0.5" />
              <span>
                <strong>Perlindungan Otomatis:</strong> Sistem secara otomatis menyimpan{" "}
                <strong>Cloud Snapshot (Auto Pre-Reset)</strong> tepat sebelum mereset data, sehingga Anda tetap bisa memulihkan kembali (Restore) kapan pun dibutuhkan.
              </span>
            </div>

            <form onSubmit={handleExecuteReset} className="space-y-4 text-xs">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setResetMode("ZERO_WALLETS")}
                  className={`p-4 rounded-xl border text-left transition-all ${
                    resetMode === "ZERO_WALLETS"
                      ? "bg-rose-500/10 border-rose-500/40 text-foreground"
                      : "bg-secondary/40 border-border text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <div className="font-bold text-sm text-foreground flex items-center justify-between">
                    <span>1. Reset Saldo Dompet ke Rp 0</span>
                    {resetMode === "ZERO_WALLETS" && (
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-rose-500 text-white font-bold">
                        Aktif
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-1">
                    Mengubah saldo semua dompet milik Anda menjadi Rp 0 tanpa menghapus daftar dompet atau pos anggaran yang sudah dibuat.
                  </p>
                </button>

                <button
                  type="button"
                  onClick={() => setResetMode("FULL_ACCOUNT_RESET")}
                  className={`p-4 rounded-xl border text-left transition-all ${
                    resetMode === "FULL_ACCOUNT_RESET"
                      ? "bg-rose-500/10 border-rose-500/40 text-foreground"
                      : "bg-secondary/40 border-border text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <div className="font-bold text-sm text-foreground flex items-center justify-between">
                    <span>2. Factory Reset Seluruh Pencatatan</span>
                    {resetMode === "FULL_ACCOUNT_RESET" && (
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-rose-500 text-white font-bold">
                        Aktif
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-1">
                    Menghapus seluruh riwayat transaksi, pos anggaran gajian, kategori custom, riwayat chat AI, dan mengembalikan dompet ke setelan awal bersaldo Rp 0.
                  </p>
                </button>
              </div>

              {resetMode === "ZERO_WALLETS" && (
                <label className="flex items-center gap-2 cursor-pointer p-3 rounded-xl bg-secondary/50 border border-border">
                  <input
                    type="checkbox"
                    checked={resetClearTx}
                    onChange={(e) => setResetClearTx(e.target.checked)}
                    className="rounded accent-rose-500"
                  />
                  <span className="text-foreground font-medium">
                    Hapus juga seluruh riwayat transaksi sebelumnya (agar laporan bulanan ikut mulai dari Rp 0)
                  </span>
                </label>
              )}

              <div className="pt-2 border-t border-border flex flex-col sm:flex-row items-stretch sm:items-end justify-between gap-4">
                <div className="flex-1">
                  <label className="block font-bold text-foreground mb-1">
                    Masukkan Kata Sandi Akun untuk Verifikasi Keamanan <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="password"
                    required
                    placeholder="Kata sandi login Anda..."
                    value={resetPassword}
                    onChange={(e) => setResetPassword(e.target.value)}
                    className="w-full px-3.5 py-2.5 rounded-xl bg-secondary border border-border text-foreground text-xs focus:outline-none focus:border-rose-500"
                  />
                </div>
                <button
                  type="submit"
                  disabled={dataLoading}
                  className="px-5 py-2.5 rounded-xl bg-rose-500 hover:bg-rose-600 disabled:opacity-50 text-white font-bold text-xs flex items-center justify-center gap-2 shadow-md shadow-rose-500/20"
                >
                  <RotateCcw className="w-4 h-4" />
                  <span>
                    {dataLoading
                      ? "Memproses Reset..."
                      : resetMode === "FULL_ACCOUNT_RESET"
                      ? "Eksekusi Factory Reset Akun"
                      : "Reset Saldo Dompet ke Rp 0"}
                  </span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
