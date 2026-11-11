import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(amount: number, currency: string = "IDR"): string {
  const c = (currency || "IDR").toUpperCase();
  if (c === "USD") {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    }).format(amount);
  }

  if (c === "GRAM" || c === "XAU") {
    return `${Number(amount).toLocaleString("id-ID", {
      minimumFractionDigits: 0,
      maximumFractionDigits: 3,
    })} gram`;
  }

  // Indonesian Rupiah format
  return `Rp ${Math.round(amount).toLocaleString("id-ID")}`;
}

export function formatMaskedCurrency(currency: string = "IDR"): string {
  const c = (currency || "IDR").toUpperCase();
  if (c === "USD") {
    return "$ ••••••";
  }
  if (c === "GRAM" || c === "XAU") {
    return "•••••• gram";
  }
  return "Rp ••••••";
}

export function formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("id-ID", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

