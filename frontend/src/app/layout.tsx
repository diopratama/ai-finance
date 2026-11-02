import type { Metadata } from "next";
import "./globals.css";
import { AppShell } from "@/components/layout/AppShell";

export const metadata: Metadata = {
  title: "AI-Finance | Smart Wealth, Budgeting & AI Financial Planner",
  description: "AI-powered Personal Finance app with automated WhatsApp/Telegram multimodal expense logging and holistic AI Financial Planner guidance.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="id" className="dark">
      <body className="bg-slate-950 text-slate-100 min-h-screen">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
