"use client";

import { useEffect, useState } from "react";
import {
  Bot,
  Send,
  Mic,
  Camera,
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
  const [simText, setSimText] = useState<string>("beli kopi kenangan 28rb pake gopay");
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
        <h1 className="text-2xl font-bold tracking-tight text-white">Integrasi Chatbot (WhatsApp & Telegram)</h1>
        <p className="text-sm text-slate-400 mt-1">
          Catat pengeluaran semudah chat ke teman. Kirim teks kasual, voice note, atau foto struk kasir tanpa membuka dashboard.
        </p>
      </div>

      {/* Grid: Pairing Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Telegram Card */}
        <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-sm flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-sky-500/10 text-sky-400 flex items-center justify-center font-bold">
                  <Bot className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-white text-base">Telegram Bot</h3>
                  <span className="text-xs text-slate-400">@AIFinanceExpenseBot</span>
                </div>
              </div>

              {botStatus.TELEGRAM.connected ? (
                <span className="flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>Terhubung</span>
                </span>
              ) : (
                <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-800 text-slate-400">
                  Belum Terhubung
                </span>
              )}
            </div>

            <p className="text-xs text-slate-400 mt-4 leading-relaxed">
              Mendukung pesan teks kasual, voice note audio instan, dan foto nota struk kasir melalui bot Telegram resmi kami.
            </p>
          </div>

          <div className="pt-4 border-t border-slate-800">
            <button
              onClick={() => handleGenerateCode("TELEGRAM")}
              disabled={loadingCode}
              className="w-full py-2.5 px-4 rounded-xl text-xs font-bold bg-sky-500 hover:bg-sky-600 text-slate-950 transition-colors shadow-sm"
            >
              {loadingCode && pairingPlatform === "TELEGRAM" ? "Menghasilkan Kode..." : "Hubungkan Akun Telegram"}
            </button>
          </div>
        </div>

        {/* WhatsApp Card */}
        <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-sm flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-emerald-500/10 text-emerald-400 flex items-center justify-center font-bold">
                  <Bot className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-white text-base">WhatsApp Cloud Bot</h3>
                  <span className="text-xs text-slate-400">+62 812-XXXX-XXXX (Cloud API)</span>
                </div>
              </div>

              {botStatus.WHATSAPP.connected ? (
                <span className="flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>Terhubung</span>
                </span>
              ) : (
                <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-800 text-slate-400">
                  Belum Terhubung
                </span>
              )}
            </div>

            <p className="text-xs text-slate-400 mt-4 leading-relaxed">
              Integrasi langsung via Meta WhatsApp Cloud API untuk pencatatan instan melalui pesan harian WhatsApp Anda.
            </p>
          </div>

          <div className="pt-4 border-t border-slate-800">
            <button
              onClick={() => handleGenerateCode("WHATSAPP")}
              disabled={loadingCode}
              className="w-full py-2.5 px-4 rounded-xl text-xs font-bold bg-emerald-500 hover:bg-emerald-600 text-slate-950 transition-colors shadow-sm"
            >
              {loadingCode && pairingPlatform === "WHATSAPP" ? "Menghasilkan Kode..." : "Hubungkan Akun WhatsApp"}
            </button>
          </div>
        </div>
      </div>

      {/* Pairing Code Banner (if generated) */}
      {pairingCode && (
        <div className="p-6 rounded-2xl bg-gradient-to-r from-emerald-950/40 via-slate-900 to-slate-900 border border-emerald-500/30 shadow-lg flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <span className="text-xs font-bold text-emerald-400 uppercase tracking-wider">
              Kode Pairing Aktif (Berlaku 15 Menit)
            </span>
            <div className="text-2xl font-mono font-extrabold text-white mt-1">
              /pair {pairingCode}
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Buka aplikasi {pairingPlatform} Anda, cari bot kami, dan kirim pesan persis seperti di atas.
            </p>
          </div>

          <button
            onClick={handleCopy}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-semibold transition-colors self-start sm:self-auto"
          >
            {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
            <span>{copied ? "Tersalin ke Clipboard" : "Salin Perintah /pair"}</span>
          </button>
        </div>
      )}

      {/* Simulator Section: Test Chatbot In-Browser */}
      <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-sm space-y-6">
        <div>
          <div className="flex items-center gap-2 text-emerald-400 text-xs font-bold uppercase tracking-wider">
            <Sparkles className="w-4 h-4" />
            <span>Interactive Chatbot Simulator</span>
          </div>
          <h2 className="text-lg font-bold text-white mt-1">Uji Coba Pengenalan Bahasa Alami (NLU) & Bot</h2>
          <p className="text-xs text-slate-400 mt-1">
            Coba ketikkan kalimat pengeluaran dalam bahasa sehari-hari. Sistem AI kami akan mem-parsing nominal, dompet, dan kategorinya secara otomatis.
          </p>
        </div>

        {/* Quick Presets */}
        <div className="space-y-2">
          <span className="text-xs text-slate-400 font-medium">Contoh Kalimat Siap Uji:</span>
          <div className="flex flex-wrap gap-2">
            {[
              { label: "☕ Kopi Kenangan 28rb (GoPay)", text: "beli kopi kenangan 28rb pake gopay", src: "TELEGRAM" },
              { label: "⛽ Bensin 50rb (Cash)", text: "isi bensin pertamax 50rb cash", src: "WHATSAPP" },
              { label: "🍛 Nasi Padang 35k (BCA)", text: "makan siang nasi padang 35k dari bca", src: "VOICE" },
              { label: "💰 Gaji Bulanan 15jt (BCA)", text: "gaji masuk 15jt ke bca", src: "TELEGRAM" },
              { label: "🎬 Netflix $15 (USD)", text: "langganan netflix $15 pake bca", src: "WHATSAPP" },
            ].map((p, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => handleQuickPreset(p.text, p.src)}
                className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 text-xs font-medium transition-colors"
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
              className="flex-1 px-4 py-3 rounded-xl bg-slate-800 border border-slate-700 text-white text-sm focus:outline-none focus:border-emerald-500"
              required
            />
            <button
              type="submit"
              disabled={simLoading}
              className="px-5 py-3 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold text-xs flex items-center gap-2 shadow-sm transition-colors"
            >
              <Send className="w-4 h-4" />
              <span>{simLoading ? "Parsing..." : "Kirim Chat"}</span>
            </button>
          </div>
        </form>

        {/* Simulator Result Card (Mock Chat Bubble) */}
        {simResult && (
          <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 flex items-start gap-3 mt-4">
            <div className="w-8 h-8 rounded-lg bg-emerald-500/20 text-emerald-400 flex items-center justify-center shrink-0 font-bold text-sm">
              🤖
            </div>
            <div className="flex-1">
              <div className="text-xs font-bold text-emerald-400 mb-1">Balasan Bot:</div>
              <pre className="text-xs text-slate-200 whitespace-pre-wrap font-sans leading-relaxed">
                {simResult.message}
              </pre>

              {simResult.parsed && (
                <div className="mt-3 pt-3 border-t border-slate-800 flex flex-wrap gap-2 text-[11px] text-slate-400">
                  <span>Tipe: <strong className="text-slate-200">{simResult.parsed.type}</strong></span>
                  <span>•</span>
                  <span>Kategori Terdeteksi: <strong className="text-slate-200">{simResult.parsed.category_name}</strong></span>
                  <span>•</span>
                  <span>Confidence: <strong className="text-emerald-400">{Math.round(simResult.parsed.confidence * 100)}%</strong></span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

