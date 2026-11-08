"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Sidebar } from "./Sidebar";
import { Navbar } from "./Navbar";
import { hasAuthToken } from "@/lib/api";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const isPublicRoute =
    pathname === "/" ||
    pathname?.startsWith("/login") ||
    pathname?.startsWith("/register");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!isPublicRoute && !hasAuthToken()) {
      router.replace("/login");
      return;
    }
    setReady(true);
  }, [isPublicRoute, router]);

  if (isPublicRoute) {
    return <>{children}</>;
  }

  if (!ready) {
    return (
      <div className="min-h-screen w-full bg-background flex items-center justify-center text-muted-foreground text-xs">
        Memuat sesi...
      </div>
    );
  }

  return (
    <div className="bg-background text-foreground flex min-h-screen w-full">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Navbar />
        <main className="flex-1 p-6 sm:p-8 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
