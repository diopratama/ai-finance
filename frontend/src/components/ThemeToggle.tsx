"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/components/ThemeProvider";

export function ThemeToggle() {
  const { theme, mounted, toggle } = useTheme();

  const isDark = theme === "dark";

  return (
    <button
      type="button"
      onClick={toggle}
      title={isDark ? "Ganti ke mode terang" : "Ganti ke mode gelap"}
      aria-label={isDark ? "Ganti ke mode terang" : "Ganti ke mode gelap"}
      className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent transition-colors border border-transparent hover:border-border"
    >
      {mounted ? isDark ? <Sun className="h-4 w-4 text-[#f0b000]" /> : <Moon className="h-4 w-4 text-[#8a6300]" /> : <Sun className="h-4 w-4" />}
    </button>
  );
}

