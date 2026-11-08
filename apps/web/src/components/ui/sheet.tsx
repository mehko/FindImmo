import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Panneau inférieur (bottom sheet) accessible, adapté à l'usage à une main. */
export function Sheet({ open, onOpenChange, title, children, footer, className }: { open: boolean; onOpenChange: (o: boolean) => void; title: string; children: ReactNode; footer?: ReactNode; className?: string }) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-[2px]" />
        <Dialog.Content
          aria-describedby={undefined}
          className={cn("animate-sheet-up fixed inset-x-0 bottom-0 z-50 mx-auto flex max-h-[92dvh] w-full max-w-xl flex-col rounded-t-3xl border-t bg-background shadow-2xl", className)}
        >
          <div className="mx-auto mt-2.5 h-1.5 w-10 rounded-full bg-input" />
          <div className="flex items-center justify-between px-5 pb-2 pt-3">
            <Dialog.Title className="text-lg font-semibold">{title}</Dialog.Title>
            <Dialog.Close className="grid size-9 place-items-center rounded-full hover:bg-muted" aria-label="Fermer">
              <X className="size-5" />
            </Dialog.Close>
          </div>
          <div className="flex-1 overflow-y-auto px-5 pb-4">{children}</div>
          {footer && <div className="pb-safe border-t bg-background px-5 pt-3">{footer}</div>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
