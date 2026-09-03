import { InfoIcon, SparklesIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { PosBadge } from "@/components/PosBadge";
import { errorMessage } from "@/lib/api";
import { fmt } from "@/lib/format";
import { useRecommendations } from "@/lib/queries";
import type { DraftView, Recommendation } from "@/lib/types";
import { cn } from "@/lib/utils";

/** ESPN slot keys that read better under their fantasy name. */
const SLOT_LABEL: Record<string, string> = { "RB/WR/TE": "FLEX", "WR/RB/TE": "FLEX", OP: "SUPERFLEX" };

const slotLabel = (slot: string) => SLOT_LABEL[slot] ?? slot;

/** ["QB","QB","RB/WR/TE"] -> [{label:"QB",n:2},{label:"FLEX",n:1}], original order kept. */
function needCounts(unfilled: string[]): { label: string; n: number }[] {
  const order: string[] = [];
  const counts = new Map<string, number>();
  for (const slot of unfilled) {
    const label = slotLabel(slot);
    if (!counts.has(label)) order.push(label);
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }
  return order.map((label) => ({ label, n: counts.get(label) ?? 0 }));
}

function needsPosition(pos: string, unfilled: string[], thin: string[]): boolean {
  if (thin.includes(pos)) return true;
  return unfilled.some((slot) => slot === pos || slot.split("/").includes(pos));
}

/** One recommendation: a single compact line. Clicking explains it; drafting happens in the lists. */
function RecChip({
  rec,
  index,
  pct,
  wanted,
  onOpenCard,
}: {
  rec: Recommendation;
  index: number;
  pct: number;
  wanted: boolean;
  onOpenCard: (playerId: number) => void;
}) {
  const p = rec.player;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          title={`Why ${p.name}?`}
          className={cn(
            "flex h-7 w-full items-center gap-1.5 rounded-md border border-l-2 px-1.5 text-left text-xs hover:bg-muted/60",
            wanted ? "border-l-primary/70" : "border-l-transparent",
          )}
        >
          <span className="num w-4 shrink-0 text-right text-[10px] text-muted-foreground">{index + 1}</span>
          <span className="min-w-0 flex-1 truncate font-medium">{p.name}</span>
          <PosBadge pos={p.position} className="h-4 shrink-0 px-1 text-[9px]" />
          <InfoIcon className="size-3 shrink-0 text-muted-foreground" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-96 space-y-2 text-xs">
        <div>
          <button
            type="button"
            className="text-sm font-semibold hover:underline"
            onClick={() => onOpenCard(p.player_id)}
            title="Open the full player card"
          >
            {p.name}
          </button>
          <div className="text-muted-foreground">
            {p.position}
            {p.pos_rank} · {p.pro_team} · tier {p.tier} · score {fmt(rec.score)}
          </div>
        </div>
        <Progress value={pct} className="h-1.5" />
        {rec.fit && <p className="font-medium">{rec.fit}</p>}
        {rec.sources && <p className="num text-[11px] text-muted-foreground">{rec.sources}</p>}
        {rec.strategy_team && (
          <p>
            <span className="font-medium">Your roster: </span>
            <span className="text-muted-foreground">{rec.strategy_team}</span>
          </p>
        )}
        {rec.strategy_market && (
          <p>
            <span className="font-medium">The room: </span>
            <span className="text-muted-foreground">{rec.strategy_market}</span>
          </p>
        )}
        {rec.why.length > 0 && (
          <ul className="list-disc space-y-0.5 pl-4 text-muted-foreground">
            {rec.why.map((b, i) => (
              <li key={i}>{b}</li>
            ))}
          </ul>
        )}
        <Button size="sm" variant="outline" className="w-full" onClick={() => onOpenCard(p.player_id)}>
          Open player card
        </Button>
      </PopoverContent>
    </Popover>
  );
}

/** A compact strip at the top of the draft: the ten picks that best answer what the roster needs. */
export function RecommendationsPanel({ view, onOpenCard }: { view: DraftView; onOpenCard: (playerId: number) => void }) {
  const recs = useRecommendations(view.on_the_clock !== null);
  const data = recs.data;
  const top = data?.top ?? [];
  const maxScore = Math.max(0, ...top.map((r) => r.score));
  const unfilled = data?.unfilled_starters ?? [];
  const thin = data?.thin_positions ?? [];
  const needs = needCounts(unfilled);

  return (
    <section className="shrink-0 rounded-xl bg-card ring-1 ring-foreground/10">
      <header className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b px-3 py-1.5 text-sm font-semibold">
        <SparklesIcon className="size-4 text-muted-foreground" />
        Recommended picks
        <span className="text-xs font-normal text-muted-foreground">click for the reasoning</span>
        {data && (
          <span className="ml-auto flex flex-wrap items-center gap-1.5 text-xs font-normal">
            <span className="text-muted-foreground">{needs.length > 0 ? "You still need:" : "All starting slots filled"}</span>
            {needs.map((n) => (
              <Badge key={n.label} variant="outline" className="num px-1.5 text-[10px]">
                {n.n > 1 ? `${n.n}\u00d7 ${n.label}` : n.label}
              </Badge>
            ))}
            {needs.length === 0 && thin.length > 0 && <span className="text-muted-foreground">thin at: {thin.join(", ")}</span>}
          </span>
        )}
      </header>
      <div className="p-2">
        {recs.isLoading && <Skeleton className="h-14" />}
        {recs.error && <p className="text-sm text-destructive">{errorMessage(recs.error)}</p>}
        {view.on_the_clock === null && !recs.isLoading && <p className="text-sm text-muted-foreground">Draft complete.</p>}
        {!recs.isLoading && !recs.error && top.length > 0 && (
          <div className="grid grid-cols-2 gap-1 sm:grid-cols-3 lg:grid-cols-5">
            {top.map((r, i) => (
              <RecChip
                key={r.player.player_id}
                rec={r}
                index={i}
                pct={maxScore > 0 ? Math.max(0, (r.score / maxScore) * 100) : 0}
                wanted={needsPosition(r.player.position, unfilled, thin)}
                onOpenCard={onOpenCard}
              />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
