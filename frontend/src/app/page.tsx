"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Bot,
  Calculator,
  CheckCircle2,
  Database,
  Flame,
  Layers,
  MoonStar,
  ShieldCheck,
  Sparkles,
  Target,
  Wallet,
} from "lucide-react";
import { AppLogo } from "@/components/AppLogo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { hasAuthToken } from "@/lib/api";

const STEPS = [
  {
    n: "01",
    title: "Atur Dompet & Alokasi Gajian",
    desc: "Buat dompet custom (Mandiri, Jago, Danamon, Kantong Syariah) lalu bagi pos bulanan & Sinking Fund dalam 1 klik.",
  },
  {
    n: "02",
    title: "Catat Instan via Chat WA & Telegram",
    desc: "Ketik 'isi bensin 250rb'—bot otomatis mengenali pos anggaran dan memotong saldo dompet Fund Location terkait.",
  },
  {
    n: "03",
    title: "Diskusi AI Planner & Kejar FIRE",
    desc: "Ngobrol santai soal arus kas, KPR, dana darurat, investasi Konvensional/Syariah, hingga peta jalan pensiun dini.",
  },
];

const FEATURES = [
  {
    icon: Target,
    title: "Payday Allocation & Fund Location",
    desc: "Tabel anggaran bergaya spreadsheet modern yang terhubung langsung ke dompet penempatan dana lengkap dengan asisten Distribusi Gajian 1-klik.",
    accent: "text-[#8a6300] dark:text-[#f0b000] bg-[#f0b000]/10 border-[#f0b000]/25",
  },
  {
    icon: Layers,
    title: "Predictable Saving (Sinking Fund)",
    desc: "Pisahkan pengeluaran rutin bulanan dari tabungan terjadwal (Umrah, Pelunasan KPR, Pajak Mobil, Qurban) yang otomatis terakumulasi lintas bulan.",
    accent: "text-amber-700 dark:text-amber-400 bg-amber-500/10 border-amber-500/20",
  },
  {
    icon: Bot,
    title: "Smart Chatbot WhatsApp & Telegram",
    desc: "Catat pengeluaran lewat chat kasual tanpa buka dashboard. Sistem otomatis mencocokkan pos anggaran & memotong saldo bank tujuan.",
    accent: "text-cyan-700 dark:text-cyan-400 bg-cyan-500/10 border-cyan-500/20",
  },
  {
    icon: Sparkles,
    title: "Adaptive AI Financial Planner",
    desc: "10 modul keahlian finansial (arus kas, dana darurat, DSR utang, pajak, proteksi, portofolio) dengan percakapan hangat & progressive profiling.",
    accent: "text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
  },
  {
    icon: MoonStar,
    title: "Mode Konvensional & Syariah",
    desc: "Aktifkan preferensi Syariah kapan saja untuk rekomendasi instrumen halal (Sukuk Negara, Reksa Dana Syariah, Saham ISSI, Emas) & pos Zakat/Sedekah.",
    accent: "text-teal-700 dark:text-teal-400 bg-teal-500/10 border-teal-500/20",
  },
  {
    icon: Flame,
    title: "Simulator FIRE & 100% Custom",
    desc: "Simulasi Rule of 25 & Coast FIRE real-time, didukung kebebasan kustomisasi penuh pada Nama Dompet, Tipe Akun, Grup TYPE, dan Kategori.",
    accent: "text-rose-700 dark:text-rose-400 bg-rose-500/10 border-rose-500/20",
  },
];

const SAMPLE_PREVIEW_ROWS = [
  { group: "LIVING NEEDS", item: "KPR Rumah", budget: "Rp 6.301.363", wallet: "Mandiri", pct: "35.05%" },
  { group: "LIVING NEEDS", item: "Bensin Mobil + Motor", budget: "Rp 1.000.000", wallet: "Danamon", pct: "" },
  { group: "LIFE STYLE", item: "Kebutuhan Keluarga & Hiburan", budget: "Rp 8.250.000", wallet: "Jago", pct: "13.25%" },
  { group: "ZAKAT & SEDEKAH", item: "Sedekah & Orang Tua", budget: "Rp 2.270.000", wallet: "Danamon", pct: "3.65%" },
  { group: "PREDICTABLE SAVING", item: "Pelunasan KPR & Nabung Umrah", budget: "Rp 13.408.637", wallet: "Mandiri / Jago", pct: "21.54%" },
];

export default function LandingPage() {
  const [loggedIn, setLoggedIn] = useState(false);

  useEffect(() => {
    setLoggedIn(hasAuthToken());
  }, []);

  return (
    <div className="min-h-screen bg-background text-foreground font-sans">
      {/* Sticky Glass Header */}
      <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-6 py-3.5 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5">
            <AppLogo size={36} />
            <span className="font-bold text-lg tracking-tight">AI-Finance</span>
          </Link>

          <div className="flex items-center gap-2 sm:gap-3">
            <a
              href="#alokasi-preview"
              className="hidden md:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold text-foreground hover:bg-accent transition-colors"
            >
              <Wallet className="h-4 w-4 text-[#8a6300] dark:text-[#f0b000]" />
              <span>Alokasi Gajian</span>
            </a>

            <a
              href="#fitur"
              className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
            >
              <Calculator className="h-4 w-4" />
              <span>Fitur</span>
            </a>

            <ThemeToggle />

            <div className="h-5 w-px bg-border mx-1 hidden sm:block" />

            {loggedIn ? (
              <Link
                href="/dashboard"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm transition-colors"
              >
                <span>Buka Dashboard</span>
                <ArrowRight className="h-4 w-4" />
              </Link>
            ) : (
              <>
                <Link
                  href="/login"
                  className="px-4 py-2 rounded-lg text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                >
                  Masuk
                </Link>
                <Link
                  href="/register"
                  className="px-4 py-2 rounded-lg text-sm font-semibold bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm transition-colors"
                >
                  Mulai Gratis
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_60%_50%_at_50%_-10%,rgba(240,176,0,0.20),transparent)] dark:bg-[radial-gradient(ellipse_60%_50%_at_50%_-10%,rgba(240,176,0,0.18),transparent)] pointer-events-none" />
        <div className="max-w-4xl mx-auto px-6 pt-20 pb-16 text-center relative">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-semibold bg-accent text-[#8a6300] dark:text-[#f0b000] border border-[#f0b000]/30 mb-6">
            <Sparkles className="h-3.5 w-3.5" />
            <span>Zero-Based Payday Budgeting &bull; Multimodal Bot &bull; AI Financial Planner</span>
          </div>

          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight leading-[1.12]">
            Kelola Gaji, Dompet &amp; Kebebasan Finansial
            <br />
            <span className="bg-gradient-to-r from-[#8a6300] via-[#f0b000] to-[#b88600] dark:from-[#f0b000] dark:via-amber-300 dark:to-[#f0b000] bg-clip-text text-transparent">
              Bersama Asisten AI Cerdas
            </span>
          </h1>

          <p className="mt-6 text-base sm:text-lg text-muted-foreground max-w-2xl mx-auto leading-relaxed">
            Ubah kebiasaan <em>spreadsheet</em> bulanan menjadi sistem otomatis yang terhubung ke saldo dompet nyata,
            pencatatan chat WhatsApp/Telegram, <em>Sinking Fund</em> lintas bulan, dan perencanaan menuju FIRE.
          </p>

          <div className="mt-9 flex flex-col sm:flex-row items-center justify-center gap-3">
            <Link
              href={loggedIn ? "/dashboard" : "/register"}
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl font-semibold bg-primary text-primary-foreground hover:bg-primary/90 shadow-lg shadow-[#f0b000]/25 transition-all"
            >
              <span>{loggedIn ? "Masuk ke Workspace Anda" : "Mulai Atur Keuangan Gratis"}</span>
              <ArrowRight className="h-4 w-4" />
            </Link>
            <a
              href="#alokasi-preview"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl font-semibold bg-card border border-border hover:bg-accent transition-colors"
            >
              <Target className="h-4 w-4 text-[#8a6300] dark:text-[#f0b000]" />
              <span>Lihat Cara Kerja Alokasi Gajian</span>
            </a>
          </div>
        </div>
      </section>

      {/* Spreadsheet Payday Allocation Preview */}
      <section id="alokasi-preview" className="max-w-6xl mx-auto px-6 py-8">
        <div className="rounded-3xl bg-card border border-border shadow-xl overflow-hidden">
          <div className="px-6 py-4 border-b border-border bg-secondary/60 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <span className="w-3 h-3 rounded-full bg-rose-500/80" />
              <span className="w-3 h-3 rounded-full bg-[#f0b000]" />
              <span className="w-3 h-3 rounded-full bg-emerald-500/80" />
              <span className="ml-2 text-xs font-semibold text-muted-foreground">
                Pratinjau Alokasi Anggaran Terhubung Dompet (Fund Location)
              </span>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className="px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 font-semibold inline-flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" /> Mandiri: Funded
              </span>
              <span className="px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 font-semibold inline-flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" /> Jago: Funded
              </span>
              <span className="px-2.5 py-1 rounded-full bg-accent text-[#8a6300] dark:text-[#f0b000] border border-[#f0b000]/30 font-semibold">
                ⚡ 1-Klik Distribusi Gajian
              </span>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs sm:text-sm">
              <thead className="bg-secondary/40 text-muted-foreground uppercase text-[11px] font-bold border-b border-border">
                <tr>
                  <th className="py-3 px-5">TYPE (Custom)</th>
                  <th className="py-3 px-5">CATEGORY / POS</th>
                  <th className="py-3 px-5 text-right">BUDGET</th>
                  <th className="py-3 px-5">FUND LOCATION</th>
                  <th className="py-3 px-5 text-right">PORSI GAJI</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {SAMPLE_PREVIEW_ROWS.map((row, idx) => (
                  <tr key={idx} className="hover:bg-secondary/40 transition-colors">
                    <td className="py-3 px-5 font-bold text-xs tracking-wide text-[#8a6300] dark:text-[#f0b000]">
                      {row.group}
                    </td>
                    <td className="py-3 px-5 font-medium text-foreground">{row.item}</td>
                    <td className="py-3 px-5 text-right font-mono font-semibold text-foreground">{row.budget}</td>
                    <td className="py-3 px-5">
                      <span className="px-2.5 py-1 rounded-lg bg-secondary border border-border text-xs font-semibold">
                        {row.wallet}
                      </span>
                    </td>
                    <td className="py-3 px-5 text-right font-bold text-muted-foreground">{row.pct || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section className="max-w-6xl mx-auto px-6 py-16">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {STEPS.map((s) => (
            <div key={s.n} className="rounded-2xl bg-card border border-border p-6 shadow-sm">
              <div className="text-3xl font-bold text-primary/40 font-mono">{s.n}</div>
              <h3 className="mt-3 font-semibold text-lg text-foreground">{s.title}</h3>
              <p className="mt-1.5 text-sm text-muted-foreground leading-relaxed">{s.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Features Grid */}
      <section id="fitur" className="max-w-6xl mx-auto px-6 py-8">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold tracking-tight">Fitur Utama</h2>
          <p className="mt-3 text-muted-foreground">
            Dirancang untuk eksekusi keuangan rumah tangga maupun personal secara presisi dan fleksibel.
          </p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {FEATURES.map((f) => (
            <div
              key={f.title}
              className="rounded-2xl bg-card border border-border p-6 hover:border-[#f0b000]/50 hover:-translate-y-0.5 transition-all shadow-sm"
            >
              <div className={`h-11 w-11 rounded-xl border flex items-center justify-center mb-4 ${f.accent}`}>
                <f.icon className="h-5 w-5" />
              </div>
              <h3 className="font-semibold text-base text-foreground">{f.title}</h3>
              <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Privacy & AI Financial Planner Callout */}
      <section className="max-w-6xl mx-auto px-6 py-12">
        <div className="rounded-3xl border border-[#f0b000]/30 bg-gradient-to-br from-[#f0b000]/10 via-card to-amber-500/10 p-8 sm:p-12 relative overflow-hidden">
          <div className="max-w-2xl">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-accent text-[#8a6300] dark:text-[#f0b000] border border-[#f0b000]/30 mb-4">
              <ShieldCheck className="h-4 w-4" />
              <span>Privasi Penuh &bull; Tanpa Kredensial M-Banking</span>
            </div>
            <h2 className="text-2xl sm:text-3xl font-bold tracking-tight">
              Kendali Penuh Atas Data Finansial Anda
            </h2>
            <p className="mt-3 text-sm sm:text-base text-muted-foreground leading-relaxed">
              Anda tidak perlu menyerahkan akses login rekening bank ke pihak ketiga. Seluruh dompet dikelola mandiri
              dengan nama &amp; tipe kustom, database PostgreSQL terisolasi, serta dukungan perencanaan keuangan adaptif
              tanpa kewajiban mengisi formulir panjang di awal.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link
                href={loggedIn ? "/planner" : "/register"}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl font-semibold bg-primary text-primary-foreground hover:bg-primary/90 shadow-md transition-all text-sm"
              >
                <span>Diskusi dengan AI Planner</span>
                <ArrowRight className="h-4 w-4" />
              </Link>
              <Link
                href={loggedIn ? "/budgets" : "/login"}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl font-medium bg-secondary border border-border text-foreground hover:bg-accent transition-colors text-sm"
              >
                <Database className="h-4 w-4 text-[#8a6300] dark:text-[#f0b000]" />
                <span>Susun Alokasi Bulanan</span>
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Bottom CTA Banner */}
      <section className="max-w-4xl mx-auto px-6 py-16">
        <div className="rounded-3xl border border-[#f0b000]/30 bg-gradient-to-br from-[#f0b000]/15 to-amber-500/15 dark:from-[#f0b000]/10 dark:to-amber-500/10 p-10 sm:p-12 text-center">
          <h2 className="text-3xl font-bold tracking-tight">Siap merapikan arus kas gajian bulan ini?</h2>
          <p className="mt-3 text-muted-foreground max-w-lg mx-auto">
            Hubungkan pos anggaran ke masing-masing dompet dan pantau perjalanan menuju kebebasan finansial Anda.
          </p>
          <Link
            href={loggedIn ? "/dashboard" : "/register"}
            className="inline-flex items-center gap-2 mt-7 px-7 py-3 rounded-xl font-semibold bg-primary text-primary-foreground hover:bg-primary/90 shadow-lg shadow-[#f0b000]/25 transition-colors"
          >
            <span>{loggedIn ? "Buka Dashboard Sekarang" : "Buat Akun Gratis"}</span>
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border">
        <div className="max-w-7xl mx-auto px-6 py-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-muted-foreground">
          <span>AI-Finance &mdash; Smart Wealth, Payday Budgeting &amp; Financial Freedom</span>
          <div className="flex items-center gap-4 text-xs sm:text-sm">
            <Link href="/login" className="hover:text-foreground transition-colors font-medium">
              Masuk
            </Link>
            <span>&middot;</span>
            <Link href="/register" className="hover:text-foreground transition-colors">
              Daftar
            </Link>
            <span>&middot;</span>
            <span>Multi-Wallet &middot; Sinking Fund &middot; FIRE</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
