"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Wallet,
  ArrowLeftRight,
  Target,
  Bot,
  Sparkles,
  Flame,
  ShieldCheck,
  UserCog,
  ShieldAlert,
  TrendingUp,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { AppLogo } from "@/components/AppLogo";
import { getStoredUser, AuthUser } from "@/lib/api";

export const NAV_ITEMS = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/wallets", label: "Dompet & Akun", icon: Wallet },
  { href: "/investment-research", label: "Riset Investasi AI", icon: TrendingUp, badge: "Swarm" },
  { href: "/budgets", label: "Alokasi Anggaran", icon: Target, badge: "Gajian" },
  { href: "/transactions", label: "Transaksi", icon: ArrowLeftRight },
  { href: "/bot-pairing", label: "Chatbot (WA & TG)", icon: Bot },
  { href: "/planner", label: "AI Financial Planner", icon: Sparkles, badge: "AI" },
  { href: "/fire", label: "FIRE Simulator", icon: Flame },
  { href: "/settings", label: "Pengaturan Profil", icon: UserCog },
];

interface SidebarProps {
  mobileOpen?: boolean;
  onClose?: () => void;
}

function SidebarContent({
  pathname,
  currentUser,
  onNavigate,
  showCloseButton,
  onClose,
}: {
  pathname: string | null;
  currentUser: AuthUser | null;
  onNavigate?: () => void;
  showCloseButton?: boolean;
  onClose?: () => void;
}) {
  return (
    <>
      {/* Brand Logo */}
      <div className="p-5 sm:p-6 border-b border-sidebar-border flex items-center justify-between gap-2">
        <Link href="/" onClick={onNavigate} className="flex items-center gap-2.5 min-w-0">
          <AppLogo size={36} />
          <div className="min-w-0">
            <div className="text-base font-bold text-foreground tracking-tight flex items-center gap-1.5">
              AI-Finance
              <span className="text-[10px] uppercase font-bold bg-[#f0b000]/15 text-[#8a6300] dark:text-[#f0b000] border border-[#f0b000]/30 px-1.5 py-0.5 rounded">
                AI
              </span>
            </div>
            <div className="text-xs text-muted-foreground font-medium truncate">
              Kelola Dompet &amp; Anggaran
            </div>
          </div>
        </Link>
        {showCloseButton && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Tutup menu navigasi"
            className="p-2 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-xl text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:hidden"
          >
            <X className="w-5 h-5" />
          </button>
        )}
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 p-4 space-y-1.5 overflow-y-auto" aria-label="Menu Utama">
        <div className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider px-3 mb-2">
          Menu Utama
        </div>
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href;
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              aria-current={isActive ? "page" : undefined}
              className={cn(
                "flex items-center justify-between px-3.5 py-2.5 min-h-[44px] rounded-xl text-sm font-medium transition-all group border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                isActive
                  ? "bg-accent text-[#8a6300] dark:text-[#f0b000] border-[#f0b000]/35 shadow-sm font-semibold"
                  : "border-transparent text-muted-foreground hover:text-foreground hover:bg-secondary/80"
              )}
            >
              <div className="flex items-center gap-3 min-w-0">
                <Icon
                  className={cn(
                    "w-4 h-4 shrink-0 transition-colors",
                    isActive
                      ? "text-[#8a6300] dark:text-[#f0b000]"
                      : "text-muted-foreground group-hover:text-foreground"
                  )}
                />
                <span className="truncate">{item.label}</span>
              </div>
              {item.badge && (
                <span className="text-[11px] font-bold px-1.5 py-0.5 rounded bg-[#f0b000]/20 text-[#8a6300] dark:text-[#f0b000] shrink-0">
                  {item.badge}
                </span>
              )}
            </Link>
          );
        })}

        {currentUser?.role === "admin" && (
          <div className="pt-3 mt-3 border-t border-sidebar-border">
            <div className="text-[11px] font-semibold text-rose-500 uppercase tracking-wider px-3 mb-1.5 flex items-center gap-1.5">
              <ShieldAlert className="w-3.5 h-3.5" />
              <span>Administrasi</span>
            </div>
            <Link
              href="/admin"
              onClick={onNavigate}
              aria-current={pathname === "/admin" ? "page" : undefined}
              className={cn(
                "flex items-center justify-between px-3.5 py-2.5 min-h-[44px] rounded-xl text-sm font-medium transition-all group border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                pathname === "/admin"
                  ? "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/35 font-semibold"
                  : "border-transparent text-muted-foreground hover:text-foreground hover:bg-secondary/80"
              )}
            >
              <div className="flex items-center gap-3">
                <ShieldAlert className="w-4 h-4 text-rose-500" />
                <span>Admin Console</span>
              </div>
              <span className="text-[11px] font-bold px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-600 dark:text-rose-400 border border-rose-500/30 uppercase">
                Admin
              </span>
            </Link>
          </div>
        )}
      </nav>

      {/* Footer Info Card */}
      <div className="p-4 border-t border-sidebar-border">
        <div className="p-3 rounded-xl bg-secondary/70 border border-border flex items-start gap-2.5">
          <ShieldCheck className="w-4 h-4 text-[#8a6300] dark:text-[#f0b000] shrink-0 mt-0.5" />
          <div>
            <div className="text-xs font-semibold text-foreground">Perencanaan Terhubung</div>
            <div className="text-xs text-muted-foreground leading-relaxed mt-0.5">
              Dompet, anggaran gajian, dan target FIRE tersinkronisasi.
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

export function Sidebar({ mobileOpen = false, onClose }: SidebarProps) {
  const pathname = usePathname();
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    setCurrentUser(getStoredUser());
  }, []);

  useEffect(() => {
    if (!mobileOpen || !onClose) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [mobileOpen, onClose]);

  return (
    <>
      {/* Desktop Permanent Sidebar */}
      <aside className="w-64 bg-sidebar text-sidebar-foreground border-r border-sidebar-border hidden md:flex flex-col h-dvh sticky top-0 shrink-0">
        <SidebarContent pathname={pathname} currentUser={currentUser} />
      </aside>

      {/* Mobile Slide-Over Drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden flex" role="dialog" aria-modal="true" aria-label="Menu Navigasi">
          <div
            className="fixed inset-0 bg-background/80 backdrop-blur-sm"
            onClick={onClose}
            aria-hidden="true"
          />
          <aside className="relative z-10 w-72 max-w-[85vw] bg-sidebar text-sidebar-foreground border-r border-sidebar-border flex flex-col h-dvh shadow-2xl">
            <SidebarContent
              pathname={pathname}
              currentUser={currentUser}
              onNavigate={onClose}
              showCloseButton
              onClose={onClose}
            />
          </aside>
        </div>
      )}
    </>
  );
}
