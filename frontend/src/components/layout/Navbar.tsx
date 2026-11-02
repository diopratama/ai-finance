"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PlusCircle, Bot, Sparkles, Database, LogOut } from "lucide-react";
import { AuthUser, getStoredUser, logoutUser } from "@/lib/api";

export function Navbar() {
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    setUser(getStoredUser());
  }, []);

  return (
    <header className="h-16 border-b border-slate-800 bg-slate-900/80 backdrop-blur-md sticky top-0 z-40 px-8 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-medium">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <Database className="w-3.5 h-3.5" />
          <span>Dynamic DB & 9router AI Active</span>
        </div>
        <span className="text-xs text-slate-400 hidden sm:inline">
          Mata Uang Acuan: <strong className="text-slate-300">{user?.base_currency || "IDR"}</strong>
        </span>
      </div>

      <div className="flex items-center gap-3">
        <Link
          href="/bot-pairing"
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors"
        >
          <Bot className="w-3.5 h-3.5 text-sky-400" />
          <span>Simulator Bot</span>
        </Link>

        <Link
          href="/planner"
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 transition-colors"
        >
          <Sparkles className="w-3.5 h-3.5" />
          <span>Tanya AI Planner</span>
        </Link>

        <Link
          href="/transactions?action=new"
          className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-emerald-500 hover:bg-emerald-600 text-slate-950 transition-colors shadow-sm"
        >
          <PlusCircle className="w-4 h-4 font-bold" />
          <span>+ Transaksi</span>
        </Link>

        {user && (
          <button
            type="button"
            onClick={logoutUser}
            title={`Keluar (${user.email})`}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-slate-800/80 hover:bg-rose-500/10 text-slate-300 hover:text-rose-400 border border-slate-700 hover:border-rose-500/30 transition-colors"
          >
            <LogOut className="w-3.5 h-3.5" />
            <span className="hidden md:inline">Keluar</span>
          </button>
        )}
      </div>
    </header>
  );
}
