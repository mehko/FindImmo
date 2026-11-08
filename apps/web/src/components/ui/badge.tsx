import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold leading-4 [&_svg]:size-3", {
  variants: {
    variant: {
      default: "bg-primary/12 text-primary",
      muted: "bg-muted text-muted-foreground",
      success: "bg-success/15 text-success",
      warning: "bg-warning/20 text-accent-foreground dark:text-warning",
      danger: "bg-danger/12 text-danger",
      accent: "bg-accent text-accent-foreground",
      solid: "bg-foreground/80 text-background backdrop-blur",
    },
  },
  defaultVariants: { variant: "default" },
});

export function Badge({ className, variant, ...props }: HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
