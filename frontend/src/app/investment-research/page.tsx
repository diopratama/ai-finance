"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  TrendingUp,
  TrendingDown,
  Search,
  Sparkles,
  ShieldCheck,
  AlertCircle,
  Calendar,
  Layers,
  Bot,
  Play,
  Square,
  Clock,
  ExternalLink,
  ChevronRight,
  Info,
  FileText,
  Send,
  History,
  Trash2,
  Building2,
  Coins,
  Globe,
  SlidersHorizontal,
  CheckCircle2,
  XCircle,
  HelpCircle,
  Radar,
  Activity,
  ArrowUpRight,
  ShieldAlert,
  Crosshair,
  Gauge,
  Check,
  RefreshCw,
} from "lucide-react";
import {
  chatWithInvestmentAgent,
  deleteInvestmentHistory,
  getInvestmentHistory,
  getInvestmentHistoryDetail,
  getInvestmentQuote,
  getShariaStocksReference,
  stopInvestmentTask,
} from "@/lib/api";
import {
  AnalysisType,
  ChatMode,
  InvestmentHistoryItem,
  InvestmentQuote,
  InvestmentRecommendation,
  InvestmentSwarmResult,
  RankedCandidate,
  RecommendationResult,
  ShariaStockIssuer,
  ValidationMeta,
} from "@/lib/types";
import { formatCurrency } from "@/lib/utils";

const MARKETS = [
  { id: "ihsg_syariah", label: "IHSG Syariah (ISSI)", icon: ShieldCheck, defaultTicker: "TLKM" },
  { id: "ihsg", label: "IHSG Konvensional", icon: Building2, defaultTicker: "BBCA" },
  { id: "crypto", label: "Crypto (Bluechip & Web3)", icon: Coins, defaultTicker: "BTC" },
  { id: "us_stock", label: "US Equities (S&P 500)", icon: Globe, defaultTicker: "AAPL" },
  { id: "us_etf", label: "US & Global ETFs", icon: Layers, defaultTicker: "VOO" },
];

const QUICK_TICKERS: Record<string, string[]> = {
  ihsg_syariah: ["TLKM", "ASII", "ICBP", "BRIS", "ADRO", "PGAS", "KLBF", "UNVR"],
  ihsg: ["BBCA", "BBRI", "BMRI", "BBNI", "ASII", "TLKM", "GOTO", "AMRT"],
  crypto: ["BTC", "ETH", "SOL", "BNB", "AVAX", "NEAR"],
  us_stock: ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA"],
  us_etf: ["VOO", "QQQ", "VTI", "SCHD", "VT", "SPY"],
};

const QUICK_AUDIT_PROMPTS = [
  { label: "🔍 Audit Divergensi 1D vs 1H", prompt: "Audit divergensi multi-timeframe 1D vs 1H dan apakah tren intraday masih selaras dengan tren makro?" },
  { label: "⚠️ Cek Price Drift & Entry", prompt: "Cek price drift terkini dari rekomendasi awal dan apakah harga sekarang masih dalam area akumulasi yang aman?" },
  { label: "🛡️ Validasi Level Support & Cutloss", prompt: "Konfirmasi validasi level support terkuat, level stop loss ketat, dan batas toleransi drawdown." },
  { label: "📊 Uji Ulang Tesis vs Berita Live", prompt: "Uji ulang tesis investasi dengan katalis berita terbaru dan risiko volatilitas pasar saat ini." },
];

interface ChatMessageItem {
  role: string;
  content: string;
  mode?: ChatMode;
  validation_meta?: ValidationMeta | null;
}

export default function InvestmentResearchPage() {
  const [analysisType, setAnalysisType] = useState<AnalysisType>("analyze");
  const [selectedMarket, setSelectedMarket] = useState("ihsg_syariah");
  const [symbol, setSymbol] = useState("TLKM");
  const [horizonFilter, setHorizonFilter] = useState<"ALL" | "SHORT" | "MEDIUM" | "LONG">("ALL");

  // Live quote
  const [quote, setQuote] = useState<InvestmentQuote | null>(null);
  const [quoteLoading, setQuoteLoading] = useState(false);

  // Swarm Execution state
  const [isRunning, setIsRunning] = useState(false);
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);
  const [agentStatuses, setAgentStatuses] = useState<Record<string, "idle" | "running" | "completed" | "failed">>({
    data_fetcher: "idle",
    technical_analyst: "idle",
    fundamental_analyst: "idle",
    on_chain_analyst: "idle",
    sentiment_analyst: "idle",
    investment_advisor: "idle",
  });
  const [liveLogs, setLiveLogs] = useState<string[]>([]);
  const [analystOutputs, setAnalystOutputs] = useState<Record<string, string>>({});
  const [activeReportTab, setActiveReportTab] = useState<string>("investment_advisor");
  const [finalResult, setFinalResult] = useState<InvestmentSwarmResult | any | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Interactive Consultant Chat & Deep Validation
  const [chatMessages, setChatMessages] = useState<ChatMessageItem[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [isChatSending, setIsChatSending] = useState(false);
  const [isDeepValidation, setIsDeepValidation] = useState(false);

  // Sharia stocks browser modal
  const [showShariaModal, setShowShariaModal] = useState(false);
  const [shariaList, setShariaList] = useState<ShariaStockIssuer[]>([]);
  const [shariaSearchQuery, setShariaSearchQuery] = useState("");
  const [shariaLoading, setShariaLoading] = useState(false);

  // Past History Drawer
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [historyList, setHistoryList] = useState<InvestmentHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const logsEndRef = useRef<HTMLDivElement>(null);

  // Fetch indicative quote when symbol or market changes (only relevant in specific analysis mode)
  useEffect(() => {
    let active = true;
    const fetchQuote = async () => {
      if (analysisType === "recommend" || !symbol.trim()) return;
      setQuoteLoading(true);
      try {
        const res = await getInvestmentQuote(selectedMarket, symbol.trim());
        if (active && res?.quote) {
          const q = res.quote;
          const candles = q.candles || [];
          const latest = candles.length > 0 ? candles[candles.length - 1] : null;
          setQuote({
            price: latest?.close ?? q.price,
            change: q.change,
            change_pct: q.change_pct,
            high: latest ? Math.max(...candles.map((c: any) => c.high)) : undefined,
            low: latest ? Math.min(...candles.map((c: any) => c.low)) : undefined,
            volume: latest?.volume,
            as_of: q.as_of,
            provider: q.provider,
          });
        }
      } catch {
        if (active) setQuote(null);
      } finally {
        if (active) setQuoteLoading(false);
      }
    };
    const timer = setTimeout(fetchQuote, 400);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [selectedMarket, symbol, analysisType]);

  // Scroll logs to bottom
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [liveLogs]);

  // Load ISSI universe on modal open
  const handleOpenShariaModal = async () => {
    setShowShariaModal(true);
    setShariaLoading(true);
    try {
      const res = await getShariaStocksReference(shariaSearchQuery);
      setShariaList(res.issuers || []);
    } catch {
      setShariaList([]);
    } finally {
      setShariaLoading(false);
    }
  };

  const handleSearchSharia = async (q: string) => {
    setShariaSearchQuery(q);
    try {
      const res = await getShariaStocksReference(q);
      setShariaList(res.issuers || []);
    } catch {}
  };

  // Load past history
  const handleOpenHistoryModal = async () => {
    setShowHistoryModal(true);
    setHistoryLoading(true);
    try {
      const list = await getInvestmentHistory();
      setHistoryList(list || []);
    } catch {
      setHistoryList([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleSelectHistoryItem = async (histId: string) => {
    try {
      const detail = await getInvestmentHistoryDetail(histId);
      if (detail?.result) {
        setFinalResult(detail.result);
        setAnalystOutputs(detail.result.agent_reports || detail.result.analyst_reports || {});
        setSelectedMarket(detail.market);
        if (detail.symbol) setSymbol(detail.symbol);
        if (detail.analysis_type === "recommend" || detail.result.ranked_candidates) {
          setAnalysisType("recommend");
        } else {
          setAnalysisType("analyze");
        }
        setActiveReportTab("investment_advisor");
        setShowHistoryModal(false);
      }
    } catch (e: any) {
      alert("Gagal memuat detail riwayat: " + e.message);
    }
  };

  const handleDeleteHistoryItem = async (histId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("Hapus catatan riwayat riset ini?")) return;
    try {
      await deleteInvestmentHistory(histId);
      setHistoryList((prev) => prev.filter((item) => item.id !== histId));
    } catch {}
  };

  // Start Multi-Agent Swarm SSE Pipeline
  const handleRunSwarm = async (overrideSymbol?: string, overrideType?: AnalysisType) => {
    const activeType = overrideType || analysisType;
    const activeSymbol = (overrideSymbol || symbol).trim().toUpperCase();

    if (activeType === "analyze" && !activeSymbol) return;
    if (isRunning) return;

    setIsRunning(true);
    setErrorMsg(null);
    setLiveLogs([
      activeType === "recommend"
        ? `📡 Memulai pemindaian peluang pasar (multi-aset) untuk ${selectedMarket.toUpperCase()}...`
        : `🚀 Memulai komite riset multi-agent untuk ${activeSymbol} (${selectedMarket.toUpperCase()})...`,
    ]);
    setAnalystOutputs({});
    setFinalResult(null);
    setChatMessages([]);
    setAgentStatuses({
      data_fetcher: "running",
      technical_analyst: "idle",
      fundamental_analyst: "idle",
      on_chain_analyst: "idle",
      sentiment_analyst: "idle",
      investment_advisor: "idle",
    });

    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("ai_finance_token") || localStorage.getItem("token")
        : null;
    const apiBase = (typeof window !== "undefined" ? "" : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001").replace(/\/+$/, "");
    const url = `${apiBase}/api/v1/investment/run`;

    try {
      const res = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          analysis_type: activeType,
          market: selectedMarket,
          symbol: activeType === "recommend" ? (activeSymbol || "ALL") : activeSymbol,
          horizon: horizonFilter,
          locale: "id",
        }),
      });

      if (!res.ok) {
        throw new Error(`Server merespon error: ${res.statusText}`);
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("Stream pembacaan SSE gagal.");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const block of lines) {
          const trimmed = block.trim();
          if (!trimmed.startsWith("data:")) continue;
          const jsonStr = trimmed.slice(5).trim();
          if (!jsonStr) continue;

          try {
            const data = JSON.parse(jsonStr);

            if (data.type === "task_init") {
              setCurrentTaskId(data.task_id);
            } else if (data.type === "log") {
              setLiveLogs((prev) => [...prev, `[${data.level || "INFO"}] ${data.message}`]);
            } else if (data.type === "agent_status") {
              setAgentStatuses((prev) => ({
                ...prev,
                [data.role]: data.status,
              }));
            } else if (data.type === "agent_output") {
              setAnalystOutputs((prev) => ({
                ...prev,
                [data.role]: data.output,
              }));
            } else if (data.type === "completed") {
              setFinalResult(data.result);
              setLiveLogs((prev) => [...prev, "✅ Seluruh riset multi-agent berhasil dirampungkan!"]);
            } else if (data.type === "stopped") {
              setLiveLogs((prev) => [...prev, "🛑 Analisis dihentikan sesuai instruksi pengguna."]);
            } else if (data.type === "error") {
              setErrorMsg(data.error);
              setLiveLogs((prev) => [...prev, `❌ Error: ${data.error}`]);
            }
          } catch {}
        }
      }
    } catch (err: any) {
      setErrorMsg(err.message || "Gagal menjalankan riset multi-agent.");
      setLiveLogs((prev) => [...prev, `❌ Error: ${err.message}`]);
    } finally {
      setIsRunning(false);
      setCurrentTaskId(null);
    }
  };

  const handleStopSwarm = async () => {
    if (!currentTaskId) return;
    try {
      await stopInvestmentTask(currentTaskId);
      setLiveLogs((prev) => [...prev, "Mengirim sinyal pembatalan ke komite AI..."]);
    } catch {}
  };

  // Follow-up chat with agent
  const handleSendChat = async (e?: React.FormEvent, directMessage?: string, forceValidation?: boolean) => {
    if (e) e.preventDefault();
    const userText = (directMessage || chatInput).trim();
    if (!userText || !finalResult || isChatSending) return;

    const useValidation = forceValidation !== undefined ? forceValidation : isDeepValidation;
    const currentMode: ChatMode = useValidation ? "deep_validation" : "standard";

    const newHistory: ChatMessageItem[] = [
      ...chatMessages,
      { role: "user", content: userText, mode: currentMode },
    ];
    setChatMessages(newHistory);
    if (!directMessage) setChatInput("");
    setIsChatSending(true);

    try {
      const activeSym = finalResult.symbol || (finalResult.ranked_candidates?.[0]?.symbol) || symbol;
      const res = await chatWithInvestmentAgent({
        symbol: activeSym,
        market: finalResult.market || selectedMarket,
        history: newHistory.map((h) => ({ role: h.role, content: h.content })),
        analysis_context: finalResult,
        user_message: userText,
        mode: currentMode,
      });

      setChatMessages([
        ...newHistory,
        {
          role: "assistant",
          content: res.reply,
          mode: res.mode,
          validation_meta: res.validation_meta,
        },
      ]);
    } catch (e: any) {
      setChatMessages([
        ...newHistory,
        { role: "assistant", content: `Maaf, kendala saat menjawab pertanyaan: ${e.message}` },
      ]);
    } finally {
      setIsChatSending(false);
    }
  };

  // Quick Action: Analyze candidate from screener
  const handleAnalyzeCandidate = (candSymbol: string) => {
    setAnalysisType("analyze");
    setSymbol(candSymbol);
    handleRunSwarm(candSymbol, "analyze");
  };

  const rec: InvestmentRecommendation | undefined = finalResult?.investment_recommendation;
  const isRecommendationResult = Boolean(finalResult?.ranked_candidates && finalResult.ranked_candidates.length > 0);
  const isSyariah = selectedMarket === "ihsg_syariah";

  return (
    <div className="space-y-6 pb-20 max-w-7xl mx-auto">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border pb-5">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-amber-500 to-amber-600 text-white flex items-center justify-center shadow-md">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl md:text-2xl font-black text-foreground tracking-tight">
                  Riset & Analisis Investasi AI Multi-Agent
                </h1>
                <span className="text-[10px] uppercase font-bold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 px-2 py-0.5 rounded-full">
                  Free Access
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Komite AI quant, fundamental, & sentimen untuk riset jangka pendek, menengah, & panjang tanpa kuota token.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {isSyariah && (
            <button
              onClick={handleOpenShariaModal}
              className="px-3.5 py-2 rounded-xl bg-secondary text-foreground text-xs font-semibold hover:bg-secondary/80 border border-border flex items-center gap-2 transition"
            >
              <ShieldCheck className="w-4 h-4 text-emerald-500" />
              <span>Daftar Saham Syariah (ISSI)</span>
            </button>
          )}

          <button
            onClick={handleOpenHistoryModal}
            className="px-3.5 py-2 rounded-xl bg-secondary text-foreground text-xs font-semibold hover:bg-secondary/80 border border-border flex items-center gap-2 transition"
          >
            <History className="w-4 h-4 text-muted-foreground" />
            <span>Riwayat Riset</span>
          </button>
        </div>
      </div>

      {/* Mode Switcher Tabs */}
      <div className="flex items-center gap-2 p-1.5 bg-secondary/60 rounded-2xl border border-border w-fit text-xs">
        <button
          onClick={() => setAnalysisType("analyze")}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl font-bold transition ${
            analysisType === "analyze"
              ? "bg-card text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <Crosshair className="w-4 h-4 text-amber-500" />
          <span>Analisis Spesifik Emiten / Koin</span>
        </button>

        <button
          onClick={() => setAnalysisType("recommend")}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl font-bold transition ${
            analysisType === "recommend"
              ? "bg-[#f0b000] text-white shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <Radar className="w-4 h-4" />
          <span>Scan Peluang Pasar (Multi-Aset)</span>
        </button>
      </div>

      {/* Market Selector Bar */}
      <div className="space-y-4">
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5">
          {MARKETS.map((m) => {
            const Icon = m.icon;
            const isSelected = selectedMarket === m.id;
            return (
              <button
                key={m.id}
                onClick={() => {
                  setSelectedMarket(m.id);
                  if (analysisType === "analyze") {
                    setSymbol(m.defaultTicker);
                  }
                }}
                className={`p-3 rounded-2xl border text-left transition flex items-center gap-2.5 ${
                  isSelected
                    ? "bg-[#f0b000]/15 border-[#f0b000] text-foreground shadow-sm"
                    : "bg-card border-border text-muted-foreground hover:bg-secondary hover:text-foreground"
                }`}
              >
                <div
                  className={`w-8 h-8 rounded-xl flex items-center justify-center shrink-0 ${
                    isSelected
                      ? "bg-[#f0b000] text-white"
                      : "bg-secondary text-muted-foreground"
                  }`}
                >
                  <Icon className="w-4 h-4" />
                </div>
                <div className="min-w-0">
                  <div className="text-xs font-bold truncate text-foreground">{m.label}</div>
                  <div className="text-[10px] text-muted-foreground">Default: {m.defaultTicker}</div>
                </div>
              </button>
            );
          })}
        </div>

        {/* Input & Action Bar */}
        <div className="p-4 rounded-3xl bg-card border border-border shadow-sm flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
          {analysisType === "analyze" ? (
            <div className="flex-1 flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
              <div className="relative flex-1">
                <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <input
                  type="text"
                  placeholder="Ketik Simbol (contoh: BBCA, TLKM, BTC, AAPL, VOO)..."
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                  disabled={isRunning}
                  className="w-full pl-10 pr-4 py-2.5 rounded-2xl bg-secondary border border-border text-foreground font-mono font-bold text-sm tracking-wide uppercase focus:outline-none focus:ring-2 focus:ring-[#f0b000]"
                />
              </div>

              {/* Horizon Filter Tabs */}
              <div className="flex items-center gap-1 p-1 bg-secondary rounded-2xl border border-border text-xs shrink-0">
                {(["ALL", "SHORT", "MEDIUM", "LONG"] as const).map((h) => (
                  <button
                    key={h}
                    onClick={() => setHorizonFilter(h)}
                    className={`px-2.5 py-1.5 rounded-xl font-bold transition text-[11px] ${
                      horizonFilter === h
                        ? "bg-card text-foreground shadow-sm"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {h === "ALL" ? "Semua Horizon" : h === "SHORT" ? "< 1 Thn" : h === "MEDIUM" ? "1-3 Thn" : "> 3-5 Thn"}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex-1 flex items-center gap-3">
              <div className="w-9 h-9 rounded-2xl bg-amber-500/10 text-amber-500 flex items-center justify-center shrink-0">
                <Radar className="w-5 h-5 animate-spin" />
              </div>
              <div>
                <div className="text-xs font-bold text-foreground">
                  Pemindaian Peluang Komprehensif Pasar {MARKETS.find((m) => m.id === selectedMarket)?.label}
                </div>
                <div className="text-[11px] text-muted-foreground">
                  AI Screener akan menyaring universe likuid, menghitung RSI/MACD/SMA, menguji keselarasan fundamental, dan menerbitkan rekomendasi multi-horizon.
                </div>
              </div>
            </div>
          )}

          <div className="flex items-center gap-2 w-full sm:w-auto shrink-0">
            {isRunning ? (
              <button
                onClick={handleStopSwarm}
                className="w-full sm:w-auto justify-center px-5 py-2.5 min-h-[44px] rounded-2xl bg-rose-500 hover:bg-rose-600 text-white font-bold text-xs flex items-center gap-2 shadow-sm transition"
              >
                <Square className="w-4 h-4 fill-current" />
                <span>Hentikan Analisis</span>
              </button>
            ) : (
              <button
                onClick={() => handleRunSwarm()}
                disabled={analysisType === "analyze" && !symbol.trim()}
                className="w-full sm:w-auto justify-center px-6 py-2.5 min-h-[44px] rounded-2xl bg-gradient-to-r from-[#f0b000] to-amber-600 hover:opacity-95 text-white font-bold text-xs flex items-center gap-2 shadow-md transition disabled:opacity-50"
              >
                {analysisType === "recommend" ? <Radar className="w-4 h-4" /> : <Play className="w-4 h-4 fill-current" />}
                <span>
                  {analysisType === "recommend"
                    ? "Mulai Scan Peluang Pasar"
                    : "Mulai Riset Multi-Agent"}
                </span>
              </button>
            )}
          </div>
        </div>

          {/* Quick Tickers & Live Quote Pill (Only when analyze mode) */}
          {analysisType === "analyze" && (
            <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-muted-foreground font-medium text-[11px]">Pilihan Populer:</span>
                {(QUICK_TICKERS[selectedMarket] || []).map((t) => (
                  <button
                    key={t}
                    onClick={() => setSymbol(t)}
                    disabled={isRunning}
                    className={`px-2.5 py-1 rounded-lg border text-[11px] font-mono font-bold transition ${
                      symbol === t
                        ? "bg-[#f0b000] text-white border-[#f0b000]"
                        : "bg-card border-border text-foreground hover:bg-secondary"
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>

              {quote && (
                <div className="flex items-center gap-3 px-3 py-1.5 rounded-xl bg-card border border-border text-xs font-mono">
                  <span className="text-muted-foreground">{symbol}:</span>
                  <span className="font-bold text-foreground">
                    {selectedMarket.includes("ihsg")
                      ? formatCurrency(quote.price || 0, "IDR")
                      : `$${(quote.price || 0).toLocaleString()}`}
                  </span>
                  {quote.change_pct !== undefined && (
                    <span
                      className={`font-bold flex items-center gap-0.5 ${
                        quote.change_pct >= 0 ? "text-emerald-500" : "text-rose-500"
                      }`}
                    >
                      {quote.change_pct >= 0 ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
                      {quote.change_pct >= 0 ? "+" : ""}
                      {quote.change_pct.toFixed(2)}%
                    </span>
                  )}
                </div>
              )}
            </div>
          )}
      </div>

      {/* Real-Time Agent Pipeline Progress (When Running or Logs Present) */}
      {(isRunning || liveLogs.length > 0) && (
        <div className="p-5 rounded-3xl bg-card border border-border shadow-sm space-y-4">
          <div className="flex items-center justify-between border-b border-border pb-3">
            <div className="flex items-center gap-2">
              <Bot className="w-5 h-5 text-[#f0b000]" />
              <h2 className="text-sm font-bold text-foreground">
                {analysisType === "recommend" ? "Status Multi-Asset Quant Screener" : "Status Swarm Multi-Agent"}
              </h2>
              {isRunning && (
                <span className="flex h-2 w-2 relative">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
              )}
            </div>
            <span className="text-[11px] text-muted-foreground font-mono">
              {isRunning ? "Analisis Sedang Berjalan..." : "Proses Selesai"}
            </span>
          </div>

          {/* Agents Pipeline Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 text-xs">
            {[
              { role: "data_fetcher", label: "Data Fetcher", desc: "Harga & Screener" },
              { role: "technical_analyst", label: "Technical", desc: "RSI & MACD" },
              { role: "fundamental_analyst", label: "Fundamental", desc: "Laporan & Rasio" },
              { role: "on_chain_analyst", label: "On-Chain", desc: "Flow / Volume", cryptoOnly: true },
              { role: "sentiment_analyst", label: "Sentiment", desc: "Exa Neural News" },
              { role: "investment_advisor", label: "Chief Advisor", desc: "Sintesis Horizon" },
            ]
              .filter((a) => !a.cryptoOnly || selectedMarket === "crypto")
              .map((agent) => {
                const st = agentStatuses[agent.role] || "idle";
                return (
                  <div
                    key={agent.role}
                    className={`p-3 rounded-2xl border transition ${
                      st === "running"
                        ? "bg-amber-500/10 border-amber-500/40 text-foreground animate-pulse"
                        : st === "completed"
                        ? "bg-emerald-500/10 border-emerald-500/30 text-foreground"
                        : st === "failed"
                        ? "bg-rose-500/10 border-rose-500/30 text-foreground"
                        : "bg-secondary/40 border-border text-muted-foreground opacity-60"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-bold text-[11px]">{agent.label}</span>
                      {st === "running" && <Clock className="w-3 h-3 text-amber-500 animate-spin" />}
                      {st === "completed" && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />}
                      {st === "failed" && <XCircle className="w-3.5 h-3.5 text-rose-500" />}
                    </div>
                    <div className="text-[10px] text-muted-foreground truncate">{agent.desc}</div>
                  </div>
                );
              })}
          </div>

          {/* Live Terminal Log Box */}
          <div className="p-3 rounded-2xl bg-black/80 font-mono text-[11px] text-emerald-400/90 h-32 overflow-y-auto space-y-1">
            {liveLogs.map((log, i) => (
              <div key={i} className="leading-relaxed">
                {log}
              </div>
            ))}
            <div ref={logsEndRef} />
          </div>
        </div>
      )}

      {/* SCAN PELUANG PASAR (MULTI-ASET) RESULTS VIEW */}
      {isRecommendationResult && (
        <div className="space-y-6">
          <div className="p-6 rounded-3xl bg-card border border-border shadow-sm space-y-6">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border pb-4">
              <div>
                <div className="flex items-center gap-2.5">
                  <Radar className="w-6 h-6 text-[#f0b000]" />
                  <h2 className="text-lg font-black text-foreground">
                    Hasil Scan Peluang Pasar {finalResult.market?.toUpperCase()}
                  </h2>
                  <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-[#f0b000]/15 text-[#8a6300] dark:text-[#f0b000] border border-[#f0b000]/30">
                    {finalResult.symbols_scanned || finalResult.ranked_candidates.length} Aset Terpindai
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  Peringkat peluang investasi berdasarkan kombinasi momentum teknikal, valuasi fundamental, dan kepatuhan syariah.
                </p>
              </div>

              {finalResult.sharia_status && (
                <span className="px-3 py-1 rounded-xl text-xs font-bold bg-teal-500/10 text-teal-600 dark:text-teal-400 border border-teal-500/30 flex items-center gap-1.5 self-start md:self-auto">
                  <ShieldCheck className="w-4 h-4" />
                  ISSI Syariah Verified
                </span>
              )}
            </div>

            {/* Ranked Candidates Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {finalResult.ranked_candidates.map((cand: RankedCandidate, idx: number) => {
                const isBuy = (cand.stance || "").includes("BUY") || (cand.stance || "").includes("ACCUMULATE");
                const isHold = (cand.stance || "").includes("HOLD");
                return (
                  <div
                    key={cand.symbol}
                    className="p-5 rounded-2xl bg-secondary/30 hover:bg-secondary/50 border border-border flex flex-col justify-between gap-4 transition group"
                  >
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="w-6 h-6 rounded-lg bg-amber-500/15 text-amber-600 dark:text-amber-400 text-xs font-black flex items-center justify-center">
                            #{idx + 1}
                          </span>
                          <span className="font-mono text-base font-black text-foreground">
                            {cand.symbol}
                          </span>
                          {cand.issi_status === "Ya" && (
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-teal-500/10 text-teal-600 dark:text-teal-400">
                              ISSI
                            </span>
                          )}
                        </div>

                        <span
                          className={`px-2.5 py-1 rounded-lg text-[11px] font-bold border ${
                            isBuy
                              ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-600 dark:text-emerald-400"
                              : isHold
                              ? "bg-amber-500/15 border-amber-500/40 text-amber-600 dark:text-amber-400"
                              : "bg-rose-500/15 border-rose-500/40 text-rose-600 dark:text-rose-400"
                          }`}
                        >
                          {cand.stance || "HOLD"}
                        </span>
                      </div>

                      {/* Price & Change */}
                      <div className="flex items-baseline justify-between">
                        <div className="text-lg font-black text-foreground">
                          {finalResult.market?.includes("ihsg")
                            ? formatCurrency(cand.price, "IDR")
                            : `$${Number(cand.price).toLocaleString()}`}
                        </div>
                        {cand.change_pct !== undefined && (
                          <div
                            className={`text-xs font-bold flex items-center gap-0.5 ${
                              cand.change_pct >= 0 ? "text-emerald-500" : "text-rose-500"
                            }`}
                          >
                            {cand.change_pct >= 0 ? "+" : ""}
                            {cand.change_pct.toFixed(2)}%
                          </div>
                        )}
                      </div>

                      {/* Technical Indicators Pill */}
                      <div className="grid grid-cols-3 gap-1.5 p-2 rounded-xl bg-card border border-border text-[10px] text-center">
                        <div>
                          <div className="text-muted-foreground font-semibold">Skor AI</div>
                          <div className="font-black text-amber-600 dark:text-amber-400">
                            {cand.score?.toFixed(1)}/10
                          </div>
                        </div>
                        <div>
                          <div className="text-muted-foreground font-semibold">RSI (14)</div>
                          <div className="font-black text-foreground">
                            {cand.rsi ? cand.rsi.toFixed(1) : "-"}
                          </div>
                        </div>
                        <div>
                          <div className="text-muted-foreground font-semibold">Confidence</div>
                          <div className="font-black text-foreground">
                            {cand.confidence || 75}%
                          </div>
                        </div>
                      </div>

                      {/* Targets TP1 - TP3 */}
                      {(cand.target_price_1 || cand.support_level) && (
                        <div className="space-y-1 text-[11px] pt-1">
                          <div className="flex justify-between text-muted-foreground">
                            <span>Support Kuat:</span>
                            <span className="font-mono font-bold text-foreground">
                              {cand.support_level ? (finalResult.market?.includes("ihsg") ? formatCurrency(cand.support_level, "IDR") : `$${cand.support_level}`) : "-"}
                            </span>
                          </div>
                          <div className="flex justify-between text-muted-foreground">
                            <span>Target TP1:</span>
                            <span className="font-mono font-bold text-emerald-600 dark:text-emerald-400">
                              {cand.target_price_1 ? (finalResult.market?.includes("ihsg") ? formatCurrency(cand.target_price_1, "IDR") : `$${cand.target_price_1}`) : "-"}
                            </span>
                          </div>
                          {cand.target_price_2 && (
                            <div className="flex justify-between text-muted-foreground">
                              <span>Target TP2:</span>
                              <span className="font-mono font-bold text-emerald-600 dark:text-emerald-400">
                                {finalResult.market?.includes("ihsg") ? formatCurrency(cand.target_price_2, "IDR") : `$${cand.target_price_2}`}
                              </span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    <button
                      onClick={() => handleAnalyzeCandidate(cand.symbol)}
                      className="w-full mt-2 py-2 rounded-xl bg-card hover:bg-[#f0b000] text-foreground hover:text-white font-bold text-xs border border-border flex items-center justify-center gap-1.5 transition shadow-sm"
                    >
                      <span>Analisis Mendalam</span>
                      <ArrowUpRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                );
              })}
            </div>

            {/* Synthesized Market Recommendation Report */}
            {finalResult.report && (
              <div className="border-t border-border pt-6 space-y-3">
                <div className="flex items-center gap-2">
                  <FileText className="w-5 h-5 text-[#f0b000]" />
                  <h3 className="text-sm font-bold text-foreground">
                    Laporan Eksekutif Komite Riset Pasar ({finalResult.market?.toUpperCase()})
                  </h3>
                </div>
                <div className="p-5 rounded-2xl bg-secondary/30 border border-border font-mono text-xs text-foreground whitespace-pre-wrap leading-relaxed max-h-[500px] overflow-y-auto">
                  {finalResult.report}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* SINGLE ASSET RESEARCH VIEW */}
      {rec && !isRecommendationResult && (
        <div className="space-y-6">
          {/* Top Recommendation Banner */}
          <div className="p-6 rounded-3xl bg-card border border-border shadow-sm space-y-6">
            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
              <div className="space-y-2">
                <div className="flex items-center gap-3 flex-wrap">
                  <span className="text-2xl font-black text-foreground font-mono">{rec.symbol}</span>
                  <span
                    className={`px-3.5 py-1 rounded-xl text-xs font-black tracking-wide border ${
                      rec.stance.includes("ACCUMULATE") || rec.stance.includes("BUY")
                        ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-600 dark:text-emerald-400"
                        : rec.stance.includes("HOLD")
                        ? "bg-amber-500/15 border-amber-500/40 text-amber-600 dark:text-amber-400"
                        : "bg-rose-500/15 border-rose-500/40 text-rose-600 dark:text-rose-400"
                    }`}
                  >
                    {rec.stance}
                  </span>

                  {rec.sharia_compliance?.is_sharia && (
                    <span className="px-2.5 py-0.5 rounded-lg text-[11px] font-bold bg-teal-500/10 text-teal-600 dark:text-teal-400 border border-teal-500/30 flex items-center gap-1">
                      <ShieldCheck className="w-3.5 h-3.5" />
                      ISSI Syariah Compliant
                    </span>
                  )}
                </div>

                <p className="text-sm text-foreground/90 leading-relaxed max-w-3xl">
                  {rec.executive_thesis}
                </p>
              </div>

              {/* Metrics Pill Group */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 sm:gap-3 w-full lg:w-auto shrink-0">
                <div className="p-3.5 rounded-2xl bg-secondary/60 border border-border text-center">
                  <div className="text-[10px] uppercase font-bold text-muted-foreground">Confidence</div>
                  <div className="text-lg font-black text-foreground">{rec.confidence_pct}%</div>
                </div>

                <div className="p-3.5 rounded-2xl bg-secondary/60 border border-border text-center">
                  <div className="text-[10px] uppercase font-bold text-muted-foreground">Kualitas Funda</div>
                  <div className="text-lg font-black text-[#8a6300] dark:text-[#f0b000]">
                    {rec.fundamental_quality_score}/10
                  </div>
                </div>

                <div className="p-3.5 rounded-2xl bg-secondary/60 border border-border text-center">
                  <div className="text-[10px] uppercase font-bold text-muted-foreground">Status Valuasi</div>
                  <div className="text-sm font-black text-foreground truncate">
                    {rec.valuation_summary?.current_valuation_status || "FAIR"}
                  </div>
                </div>
              </div>
            </div>

            {/* Multi-Horizon Outlook Cards */}
            <div className="border-t border-border pt-6 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                  <Clock className="w-4 h-4 text-[#f0b000]" />
                  Pemetaan Tesis Multi-Horizon Investasi
                </h3>
                <span className="text-[11px] text-muted-foreground">Fokus Strategis & Target Harga</span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Short-Term Card */}
                {(horizonFilter === "ALL" || horizonFilter === "SHORT") && rec.multi_horizon_outlook?.short_term && (
                  <div className="p-5 rounded-2xl bg-gradient-to-b from-card to-secondary/30 border border-border space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-muted-foreground">Jangka Pendek (&lt; 1 Thn)</span>
                      <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-sky-500/10 text-sky-500">
                        {rec.multi_horizon_outlook.short_term.stance}
                      </span>
                    </div>
                    <div className="text-sm font-black text-foreground">
                      Target: {rec.multi_horizon_outlook.short_term.target_range}
                    </div>
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      {rec.multi_horizon_outlook.short_term.thesis}
                    </p>
                    {rec.multi_horizon_outlook.short_term.catalysts && (
                      <div className="text-[11px] space-y-1 pt-2 border-t border-border/60">
                        <span className="font-semibold text-foreground">Katalis:</span>
                        <div className="text-muted-foreground">
                          {rec.multi_horizon_outlook.short_term.catalysts.join(", ")}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Medium-Term Card */}
                {(horizonFilter === "ALL" || horizonFilter === "MEDIUM") && rec.multi_horizon_outlook?.medium_term && (
                  <div className="p-5 rounded-2xl bg-gradient-to-b from-card to-secondary/30 border border-border space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-muted-foreground">Jangka Menengah (1 - 3 Thn)</span>
                      <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-amber-500/10 text-amber-500">
                        {rec.multi_horizon_outlook.medium_term.stance}
                      </span>
                    </div>
                    <div className="text-sm font-black text-foreground">
                      Target: {rec.multi_horizon_outlook.medium_term.target_range}
                    </div>
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      {rec.multi_horizon_outlook.medium_term.thesis}
                    </p>
                    {rec.multi_horizon_outlook.medium_term.catalysts && (
                      <div className="text-[11px] space-y-1 pt-2 border-t border-border/60">
                        <span className="font-semibold text-foreground">Katalis:</span>
                        <div className="text-muted-foreground">
                          {rec.multi_horizon_outlook.medium_term.catalysts.join(", ")}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Long-Term Card */}
                {(horizonFilter === "ALL" || horizonFilter === "LONG") && rec.multi_horizon_outlook?.long_term && (
                  <div className="p-5 rounded-2xl bg-gradient-to-b from-card to-secondary/30 border border-border space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-muted-foreground">Jangka Panjang (&gt; 3 - 5 Thn)</span>
                      <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-emerald-500/10 text-emerald-500">
                        {rec.multi_horizon_outlook.long_term.stance}
                      </span>
                    </div>
                    <div className="text-sm font-black text-foreground">
                      Target: {rec.multi_horizon_outlook.long_term.target_range}
                    </div>
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      {rec.multi_horizon_outlook.long_term.thesis}
                    </p>
                    {rec.multi_horizon_outlook.long_term.compounding_factors && (
                      <div className="text-[11px] space-y-1 pt-2 border-t border-border/60">
                        <span className="font-semibold text-foreground">Faktor Compounding:</span>
                        <div className="text-muted-foreground">
                          {rec.multi_horizon_outlook.long_term.compounding_factors.join(", ")}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* User Portfolio Fit & DCA Simulation Card */}
            {rec.portfolio_and_dca_simulation && (
              <div className="p-4 rounded-2xl bg-secondary/40 border border-border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                <div className="space-y-1">
                  <div className="text-xs font-bold text-foreground flex items-center gap-2">
                    <span>💡 Rekomendasi Alokasi Dompet & Strategi Cicil (DCA):</span>
                    <span className="text-muted-foreground font-normal">
                      ({rec.portfolio_and_dca_simulation.risk_profile_match})
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {rec.portfolio_and_dca_simulation.action_plan}
                  </p>
                </div>

                <div className="flex items-center gap-3 shrink-0">
                  <div className="text-right">
                    <div className="text-[10px] text-muted-foreground">Maks Bobot Portofolio</div>
                    <div className="text-sm font-bold text-foreground">
                      {rec.portfolio_and_dca_simulation.recommended_max_allocation_pct}%
                    </div>
                  </div>
                  {rec.portfolio_and_dca_simulation.suggested_monthly_dca_amount > 0 && (
                    <div className="text-right">
                      <div className="text-[10px] text-muted-foreground">Saran DCA Bulanan</div>
                      <div className="text-sm font-bold text-emerald-600 dark:text-emerald-400">
                        {formatCurrency(rec.portfolio_and_dca_simulation.suggested_monthly_dca_amount)}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Detailed Analyst Reports Tabs */}
          <div className="p-6 rounded-3xl bg-card border border-border shadow-sm space-y-4">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                Laporan Rinci Per Agen Spesialis
              </h3>
              <div className="flex items-center gap-1.5 overflow-x-auto">
                {Object.keys(analystOutputs).map((role) => (
                  <button
                    key={role}
                    onClick={() => setActiveReportTab(role)}
                    className={`px-3 py-1.5 rounded-xl text-xs font-bold transition whitespace-nowrap ${
                      activeReportTab === role
                        ? "bg-[#f0b000] text-white shadow-sm"
                        : "bg-secondary text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {role.replace("_", " ").toUpperCase()}
                  </button>
                ))}
              </div>
            </div>

            <div className="p-4 rounded-2xl bg-secondary/30 border border-border font-mono text-xs text-foreground whitespace-pre-wrap leading-relaxed max-h-96 overflow-y-auto">
              {analystOutputs[activeReportTab] || "Laporan belum tersedia."}
            </div>
          </div>
        </div>
      )}

      {/* Exa News & Sources Citations */}
      {finalResult?.news_sources && finalResult.news_sources.length > 0 && (
        <div className="p-6 rounded-3xl bg-card border border-border shadow-sm space-y-3">
          <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
            <Globe className="w-4 h-4 text-emerald-500" />
            Sumber Berita & Katalis Real-Time (Exa Neural Search)
          </h3>
          <div className="space-y-2">
            {finalResult.news_sources.map((item: any, idx: number) => (
              <a
                key={idx}
                href={item.url}
                target="_blank"
                rel="noreferrer"
                className="p-3 rounded-2xl bg-secondary/40 hover:bg-secondary border border-border flex items-start justify-between gap-3 text-xs transition group block"
              >
                <div>
                  <div className="font-bold text-foreground group-hover:text-[#f0b000] transition">
                    {item.title}
                  </div>
                  {item.snippet && <div className="text-muted-foreground text-[11px] mt-0.5 line-clamp-1">{item.snippet}</div>}
                </div>
                <div className="text-[10px] text-muted-foreground shrink-0 flex items-center gap-1 mt-0.5">
                  {item.published_date && <span>{item.published_date}</span>}
                  <ExternalLink className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition" />
                </div>
              </a>
            ))}
          </div>
        </div>
      )}

      {/* Interactive AI Investment Consultant & Deep Validation Chat */}
      {finalResult && (
        <div className="p-6 rounded-3xl bg-card border border-border shadow-sm space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border pb-4">
            <div className="flex items-center gap-2.5">
              <Bot className="w-5 h-5 text-[#f0b000]" />
              <div>
                <h3 className="text-sm font-bold text-foreground">
                  Konsultasi & Chief Auditor AI Swarm
                </h3>
                <p className="text-[11px] text-muted-foreground">
                  Tanyakan hal spesifik seputar valuasi, waktu masuk DCA, atau aktifkan Deep Validation untuk verifikasi live multi-timeframe.
                </p>
              </div>
            </div>

            {/* Deep Validation Mode Switcher Toggle */}
            <div className="flex items-center gap-2.5 self-start sm:self-auto bg-secondary/60 p-1.5 rounded-2xl border border-border">
              <ShieldAlert className={`w-4 h-4 ${isDeepValidation ? "text-amber-500" : "text-muted-foreground"}`} />
              <span className="text-[11px] font-bold text-foreground">
                Deep Validation Audit:
              </span>
              <button
                type="button"
                onClick={() => setIsDeepValidation(!isDeepValidation)}
                className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                  isDeepValidation ? "bg-[#f0b000]" : "bg-muted"
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                    isDeepValidation ? "translate-x-4" : "translate-x-0"
                  }`}
                />
              </button>
            </div>
          </div>

          {/* Quick Audit Action Chips */}
          <div className="space-y-1.5">
            <div className="text-[10px] uppercase font-bold text-muted-foreground flex items-center gap-1">
              <ZapIcon className="w-3 h-3 text-[#f0b000]" />
              <span>Aksi Cepat Audit & Validasi Independen:</span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {QUICK_AUDIT_PROMPTS.map((q, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSendChat(undefined, q.prompt, true)}
                  disabled={isChatSending}
                  className="px-3 py-1.5 rounded-xl bg-secondary/80 hover:bg-secondary text-foreground text-[11px] font-semibold border border-border transition flex items-center gap-1.5 disabled:opacity-50"
                >
                  <span>{q.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Chat Messages */}
          <div className="space-y-4 min-h-[140px] max-h-96 overflow-y-auto p-1">
            {chatMessages.length === 0 ? (
              <div className="text-center py-8 text-xs text-muted-foreground space-y-2">
                <p>Belum ada diskusi lanjutan. Gunakan quick-audit di atas atau ajukan pertanyaan spesifik Anda.</p>
              </div>
            ) : (
              chatMessages.map((msg, i) => (
                <div
                  key={i}
                  className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"} space-y-2`}
                >
                  <div
                    className={`max-w-[90%] rounded-2xl p-3.5 text-xs leading-relaxed ${
                      msg.role === "user"
                        ? "bg-[#f0b000] text-white rounded-br-none font-medium"
                        : "bg-secondary text-foreground rounded-bl-none border border-border whitespace-pre-wrap"
                    }`}
                  >
                    {msg.content}
                  </div>

                  {/* Validation Meta Dossier Card if Present */}
                  {msg.validation_meta && (
                    <div className="max-w-[90%] p-4 rounded-2xl bg-amber-500/10 border border-amber-500/30 text-xs space-y-3">
                      <div className="flex items-center justify-between border-b border-amber-500/20 pb-2">
                        <div className="flex items-center gap-1.5 font-bold text-amber-700 dark:text-amber-300">
                          <ShieldCheck className="w-4 h-4 text-emerald-500" />
                          <span>Bukti Validasi Independen Auditor (Data Real-Time)</span>
                        </div>
                        <span className="text-[10px] text-muted-foreground">
                          Sumber: {msg.validation_meta.checked_sources?.join(", ") || "Live API"}
                        </span>
                      </div>

                      {/* Snapshots Table */}
                      {msg.validation_meta.live_snapshots && msg.validation_meta.live_snapshots.length > 0 && (
                        <div className="space-y-2">
                          {msg.validation_meta.live_snapshots.map((snap: any, sIdx: number) => (
                            <div key={sIdx} className="p-2.5 rounded-xl bg-card border border-border flex items-center justify-between gap-3 font-mono text-[11px]">
                              <div>
                                <span className="font-bold text-foreground">{snap.symbol}: </span>
                                <span className="text-foreground">{snap.price}</span>
                                {snap.drift_pct !== undefined && snap.drift_pct !== null && (
                                  <span className={`ml-2 font-bold ${snap.drift_pct >= 0 ? "text-emerald-500" : "text-rose-500"}`}>
                                    (Drift: {snap.drift_pct >= 0 ? "+" : ""}{snap.drift_pct}%)
                                  </span>
                                )}
                              </div>
                              <div className="flex items-center gap-2 text-muted-foreground text-[10px]">
                                <span>RSI 1D: <b className="text-foreground">{snap.rsi_1d ?? "-"}</b></span>
                                <span>RSI 1H: <b className="text-foreground">{snap.rsi_1h ?? "-"}</b></span>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Discrepancy Flags */}
                      {msg.validation_meta.discrepancy_flags && msg.validation_meta.discrepancy_flags.length > 0 && (
                        <div className="space-y-1">
                          <span className="text-[10px] font-bold text-amber-600 dark:text-amber-400">
                            Peringatan & Catatan Divergensi:
                          </span>
                          <ul className="list-disc pl-4 space-y-0.5 text-[11px] text-foreground/90">
                            {msg.validation_meta.discrepancy_flags.map((flag: string, fIdx: number) => (
                              <li key={fIdx}>{flag}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>

          {/* Chat Input */}
          <form onSubmit={(e) => handleSendChat(e)} className="flex items-center gap-2 pt-2">
            <input
              type="text"
              placeholder={
                isDeepValidation
                  ? "Tanyakan verifikasi live (Mode Audit Aktif: multi-timeframe re-fetch)..."
                  : "Tanyakan analisis mendalam seputar rekomendasi ini..."
              }
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              disabled={isChatSending}
              className="flex-1 px-4 py-2.5 rounded-2xl bg-secondary border border-border text-foreground text-xs focus:outline-none focus:ring-2 focus:ring-[#f0b000]"
            />
            <button
              type="submit"
              disabled={!chatInput.trim() || isChatSending}
              className="p-2.5 rounded-2xl bg-[#f0b000] hover:bg-[#d99f00] text-white font-bold transition disabled:opacity-50"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>
      )}

      {/* Sharia Stocks ISSI Universe Modal */}
      {showShariaModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="bg-card border border-border rounded-3xl w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
            <div className="p-5 border-b border-border flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <ShieldCheck className="w-5 h-5 text-emerald-500" />
                <div>
                  <h3 className="text-base font-bold text-foreground">Daftar Saham Syariah (ISSI) BEI</h3>
                  <p className="text-xs text-muted-foreground">
                    Database resmi Bursa Efek Indonesia untuk efek syariah terverifikasi.
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowShariaModal(false)}
                className="p-2 rounded-xl hover:bg-secondary text-muted-foreground"
              >
                ✕
              </button>
            </div>

            <div className="p-4 border-b border-border">
              <input
                type="text"
                placeholder="Cari kode saham atau nama perusahaan (contoh: TLKM, Indofood)..."
                value={shariaSearchQuery}
                onChange={(e) => handleSearchSharia(e.target.value)}
                className="w-full px-3.5 py-2 rounded-xl bg-secondary border border-border text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {shariaLoading ? (
                <div className="text-center py-8 text-xs text-muted-foreground">Memuat database ISSI...</div>
              ) : shariaList.length === 0 ? (
                <div className="text-center py-8 text-xs text-muted-foreground">Tidak ada saham yang cocok.</div>
              ) : (
                shariaList.map((s) => (
                  <div
                    key={s.ticker}
                    onClick={() => {
                      setSymbol(s.ticker.replace(".JK", ""));
                      setShowShariaModal(false);
                    }}
                    className="p-3 rounded-2xl bg-secondary/50 hover:bg-secondary border border-border flex items-center justify-between text-xs cursor-pointer transition group"
                  >
                    <div>
                      <div className="font-mono font-bold text-foreground group-hover:text-emerald-500 transition">
                        {s.ticker}
                      </div>
                      <div className="text-muted-foreground text-[11px]">{s.name}</div>
                    </div>
                    <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-emerald-500/10 text-emerald-500 border border-emerald-500/30">
                      ISSI Syariah
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* Past History Modal */}
      {showHistoryModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="bg-card border border-border rounded-3xl w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
            <div className="p-5 border-b border-border flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <History className="w-5 h-5 text-[#f0b000]" />
                <div>
                  <h3 className="text-base font-bold text-foreground">Riwayat Riset Multi-Agent</h3>
                  <p className="text-xs text-muted-foreground">
                    Daftar analisis emiten yang pernah Anda jalankan sebelumnya.
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowHistoryModal(false)}
                className="p-2 rounded-xl hover:bg-secondary text-muted-foreground"
              >
                ✕
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {historyLoading ? (
                <div className="text-center py-8 text-xs text-muted-foreground">Memuat riwayat...</div>
              ) : historyList.length === 0 ? (
                <div className="text-center py-8 text-xs text-muted-foreground">Belum ada riwayat riset tersimpan.</div>
              ) : (
                historyList.map((h) => (
                  <div
                    key={h.id}
                    onClick={() => handleSelectHistoryItem(h.id)}
                    className="p-3.5 rounded-2xl bg-secondary/40 hover:bg-secondary border border-border flex items-center justify-between text-xs cursor-pointer transition group"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-foreground group-hover:text-[#f0b000] transition">
                          {h.symbol}
                        </span>
                        <span className="text-[10px] text-muted-foreground uppercase">({h.market})</span>
                        {h.decision && (
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/10 text-amber-500 border border-amber-500/30">
                            {h.decision}
                          </span>
                        )}
                      </div>
                      <div className="text-[11px] text-muted-foreground line-clamp-1">
                        {h.report_preview || "Analisis lengkap tersimpan"}
                      </div>
                    </div>

                    <div className="flex items-center gap-3 shrink-0">
                      <span className="text-[10px] text-muted-foreground">
                        {h.created_at ? new Date(h.created_at).toLocaleDateString("id-ID") : ""}
                      </span>
                      <button
                        onClick={(e) => handleDeleteHistoryItem(h.id, e)}
                        className="p-1.5 rounded-lg hover:bg-rose-500/10 text-muted-foreground hover:text-rose-500 transition"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ZapIcon({ className }: { className?: string }) {
  return (
    <svg className={className} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  );
}
