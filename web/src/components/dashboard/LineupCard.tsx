import { ChevronLeftIcon, ChevronRightIcon, RefreshCwIcon, TriangleAlertIcon, UserRoundIcon } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { InjuryBadge, PosBadge } from "@/components/PosBadge";
import { fmt, fmtSigned } from "@/lib/format";
import type { SlotRow, WeekPlayer, WeekView } from "@/lib/types";
import { cn } from "@/lib/utils";

const MIN_WEEK = 1;
const MAX_WEEK = 18;
const NA = "--";

function isStarterSlot(slot: string): boolean {
  return slot !== "BE" && slot !== "IR";
}

function ordinal(n: number): string {
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 13) return `${n}th`;
  switch (n % 10) {
    case 1:
      return `${n}st`;
    case 2:
      return `${n}nd`;
    case 3:
      return `${n}rd`;
    default:
      return `${n}th`;
  }
}

function num(n: number | null | undefined, digits = 1): string {
  if (n === null || n === undefined || Number.isNaN(n)) return NA;
  return n.toFixed(digits);
}

/** Sum of a numeric field over players, or null when no player has it. */
function sumField(players: WeekPlayer[], pick: (p: WeekPlayer) => number | null): number | null {
  let total: number | null = null;
  for (const p of players) {
    const v = pick(p);
    if (v === null || v === undefined) continue;
    total = (total ?? 0) + v;
  }
  return total;
}

function formatFetched(iso: string | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function NumCell({ children, className }: { children: React.ReactNode; className?: string }) {
  return <TableCell className={cn("num text-right", className)}>{children}</TableCell>;
}

function OprkCell({ rank }: { rank: number | null }) {
  if (rank === null) return <NumCell className="text-muted-foreground">{NA}</NumCell>;
  const tone = rank >= 20 ? "text-emerald-700 dark:text-emerald-300" : rank <= 8 ? "text-rose-700 dark:text-rose-300" : "";
  return <NumCell className={tone}>{ordinal(rank)}</NumCell>;
}

function FpCell({ p }: { p: WeekPlayer }) {
  if (!p.fp_pos_rank && !p.fp_grade) return <TableCell className="text-muted-foreground">{NA}</TableCell>;
  return (
    <TableCell>
      <span className="inline-flex items-center gap-1">
        <span className="num">{p.fp_pos_rank ?? NA}</span>
        {p.fp_grade && (
          <Badge variant="outline" className="h-4 px-1 text-[10px] font-semibold">
            {p.fp_grade}
          </Badge>
        )}
      </span>
    </TableCell>
  );
}

function PlayerCell({ p }: { p: WeekPlayer | null }) {
  return (
    <TableCell className="min-w-56">
      <div className="flex items-center gap-2.5">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
          <UserRoundIcon className="size-4" />
        </span>
        {p ? (
          <div className="flex min-w-0 flex-col gap-0.5">
            <span className="truncate font-semibold">{p.name}</span>
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span>{p.pro_team || NA}</span>
              <PosBadge pos={p.position} className="h-4 text-[10px]" />
            </span>
          </div>
        ) : (
          <span className="text-muted-foreground">Empty</span>
        )}
      </div>
    </TableCell>
  );
}

function PlayerRow({ row, tint, recommendedName }: { row: SlotRow; tint: "amber" | "green" | null; recommendedName: string | null }) {
  const p = row.player;
  const plusMinus = p && p.points !== null && p.espn_proj !== null ? p.points - p.espn_proj : null;
  const slotCell = (
    <TableCell className={cn("w-16 font-semibold text-muted-foreground", tint && "cursor-help")}>{row.label}</TableCell>
  );
  return (
    <TableRow
      className={cn(
        tint === "amber" && "bg-amber-500/10 hover:bg-amber-500/15",
        tint === "green" && "bg-emerald-500/10 hover:bg-emerald-500/15",
      )}
    >
      {tint && recommendedName ? (
        <Tooltip>
          <TooltipTrigger asChild>{slotCell}</TooltipTrigger>
          <TooltipContent>Recommended: {recommendedName}</TooltipContent>
        </Tooltip>
      ) : (
        slotCell
      )}
      <PlayerCell p={p} />
      {p ? (
        <>
          <TableCell className={cn(p.on_bye && "font-semibold text-muted-foreground")}>{p.on_bye ? "BYE" : (p.opponent ?? NA)}</TableCell>
          <TableCell>
            {p.injury_status && p.injury_status !== "ACTIVE" ? <InjuryBadge status={p.injury_status} /> : <span className="text-muted-foreground">{NA}</span>}
          </TableCell>
          <NumCell>{num(p.espn_proj)}</NumCell>
          <NumCell className={cn(p.points === null && "text-muted-foreground")}>{num(p.points)}</NumCell>
          <OprkCell rank={p.opp_rank_vs_pos} />
          <FpCell p={p} />
          <NumCell className={cn(p.bc_tier === null && "text-muted-foreground")}>{p.bc_tier === null ? NA : `T${p.bc_tier}`}</NumCell>
          <NumCell>{num(p.percent_started)}</NumCell>
          <NumCell>{num(p.percent_owned)}</NumCell>
          <NumCell
            className={cn(
              plusMinus === null && "text-muted-foreground",
              plusMinus !== null && plusMinus > 0 && "text-emerald-700 dark:text-emerald-300",
              plusMinus !== null && plusMinus < 0 && "text-rose-700 dark:text-rose-300",
            )}
          >
            {plusMinus === null ? NA : fmtSigned(plusMinus)}
          </NumCell>
          <NumCell>{num(p.season_proj)}</NumCell>
          <NumCell>{num(p.season_avg)}</NumCell>
          <NumCell>{num(p.last_points)}</NumCell>
        </>
      ) : (
        Array.from({ length: 13 }, (_, i) => (
          <TableCell key={i} className={cn("text-muted-foreground", i >= 2 && "text-right")}>
            {NA}
          </TableCell>
        ))
      )}
    </TableRow>
  );
}

function TotalsRow({ players }: { players: WeekPlayer[] }) {
  const proj = sumField(players, (p) => p.espn_proj);
  const pts = sumField(players, (p) => p.points);
  const fpts = sumField(players, (p) => p.season_proj);
  const avg = sumField(players, (p) => p.season_avg);
  const last = sumField(players, (p) => p.last_points);
  return (
    <TableRow className="bg-muted/40 font-semibold hover:bg-muted/40">
      <TableCell colSpan={4} className="text-xs tracking-wide text-muted-foreground uppercase">
        Totals
      </TableCell>
      <NumCell>{num(proj)}</NumCell>
      <NumCell className={cn(pts === null && "text-muted-foreground")}>{num(pts)}</NumCell>
      <TableCell colSpan={6} />
      <NumCell>{num(fpts)}</NumCell>
      <NumCell>{num(avg)}</NumCell>
      <NumCell>{num(last)}</NumCell>
    </TableRow>
  );
}

function GroupHead({ children, colSpan, className }: { children: React.ReactNode; colSpan: number; className?: string }) {
  return (
    <TableHead colSpan={colSpan} className={cn("h-8 border-b text-center text-[11px] font-semibold tracking-wide text-muted-foreground uppercase", className)}>
      {children}
    </TableHead>
  );
}

function ColHead({ children, right, tip }: { children: React.ReactNode; right?: boolean; tip?: string }) {
  const inner = tip ? (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="cursor-help underline decoration-dotted underline-offset-4">{children}</span>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">{tip}</TooltipContent>
    </Tooltip>
  ) : (
    children
  );
  return <TableHead className={cn("h-8 text-xs", right && "text-right")}>{inner}</TableHead>;
}

export interface LineupCardProps {
  view: WeekView;
  onWeekChange: (week: number) => void;
  onRefresh: () => void;
  refreshing: boolean;
}

export function LineupCard({ view, onWeekChange, onRefresh, refreshing }: LineupCardProps) {
  const starters = view.rows.filter((r) => isStarterSlot(r.slot));
  const bench = view.rows.filter((r) => r.slot === "BE");
  const ir = view.rows.filter((r) => r.slot === "IR");
  const shouldStart = new Set(Object.values(view.optimal_slots));
  const names = new Map<number, string>();
  for (const p of [...view.starters, ...view.bench]) names.set(p.player_id, p.name);

  const espnFetched = formatFetched(view.sources.espn);
  const fp = view.sources.fantasypros;
  const bc = view.sources.borischen;

  const groupCols = { starters: 2, week: 11, season: 3 } as const;

  return (
    <Card className="shadow-sm">
      <CardHeader className="gap-2">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <span className="text-sm text-muted-foreground">Set Lineup:</span>
          <div className="flex items-center gap-1">
            <Button size="icon-xs" variant="ghost" aria-label="Previous week" disabled={view.week <= MIN_WEEK} onClick={() => onWeekChange(view.week - 1)}>
              <ChevronLeftIcon />
            </Button>
            <span className="font-heading text-base font-medium">{view.week_label}</span>
            <Button size="icon-xs" variant="ghost" aria-label="Next week" disabled={view.week >= MAX_WEEK} onClick={() => onWeekChange(view.week + 1)}>
              <ChevronRightIcon />
            </Button>
          </div>
          {view.opponent_name && <span className="text-sm text-muted-foreground">vs {view.opponent_name}</span>}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button size="icon-sm" variant="outline" className="ml-auto" aria-label="Refresh week" disabled={refreshing} onClick={onRefresh}>
                <RefreshCwIcon className={cn(refreshing && "animate-spin")} />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Re-pull this week from ESPN and FantasyPros</TooltipContent>
          </Tooltip>
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <span>ESPN {espnFetched ? `fetched ${espnFetched}` : "not fetched"}</span>
          {fp && <span>· FantasyPros {fp}</span>}
          {bc && <span>· Boris Chen {bc}</span>}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {view.roster_empty && (
          <Alert>
            <TriangleAlertIcon />
            <AlertDescription>Your ESPN roster is empty — this fills in after the draft. Use the Keeper and Board tabs for now.</AlertDescription>
          </Alert>
        )}
        <div className="overflow-x-auto rounded-lg border">
          <Table className="text-xs sm:text-sm">
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <GroupHead colSpan={groupCols.starters} className="text-left">
                  Starters
                </GroupHead>
                <GroupHead colSpan={groupCols.week} className="border-l">
                  NFL Week {view.week}
                </GroupHead>
                <GroupHead colSpan={groupCols.season} className="border-l">
                  {view.season} Projections
                </GroupHead>
              </TableRow>
              <TableRow className="hover:bg-transparent">
                <ColHead>Slot</ColHead>
                <ColHead>Player</ColHead>
                <ColHead>Opp</ColHead>
                <ColHead>Status</ColHead>
                <ColHead right tip="ESPN projected points this week">
                  Proj
                </ColHead>
                <ColHead right>Score</ColHead>
                <ColHead right tip="Opponent's rank against this position: 1st = toughest matchup, 32nd = softest">
                  OPRK
                </ColHead>
                <ColHead tip="FantasyPros expert consensus weekly position rank and start/sit grade">FP</ColHead>
                <ColHead right tip="Boris Chen tier this week (lower is better)">
                  BC
                </ColHead>
                <ColHead right tip="Percent of ESPN leagues starting him">
                  %ST
                </ColHead>
                <ColHead right tip="Percent of ESPN leagues rostering him">
                  %ROST
                </ColHead>
                <ColHead right tip="Actual score minus projection">
                  +/-
                </ColHead>
                <ColHead right tip="Season projected points">
                  FPTS
                </ColHead>
                <ColHead right tip="Season average per game">
                  AVG
                </ColHead>
                <ColHead right tip="Points last week">
                  LAST
                </ColHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {starters.map((row) => {
                const rec = row.recommended_player_id;
                const mismatch = rec !== null && rec !== (row.player?.player_id ?? null);
                return <PlayerRow key={row.key} row={row} tint={mismatch ? "amber" : null} recommendedName={mismatch ? (names.get(rec) ?? null) : null} />;
              })}
              <TotalsRow players={starters.flatMap((r) => (r.player ? [r.player] : []))} />
              {bench.map((row) => {
                const p = row.player;
                const promote = p !== null && shouldStart.has(p.player_id);
                return <PlayerRow key={row.key} row={row} tint={promote ? "green" : null} recommendedName={promote && p ? p.name : null} />;
              })}
              {bench.length > 0 && <TotalsRow players={bench.flatMap((r) => (r.player ? [r.player] : []))} />}
              {ir.map((row) => (
                <PlayerRow key={row.key} row={row} tint={null} recommendedName={null} />
              ))}
            </TableBody>
          </Table>
        </div>
        {!view.roster_empty && (
          <p className="text-xs text-muted-foreground">
            Current lineup projects <span className="num font-medium text-foreground">{fmt(view.current_total)}</span> · optimal{" "}
            <span className="num font-medium text-foreground">{fmt(view.optimal_total)}</span>
            {view.optimal_total - view.current_total > 0.05 && (
              <>
                {" "}
                (<span className="num text-emerald-700 dark:text-emerald-300">{fmtSigned(view.optimal_total - view.current_total)}</span> available)
              </>
            )}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
