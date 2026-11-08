"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Lock, Mail, User as UserIcon, ArrowRight, ArrowLeft } from "lucide-react";
import { hasAuthToken, loginUser, registerUser } from "@/lib/api";
import { AppLogo } from "@/components/AppLogo";
import { ThemeToggle } from "@/components/ThemeToggle";

export function AuthScreen({ defaultMode = "login" }: { defaultMode?: "login" | "register" }) {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">(defaultMode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [baseCurrency, setBaseCurrency] = useState("IDR");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (hasAuthToken()) {
      router.replace("/dashboard");
      return;
    }
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const qMode = params.get("mode");
      if (qMode === "register" || qMode === "login") {
        setMode(qMode);
      }
    }
  }, [router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (mode === "login") {
        await loginUser(email, password);
      } else {
        await registerUser({
          email,
          password,
          full_name: fullName || undefined,
          base_currency: baseCurrency,
        });
      }
      router.replace("/dashboard");
    } catch (err: any) {
      setError(err?.message || "Autentikasi gagal. Periksa kembali email & password Anda.");
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
        <div className="grid grid-cols-2 gap-1.5 p-1 rounded-xl bg-secondary mb-6 border border-border">
          <button
            type="button"
            onClick={() => {
              setMode("login");
              setError(null);
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

        <h1 className="text-xl font-bold text-foreground">
          {mode === "login" ? "Selamat Datang Kembali" : "Buat Akun AI-Finance"}
        </h1>
        <p className="text-xs text-muted-foreground mt-1">
          {mode === "login"
            ? "Masuk untuk mengatur alokasi gajian per dompet & diskusi bersama AI Financial Planner."
            : "Otomatis mendapatkan dompet awal yang bebas Anda kustomisasi nama dan tipenya."}
        </p>

        {error && (
          <div className="mt-4 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-600 dark:text-rose-400 text-xs font-medium">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          {mode === "register" && (
            <div>
              <label className="text-xs font-semibold text-foreground block mb-1.5">Nama Lengkap</label>
              <div className="relative">
                <UserIcon className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Contoh: Dio Pratama"
                  className="w-full pl-9 pr-3 py-2.5 rounded-xl bg-secondary border border-border text-foreground text-sm focus:outline-none focus:border-[#f0b000]"
                />
              </div>
            </div>
          )}

          <div>
            <label className="text-xs font-semibold text-foreground block mb-1.5">Email</label>
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
              </select>
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 px-4 rounded-xl bg-primary hover:bg-primary/90 disabled:opacity-50 text-primary-foreground font-bold text-sm flex items-center justify-center gap-2 transition-colors shadow-lg shadow-[#f0b000]/20"
          >
            <span>{loading ? "Memproses..." : mode === "login" ? "Masuk ke Dashboard" : "Buat Akun & Mulai"}</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </form>
      </div>
    </div>
  );
}

