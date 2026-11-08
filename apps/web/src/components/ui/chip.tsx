import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Chip({ active, className, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { active?: boolean }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      className={cn(
        "inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full border px-3.5 text-sm font-medium transition-colors [&_svg]:size-4",
        active ? "border-primary bg-primary text-primary-foreground" : "border-input bg-card text-foreground hover:bg-muted",
        className,
      )}
      {...props}
    />
  );
}

export function Segmented<T extends string>({ value, options, onChange, className }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; className?: string }) {
  return (
    <div className={cn("grid auto-cols-fr grid-flow-col gap-1 rounded-xl bg-muted p-1", className)} role="radiogroup">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn("h-9 rounded-lg px-2 text-sm font-medium transition-all", value === o.value ? "bg-card text-foreground shadow-sm" : "text-muted-foreground")}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
