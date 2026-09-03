import { useMemo, useState, type KeyboardEvent } from "react";
import { ListOrderedIcon } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { DraftRow, useDraftActions, type RankSource } from "@/components/draft/DraftRow";
import type { CheatSheetResponse, DraftView, RankedPlayer } from "@/lib/types";

export type { RankSource };

// Deep enough that a full draft's worth of crossed-off rows never starves the list.
const MAX_ROWS = 1200;  // the whole ESPN pool; drafts run 18 rounds and waivers go deeper

const SOURCE_LABELS: { value: RankSource; label: string; title: string }[] = [
  { value: "espn", label: "ESPN", title: "ESPN average draft position — where the market is actually taking players" },
  { value: "fp", label: "FantasyPros", title: "FantasyPros expert consensus rank" },
  { value: "bc", label: "Boris Chen", title: "Boris Chen tiers first, expert consensus within a tier" },
];

interface Row {
  player: RankedPlayer;
  /** Position in the full list, so filtering never renumbers a player. */
  rank: number;
  taken: boolean;
}

/** `overall` is only the top 200; the per-position tiers carry the rest of the pool. */
function pool(sheet: CheatSheetResponse | undefined): RankedPlayer[] {
  if (!sheet) return [];
  const seen = new Set<number>();
  const out: RankedPlayer[] = [];
  const add = (p: RankedPlayer) => {
    if (seen.has(p.player_id)) return;
    seen.add(p.player_id);
    out.push(p);
  };
  for (const p of sheet.overall) add(p);
  for (const tiers of Object.values(sheet.by_pos)) {
    for (const tier of tiers ?? []) for (const p of tier) add(p);
  }
  return out;
}

/** Anything the source has no number for sorts last rather than first. */
function key(n: number | null | undefined): number {
  return n === null || n === undefined || Number.isNaN(n) ? Number.POSITIVE_INFINITY : n;
}

function compare(source: RankSource): (a: RankedPlayer, b: RankedPlayer) => number {
  if (source === "espn") {
    // Where drafters are actually taking him; players ESPN has no ADP for fall back to its own rank.
    return (a, b) => {
      const ak = key(a.adp ?? a.espn_rank);
      const bk = key(b.adp ?? b.espn_rank);
      if (ak !== bk) return ak - bk;
      return a.overall_rank - b.overall_rank;
    };
  }
  if (source === "bc") {
    // Tiers are per position, so an overall list is tier first, consensus within the tier.
    return (a, b) => {
      const at = key(a.bc_tier);
      const bt = key(b.bc_tier);
      if (at !== bt) return at - bt;
      const af = key(a.fp_rank);
      const bf = key(b.fp_rank);
      if (af !== bf) return af - bf;
      return a.overall_rank - b.overall_rank;
    };
  }
  return (a, b) => {
    const ar = key(a.fp_rank);
    const br = key(b.fp_rank);
    if (ar !== br) return ar - br;
    return a.overall_rank - b.overall_rank;
  };
}

export function OverallRankings({
  view,
  sheet,
  isLoading,
  source,
  onSourceChange,
  onOpenCard,
}: {
  view: DraftView;
  sheet: CheatSheetResponse | undefined;
  isLoading: boolean;
  source: RankSource;
  onSourceChange: (s: RankSource) => void;
  onOpenCard: (playerId: number) => void;
}) {
  const [q, setQ] = useState("");
  const actions = useDraftActions(view);

  const sorted = useMemo<Row[]>(() => {
    const taken = new Set(view.taken_ids);
    return pool(sheet)
      .sort(compare(source))
      .map((player, i) => ({ player, rank: i + 1, taken: taken.has(player.player_id) }));
  }, [sheet, view.taken_ids, source]);

  const rows = useMemo(() => {
    const ql = q.trim().toLowerCase();
    if (!ql) return sorted.slice(0, MAX_ROWS);
    return sorted
      .filter(
        ({ player: p }) =>
          p.name.toLowerCase().includes(ql) || p.pro_team.toLowerCase().includes(ql) || p.position.toLowerCase() === ql,
      )
      .slice(0, MAX_ROWS);
  }, [sorted, q]);

  // Enter drafts the top available row into the pick on the clock.
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== "Enter" || actions.busy || actions.draftOver) return;
    const first = rows.find((r) => !r.taken);
    if (!first) return;
    actions.draft(first.player.player_id);
    setQ("");
  };

  const firstAvailable = rows.find((r) => !r.taken)?.player.player_id;

  return (
    <section className="flex max-h-[70vh] min-h-0 flex-col overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10 lg:max-h-none lg:w-[34%] lg:min-w-80 lg:shrink-0">
      <header className="flex h-9 shrink-0 items-center justify-center gap-2 bg-muted px-3 text-sm font-semibold">
        <ListOrderedIcon className="size-4 text-muted-foreground" />
        Overall Rankings
      </header>
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b p-2">
        <ToggleGroup
          type="single"
          size="sm"
          variant="outline"
          spacing={0}
          value={source}
          aria-label="Ranking source"
          onValueChange={(v) => v && onSourceChange(v as RankSource)}
          className="grid w-auto flex-1 basis-52 grid-cols-3"
        >
          {SOURCE_LABELS.map((s) => (
            <ToggleGroupItem key={s.value} value={s.value} title={s.title} className="px-1 text-xs">
              {s.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <Input
          placeholder="Search players… (Enter = Draft)"
          className="h-7 min-w-0 flex-1 basis-44 text-xs"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={onKeyDown}
        />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {isLoading && <Skeleton className="m-2 h-[80vh]" />}
        {!isLoading && rows.length === 0 && <p className="p-3 text-xs text-muted-foreground">No players match.</p>}
        {rows.map((r) => (
          <DraftRow
            key={r.player.player_id}
            player={r.player}
            actions={actions}
            rank={r.rank}
            taken={r.taken}
            showPos
            sources
            activeSource={source}
            onOpenCard={onOpenCard}
            highlight={q.trim() !== "" && r.player.player_id === firstAvailable}
          />
        ))}
      </div>
    </section>
  );
}
