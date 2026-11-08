"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
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
} from "lucide-react";
import {
  AuthUser,
  getUserProfile,
  updateUserProfile,
  changePassword,
  getBotStatus,
} from "@/lib/api";
import { BotStatusMap } from "@/lib/types";
import Link from "next/link";

export default function SettingsPage() {
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

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const p = await getUserProfile();
      setProfile(p);
      setFullName(p.full_name || "");
      setEmail(p.email || "");
      setBaseCurrency(p.base_currency || "IDR");

      const b = await getBotStatus();
      setBotStatus(b);
    } catch (err: any) {
      setProfileMsg({ type: "error", text: "Gagal memuat profil: " + err.message });
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

  return (
    <AppShell>
      <div className="p-6 max-w-5xl mx-auto space-y-8">
        {/* Page Header */}
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-[#8a6300] dark:text-[#f0b000] uppercase tracking-wider">
            <span>Personalisasi & Akun</span>
          </div>
          <h1 className="text-2xl font-bold text-foreground mt-1 tracking-tight">
            Pengaturan Profil Pengguna
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Kelola nama lengkap, kontak email terverifikasi, preferensi mata uang, dan keamanan akun Anda.
          </p>
        </div>

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
                    {new Date(profile.created_at).toLocaleDateString("id-ID", {
                      day: "numeric",
                      month: "short",
                      year: "numeric",
                    })}
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
                      botStatus.TELEGRAM.connected
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-muted-foreground"
                    }`}
                  >
                    {botStatus.TELEGRAM.connected ? "Terhubung ✅" : "Belum Terhubung"}
                  </span>
                </div>
                <div className="flex items-center justify-between p-2 rounded-lg bg-card border border-border">
                  <span className="text-muted-foreground">WhatsApp</span>
                  <span
                    className={`font-semibold ${
                      botStatus.WHATSAPP.connected
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-muted-foreground"
                    }`}
                  >
                    {botStatus.WHATSAPP.connected ? "Terhubung ✅" : "Belum Terhubung"}
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
                <h3 className="text-base font-bold text-foreground">Keamanan & Ubah Kata Sandi</h3>
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
      </div>
    </AppShell>
  );
}
