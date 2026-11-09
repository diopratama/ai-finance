"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Lock, Mail, User as UserIcon, ArrowRight, ArrowLeft, KeyRound, RefreshCw, CheckCircle2 } from "lucide-react";
import { hasAuthToken, loginUser, registerUser, verifyEmail, resendVerification, apiFetch } from "@/lib/api";
import { AppLogo } from "@/components/AppLogo";
import { ThemeToggle } from "@/components/ThemeToggle";

export function AuthScreen({ defaultMode = "login" }: { defaultMode?: "login" | "register" }) {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register" | "verify">(defaultMode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [baseCurrency, setBaseCurrency] = useState("IDR");
  const [otpCode, setOtpCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);

  useEffect(() => {
    if (hasAuthToken()) {
      // Validate existing session token against backend /auth/me
      apiFetch("/auth/me")
        .then(() => {
          window.location.href = "/dashboard";
        })
        .catch(() => {
          // Token is stale or invalid: clear it so user can freely enter credentials
          if (typeof window !== "undefined") {
            localStorage.removeItem("ai_finance_token");
            localStorage.removeItem("ai_finance_user");
          }
        });
      return;
    }
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const qMode = params.get("mode");
      if (qMode === "register" || qMode === "login") {
        setMode(qMode);
      }
    }
  }, []);

  useEffect(() => {
    if (resendCooldown > 0) {
      const timer = setTimeout(() => setResendCooldown(resendCooldown - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [resendCooldown]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccessMsg(null);
    setLoading(true);

    try {
      if (mode === "login") {
        await loginUser(email, password);
        window.location.href = "/dashboard";
      } else if (mode === "register") {
        if (!fullName.trim() || fullName.trim().length < 2) {
          throw new Error("Nama lengkap wajib diisi minimal 2 karakter.");
        }
        const res = await registerUser({
          email,
          password,
          full_name: fullName.trim(),
          base_currency: baseCurrency,
        });
        setSuccessMsg(res.message || "Kode verifikasi telah dikirim ke email Anda.");
        setMode("verify");
        setResendCooldown(60);
      } else if (mode === "verify") {
        if (!otpCode.trim() || otpCode.trim().length !== 6) {
          throw new Error("Silakan masukkan 6 digit kode verifikasi.");
        }
        await verifyEmail(email, otpCode.trim());
        window.location.href = "/dashboard";
      }
    } catch (err: any) {
      const msg = err?.message || "Terjadi kesalahan. Silakan coba beberapa saat lagi.";
      setError(msg);
      // If login failed because unverified, automatically transition to verify screen
      if (mode === "login" && msg.toLowerCase().includes("belum diverifikasi")) {
        setMode("verify");
        setResendCooldown(60);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    if (resendCooldown > 0 || !email) return;
    setError(null);
    setSuccessMsg(null);
    setLoading(true);
    try {
      const res = await resendVerification(email);
      setSuccessMsg(res.message || "Kode verifikasi baru berhasil dikirim!");
      setResendCooldown(60);
    } catch (err: any) {
      setError(err?.message || "Gagal mengirim ulang kode. Silakan coba lagi.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full bg-background text-foreground flex flex-col items-center justify-center p-4 relative overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_60%_45%_at_50%_0%,rgba(240,176,0,0.18),transparent)] pointer-events-none" />

      {/* Top Navigation Bar */}
      <div className="w-full max-w-md flex items-center justify-between mb-6 relative z-10">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Kembali ke Beranda</span>
        </Link>
        <ThemeToggle />
      </div>

      {/* Brand */}
      <Link href="/" className="relative flex items-center gap-3 mb-6">
        <AppLogo size={42} />
        <div>
          <div className="text-xl font-bold text-foreground tracking-tight flex items-center gap-2">
            AI-Finance
            <span className="text-[10px] uppercase font-bold bg-accent text-[#8a6300] dark:text-[#f0b000] border border-[#f0b000]/30 px-1.5 py-0.5 rounded">
              AI
            </span>
          </div>
          <div className="text-xs text-muted-foreground">Smart Wealth, Payday Budgeting & Freedom</div>
        </div>
      </Link>

      {/* Card */}
      <div className="relative w-full max-w-md rounded-2xl bg-card border border-border p-7 shadow-xl">
        {/* Mode Switcher */}
        {mode !== "verify" ? (
          <div className="grid grid-cols-2 gap-1.5 p-1 rounded-xl bg-secondary mb-6 border border-border">
            <button
              type="button"
              onClick={() => {
                setMode("login");
                setError(null);
                setSuccessMsg(null);
              }}
              className={`py-2 text-xs font-bold rounded-lg transition-colors ${
                mode === "login"
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Masuk (Login)
            </button>
            <button
              type="button"
              onClick={() => {
                setMode("register");
                setError(null);
                setSuccessMsg(null);
              }}
              className={`py-2 text-xs font-bold rounded-lg transition-colors ${
                mode === "register"
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Daftar Akun Baru
            </button>
          </div>
        ) : (
          <div className="flex items-center justify-between mb-6 pb-3 border-b border-border">
            <div className="flex items-center gap-2 text-xs font-bold text-[#8a6300] dark:text-[#f0b000]">
              <KeyRound className="w-4 h-4" />
              <span>Verifikasi Email (Resend)</span>
            </div>
            <button
              type="button"
              onClick={() => {
                setMode("login");
                setError(null);
                setSuccessMsg(null);
              }}
              className="text-xs text-muted-foreground hover:text-foreground underline"
            >
              Kembali ke Login
            </button>
          </div>
        )}

        <h1 className="text-xl font-bold text-foreground">
          {mode === "login"
            ? "Selamat Datang Kembali"
            : mode === "register"
            ? "Buat Akun AI-Finance"
            : "Verifikasi Alamat Email"}
        </h1>
        <p className="text-xs text-muted-foreground mt-1">
          {mode === "login"
            ? "Masuk untuk mengatur alokasi gajian per dompet & diskusi bersama AI Financial Planner."
            : mode === "register"
            ? "Daftar dengan mengisi nama lengkap dan alamat email yang valid untuk menerima kode verifikasi."
            : `Masukkan 6-digit kode OTP yang telah dikirimkan ke ${email || "email Anda"}.`}
        </p>

        {error && (
          <div className="mt-4 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-600 dark:text-rose-400 text-xs font-medium">
            {error}
          </div>
        )}

        {successMsg && (
          <div className="mt-4 p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-600 dark:text-emerald-400 text-xs font-medium flex items-start gap-2">
            <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{successMsg}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          {mode === "register" && (
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
                  placeholder="Contoh: Dio Pratama"
                  className="w-full pl-9 pr-3 py-2.5 rounded-xl bg-secondary border border-border text-foreground text-sm focus:outline-none focus:border-[#f0b000]"
                />
              </div>
            </div>
          )}

          {mode !== "verify" && (
            <div>
              <label className="text-xs font-semibold text-foreground block mb-1.5">
                Email {mode === "register" && <span className="text-rose-500 font-bold">* (Wajib)</span>}
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
          )}

          {mode !== "verify" && (
            <div>
              <label className="text-xs font-semibold text-foreground block mb-1.5">Password</label>
              <div className="relative">
                <Lock className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full pl-9 pr-3 py-2.5 rounded-xl bg-secondary border border-border text-foreground text-sm focus:outline-none focus:border-[#f0b000]"
                />
              </div>
            </div>
          )}

          {mode === "register" && (
            <div>
              <label className="text-xs font-semibold text-foreground block mb-1.5">Mata Uang Utama</label>
              <select
                value={baseCurrency}
                onChange={(e) => setBaseCurrency(e.target.value)}
                className="w-full px-3 py-2.5 rounded-xl bg-secondary border border-border text-foreground text-sm focus:outline-none focus:border-[#f0b000]"
              >
                <option value="IDR">IDR (Rupiah)</option>
                <option value="USD">USD (US Dollar)</option>
                <option value="SGD">SGD (Singapore Dollar)</option>
                <option value="EUR">EUR (Euro)</option>
              </select>
            </div>
          )}

          {mode === "verify" && (
            <div className="space-y-3">
              <div>
                <label className="text-xs font-semibold text-foreground block mb-1.5">
                  Kode Verifikasi OTP (6-Digit)
                </label>
                <div className="relative">
                  <KeyRound className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    maxLength={6}
                    required
                    value={otpCode}
                    onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, ""))}
                    placeholder="123456"
                    className="w-full pl-9 pr-3 py-3 rounded-xl bg-secondary border-2 border-[#f0b000]/40 text-foreground text-center text-xl font-bold tracking-widest focus:outline-none focus:border-[#f0b000]"
                  />
                </div>
              </div>

              <div className="flex items-center justify-between text-xs pt-1">
                <span className="text-muted-foreground">Tidak menerima kode?</span>
                <button
                  type="button"
                  onClick={handleResend}
                  disabled={resendCooldown > 0 || loading}
                  className="font-semibold text-[#8a6300] dark:text-[#f0b000] hover:underline disabled:opacity-50 flex items-center gap-1"
                >
                  <RefreshCw className="w-3 h-3" />
                  <span>
                    {resendCooldown > 0 ? `Kirim Ulang (${resendCooldown}s)` : "Kirim Ulang Kode"}
                  </span>
                </button>
              </div>
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 px-4 rounded-xl bg-primary hover:bg-primary/90 disabled:opacity-50 text-primary-foreground font-bold text-sm flex items-center justify-center gap-2 transition-colors shadow-lg shadow-[#f0b000]/20"
          >
            <span>
              {loading
                ? "Memproses..."
                : mode === "login"
                ? "Masuk ke Dashboard"
                : mode === "register"
                ? "Daftar & Kirim Kode Verifikasi"
                : "Verifikasi Akun Sekarang"}
            </span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </form>
      </div>
    </div>
  );
}
