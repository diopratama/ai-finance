import { Sparkles } from "lucide-react";

interface AppLogoProps {
  size?: number;
  className?: string;
}

export function AppLogo({ size = 36, className = "" }: AppLogoProps) {
  return (
    <div
      className={`relative flex items-center justify-center rounded-xl bg-gradient-to-tr from-[#f0b000] via-amber-400 to-[#d49a00] border border-[#f0b000]/50 shadow-md shadow-[#f0b000]/20 shrink-0 ${className}`}
      style={{ width: size, height: size }}
    >
      <Sparkles
        className="text-[#0c0a00]"
        style={{ width: Math.round(size * 0.54), height: Math.round(size * 0.54) }}
      />
    </div>
  );
}

