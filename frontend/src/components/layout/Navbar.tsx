"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { PlusCircle, Bot, Sparkles, LogOut, User as UserIcon, Menu } from "lucide-react";
import { AuthUser, getStoredUser, logoutUser } from "@/lib/api";
import { ThemeToggle } from "@/components/ThemeToggle";
import { NAV_ITEMS } from "@/components/layout/Sidebar";

interface NavbarProps {
  onOpenMobileNav?: () => void;
}

export function Navbar({ onOpenMobileNav }: NavbarProps) {
  const pathname = usePathname();
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    setUser(getStoredUser());
  }, []);

  const currentNav =
    NAV_ITEMS.find((item) => pathname === item.href) ||
    (pathname === "/admin" ? { label: "Admin Console" } : { label: "AI-Finance" });

  return (
    <header className="h-16 border-b border-border bg-background/85 backdrop-blur-xl sticky top-0 z-40 px-4 sm:px-6 lg:px-8 flex items-center justify-between gap-2 sm:gap-3">
      <div className="flex items-center gap-2.5 min-w-0">
        {onOpenMobileNav && (
          <button
            type="button"
            onClick={onOpenMobileNav}
            aria-label="Buka menu navigasi"
            className="md:hidden p-2 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-xl bg-secondary hover:bg-accent text-foreground border border-border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring shrink-0"
          >
            <Menu className="w-5 h-5" />
          </button>
        )}

        <div className="min-w-0 flex items-center gap-3">
          <span className="md:hidden text-sm font-bold text-foreground truncate">
            {currentNav.label}
          </span>
          <span className="hidden md:inline text-xs text-muted-foreground">
            Mata Uang Acuan: <strong className="text-foreground">{user?.base_currency || "IDR"}</strong>
          </span>
        </div>
      </div>

      <div className="flex items-center gap-1.5 sm:gap-2.5 shrink-0">
        <ThemeToggle />

        <Link
          href="/bot-pairing"
          className="hidden lg:flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-semibold bg-secondary hover:bg-accent text-foreground border border-border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Bot className="w-3.5 h-3.5 text-[#8a6300] dark:text-[#f0b000]" />
          <span>Chatbot</span>
        </Link>

        <Link
          href="/planner"
          className="hidden sm:flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-semibold bg-accent hover:bg-[#f0b000]/20 text-[#8a6300] dark:text-[#f0b000] border border-[#f0b000]/35 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Sparkles className="w-3.5 h-3.5" />
          <span>Tanya AI</span>
        </Link>

        <Link
          href="/transactions?action=new"
          className="flex items-center gap-1.5 px-3 sm:px-3.5 py-2 min-h-[40px] rounded-xl text-xs font-bold bg-primary hover:bg-primary/90 text-primary-foreground transition-colors shadow-sm shadow-[#f0b000]/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <PlusCircle className="w-4 h-4 shrink-0" />
          <span className="hidden xs:inline sm:inline">Transaksi</span>
        </Link>

        {user && (
          <Link
            href="/settings"
            title="Pengaturan Profil"
            aria-label="Pengaturan Profil"
            className="flex items-center gap-1.5 px-2.5 py-2 min-h-[40px] min-w-[40px] justify-center rounded-xl text-xs font-semibold bg-secondary hover:bg-accent text-foreground border border-border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <UserIcon className="w-4 h-4 text-[#8a6300] dark:text-[#f0b000]" />
            <span className="hidden sm:inline max-w-[120px] truncate">{user.full_name || user.email}</span>
          </Link>
        )}

        {user && (
          <button
            type="button"
            onClick={logoutUser}
            title={`Keluar (${user.email})`}
            aria-label="Keluar dari akun"
            className="flex items-center gap-1.5 px-2.5 py-2 min-h-[40px] min-w-[40px] justify-center rounded-xl text-xs font-medium bg-secondary hover:bg-rose-500/10 text-muted-foreground hover:text-rose-500 border border-border hover:border-rose-500/30 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <LogOut className="w-4 h-4" />
            <span className="hidden xl:inline">Keluar</span>
          </button>
        )}
      </div>
    </header>
  );
}
