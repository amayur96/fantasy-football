import { Link } from "react-router";
import {
  HistoryIcon,
  LayoutGridIcon,
  RotateCcwIcon,
  SkipForwardIcon,
  SparklesIcon,
  TriangleAlertIcon,
  UserRoundIcon,
  WrenchIcon,
  XIcon,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { RecentPicks, RosterPanel } from "@/components/draft/SidePanels";
import { StrategyDialog } from "@/components/draft/StrategyDialog";
import { teamName } from "@/lib/format";
import { useDraftAssign, useDraftSkip, useDraftUndo, useRecommendations } from "@/lib/queries";
import type { DraftPick, DraftView } from "@/lib/types";
import { cn } from "@/lib/utils";

function Divider() {
  return <span className="hidden h-4 w-px shrink-0 bg-border sm:block" />;
}

/** How many of the most recent filled picks the "Fix a pick" list offers. */
const FIXABLE_PICKS = 10;

/** Newest-first list of picks that hold something — a player, or a skip. */
function filledPicks(view: DraftView): DraftPick[] {
  return view.state.picks
    .filter((p) => p.player_id !== null || p.unknown)
    .sort((a, b) => b.overall - a.overall)
    .slice(0, FIXABLE_PICKS);
}

/** Clear any recent pick that went in wrong — the escape hatch for an out-of-order board. */
function FixPickPopover({ view }: { view: DraftView }) {
  const assign = useDraftAssign();
  const rows = filledPicks(view);

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button size="xs" variant="outline">
          <WrenchIcon /> Fix a pick
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[24rem] gap-1 p-1.5">
        <div className="px-1 pt-0.5 text-[11px] font-medium text-muted-foreground">
          Most recent picks — clear one to re-enter it
        </div>
        {rows.length === 0 ? (
          <p className="p-1.5 text-xs text-muted-foreground">Nothing recorded yet.</p>
        ) : (
          <div className="max-h-[60vh] overflow-y-auto">
            {rows.map((p) => {
              const mine = p.owner_team_id === view.state.my_team_id;
              const name = p.unknown
                ? "skipped"
                : p.player_id !== null
                  ? (view.player_names[String(p.player_id)] ?? `#${p.player_id}`)
                  : "?";
              return (
                <div key={p.overall} className="flex h-7 items-center gap-1.5 rounded px-1.5 text-xs hover:bg-muted">
                  <span className="num w-20 shrink-0 text-muted-foreground">
                    R{p.round}.{p.pick_in_round} #{p.overall}
                  </span>
                  <span className={cn("w-24 shrink-0 truncate", mine ? "font-medium" : "text-muted-foreground")}>
                    {mine ? "You" : teamName(view.team_names, p.owner_team_id)}
                  </span>
                  <span className={cn("min-w-0 flex-1 truncate", p.unknown && "text-muted-foreground italic")}>{name}</span>
                  <Button
                    size="icon-xs"
                    variant="ghost"
                    className="shrink-0"
                    disabled={assign.isPending}
                    title={`Clear pick #${p.overall}`}
                    aria-label={`Clear pick #${p.overall}`}
                    onClick={() => assign.mutate({ overall: p.overall, player_id: null })}
                  >
                    <XIcon />
                  </Button>
                </div>
              );
            })}
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}

export function DraftTopBar({ view }: { view: DraftView }) {
  const skip = useDraftSkip();
  const undo = useDraftUndo();
  const recs = useRecommendations(view.on_the_clock !== null);
  const top = recs.data?.top?.[0];

  const otc = view.on_the_clock;
  const mine = otc !== null && otc.owner_team_id === view.state.my_team_id;
  const until = view.picks_until_my_turn;
  const busy = skip.isPending || undo.isPending;

  return (
    <div className={cn("shrink-0 rounded-xl bg-card px-3 py-2 ring-1 ring-foreground/10", mine && "ring-2 ring-emerald-500/60")}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs">
        {otc ? (
          <span className="num font-semibold">
            Round {otc.round} · Pick {otc.pick_in_round} <span className="text-muted-foreground">(#{otc.overall} overall)</span>
          </span>
        ) : (
          <span className="font-semibold">Draft complete</span>
        )}
        {view.state.provisional_order && (
          <Badge variant="outline" className="text-[10px]">
            provisional order
          </Badge>
        )}
        <Divider />
        {otc && (
          <span>
            <span className="text-muted-foreground">On the clock: </span>
            <span className="font-medium">{mine ? "You" : teamName(view.team_names, otc.owner_team_id)}</span>
            {otc.owner_team_id !== otc.original_team_id && (
              <span className="text-muted-foreground"> (via {teamName(view.team_names, otc.original_team_id)})</span>
            )}
          </span>
        )}
        <Divider />
        <span className={cn(until === 0 && "font-semibold text-emerald-600 dark:text-emerald-400")}>
          {until === null
            ? "No picks remaining for you"
            : until === 0
              ? "It is your pick"
              : `${until} pick${until === 1 ? "" : "s"} until your turn`}
        </span>
        {view.my_next_pick && (
          <span className="text-muted-foreground">
            Your next pick <span className="num font-medium text-foreground">#{view.my_next_pick.overall}</span> (R
            {view.my_next_pick.round}.{view.my_next_pick.pick_in_round})
          </span>
        )}

        <div className="ml-auto flex flex-wrap items-center gap-1.5">
          {top && (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="flex items-center gap-1.5 rounded-md bg-muted px-2 py-1">
                  <SparklesIcon className="size-3.5 text-muted-foreground" />
                  <span className="text-muted-foreground">Recommended:</span>
                  <span className="font-medium">
                    {top.player.name} ({top.player.position})
                  </span>
                </span>
              </TooltipTrigger>
              <TooltipContent className="max-w-sm">{top.reason}</TooltipContent>
            </Tooltip>
          )}
          <Popover>
            <PopoverTrigger asChild>
              <Button size="xs" variant="outline">
                <UserRoundIcon /> My roster
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" className="max-h-[75vh] w-80 overflow-y-auto p-0">
              <RosterPanel view={view} className="ring-0" />
            </PopoverContent>
          </Popover>
          <Popover>
            <PopoverTrigger asChild>
              <Button size="xs" variant="outline">
                <HistoryIcon /> Recent picks
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" className="max-h-[75vh] w-96 overflow-y-auto p-0">
              <RecentPicks view={view} className="ring-0" />
            </PopoverContent>
          </Popover>
          <FixPickPopover view={view} />
          <Tooltip>
            <TooltipTrigger asChild>
              <Button size="xs" disabled={busy || !view.can_undo} onClick={() => undo.mutate()}>
                <RotateCcwIcon /> Undo
              </Button>
            </TooltipTrigger>
            <TooltipContent>{view.undo_label ? `Undo ${view.undo_label}` : "Nothing to undo"}</TooltipContent>
          </Tooltip>
          <Button size="xs" variant="outline" disabled={busy || otc === null} onClick={() => skip.mutate()}>
            <SkipForwardIcon /> Skip
          </Button>
          <StrategyDialog />
          <Button asChild size="xs" variant="outline">
            <Link to="/board">
              <LayoutGridIcon /> Open board
            </Link>
          </Button>
        </div>
      </div>
      {view.state.warnings.length > 0 && (
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-amber-700 dark:text-amber-400">
          {view.state.warnings.map((w, i) => (
            <span key={i} className="flex items-center gap-1">
              <TriangleAlertIcon className="size-3" />
              {w}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
