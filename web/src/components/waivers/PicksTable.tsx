import { Fragment, useState } from "react";
import { ChevronDownIcon, WavesIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { ColHead, NumCell, PlayerCell } from "@/components/dashboard/LineupCard";
import { InjuryBadge } from "@/components/PosBadge";
import { fmt, fmtSigned } from "@/lib/format";
import type { WaiverPick, WaiverPlayer, WaiverTier } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ScoreBar } from "./ScoreBar";

const NA = "--";
const POSITIONS = ["QB", "RB", "WR", "TE", "D/ST"] as const;
const TIER_LABEL: Record<WaiverTier, string> = { claim: "Claim now", stash: "Stash", watch: "Watch" };
const TIER_CLASS: Record<WaiverTier, string> = {
  claim: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  stash: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  watch: "bg-muted text-muted-foreground",
};
const COMPONENT_LABEL: Record<string, string> = { ros: "ROS experts", espn: "ESPN proj", fp_waiver: "Waiver panel", momentum: "Momentum", usage: "Usage" };

function TierBadge({ tier }: { tier: WaiverTier }) {
  return <span className={cn("inline-flex h-5 items-center rounded-full px-2 text-[11px] font-medium", TIER_CLASS[tier])}>{TIER_LABEL[tier]}</span>;
}

function usageText(p: WaiverPlayer): string {
  if (p.usage.length === 0 && p.snap_pct === null) return NA;
  const n = p.usage.length;
  const bits: string[] = [];
  if (n > 0) {
    const opps = p.usage.reduce((s, u) => s + (p.position === "QB" ? (u.pass_att ?? 0) + (u.carries ?? 0) : (u.targets ?? 0) + (u.carries ?? 0)), 0);
    bits.push(`${fmt(opps / n, 1)} ${p.position === "QB" ? "att" : "touches"}/g`);
  }
  if (p.snap_pct !== null) bits.push(`${Math.round(p.snap_pct * 100)}% snaps`);
  return bits.join(" · ");
}

function trendText(p: WaiverPlayer): string {
  const bits: string[] = [];
  if (p.sleeper_adds) bits.push(`${p.sleeper_adds.toLocaleString()} adds`);
  if (p.rw_add_pct) bits.push(`${fmtSigned(p.rw_add_pct, 0)}% MFL`);
  return bits.length ? bits.join(" · ") : NA;
}

function Components({ p }: { p: WaiverPlayer }) {
  const entries = Object.entries(p.components);
  if (entries.length === 0) return null;
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1.5">
      {entries.map(([k, v]) => (
        <li key={k} className="flex items-center gap-2 text-xs">
          <span className="w-24 text-muted-foreground">{COMPONENT_LABEL[k] ?? k}</span>
          <span className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
            <span className="block h-full rounded-full bg-foreground/60" style={{ width: `${Math.round(v * 100)}%` }} />
          </span>
          <span className="num w-7 text-right tabular-nums">{Math.round(v * 100)}</span>
        </li>
      ))}
      {p.missing.map((k) => (
        <li key={k} className="flex items-center gap-2 text-xs text-muted-foreground/70">
          <span className="w-24">{COMPONENT_LABEL[k] ?? k}</span>
          <span>no data</span>
        </li>
      ))}
    </ul>
  );
}

function PickRow({ pick, open, onToggle }: { pick: WaiverPick; open: boolean; onToggle: () => void }) {
  const p = pick.player;
  return (
    <Fragment>
      <TableRow className={cn("cursor-pointer", open && "bg-muted/40")} onClick={onToggle} aria-expanded={open}>
        <TableCell className="w-8 pr-0">
          <ChevronDownIcon className={cn("size-4 text-muted-foreground transition-transform", open && "rotate-180")} />
        </TableCell>
        <PlayerCell p={p} />
        <TableCell>
          <span className="flex flex-wrap items-center gap-1">
            <TierBadge tier={pick.tier} />
            <InjuryBadge status={p.injury_status ?? p.sleeper_injury} />
          </span>
        </TableCell>
        <TableCell>
          <ScoreBar score={p.add_score} />
        </TableCell>
        <TableCell className="num">{p.ros_pos_rank ?? <span className="text-muted-foreground">{NA}</span>}</TableCell>
        <TableCell>
          {p.fp_waiver_rank ? (
            <span className="inline-flex items-center gap-1">
              <span className="num">#{p.fp_waiver_rank}</span>
              {p.fp_faab && (
                <Badge variant="outline" className="h-4 px-1 text-[10px] font-semibold">
                  {p.fp_faab}
                </Badge>
              )}
            </span>
          ) : (
            <span className="text-muted-foreground">{NA}</span>
          )}
        </TableCell>
        <NumCell>{p.season_proj ? fmt(p.season_proj, 0) : NA}</NumCell>
        <NumCell>
          {p.percent_owned !== null ? `${Math.round(p.percent_owned)}%` : NA}
          {p.percent_change !== null && Math.abs(p.percent_change) >= 1 && (
            <span className={cn("ml-1 text-xs", p.percent_change > 0 ? "text-emerald-700 dark:text-emerald-300" : "text-rose-700 dark:text-rose-300")}>{fmtSigned(p.percent_change, 0)}</span>
          )}
        </NumCell>
        <TableCell className="text-xs">{trendText(p)}</TableCell>
        <TableCell className="text-xs">{usageText(p)}</TableCell>
        <TableCell>
          {pick.drop ? (
            <span className="flex flex-col">
              <span className="font-medium">{pick.drop.name}</span>
              <span className="text-xs text-muted-foreground">
                {pick.drop.position} · score {Math.round(pick.drop.add_score)}
              </span>
            </span>
          ) : (
            <span className="text-xs text-muted-foreground">{pick.tier === "watch" ? "no clear drop" : "open spot"}</span>
          )}
        </TableCell>
      </TableRow>
      {open && (
        <TableRow className="hover:bg-transparent">
          <TableCell colSpan={11} className="bg-muted/20 px-6 py-4">
            <div className="space-y-3">
              <p className="max-w-prose text-sm leading-7 text-foreground">{pick.why}</p>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <Components p={p} />
                <span className="flex flex-wrap gap-1">
                  {pick.sources.map((s) => (
                    <Badge key={s} variant="outline" className="h-5 text-[10px] font-medium text-muted-foreground">
                      {s}
                    </Badge>
                  ))}
                </span>
              </div>
            </div>
          </TableCell>
        </TableRow>
      )}
    </Fragment>
  );
}

export function PicksTable({ picks }: { picks: WaiverPick[] }) {
  const [pos, setPos] = useState<string>("ALL");
  const [tier, setTier] = useState<string>("all");
  const [open, setOpen] = useState<Set<number>>(() => new Set());
  const shown = picks.filter((pk) => (pos === "ALL" || pk.player.position === pos) && (tier === "all" || pk.tier === tier));
  const toggle = (id: number) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  return (
    <Card className="shadow-sm">
      <CardHeader className="gap-3">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <div>
            <CardTitle className="flex items-center gap-1.5">
              <WavesIcon className="size-4 text-muted-foreground" />
              Pickups
            </CardTitle>
            <CardDescription>Click a row for the reasoning. Score is 0-100 on the same scale as your bench, so a pickup only appears with a drop when it clearly beats someone.</CardDescription>
          </div>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <Tabs value={tier} onValueChange={setTier}>
              <TabsList>
                <TabsTrigger value="all">All</TabsTrigger>
                <TabsTrigger value="claim">Claim now</TabsTrigger>
                <TabsTrigger value="stash">Stash</TabsTrigger>
                <TabsTrigger value="watch">Watch</TabsTrigger>
              </TabsList>
            </Tabs>
            <ToggleGroup type="single" size="sm" variant="outline" value={pos} onValueChange={(v) => v && setPos(v)} aria-label="Position filter">
              <ToggleGroupItem value="ALL">All</ToggleGroupItem>
              {POSITIONS.map((p) => (
                <ToggleGroupItem key={p} value={p}>
                  {p}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {shown.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing on the wire clears the bar for this filter.</p>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <ColHead>{""}</ColHead>
                  <ColHead>Player</ColHead>
                  <ColHead tip="Claim now: beats a bench player by a clear margin. Stash: worth a spot, or a good player who is hurt. Watch: on the radar, no move yet.">Tier</ColHead>
                  <ColHead tip="Blend of FantasyPros rest-of-season rank, ESPN season projection, the FantasyPros waiver panel, add/drop momentum (Sleeper, Rotowire, ESPN) and usage (touches, snaps), adjusted for health and your roster's needs.">
                    Score
                  </ColHead>
                  <ColHead tip="FantasyPros rest-of-season consensus, position rank. A 1-QB list, so quarterbacks run deeper in a 2-QB league.">ROS</ColHead>
                  <ColHead tip="FantasyPros' weekly waiver-wire panel: rank and suggested FAAB bid.">Panel</ColHead>
                  <ColHead right tip="ESPN's full-season projection in this league's scoring.">
                    Proj
                  </ColHead>
                  <ColHead right tip="Rostered in ESPN leagues, with the 7-day change.">
                    Own
                  </ColHead>
                  <ColHead tip="Sleeper adds in the last two days; Rotowire's MyFantasyLeague roster-% swing this week.">Trend</ColHead>
                  <ColHead tip="Opportunities per game over the last three played weeks (targets + carries, or attempts for a QB) and the latest offensive snap share from nflverse.">
                    Usage
                  </ColHead>
                  <ColHead tip="The weakest bench player he can replace, chosen so you never fall below your starting slots at any position.">Drop</ColHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {shown.map((pk) => (
                  <PickRow key={pk.player.player_id} pick={pk} open={open.has(pk.player.player_id)} onToggle={() => toggle(pk.player.player_id)} />
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
