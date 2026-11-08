import { cn } from "@/lib/utils";

export function ScoreRing({ score, size = 44, className }: { score: number; size?: number; className?: string }) {
  const r = (size - 6) / 2;
  const c = 2 * Math.PI * r;
  const tone = score >= 75 ? "stroke-success" : score >= 50 ? "stroke-primary" : "stroke-warning";
  return (
    <span className={cn("relative inline-grid place-items-center", className)} style={{ width: size, height: size }} title={`Pertinence ${score}/100`}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth="4" className="stroke-muted" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth="4" strokeLinecap="round" className={tone} strokeDasharray={c} strokeDashoffset={c * (1 - score / 100)} />
      </svg>
      <span className="absolute text-xs font-bold tabular-nums">{score}</span>
    </span>
  );
}
