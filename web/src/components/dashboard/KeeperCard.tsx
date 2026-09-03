import { Fragment, useMemo, useState } from "react";
import { ArrowDownIcon, ArrowUpIcon, CheckIcon, ChevronDownIcon, ChevronRightIcon, StarIcon, TriangleAlertIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { NotReady } from "@/components/NotReady";
import { InjuryBadge, PosBadge } from "@/components/PosBadge";
import { fmt, fmtInt, fmtSigned, fpRankText, scoringLabel } from "@/lib/format";
import { useKeeperCostOverride, useKeeperOptions, useSaveKeepers, useSetup, useSettings } from "@/lib/queries";
import type { CostSource, KeeperOption, RankedPlayer, SeasonPoints } from "@/lib/types";
import { cn } from "@/lib/utils";

const SOURCE_STYLE: Record<CostSource, string> = {
  drafted: "",
  kept: "bg-sky-500/15 text-sky-700 dark:text-sky-300",
  undrafted: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  override: "bg-violet-500/15 text-violet-700 dark:text-violet-300",
};

function sortOptions(opts: KeeperOption[]): KeeperOption[] {
  return [...opts].sort((a, b) => {
    const av = a.surplus_points;
    const bv = b.surplus_points;
    if (av === null && bv === null) return a.roster_entry.name.localeCompare(b.roster_entry.name);
    if (av === null) return 1;
    if (bv === null) return -1;
    return bv - av;
  });
}

function Th({ label, tip, className }: { label: string; tip: string; className?: string }) {
  return (
    <TableHead className={className}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="cursor-help underline decoration-dotted underline-offset-4">{label}</span>
        </TooltipTrigger>
        <TooltipContent className="max-w-xs">{tip}</TooltipContent>
      </Tooltip>
    </TableHead>
  );
}

/** ESPN-vs-experts disagreement chip; hidden unless the gap is large. */
const GAP_THRESHOLD = 15;

function FpRankCell({ p }: { p: RankedPlayer | null }) {
  const text = p ? fpRankText(p) : null;
  if (!p || text === null) return <span className="text-muted-foreground">—</span>;
  const gap = p.consensus_gap;
  const showGap = gap !== null && Math.abs(gap) >= GAP_THRESHOLD;
  const n = gap === null ? 0 : Math.round(Math.abs(gap));
  return (
    <div className="flex items-center gap-1.5">
      <span className="num">{text}</span>
      {showGap && (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="inline-flex cursor-help items-center rounded-full bg-amber-500/15 p-0.5 text-amber-700 dark:text-amber-300">
              {gap > 0 ? <ArrowUpIcon className="size-3" /> : <ArrowDownIcon className="size-3" />}
            </span>
          </TooltipTrigger>
          <TooltipContent className="max-w-xs">
            ESPN projects him {n} spots {gap > 0 ? "higher" : "lower"} than the experts do
          </TooltipContent>
        </Tooltip>
      )}
    </div>
  );
}

function TierCell({ tier }: { tier: number | null | undefined }) {
  if (tier === null || tier === undefined) return <span className="text-muted-foreground">—</span>;
  return (
    <Badge variant="secondary" className="num px-1.5 text-[10px]">
      Tier {tier}
    </Badge>
  );
}

function RecentSeasons({ rows }: { rows: SeasonPoints[] }) {
  if (rows.length === 0) return null;
  return (
    <div className="mt-2">
      <div className="text-xs font-medium text-muted-foreground">Recent seasons</div>
      <table className="mt-0.5 text-xs">
        <thead className="text-muted-foreground">
          <tr>
            <th className="pr-4 text-left font-normal">Season</th>
            <th className="pr-4 text-right font-normal">Points</th>
            <th className="pr-4 text-right font-normal">Per game</th>
            <th className="text-right font-normal">Games</th>
          </tr>
        </thead>
        <tbody className="num">
          {rows.map((r) => (
            <tr key={r.season}>
              <td className="pr-4 text-left">{r.season}</td>
              <td className="pr-4 text-right">{r.games > 0 ? fmt(r.points, 0) : "—"}</td>
              <td className="pr-4 text-right">{r.games > 0 ? fmt(r.avg) : "—"}</td>
              <td className="text-right">{r.games > 0 ? r.games : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OverrideInput({ opt, overrideRound }: { opt: KeeperOption; overrideRound: number | undefined }) {
  const mut = useKeeperCostOverride();
  const [val, setVal] = useState<string>(overrideRound !== undefined ? String(overrideRound) : "");
  const [seen, setSeen] = useState(overrideRound);
  if (seen !== overrideRound) {
    setSeen(overrideRound);
    setVal(overrideRound !== undefined ? String(overrideRound) : "");
  }
  const commit = () => {
    const trimmed = val.trim();
    const n = trimmed === "" ? null : Number(trimmed);
    if (n !== null && (!Number.isInteger(n) || n < 1)) return;
    if (n === (overrideRound ?? null)) return;
    mut.mutate({ player_id: opt.roster_entry.player_id, cost_round: n });
  };
  return (
    <Input
      type="number"
      min={1}
      placeholder="—"
      className="num h-7 w-16"
      value={val}
      disabled={mut.isPending}
      onChange={(e) => setVal(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
      }}
    />
  );
}

export function KeeperCard() {
  const options = useKeeperOptions();
  const setup = useSetup();
  const settings = useSettings();
  const save = useSaveKeepers();
  const ext = settings.data?.external ?? null;
  const fmtLabel = ext ? `${scoringLabel(ext.scoring).toLowerCase()}${ext.superflex ? " superflex" : ""}` : "your scoring format";
  const fpRankTip = ext
    ? `FantasyPros expert consensus rank (${fmtLabel}, ${ext.fp_experts} experts): overall rank · position rank. An amber arrow means ESPN's projection disagrees with the experts by 15+ spots.`
    : "FantasyPros expert consensus rank: overall rank · position rank. Not loaded yet: sync or refresh rankings.";
  const fpTierTip = `FantasyPros' own tier for the same consensus list (${fmtLabel}). Players in the same tier are close to interchangeable.`;
  const bcTierTip = "Boris Chen tier: his clustering of the FantasyPros consensus by position. A tier break means a real drop-off. Note it's built from one-QB rankings, so it doesn't reflect your two-QB league across positions.";
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [confirm, setConfirm] = useState<KeeperOption | null>(null);

  const sorted = useMemo(() => sortOptions(options.data ?? []), [options.data]);
  const maxPts = useMemo(() => Math.max(0, ...sorted.map((o) => o.surplus_points ?? 0)), [sorted]);
  const myKeeper = setup.data?.setup.my_keeper ?? null;
  const overrides = setup.data?.setup.keeper_cost_overrides ?? {};
  const best = sorted.find((o) => o.player && o.surplus_points !== null) ?? null;

  if (options.error) return <NotReady error={options.error} />;
  if (options.isLoading || !options.data) return <Skeleton className="h-64 w-full" />;

  const toggle = (id: number) =>
    setExpanded((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  const doSetKeeper = (opt: KeeperOption) => {
    const s = setup.data;
    if (!s) return;
    save.mutate(
      {
        other_keepers: s.setup.other_keepers,
        my_keeper: {
          team_id: s.my_team_id,
          player_id: opt.roster_entry.player_id,
          player_name: opt.roster_entry.name,
          round: opt.cost_round,
          tentative: false,
          owner_name: "",
        },
      },
      { onSuccess: () => setConfirm(null) },
    );
  };

  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle>Keeper</CardTitle>
        <CardDescription>
          Your players from last season, ranked by how much value each returns for the round you would give up.
          {myKeeper ? (
            <>
              {" "}
              Current keeper: <span className="font-medium text-foreground">{myKeeper.player_name}</span> (round {myKeeper.round}).
            </>
          ) : (
            " No keeper selected yet."
          )}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {sorted.some((o) => !o.slot_known) && (
          <p className="text-xs text-muted-foreground">
            Draft order not confirmed yet: surplus values assume an average draft slot. Hover a surplus number to see its range across
            slots, and confirm the order or pick your slot in the Draft slot card to make these exact.
          </p>
        )}
        {best && (
          <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <StarIcon className="size-4 text-emerald-600" />
              <span className="text-sm font-medium">
                Recommendation: keep {best.roster_entry.name} at round {best.cost_round}
              </span>
              <Badge variant="secondary" className="num">
                {fmtSigned(best.surplus_rounds)} rounds
              </Badge>
              <Badge variant="secondary" className="num">
                {fmtSigned(best.surplus_points)} pts
              </Badge>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">{best.reason}</p>
            {sorted.length > 1 && sorted[1].player && (
              <p className="mt-1 text-xs text-muted-foreground">
                Runner-up: {sorted[1].roster_entry.name} at round {sorted[1].cost_round} ({fmtSigned(sorted[1].surplus_points)} pts).
              </p>
            )}
          </div>
        )}
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <Th className="w-10 text-right" label="#" tip="Rank by surplus points: how much more value you get than you give up. #1 is the recommendation." />
                <TableHead>Player</TableHead>
                <TableHead>Pos</TableHead>
                <Th label="FP Rank" tip={fpRankTip} />
                <Th label="FP Tier" tip={fpTierTip} />
                <Th label="BC Tier" tip={bcTierTip} />
                <Th
                  className="text-right"
                  label="Cost Rd"
                  tip="The round pick you give up to keep him. First year kept = the round he was drafted; each extra year = 2 rounds earlier; undrafted pickups cost the last round. Click the row to override."
                />
                <Th
                  className="text-right"
                  label="ADP Rd"
                  tip="Where drafts are taking him right now (ESPN average draft position, converted to a round for this league). Lower = more valuable."
                />
                <Th
                  className="text-right"
                  label="Surplus Rds"
                  tip="Cost round minus ADP round. +5 means you keep a round-4-caliber player for a round-9 pick. Zero or negative means keeping him gains nothing."
                />
                <Th
                  className="w-40"
                  label="Surplus Pts"
                  tip="Projected season points he gives you minus the projected points of the best player you could expect to be available at that pick. The bar is relative to your best option."
                />
                <TableHead className="w-28" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.map((opt, idx) => {
                const id = opt.roster_entry.player_id;
                const isMine = myKeeper?.player_id === id;
                const open = expanded.has(id);
                const pts = opt.surplus_points;
                const pct = pts !== null && maxPts > 0 ? Math.max(0, (pts / maxPts) * 100) : 0;
                const p = opt.player;
                return (
                  <Fragment key={id}>
                    <TableRow
                      className={cn("cursor-pointer", isMine && "bg-emerald-500/5", !p && "text-muted-foreground")}
                      onClick={() => toggle(id)}
                    >
                      <TableCell className="num text-right">
                        <span className={cn("font-semibold", idx === 0 && p && "text-emerald-600 dark:text-emerald-400")}>{p ? idx + 1 : "—"}</span>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          {open ? <ChevronDownIcon className="size-4 text-muted-foreground" /> : <ChevronRightIcon className="size-4 text-muted-foreground" />}
                          <span className="font-medium">{opt.roster_entry.name}</span>
                          <span className="text-xs text-muted-foreground">{p?.pro_team ?? opt.roster_entry.pro_team}</span>
                          <InjuryBadge status={p?.injury_status} />
                          {isMine && (
                            <Badge className="bg-emerald-600 text-white">
                              <CheckIcon /> my keeper
                            </Badge>
                          )}
                        </div>
                        {opt.warnings.length > 0 && (
                          <div className="mt-1 space-y-0.5">
                            {opt.warnings.map((w, i) => (
                              <div key={i} className="flex items-center gap-1 text-xs text-amber-700 dark:text-amber-300">
                                <TriangleAlertIcon className="size-3" /> {w}
                              </div>
                            ))}
                          </div>
                        )}
                      </TableCell>
                      <TableCell>
                        <PosBadge pos={opt.roster_entry.position} />
                      </TableCell>
                      <TableCell>
                        <FpRankCell p={p} />
                      </TableCell>
                      <TableCell>
                        <TierCell tier={p?.fp_tier} />
                      </TableCell>
                      <TableCell>
                        <TierCell tier={p?.bc_tier} />
                      </TableCell>
                      <TableCell className="text-right">
                        <span className="num font-medium">{opt.cost_round}</span>
                        <Badge variant="secondary" className={cn("ml-1.5 px-1.5 text-[10px]", SOURCE_STYLE[opt.cost_source])}>
                          {opt.cost_source}
                        </Badge>
                      </TableCell>
                      <TableCell className="num text-right">{fmtInt(opt.adp_round)}</TableCell>
                      <TableCell className={cn("num text-right", (opt.surplus_rounds ?? 0) > 0 ? "text-emerald-600 dark:text-emerald-400" : (opt.surplus_rounds ?? 0) < 0 ? "text-destructive" : "")}>
                        {fmtSigned(opt.surplus_rounds)}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          {opt.surplus_by_slot ? (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <span className="num w-12 cursor-help text-right underline decoration-dotted underline-offset-4">{fmt(pts)}</span>
                              </TooltipTrigger>
                              <TooltipContent className="max-w-xs">
                                Draft slot unknown, so this is the average. Across slots 1–{Object.keys(opt.surplus_by_slot).length}:{" "}
                                {fmtSigned(Math.min(...Object.values(opt.surplus_by_slot)))} to {fmtSigned(Math.max(...Object.values(opt.surplus_by_slot)))} pts.
                              </TooltipContent>
                            </Tooltip>
                          ) : (
                            <span className="num w-12 text-right">{fmt(pts)}</span>
                          )}
                          <Progress value={pct} className="h-1.5 flex-1" />
                        </div>
                      </TableCell>
                      <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                        <Button size="sm" variant={isMine ? "secondary" : "outline"} disabled={isMine || !setup.data} onClick={() => setConfirm(opt)}>
                          <StarIcon /> {isMine ? "Selected" : "Keep"}
                        </Button>
                      </TableCell>
                    </TableRow>
                    {open && (
                      <TableRow className="bg-muted/40 hover:bg-muted/40">
                        <TableCell />
                        <TableCell colSpan={10} className="whitespace-normal break-words text-sm">
                          <p className="max-w-prose leading-relaxed text-foreground">{opt.reason || "No analysis available."}</p>
                          <RecentSeasons rows={opt.history_points ?? []} />
                          {opt.history.length > 0 && (
                            <p className="mt-1 text-xs text-muted-foreground">
                              History: {opt.history.map((h) => `${h.season} rd ${h.round}${h.was_keeper ? " (kept)" : ""}`).join(" · ")}
                            </p>
                          )}
                          {p && (
                            <p className="text-xs text-muted-foreground">
                              Proj {fmt(p.proj_points, 0)} · ADP {fmt(p.adp)} · value {fmt(p.value)} · tier {p.tier} · {p.position}
                              {p.pos_rank}
                            </p>
                          )}
                          <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground" onClick={(e) => e.stopPropagation()}>
                            <span>Override cost round:</span>
                            <OverrideInput opt={opt} overrideRound={overrides[String(id)]} />
                            <span className="text-muted-foreground">(if the league rules it differently)</span>
                          </div>
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
                );
              })}
              {sorted.length === 0 && (
                <TableRow>
                  <TableCell colSpan={11} className="text-center text-muted-foreground">
                    No prior-season roster found. Sync with draft history to populate keeper options.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </CardContent>

      <Dialog open={confirm !== null} onOpenChange={(o) => !o && setConfirm(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Keep {confirm?.roster_entry.name}?</DialogTitle>
            <DialogDescription>
              This sets your keeper to {confirm?.roster_entry.name} at round {confirm?.cost_round}
              {myKeeper ? `, replacing ${myKeeper.player_name}` : ""}. The draft board is rebuilt with your round {confirm?.cost_round} pick
              consumed.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
            <Button disabled={save.isPending} onClick={() => confirm && doSetKeeper(confirm)}>
              Confirm
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
