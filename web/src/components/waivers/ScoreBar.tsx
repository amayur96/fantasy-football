import { cn } from "@/lib/utils";

/** 0-100 add score as a short bar with the number; tone follows the tier cut-offs in waivers.py. */
export function ScoreBar({ score, className }: { score: number; className?: string }) {
  const tone = score >= 55 ? "bg-emerald-500" : score >= 40 ? "bg-amber-500" : "bg-muted-foreground/50";
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <span className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
        <span className={cn("block h-full rounded-full", tone)} style={{ width: `${Math.max(2, Math.min(100, score))}%` }} />
      </span>
      <span className="num w-8 text-right text-sm font-medium tabular-nums">{Math.round(score)}</span>
    </span>
  );
}
