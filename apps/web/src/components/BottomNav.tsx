import { Bell, Compass, Heart, ListFilter } from "lucide-react";
import { NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";

const TABS = [
  { to: "/", label: "Explorer", icon: Compass, end: true },
  { to: "/recherches", label: "Recherches", icon: ListFilter },
  { to: "/favoris", label: "Favoris", icon: Heart },
  { to: "/alertes", label: "Alertes", icon: Bell },
];

export function BottomNav({ alertCount }: { alertCount: number }) {
  return (
    <nav className="pb-safe fixed inset-x-0 bottom-0 z-30 border-t bg-nav backdrop-blur-lg" aria-label="Navigation principale">
      <ul className="mx-auto grid max-w-xl grid-cols-4">
        {TABS.map(({ to, label, icon: Icon, end }) => (
          <li key={to}>
            <NavLink to={to} end={end} className={({ isActive }) => cn("flex flex-col items-center gap-1 pt-2 pb-1 text-[11px] font-medium transition-colors", isActive ? "text-primary" : "text-muted-foreground")}>
              {({ isActive }) => (
                <>
                  <span className={cn("relative grid h-8 w-14 place-items-center rounded-full transition-colors", isActive && "bg-primary/12")}>
                    <Icon className="size-[22px]" strokeWidth={isActive ? 2.4 : 2} />
                    {to === "/alertes" && alertCount > 0 && (
                      <span className="absolute -top-0.5 right-2 min-w-4 rounded-full bg-danger px-1 text-center text-[10px] font-bold leading-4 text-white">{alertCount > 99 ? "99+" : alertCount}</span>
                    )}
                  </span>
                  {label}
                </>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
