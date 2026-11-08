import { ArrowLeft, Settings } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Logo } from "./Logo";

export function TopBar({ title, back, actions }: { title?: string; back?: boolean; actions?: ReactNode }) {
  const navigate = useNavigate();
  return (
    <header className="pt-safe sticky top-0 z-30 border-b border-transparent bg-background/85 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-xl items-center gap-2 px-4">
        {back ? (
          <button onClick={() => (history.length > 1 ? navigate(-1) : navigate("/"))} className="-ml-2 grid size-10 place-items-center rounded-full hover:bg-muted" aria-label="Retour">
            <ArrowLeft className="size-5" />
          </button>
        ) : null}
        <div className="min-w-0 flex-1">{title ? <h1 className="truncate text-lg font-semibold">{title}</h1> : <Logo />}</div>
        {actions}
        {!back && (
          <Link to="/parametres" className="grid size-10 place-items-center rounded-full hover:bg-muted" aria-label="Paramètres">
            <Settings className="size-5" />
          </Link>
        )}
      </div>
    </header>
  );
}
