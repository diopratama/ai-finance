"use client";

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
} from "lucide-react";
import { cn } from "@/lib/utils";
import { AppLogo } from "@/components/AppLogo";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/wallets", label: "Dompet & Akun", icon: Wallet },
  { href: "/budgets", label: "Alokasi Anggaran", icon: Target, badge: "Gajian" },
  { href: "/transactions", label: "Transaksi", icon: ArrowLeftRight },
  { href: "/bot-pairing", label: "Chatbot (WA & TG)", icon: Bot },
  { href: "/planner", label: "AI Financial Planner", icon: Sparkles, badge: "AI" },
  { href: "/fire", label: "FIRE Simulator", icon: Flame },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 bg-sidebar text-sidebar-foreground border-r border-sidebar-border hidden md:flex flex-col h-screen sticky top-0 shrink-0">
      {/* Brand Logo */}
      <div className="p-6 border-b border-sidebar-border flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5">
          <AppLogo size={36} />
          <div>
            <div className="text-base font-bold text-foreground tracking-tight flex items-center gap-1.5">
              AI-Finance
              <span className="text-[10px] uppercase font-bold bg-[#f0b000]/15 text-[#8a6300] dark:text-[#f0b000] border border-[#f0b000]/30 px-1.5 py-0.5 rounded">
                AI
              </span>
            </div>
            <div className="text-[11px] text-muted-foreground font-medium">Smart Wealth & Freedom</div>
          </div>
        </Link>
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 p-4 space-y-1.5 overflow-y-auto">
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
              className={cn(
                "flex items-center justify-between px-3.5 py-2.5 rounded-xl text-sm font-medium transition-all group border",
                isActive
                  ? "bg-accent text-[#8a6300] dark:text-[#f0b000] border-[#f0b000]/35 shadow-sm font-semibold"
                  : "border-transparent text-muted-foreground hover:text-foreground hover:bg-secondary/80"
              )}
            >
              <div className="flex items-center gap-3">
                <Icon
                  className={cn(
                    "w-4 h-4 transition-colors",
                    isActive
                      ? "text-[#8a6300] dark:text-[#f0b000]"
                      : "text-muted-foreground group-hover:text-foreground"
                  )}
                />
                <span>{item.label}</span>
              </div>
              {item.badge && (
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-[#f0b000]/20 text-[#8a6300] dark:text-[#f0b000]">
                  {item.badge}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Holistic Status Card */}
      <div className="p-4 border-t border-sidebar-border">
        <div className="p-3 rounded-xl bg-secondary/70 border border-border flex items-start gap-2.5">
          <ShieldCheck className="w-4 h-4 text-[#8a6300] dark:text-[#f0b000] shrink-0 mt-0.5" />
          <div>
            <div className="text-xs font-semibold text-foreground">Holistic Planning Active</div>
            <div className="text-[11px] text-muted-foreground leading-relaxed mt-0.5">
              Alokasi gajian per dompet, Sinking Fund, 4% Rule & perencanaan adaptif.
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
