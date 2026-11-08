import type { PricePoint, TransactionType } from "@findimmo/shared";
import { formatDate, formatPrice, percent } from "@/lib/format";

/** Historique des prix en escalier. Affiché seulement s'il y a au moins un changement. */
export function PriceHistory({ history, transaction }: { history: PricePoint[]; transaction?: TransactionType }) {
  if (history.length < 2) {
    return <p className="text-sm text-muted-foreground">Aucun changement de prix observé depuis la première détection.</p>;
  }
  const prices = history.map((p) => p.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const t0 = Date.parse(history[0]!.at);
  const t1 = Math.max(Date.parse(history[history.length - 1]!.at), t0 + 1);
  const W = 320;
  const H = 90;
  const x = (at: string) => 8 + ((Date.parse(at) - t0) / (t1 - t0)) * (W - 16);
  const y = (p: number) => (max === min ? H / 2 : 10 + (1 - (p - min) / (max - min)) * (H - 20));
  let d = `M ${x(history[0]!.at)} ${y(history[0]!.price)}`;
  for (const p of history.slice(1)) d += ` H ${x(p.at)} V ${y(p.price)}`;
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-24 w-full" role="img" aria-label="Évolution du prix">
        <path d={d} fill="none" className="stroke-primary" strokeWidth="2.5" strokeLinejoin="round" />
        {history.map((p) => (
          <circle key={p.at} cx={x(p.at)} cy={y(p.price)} r="3.5" className="fill-card stroke-primary" strokeWidth="2" />
        ))}
      </svg>
      <ul className="mt-2 divide-y text-sm">
        {[...history].reverse().map((p, i, arr) => {
          const prev = arr[i + 1];
          return (
            <li key={p.at} className="flex items-center justify-between py-2">
              <span className="text-muted-foreground">{formatDate(p.at)}</span>
              <span className="font-medium tabular-nums">
                {formatPrice(p.price, transaction)}
                {prev && <span className={p.price < prev.price ? "ml-2 text-success" : "ml-2 text-danger"}>{percent(prev.price, p.price)}</span>}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
