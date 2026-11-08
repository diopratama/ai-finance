"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PlusCircle, Bot, Sparkles, Database, LogOut } from "lucide-react";
import { AuthUser, getStoredUser, logoutUser } from "@/lib/api";
import { ThemeToggle } from "@/components/ThemeToggle";

export function Navbar() {
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    setUser(getStoredUser());
  }, []);

  return (
    <header className="h-16 border-b border-border bg-background/85 backdrop-blur-xl sticky top-0 z-40 px-6 sm:px-8 flex items-center justify-between gap-3">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 px-2.5 py-1 rounded-full bg-accent border border-[#f0b000]/30 text-[#8a6300] dark:text-[#f0b000] text-xs font-semibold">
          <span className="w-2 h-2 rounded-full bg-[#f0b000] animate-pulse" />
          <Database className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Dynamic DB & 9router AI Active</span>
          <span className="sm:hidden">AI Active</span>
        </div>
        <span className="text-xs text-muted-foreground hidden lg:inline">
          Mata Uang Acuan: <strong className="text-foreground">{user?.base_currency || "IDR"}</strong>
        </span>
      </div>

      <div className="flex items-center gap-2 sm:gap-2.5">
        <ThemeToggle />

        <Link
          href="/bot-pairing"
          className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold bg-secondary hover:bg-accent text-foreground border border-border transition-colors"
        >
          <Bot className="w-3.5 h-3.5 text-[#8a6300] dark:text-[#f0b000]" />
          <span>Simulator Bot</span>
        </Link>

        <Link
          href="/planner"
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold bg-accent hover:bg-[#f0b000]/20 text-[#8a6300] dark:text-[#f0b000] border border-[#f0b000]/35 transition-colors"
        >
          <Sparkles className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Tanya AI Planner</span>
          <span className="sm:hidden">AI</span>
        </Link>

        <Link
          href="/transactions?action=new"
          className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-bold bg-primary hover:bg-primary/90 text-primary-foreground transition-colors shadow-sm shadow-[#f0b000]/20"
        >
          <PlusCircle className="w-4 h-4" />
          <span>+ Transaksi</span>
        </Link>

        {user && (
          <button
            type="button"
            onClick={logoutUser}
            title={`Keluar (${user.email})`}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-secondary hover:bg-rose-500/10 text-muted-foreground hover:text-rose-500 border border-border hover:border-rose-500/30 transition-colors"
          >
            <LogOut className="w-3.5 h-3.5" />
            <span className="hidden xl:inline">Keluar</span>
          </button>
        )}
      </div>
    </header>
  );
}
