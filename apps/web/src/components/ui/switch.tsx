import { cn } from "@/lib/utils";

export function Switch({ checked, onCheckedChange, label, className }: { checked: boolean; onCheckedChange: (v: boolean) => void; label: string; className?: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onCheckedChange(!checked)}
      className={cn("relative inline-flex h-7 w-12 shrink-0 items-center rounded-full transition-colors", checked ? "bg-primary" : "bg-input", className)}
    >
      <span className={cn("inline-block size-5 rounded-full bg-white shadow transition-transform", checked ? "translate-x-6" : "translate-x-1")} />
    </button>
  );
}
