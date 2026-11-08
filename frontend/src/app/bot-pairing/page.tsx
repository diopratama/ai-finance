"use client";

import { useEffect, useState } from "react";
import {
  Bot,
  Send,
  CheckCircle2,
  AlertCircle,
  Copy,
  Check,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { generatePairingCode, getBotStatus, simulateChatMessage } from "@/lib/api";
import { BotStatusMap } from "@/lib/types";

export default function BotPairingPage() {
  const [botStatus, setBotStatus] = useState<BotStatusMap>({
    TELEGRAM: { connected: false, username: null },
    WHATSAPP: { connected: false, username: null },
  });

  const [pairingCode, setPairingCode] = useState<string | null>(null);
  const [pairingPlatform, setPairingPlatform] = useState<string>("TELEGRAM");
  const [copied, setCopied] = useState<boolean>(false);
  const [loadingCode, setLoadingCode] = useState<boolean>(false);

  // Simulator states
  const [simText, setSimText] = useState<string>("isi bensin 250rb");
  const [simSource, setSimSource] = useState<string>("TELEGRAM");
  const [simLoading, setSimLoading] = useState<boolean>(false);
  const [simResult, setSimResult] = useState<any>(null);

  const fetchStatus = async () => {
    const s = await getBotStatus();
    setBotStatus(s);
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const handleGenerateCode = async (platform: "TELEGRAM" | "WHATSAPP") => {
    setLoadingCode(true);
    setPairingPlatform(platform);
    try {
      const res = await generatePairingCode(platform);
      setPairingCode(res.pairing_code);
    } finally {
      setLoadingCode(false);
    }
  };

  const handleCopy = () => {
    if (!pairingCode) return;
    navigator.clipboard.writeText(`/pair ${pairingCode}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSimulateSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!simText.trim()) return;

    setSimLoading(true);
    setSimResult(null);
    try {
      const res = await simulateChatMessage(simText, simSource);
      setSimResult(res);
    } catch (err: any) {
      setSimResult({ success: false, message: err.message || "Gagal memproses pesan" });
    } finally {
      setSimLoading(false);
    }
  };

  const handleQuickPreset = (txt: string, src: string = "TELEGRAM") => {
    setSimText(txt);
    setSimSource(src);
  };

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">
          Integrasi Chatbot (WhatsApp &amp; Telegram)
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Catat pengeluaran semudah chat ke teman. Bot otomatis mendeteksi pos anggaran dan dompet penempatan dana (Fund Location).
        </p>
      </div>

      {/* Grid: Pairing Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Telegram Card */}
        <div className="p-6 rounded-3xl bg-card border border-border shadow-sm flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-11 h-11 rounded-2xl bg-sky-500/10 text-sky-600 dark:text-sky-400 border border-sky-500/20 flex items-center justify-center font-bold">
                  <Bot className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-foreground text-base">Telegram Bot</h3>
                  <span className="text-xs text-muted-foreground">@AIFinanceExpenseBot</span>
                </div>
              </div>

              {botStatus.TELEGRAM.connected ? (
                <span className="flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>Terhubung</span>
                </span>
              ) : (
                <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-secondary text-muted-foreground border border-border">
                  Belum Terhubung
                </span>
              )}
            </div>

            <p className="text-xs text-muted-foreground mt-4 leading-relaxed">
              Mendukung pesan teks kasual, voice note audio instan, dan foto nota struk kasir melalui bot Telegram resmi kami.
            </p>
          </div>

          <div className="pt-4 border-t border-border">
            <button
              onClick={() => handleGenerateCode("TELEGRAM")}
              disabled={loadingCode}
              className="w-full py-2.5 px-4 rounded-xl text-xs font-bold bg-primary hover:bg-primary/90 text-primary-foreground transition-colors shadow-sm"
            >
              {loadingCode && pairingPlatform === "TELEGRAM" ? "Menghasilkan Kode..." : "Hubungkan Akun Telegram"}
            </button>
          </div>
        </div>

        {/* WhatsApp Card */}
        <div className="p-6 rounded-3xl bg-card border border-border shadow-sm flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-11 h-11 rounded-2xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 flex items-center justify-center font-bold">
                  <Bot className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-foreground text-base">WhatsApp Cloud Bot</h3>
                  <span className="text-xs text-muted-foreground">+62 812-XXXX-XXXX (Cloud API)</span>
                </div>
              </div>

              {botStatus.WHATSAPP.connected ? (
                <span className="flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>Terhubung</span>
                </span>
              ) : (
                <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-secondary text-muted-foreground border border-border">
                  Belum Terhubung
                </span>
              )}
            </div>

            <p className="text-xs text-muted-foreground mt-4 leading-relaxed">
              Integrasi langsung via Meta WhatsApp Cloud API untuk pencatatan instan melalui pesan harian WhatsApp Anda.
            </p>
          </div>

          <div className="pt-4 border-t border-border">
            <button
              onClick={() => handleGenerateCode("WHATSAPP")}
              disabled={loadingCode}
              className="w-full py-2.5 px-4 rounded-xl text-xs font-bold bg-primary hover:bg-primary/90 text-primary-foreground transition-colors shadow-sm"
            >
              {loadingCode && pairingPlatform === "WHATSAPP" ? "Menghasilkan Kode..." : "Hubungkan Akun WhatsApp"}
            </button>
          </div>
        </div>
      </div>

      {/* Pairing Code Banner (if generated) */}
      {pairingCode && (
        <div className="p-6 rounded-3xl bg-accent border border-[#f0b000]/30 shadow-lg flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <span className="text-xs font-bold text-[#8a6300] dark:text-[#f0b000] uppercase tracking-wider">
              Kode Pairing Aktif (Berlaku 15 Menit)
            </span>
            <div className="text-2xl font-mono font-extrabold text-foreground mt-1">
              /pair {pairingCode}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Buka aplikasi {pairingPlatform} Anda, cari bot kami, dan kirim pesan persis seperti di atas.
            </p>
          </div>

          <button
            onClick={handleCopy}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-card hover:bg-secondary text-foreground border border-border text-xs font-semibold transition-colors self-start sm:self-auto"
          >
            {copied ? <Check className="w-4 h-4 text-emerald-600 dark:text-emerald-400" /> : <Copy className="w-4 h-4" />}
            <span>{copied ? "Tersalin ke Clipboard" : "Salin Perintah /pair"}</span>
          </button>
        </div>
      )}

      {/* Simulator Section: Test Chatbot In-Browser */}
      <div className="p-6 rounded-3xl bg-card border border-border shadow-sm space-y-6">
        <div>
          <div className="flex items-center gap-2 text-[#8a6300] dark:text-[#f0b000] text-xs font-bold uppercase tracking-wider">
            <Sparkles className="w-4 h-4" />
            <span>Interactive Chatbot Simulator</span>
          </div>
          <h2 className="text-lg font-bold text-foreground mt-1">
            Uji Coba Pengenalan Pos Anggaran &amp; Dompet Otomatis
          </h2>
          <p className="text-xs text-muted-foreground mt-1">
            Coba ketikkan kalimat pengeluaran dalam bahasa sehari-hari. Sistem kami otomatis memotong dompet Fund Location pos terkait meskipun Anda tidak menyebut nama bank di chat!
          </p>
        </div>

        {/* Quick Presets */}
        <div className="space-y-2">
          <span className="text-xs text-muted-foreground font-medium">Contoh Kalimat Siap Uji:</span>
          <div className="flex flex-wrap gap-2">
            {[
              { label: "⛽ Isi Bensin 250rb (Auto-Danamon)", text: "isi bensin 250rb", src: "WHATSAPP" },
              { label: "💧 Bayar PDAM 250k (Auto-Jago)", text: "bayar pdam 250k", src: "TELEGRAM" },
              { label: "☕ Kopi Kenangan 28rb pake GoPay", text: "beli kopi kenangan 28rb pake gopay", src: "TELEGRAM" },
              { label: "💰 Gaji Masuk 15jt ke BCA", text: "gaji masuk 15jt ke bca", src: "WHATSAPP" },
            ].map((p, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => handleQuickPreset(p.text, p.src)}
                className="px-3 py-1.5 rounded-xl bg-secondary hover:bg-accent border border-border text-foreground text-xs font-medium transition-colors"
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {/* Simulator Input Form */}
        <form onSubmit={handleSimulateSend} className="space-y-3">
          <div className="flex gap-2">
            <input
              type="text"
              value={simText}
              onChange={(e) => setSimText(e.target.value)}
              placeholder="Ketik pesan seperti di chat WhatsApp/Telegram..."
              className="flex-1 px-4 py-3 rounded-xl bg-secondary border border-border text-foreground text-sm focus:outline-none focus:border-[#f0b000]"
              required
            />
            <button
              type="submit"
              disabled={simLoading}
              className="px-5 py-3 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground font-bold text-xs flex items-center gap-2 shadow-sm shadow-[#f0b000]/20 transition-colors"
            >
              <Send className="w-4 h-4" />
              <span>{simLoading ? "Parsing..." : "Kirim Chat"}</span>
            </button>
          </div>
        </form>

        {/* Simulator Result Card */}
        {simResult && (
          <div className="p-5 rounded-2xl bg-secondary/80 border border-border flex items-start gap-3 mt-4">
            <div className="w-8 h-8 rounded-xl bg-accent text-[#8a6300] dark:text-[#f0b000] flex items-center justify-center shrink-0 font-bold text-sm">
              🤖
            </div>
            <div className="flex-1">
              <div className="text-xs font-bold text-[#8a6300] dark:text-[#f0b000] mb-1">Balasan Bot:</div>
              <pre className="text-xs text-foreground whitespace-pre-wrap font-sans leading-relaxed">
                {simResult.message}
              </pre>

              {simResult.parsed && (
                <div className="mt-3 pt-3 border-t border-border flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                  <span>Tipe: <strong className="text-foreground">{simResult.parsed.type}</strong></span>
                  <span>&bull;</span>
                  <span>Kategori: <strong className="text-foreground">{simResult.parsed.category_name}</strong></span>
                  {simResult.matched_budget && (
                    <>
                      <span>&bull;</span>
                      <span>Pos Anggaran: <strong className="text-[#8a6300] dark:text-[#f0b000]">{simResult.matched_budget.name}</strong></span>
                    </>
                  )}
                  <span>&bull;</span>
                  <span>Dompet Terpotong: <strong className="text-foreground">{simResult.wallet?.name}</strong></span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
