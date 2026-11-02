"use client";

import React, { useEffect, useState, useRef } from "react";
import {
  Sparkles,
  Send,
  ShieldCheck,
  PieChart,
  SlidersHorizontal,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  Trash2,
  Brain,
  MoonStar,
} from "lucide-react";
import {
  clearPlannerChatHistory,
  getPlannerChatHistory,
  getPlannerOverview,
  sendPlannerMessageStream,
  updatePersonalProfile,
} from "@/lib/api";
import {
  PlannerHealthContext,
  AssetAllocation,
  PersonalProfile,
  PlannerMessage,
  PlannerStreamMeta,
} from "@/lib/types";

function renderInlineBold(text: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, idx) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return (
        <strong key={idx} className="font-semibold text-white">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return <React.Fragment key={idx}>{part}</React.Fragment>;
  });
}

function FormattedAssistantMessage({ content }: { content: string }) {
  const lines = content.split("\n");
  return (
    <div className="space-y-1.5">
      {lines.map((rawLine, idx) => {
        const line = rawLine.trim();
        if (!line) {
          return <div key={idx} className="h-1" />;
        }
        if (line.startsWith("### ") || line.startsWith("## ")) {
          const cleanHeading = line.replace(/^#{2,3}\s+/, "");
          return (
            <div key={idx} className="font-bold text-emerald-300 pt-1 text-xs">
              {renderInlineBold(cleanHeading)}
            </div>
          );
        }
        if (/^[-*•]\s+/.test(line)) {
          const itemText = line.replace(/^[-*•]\s+/, "");
          return (
            <div key={idx} className="flex items-start gap-2 pl-1">
              <span className="text-emerald-400 mt-0.5 shrink-0">•</span>
              <span>{renderInlineBold(itemText)}</span>
            </div>
          );
        }
        const numMatch = line.match(/^(\d+)\.\s+(.*)$/);
        if (numMatch) {
          return (
            <div key={idx} className="flex items-start gap-2 pl-1">
              <span className="text-emerald-400 font-semibold shrink-0">{numMatch[1]}.</span>
              <span>{renderInlineBold(numMatch[2])}</span>
            </div>
          );
        }
        return <p key={idx}>{renderInlineBold(rawLine)}</p>;
      })}
    </div>
  );
}

export default function FinancialPlannerPage() {
  const [messages, setMessages] = useState<PlannerMessage[]>([]);
  const [inputMsg, setInputMsg] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [healthContext, setHealthContext] = useState<PlannerHealthContext | null>(null);
  const [allocations, setAllocations] = useState<AssetAllocation | null>(null);
  const [profile, setProfile] = useState<PersonalProfile | null>(null);
  const [activeSkills, setActiveSkills] = useState<string[]>([]);
  const [autoUpdatedNotice, setAutoUpdatedNotice] = useState(false);
  const [showProfileForm, setShowProfileForm] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);
  const [loading, setLoading] = useState(true);

  // Optional quick-fill form state
  const [incomeInput, setIncomeInput] = useState<number>(0);
  const [expenseInput, setExpenseInput] = useState<number>(8000000);
  const [debtInput, setDebtInput] = useState<number>(0);
  const [maritalInput, setMaritalInput] = useState<"SINGLE" | "MARRIED">("SINGLE");
  const [dependentsInput, setDependentsInput] = useState<number>(0);
  const [ageInput, setAgeInput] = useState<number>(28);
  const [fireAgeInput, setFireAgeInput] = useState<number>(50);
  const [riskInput, setRiskInput] = useState<"CONSERVATIVE" | "MODERATE" | "AGGRESSIVE">("MODERATE");

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const syncProfileForm = (p?: PersonalProfile) => {
    if (!p) return;
    setProfile(p);
    setIncomeInput(p.monthly_income || 0);
    setExpenseInput(p.monthly_living_expense || 8000000);
    setDebtInput(p.monthly_debt_payment || 0);
    setMaritalInput(p.marital_status || "SINGLE");
    setDependentsInput(p.dependents_count || 0);
    setAgeInput(p.current_age || 28);
    setFireAgeInput(p.target_fire_age || 50);
    setRiskInput(p.risk_tolerance || "MODERATE");
  };

  const refreshOverview = async () => {
    const overview = await getPlannerOverview();
    setHealthContext(overview.context);
    setAllocations(overview.allocations);
    if (overview.personal_profile) {
      syncProfileForm(overview.personal_profile);
    }
  };

  useEffect(() => {
    async function loadData() {
      try {
        const [hist, overview] = await Promise.all([getPlannerChatHistory(), getPlannerOverview()]);
        setMessages(hist);
        setHealthContext(overview.context);
        setAllocations(overview.allocations);
        if (overview.personal_profile) {
          syncProfileForm(overview.personal_profile);
        }
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isStreaming]);

  const handleToggleSharia = async () => {
    const nextVal = !(profile?.sharia_preference ?? healthContext?.sharia_preference ?? false);
    try {
      const updated = await updatePersonalProfile({ sharia_preference: nextVal });
      setHealthContext(updated.context);
      setAllocations(updated.allocations);
      syncProfileForm(updated.personal_profile);
    } catch (err) {
      console.error("Failed toggling Sharia preference", err);
    }
  };

  const handleSaveOptionalProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingProfile(true);
    try {
      const updated = await updatePersonalProfile({
        monthly_income: incomeInput,
        monthly_living_expense: expenseInput,
        monthly_debt_payment: debtInput,
        marital_status: maritalInput,
        dependents_count: dependentsInput,
        current_age: ageInput,
        target_fire_age: fireAgeInput,
        risk_tolerance: riskInput,
      });
      setHealthContext(updated.context);
      setAllocations(updated.allocations);
      syncProfileForm(updated.personal_profile);
      setShowProfileForm(false);
    } catch (err) {
      console.error("Failed saving optional profile", err);
    } finally {
      setSavingProfile(false);
    }
  };

  const handleResetChat = async () => {
    if (isStreaming) return;
    try {
      await clearPlannerChatHistory();
      setMessages([]);
      setActiveSkills([]);
    } catch (err) {
      console.error("Failed clearing chat history", err);
    }
  };

  const handleSend = async (customPrompt?: string) => {
    const textToSend = (customPrompt || inputMsg).trim();
    if (!textToSend || isStreaming) return;

    setInputMsg("");
    setAutoUpdatedNotice(false);

    const userMessage: PlannerMessage = {
      id: `m-${Date.now()}`,
      role: "user",
      content: textToSend,
      created_at: new Date().toISOString(),
    };

    const botMsgId = `bot-${Date.now()}`;
    const initialBotMessage: PlannerMessage = {
      id: botMsgId,
      role: "assistant",
      content: "",
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage, initialBotMessage]);
    setIsStreaming(true);

    let didUpdateProfile = false;

    try {
      await sendPlannerMessageStream(
        textToSend,
        (chunk: string) => {
          setMessages((prev) =>
            prev.map((msg) => (msg.id === botMsgId ? { ...msg, content: msg.content + chunk } : msg))
          );
        },
        (meta: PlannerStreamMeta) => {
          if (meta.active_skills?.length) {
            setActiveSkills(meta.active_skills);
          }
          if (meta.profile_updated) {
            didUpdateProfile = true;
            setAutoUpdatedNotice(true);
          }
        }
      );

      if (didUpdateProfile) {
        await refreshOverview();
      }
    } catch {
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === botMsgId
            ? { ...msg, content: msg.content + "\n\n*(Koneksi ke engine AI sedang terkendala, silakan coba lagi)*" }
            : msg
        )
      );
    } finally {
      setIsStreaming(false);
    }
  };

  const completenessPct = profile?.profile_completeness_pct ?? healthContext?.profile_completeness_pct ?? 20;
  const missingHints = profile?.missing_profile_hints ?? healthContext?.missing_profile_hints ?? [];
  const shariaActive = profile?.sharia_preference ?? healthContext?.sharia_preference ?? false;

  return (
    <div className="max-w-7xl mx-auto h-[calc(100vh-8rem)] flex flex-col lg:flex-row gap-6">
      {/* Left Chat Area */}
      <div className="flex-1 flex flex-col bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-sm">
        {/* Chat Header */}
        <div className="p-4 border-b border-slate-800 bg-slate-900/60 backdrop-blur-sm flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-emerald-500 to-teal-400 flex items-center justify-center text-slate-950 font-bold shadow-md shadow-emerald-500/20">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-sm font-bold text-white">AI Financial Planner</h2>
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  Adaptive Mentor
                </span>
                {shariaActive && (
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-teal-500/15 text-teal-300 border border-teal-500/30">
                    Mode Syariah Aktif
                  </span>
                )}
              </div>
              <p className="text-[11px] text-slate-400">
                Teman ngobrol strategi arus kas, dana darurat, KPR/cicilan, portofolio & pensiun berbasis data riilmu.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {activeSkills.map((skill, idx) => (
              <span
                key={idx}
                className="hidden sm:inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-1 rounded-lg bg-slate-800 text-emerald-300 border border-slate-700"
              >
                <Brain className="w-3 h-3 text-emerald-400" />
                {skill}
              </span>
            ))}
            {messages.length > 0 && (
              <button
                type="button"
                onClick={handleResetChat}
                disabled={isStreaming}
                title="Bersihkan riwayat obrolan"
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-medium bg-slate-800 hover:bg-rose-500/10 text-slate-400 hover:text-rose-400 border border-slate-700 hover:border-rose-500/30 transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span className="hidden md:inline">Reset Chat</span>
              </button>
            )}
          </div>
        </div>

        {/* Messages Scroll Area */}
        <div className="flex-1 p-5 overflow-y-auto space-y-4">
          {!loading && messages.length === 0 && (
            <div className="p-5 rounded-2xl bg-slate-800/40 border border-slate-800 space-y-3 max-w-2xl">
              <div className="text-sm font-bold text-white flex items-center gap-2">
                <span>Hai! Yuk ngobrol santai soal rencana keuanganmu</span>
              </div>
              <p className="text-xs text-slate-300 leading-relaxed">
                Nggak perlu isi form dulu buat mulai. Kamu bebas curhat soal pengeluaran yang sering bocor, tanya
                hitungan KPR, atur dana darurat, sampai susun investasi konvensional maupun syariah. Kalau sambil
                ngobrol kamu nyebutin konteks seperti gaji, cicilan, atau tanggungan, aku bakal otomatis mengingatnya
                supaya saran makin pas!
              </p>
              <div className="flex flex-wrap gap-2 pt-1">
                {[
                  "Duh bulan ini rasanya gampang bocor buat jajan, gimana ngeremnya ya?",
                  "Tolong bedah total kondisi keuanganku sekarang, mulai beresin dari mana?",
                  "Kalau mau fokus investasi syariah yang aman tapi tumbuh, bagi porsinya gimana?",
                  "Berapa dana darurat & proteksi dasar yang pas buat posisiku?",
                ].map((starter, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => handleSend(starter)}
                    className="text-left px-3 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-xs text-slate-200 border border-slate-700/80 hover:border-emerald-500/40 transition-colors"
                  >
                    {starter}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m) => {
            const isUser = m.role === "user";
            return (
              <div key={m.id} className={`flex items-start gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
                {!isUser ? (
                  <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center shrink-0 font-bold text-[11px] border border-emerald-500/20">
                    AI
                  </div>
                ) : (
                  <div className="w-8 h-8 rounded-lg bg-slate-800 text-slate-300 flex items-center justify-center shrink-0 font-bold text-[11px]">
                    Kamu
                  </div>
                )}

                <div
                  className={`max-w-[85%] rounded-2xl p-4 text-xs leading-relaxed shadow-sm ${
                    isUser
                      ? "bg-emerald-500 text-slate-950 font-medium rounded-tr-none whitespace-pre-wrap"
                      : "bg-slate-800/80 text-slate-200 border border-slate-700/60 rounded-tl-none"
                  }`}
                >
                  {isUser ? (
                    m.content
                  ) : m.content ? (
                    <FormattedAssistantMessage content={m.content} />
                  ) : isStreaming ? (
                    <span className="text-slate-400 animate-pulse">Sedang meracik jawaban...</span>
                  ) : (
                    ""
                  )}
                </div>
              </div>
            );
          })}
          <div ref={messagesEndRef} />
        </div>

        {/* Quick Topic Chips */}
        <div className="px-4 py-2 border-t border-slate-800/80 bg-slate-900/40 flex items-center gap-2 overflow-x-auto text-xs">
          <span className="text-[11px] text-slate-500 shrink-0 font-medium">Topik Cepat:</span>
          {[
            "Bedah kesehatan finansial 360°",
            "Simulasi aman ambil KPR rumah",
            "Jelaskan target Coast FIRE punyaku",
            "Strategi dana pendidikan anak",
          ].map((prompt, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => handleSend(prompt)}
              className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 whitespace-nowrap text-[11px] border border-slate-700 transition-colors"
            >
              {prompt}
            </button>
          ))}
        </div>

        {/* Chat Input */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="p-4 border-t border-slate-800 bg-slate-900 flex items-center gap-2"
        >
          <input
            type="text"
            value={inputMsg}
            onChange={(e) => setInputMsg(e.target.value)}
            placeholder="Ceritakan kondisimu atau tanyakan strategi keuangan apa pun..."
            className="flex-1 px-4 py-3 rounded-xl bg-slate-800 border border-slate-700 text-white text-xs focus:outline-none focus:border-emerald-500"
            disabled={isStreaming}
          />
          <button
            type="submit"
            disabled={!inputMsg.trim() || isStreaming}
            className="px-5 py-3 rounded-xl bg-emerald-500 hover:bg-emerald-600 disabled:opacity-50 text-slate-950 font-bold text-xs flex items-center gap-2 transition-colors shadow-sm"
          >
            <Send className="w-4 h-4" />
            <span className="hidden sm:inline">Kirim</span>
          </button>
        </form>
      </div>

      {/* Right Sidebar: Progressive Personalization + Live Snapshot + Allocation */}
      <div className="w-full lg:w-80 xl:w-96 flex flex-col gap-4 overflow-y-auto">
        {/* Card 1: Optional Profile Completeness & Smart Nudge */}
        <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-sm space-y-3.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-bold text-slate-200 uppercase tracking-wider">
              <SlidersHorizontal className="w-4 h-4 text-emerald-400" />
              <span>Akurasi Personalisasi</span>
            </div>
            <span className="text-xs font-extrabold text-emerald-400">{completenessPct}%</span>
          </div>

          <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-teal-400 transition-all duration-500"
              style={{ width: `${Math.max(8, completenessPct)}%` }}
            />
          </div>

          {autoUpdatedNotice && (
            <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-[11px] text-emerald-300 font-medium">
              <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
              <span>Profil diperbarui otomatis dari obrolanmu!</span>
            </div>
          )}

          {missingHints.length > 0 ? (
            <p className="text-[11px] text-slate-400 leading-relaxed">
              <strong className="text-slate-200">Opsional:</strong> Ceritakan lewat chat atau isi cepat{" "}
              <span className="text-emerald-300">{missingHints.slice(0, 2).join(" & ").toLowerCase()}</span> supaya
              hitungan dana darurat, rasio cicilan, & portofolio makin presisi.
            </p>
          ) : (
            <p className="text-[11px] text-emerald-300/90 leading-relaxed">
              Profil finansial intimu sudah lengkap—rekomendasi AI kini dipersonalisasi penuh.
            </p>
          )}

          {/* Instant Sharia Toggle */}
          <div className="flex items-center justify-between pt-1 pb-1 border-t border-slate-800/80">
            <div className="flex items-center gap-2">
              <MoonStar className="w-3.5 h-3.5 text-teal-400" />
              <span className="text-xs font-medium text-slate-200">Preferensi Instrumen Syariah</span>
            </div>
            <button
              type="button"
              onClick={handleToggleSharia}
              className={`w-10 h-5 rounded-full transition-colors p-0.5 ${
                shariaActive ? "bg-emerald-500" : "bg-slate-700"
              }`}
              aria-label="Toggle Mode Syariah"
            >
              <div
                className={`w-4 h-4 rounded-full bg-white transition-transform ${
                  shariaActive ? "translate-x-5" : "translate-x-0"
                }`}
              />
            </button>
          </div>

          {/* Captured AI Memory Pills */}
          {profile?.memory_notes_list && profile.memory_notes_list.length > 0 && (
            <div className="space-y-1.5 pt-1 border-t border-slate-800/80">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                Konteks yang Diingat AI
              </div>
              <div className="flex flex-wrap gap-1.5">
                {profile.memory_notes_list.map((note, idx) => (
                  <span
                    key={idx}
                    className="text-[10px] px-2 py-0.5 rounded-md bg-slate-800 text-slate-300 border border-slate-700"
                  >
                    {note}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Collapsible Optional Profile Quick-Editor */}
          <button
            type="button"
            onClick={() => setShowProfileForm((v) => !v)}
            className="w-full py-2 px-3 rounded-xl bg-slate-800 hover:bg-slate-700/80 text-slate-200 text-xs font-semibold flex items-center justify-between border border-slate-700 transition-colors"
          >
            <span>{showProfileForm ? "Tutup Form Profil Opsional" : "Lengkapi / Edit Profil (Opsional)"}</span>
            {showProfileForm ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>

          {showProfileForm && (
            <form onSubmit={handleSaveOptionalProfile} className="space-y-3 pt-2 border-t border-slate-800 text-xs">
              <div className="grid grid-cols-2 gap-2.5">
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Penghasilan/bln (Rp)</label>
                  <input
                    type="number"
                    min="0"
                    value={incomeInput}
                    onChange={(e) => setIncomeInput(parseFloat(e.target.value) || 0)}
                    className="w-full px-2.5 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-white"
                  />
                </div>
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Pengeluaran/bln (Rp)</label>
                  <input
                    type="number"
                    min="0"
                    value={expenseInput}
                    onChange={(e) => setExpenseInput(parseFloat(e.target.value) || 0)}
                    className="w-full px-2.5 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-white"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2.5">
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Cicilan Utang/bln (Rp)</label>
                  <input
                    type="number"
                    min="0"
                    value={debtInput}
                    onChange={(e) => setDebtInput(parseFloat(e.target.value) || 0)}
                    className="w-full px-2.5 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-white"
                  />
                </div>
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Status Pernikahan</label>
                  <select
                    value={maritalInput}
                    onChange={(e) => setMaritalInput(e.target.value as "SINGLE" | "MARRIED")}
                    className="w-full px-2.5 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-white"
                  >
                    <option value="SINGLE">Lajang</option>
                    <option value="MARRIED">Menikah</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Tanggungan</label>
                  <input
                    type="number"
                    min="0"
                    max="15"
                    value={dependentsInput}
                    onChange={(e) => setDependentsInput(parseInt(e.target.value) || 0)}
                    className="w-full px-2 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-white"
                  />
                </div>
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Usia</label>
                  <input
                    type="number"
                    min="17"
                    max="85"
                    value={ageInput}
                    onChange={(e) => setAgeInput(parseInt(e.target.value) || 28)}
                    className="w-full px-2 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-white"
                  />
                </div>
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Target FIRE</label>
                  <input
                    type="number"
                    min="25"
                    max="90"
                    value={fireAgeInput}
                    onChange={(e) => setFireAgeInput(parseInt(e.target.value) || 50)}
                    className="w-full px-2 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-white"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[11px] text-slate-400 mb-1">Profil Risiko Investasi</label>
                <select
                  value={riskInput}
                  onChange={(e) => setRiskInput(e.target.value as "CONSERVATIVE" | "MODERATE" | "AGGRESSIVE")}
                  className="w-full px-2.5 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-white"
                >
                  <option value="CONSERVATIVE">Konservatif (Utamakan Aman)</option>
                  <option value="MODERATE">Moderat (Seimbang)</option>
                  <option value="AGGRESSIVE">Agresif (Pertumbuhan Maksimal)</option>
                </select>
              </div>

              <button
                type="submit"
                disabled={savingProfile}
                className="w-full py-2 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold transition-colors"
              >
                {savingProfile ? "Menyimpan..." : "Simpan Profil"}
              </button>
            </form>
          )}
        </div>

        {/* Card 2: Live Financial Snapshot */}
        <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-bold text-slate-200 uppercase tracking-wider">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <span>Snapshot Keuanganmu</span>
            </div>
            {healthContext && (
              <span className="text-[11px] font-bold px-2 py-0.5 rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                Skor {healthContext.health_score}/100
              </span>
            )}
          </div>

          <div className="space-y-2 text-xs">
            <div className="flex justify-between py-1.5 border-b border-slate-800 text-slate-400">
              <span>Kekayaan Bersih:</span>
              <strong className="text-white">{healthContext?.net_worth_formatted}</strong>
            </div>
            <div className="flex justify-between py-1.5 border-b border-slate-800 text-slate-400">
              <span>Penghasilan Acuan:</span>
              <strong className="text-slate-200">{healthContext?.monthly_income_formatted || "-"}</strong>
            </div>
            <div className="flex justify-between py-1.5 border-b border-slate-800 text-slate-400">
              <span>Pengeluaran Bulanan:</span>
              <strong className="text-white">{healthContext?.monthly_expenses_formatted}</strong>
            </div>
            <div className="flex justify-between py-1.5 border-b border-slate-800 text-slate-400">
              <span>Rasio Cicilan (DSR):</span>
              <strong
                className={
                  (healthContext?.dsr_percentage || 0) <= 30 ? "text-emerald-400" : "text-amber-400"
                }
              >
                {healthContext?.dsr_percentage ?? 0}% (maks 30%)
              </strong>
            </div>
            <div className="flex justify-between py-1.5 border-b border-slate-800 text-slate-400">
              <span>Dana Darurat ({healthContext?.household_summary || "Lajang"}):</span>
              <span className="text-emerald-400 font-semibold">
                {healthContext?.emergency_fund_months} / {healthContext?.emergency_target_months} bln
              </span>
            </div>
            <div className="flex justify-between py-1.5 border-b border-slate-800 text-slate-400">
              <span>Target Coast FIRE:</span>
              <strong className="text-sky-400">{healthContext?.coast_fire_formatted || "-"}</strong>
            </div>
            <div className="flex justify-between py-1.5 text-slate-400">
              <span>Target Penuh FIRE ({healthContext?.target_fire_age} th):</span>
              <strong className="text-emerald-400 font-bold">{healthContext?.fire_target_formatted}</strong>
            </div>
          </div>
        </div>

        {/* Card 3: Recommended Asset Allocation */}
        {allocations && (
          <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-sm space-y-4">
            <div className="flex items-center gap-2 text-xs font-bold text-slate-200 uppercase tracking-wider">
              <PieChart className="w-4 h-4 text-sky-400" />
              <span>Referensi Alokasi Portofolio</span>
            </div>

            <p className="text-[11px] text-slate-400 leading-relaxed">
              Model <strong>{allocations.profile}</strong> dengan estimasi imbal hasil historis{" "}
              <strong>{allocations.expected_cagr}</strong>/tahun.
            </p>

            <div className="space-y-2.5">
              {allocations.allocations.map((a, idx) => (
                <div key={idx} className="space-y-1">
                  <div className="flex justify-between text-[11px]">
                    <span className="text-slate-300">{a.asset}</span>
                    <span className="font-bold text-white">{a.percentage}%</span>
                  </div>
                  <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${a.percentage}%`, backgroundColor: a.color }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Honest Educational Disclaimer */}
        <div className="p-4 rounded-xl bg-slate-950 border border-slate-800/80 text-[10px] text-slate-500 leading-relaxed">
          <strong>Catatan Edukasi:</strong> AI Financial Planner adalah asisten perencanaan keuangan berbasis data &
          metodologi umum, bukan perencana keuangan berlisensi resmi. Seluruh keputusan finansial dan investasi berada
          sepenuhnya di tangan Anda.
        </div>
      </div>
    </div>
  );
}

