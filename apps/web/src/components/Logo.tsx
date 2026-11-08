import { cn } from "@/lib/utils";

/** Logo FindImmo : maison dont le toit forme une loupe. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={cn("size-8", className)} aria-hidden="true">
      <rect width="64" height="64" rx="16" className="fill-primary" />
      <path d="M14 31 32 16l18 15" fill="none" className="stroke-primary-foreground" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M19 29v18h14" fill="none" className="stroke-primary-foreground" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="40" cy="39" r="7" fill="none" className="stroke-primary-foreground" strokeWidth="4.5" />
      <path d="m45 44 5 5" className="stroke-primary-foreground" strokeWidth="4.5" strokeLinecap="round" />
    </svg>
  );
}

export function Logo() {
  return (
    <span className="flex items-center gap-2">
      <LogoMark className="size-7" />
      <span className="text-lg font-bold tracking-tight">
        Find<span className="text-primary">Immo</span>
      </span>
    </span>
  );
}
