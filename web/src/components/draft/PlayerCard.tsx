import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { InjuryBadge, PosBadge } from "@/components/PosBadge";
import { useDraftActions } from "@/components/draft/DraftRow";
import { errorMessage } from "@/lib/api";
import { fmt } from "@/lib/format";
import { useDraftState, usePlayerDetail } from "@/lib/queries";
import type { DetailMetric, DraftView, InjuryReport, PlayerDetail, RankedPlayer, SeasonPoints } from "@/lib/types";
import { cn } from "@/lib/utils";

function toneClass(tone: DetailMetric["tone"]): string {
  if (tone === "good") return "text-emerald-600 dark:text-emerald-400";
  if (tone === "bad") return "text-destructive";
  return "";
}

/** Season totals with a bar per row, so a rising or fading player reads without doing the arithmetic. */
function RecentSeasons({ rows, error }: { rows: SeasonPoints[]; error: string | null }) {
  if (rows.length === 0) {
    return <p className="text-xs text-muted-foreground">{error ?? "No season history in this league's data."}</p>;
  }
  const max = Math.max(...rows.map((r) => r.points), 0);
  return (
    <table className="w-full text-xs">
      <thead className="text-muted-foreground">
        <tr>
          <th className="pr-3 text-left font-normal">Season</th>
          <th className="pr-3 text-right font-normal">Points</th>
          <th className="pr-3 text-right font-normal">Per game</th>
          <th className="pr-3 text-right font-normal">Games</th>
          <th className="w-24" />
        </tr>
      </thead>
      <tbody className="num">
        {rows.map((r) => (
          <tr key={r.season}>
            <td className="pr-3 text-left">{r.season}</td>
            <td className="pr-3 text-right">{r.games > 0 ? fmt(r.points, 0) : "—"}</td>
            <td className="pr-3 text-right">{r.games > 0 ? fmt(r.avg) : "—"}</td>
            <td className="pr-3 text-right">{r.games > 0 ? r.games : "—"}</td>
            <td className="py-1">
              <div className="h-1.5 w-full rounded-full bg-muted">
                <div
                  className="h-1.5 rounded-full bg-foreground/40"
                  style={{ width: `${max > 0 ? Math.max(0, (r.points / max) * 100) : 0}%` }}
                />
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function MetricRow({ metric }: { metric: DetailMetric }) {
  return (
    <div className="flex items-baseline justify-between gap-2 border-b border-border/60 py-1 text-xs last:border-b-0">
      {metric.hint ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="cursor-help text-muted-foreground underline decoration-dotted underline-offset-4">{metric.label}</span>
          </TooltipTrigger>
          <TooltipContent className="max-w-xs">{metric.hint}</TooltipContent>
        </Tooltip>
      ) : (
        <span className="text-muted-foreground">{metric.label}</span>
      )}
      <span className={cn("num shrink-0 font-medium", toneClass(metric.tone))}>{metric.value}</span>
    </div>
  );
}

/** Same assign path as every other draft control on the page. */
function DraftFooter({
  view,
  player,
  taken,
  onDone,
}: {
  view: DraftView;
  player: RankedPlayer;
  taken: boolean;
  onDone: () => void;
}) {
  const actions = useDraftActions(view);
  const otc = actions.onTheClock;
  return (
    <DialogFooter>
      <DialogClose asChild>
        <Button variant="outline">Close</Button>
      </DialogClose>
      <Button
        disabled={taken || actions.busy || actions.draftOver}
        title={
          taken
            ? `${player.name} is already off the board`
            : otc
              ? `Draft ${player.name} at #${otc.overall} (R${otc.round}.${otc.pick_in_round})`
              : "Draft complete"
        }
        onClick={() => {
          actions.draft(player.player_id);
          onDone();
        }}
      >
        {taken ? "Already drafted" : otc ? `Draft at #${otc.overall}` : "Draft complete"}
      </Button>
    </DialogFooter>
  );
}

function CardBody({ detail, view, onDone }: { detail: PlayerDetail; view: DraftView | undefined; onDone: () => void }) {
  const p = detail.player;
  const taken = detail.taken_at !== null || view?.taken_ids.includes(p.player_id) === true;
  return (
    <>
      <DialogHeader>
        <div className="flex flex-wrap items-center gap-2 pr-8">
          <DialogTitle>{p.name}</DialogTitle>
          <PosBadge pos={p.position} />
          <InjuryBadge status={p.injury_status} />
        </div>
        <DialogDescription>
          {p.pro_team || "FA"} · {p.position}
          {p.pos_rank} · Bye {p.bye_week ?? "—"}
        </DialogDescription>
      </DialogHeader>

      {detail.taken_at !== null && (
        <p className="text-xs text-muted-foreground">
          Drafted at pick #{detail.taken_at}
          {detail.taken_by ? ` by ${detail.taken_by}` : ""}
        </p>
      )}

      {detail.injury && <Injury report={detail.injury} />}

      <section className="space-y-1">
        <h3 className="text-xs font-semibold text-muted-foreground">Recent seasons</h3>
        <RecentSeasons rows={detail.history} error={detail.history_error} />
      </section>

      {detail.metrics.length > 0 && (
        <section className="grid grid-cols-1 gap-x-6 sm:grid-cols-2">
          {detail.metrics.map((m) => (
            <MetricRow key={m.label} metric={m} />
          ))}
        </section>
      )}

      {detail.notes.length > 0 && (
        <ul className="list-disc space-y-1 pl-4 text-xs text-muted-foreground">
          {detail.notes.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ul>
      )}

      {view && <DraftFooter view={view} player={p} taken={taken} onDone={onDone} />}
    </>
  );
}

/** The card behind a click on a player's name. The first open for a player can take a
 *  couple of seconds: the server goes to ESPN for his season history. */
const INJURY_STYLE: Record<string, string> = {
  none: "border-emerald-500/30 bg-emerald-500/5",
  watch: "border-amber-500/40 bg-amber-500/5",
  concern: "border-destructive/40 bg-destructive/5",
};

const INJURY_LABEL: Record<string, string> = { none: "No injury flags", watch: "Worth watching", concern: "Injury concern" };

/** Current designation, what the beat writers are saying, and games missed in past seasons. */
function Injury({ report }: { report: InjuryReport }) {
  return (
    <section className={cn("space-y-1.5 rounded-lg border p-2.5", INJURY_STYLE[report.level] ?? INJURY_STYLE.none)}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-xs font-semibold">Injury</h3>
        <span className="text-xs font-medium">{INJURY_LABEL[report.level] ?? ""}</span>
        {report.status && <InjuryBadge status={report.status.toUpperCase()} />}
        {report.body_part && <span className="text-xs text-muted-foreground">({report.body_part})</span>}
      </div>
      <p className="text-xs">{report.concern}</p>
      {report.missed.length > 0 && (
        <p className="num text-[11px] text-muted-foreground">
          Games missed: {report.missed.map((m) => `${m.season} ${m.missed}`).join(" · ")}
        </p>
      )}
      {report.notes.length > 0 && (
        <ul className="space-y-0.5 text-[11px] text-muted-foreground">
          {report.notes.map((n, i) => (
            <li key={i}>
              <span className="num">{n.date}</span> {n.headline}
            </li>
          ))}
        </ul>
      )}
      {report.error && <p className="text-[11px] text-muted-foreground">{report.error}</p>}
    </section>
  );
}

export function PlayerCard({ playerId, onOpenChange }: { playerId: number | null; onOpenChange: (open: boolean) => void }) {
  const detail = usePlayerDetail(playerId);
  const { data: view } = useDraftState();

  // Hold the last card through the close animation, so dismissing never flashes the skeleton.
  const [last, setLast] = useState<PlayerDetail | null>(null);
  if (detail.data && detail.data !== last) setLast(detail.data);
  const shown = detail.data ?? (playerId === null ? last : null);

  return (
    <Dialog open={playerId !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        {shown ? (
          <CardBody detail={shown} view={view} onDone={() => onOpenChange(false)} />
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>{detail.error ? "Player unavailable" : "Loading player…"}</DialogTitle>
              <DialogDescription>
                {detail.error ? errorMessage(detail.error) : "Pulling his season history from ESPN."}
              </DialogDescription>
            </DialogHeader>
            {!detail.error && (
              <div className="space-y-2">
                <Skeleton className="h-20 w-full" />
                <Skeleton className="h-28 w-full" />
                <Skeleton className="h-12 w-full" />
              </div>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
