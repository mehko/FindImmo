import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export function EmptyState({ icon: Icon, title, children }: { icon: LucideIcon; title: string; children?: ReactNode }) {
  return (
    <div className="animate-fade-up flex flex-col items-center px-6 py-16 text-center">
      <span className="mb-4 grid size-16 place-items-center rounded-2xl bg-muted text-muted-foreground">
        <Icon className="size-7" />
      </span>
      <h2 className="text-base font-semibold">{title}</h2>
      {children && <div className="mt-2 max-w-xs text-sm text-muted-foreground">{children}</div>}
    </div>
  );
}
