import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-2xl border bg-card text-card-foreground shadow-[0_1px_2px_rgb(0_0_0/0.04)]", className)} {...props} />;
}
