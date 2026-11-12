"use client";

// Build version timestamp: 20261108-223500
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Sidebar } from "./Sidebar";
import { Navbar } from "./Navbar";
import { hasAuthToken } from "@/lib/api";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isPublicRoute =
    pathname === "/" ||
    pathname?.startsWith("/login") ||
    pathname?.startsWith("/register");
  const [ready, setReady] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    if (!isPublicRoute && !hasAuthToken()) {
      window.location.href = "/login";
      return;
    }
    setReady(true);
  }, [isPublicRoute, pathname]);

  useEffect(() => {
    setMobileNavOpen(false);
  }, [pathname]);

  if (isPublicRoute) {
    return <>{children}</>;
  }

  if (!ready) {
    return (
      <div className="min-h-dvh w-full bg-background flex items-center justify-center text-muted-foreground text-xs">
        Memuat sesi...
      </div>
    );
  }

  return (
    <div className="bg-background text-foreground flex min-h-dvh w-full">
      <Sidebar mobileOpen={mobileNavOpen} onClose={() => setMobileNavOpen(false)} />
      <div className="flex-1 flex flex-col min-w-0">
        <Navbar onOpenMobileNav={() => setMobileNavOpen(true)} />
        <main className="flex-1 p-4 sm:p-6 lg:p-8 pb-[max(1rem,env(safe-area-inset-bottom))] overflow-y-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
