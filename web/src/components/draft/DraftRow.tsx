import { useMemo } from "react";
import { Button } from "@/components/ui/button";
import { useDraftAssign } from "@/lib/queries";
import type { DraftPick, DraftView, RankedPlayer } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Which ranking the overall list is sorted by: ESPN ADP, FantasyPros consensus, Boris Chen tiers. */
export type RankSource = "espn" | "fp" | "bc";

/** Pastel tints that repeat every four tiers, mirroring Boris Chen's Draft Aid. */
const TIER_TINT = [
  "bg-emerald-100 text-emerald-950 dark:bg-emerald-400/15 dark:text-emerald-50",
  "bg-amber-100 text-amber-950 dark:bg-amber-400/15 dark:text-amber-50",
  "bg-sky-100 text-sky-950 dark:bg-sky-400/15 dark:text-sky-50",
  "bg-zinc-100 text-zinc-950 dark:bg-zinc-400/20 dark:text-zinc-50",
];

/** How many upcoming open picks the "Draft to…" list offers past the one on the clock. */

function tierTint(tier: number | null | undefined): string {
  const t = tier === null || tier === undefined || Number.isNaN(tier) ? 1 : Math.max(1, Math.round(tier));
  return TIER_TINT[(t - 1) % TIER_TINT.length];
}

export interface DraftActions {
  /** Put a player in a specific pick; `overall` defaults to whoever is on the clock. */
  draft: (playerId: number, overall?: number) => void;
  /** The pick a player sits in, or undefined when they are still available. */
  pickOf: (playerId: number) => DraftPick | undefined;
  busy: boolean;
  draftOver: boolean;
  onTheClock: DraftPick | null;
  myTeamId: number;
}

/** Shared assign wiring: every pick control on this page routes through `/draft/assign`. */
export function useDraftActions(view: DraftView): DraftActions {
  const assign = useDraftAssign();
  const picks = view.state.picks;
  const otc = view.on_the_clock;

  const byPlayer = useMemo(() => {
    const m = new Map<number, DraftPick>();
    for (const p of picks) if (p.player_id !== null) m.set(p.player_id, p);
    return m;
  }, [picks]);

  return {
    draft: (playerId, overall) => {
      const target = overall ?? otc?.overall;
      if (target === undefined) return;
      assign.mutate({ overall: target, player_id: playerId });
    },
    pickOf: (playerId) => byPlayer.get(playerId),
    busy: assign.isPending,
    draftOver: otc === null,
    onTheClock: otc,
    myTeamId: view.state.my_team_id,
  };
}

function injuryTag(status: string | null | undefined): string | null {
  if (!status || status === "ACTIVE" || status === "NORMAL") return null;
  return status.replace(/_/g, " ").slice(0, 3);
}


/** One button: draft this player into the pick that's on the clock. Corrections happen on the board. */
function DraftButton({ player, actions }: { player: RankedPlayer; actions: DraftActions }) {
  const otc = actions.onTheClock;
  return (
    <Button
      size="xs"
      className="h-5 shrink-0 px-1.5 text-[10px] opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100"
      disabled={actions.busy || actions.draftOver}
      title={otc ? `Draft ${player.name} at #${otc.overall} (R${otc.round}.${otc.pick_in_round})` : "Draft complete"}
      onClick={(e) => {
        e.stopPropagation();
        actions.draft(player.player_id);
      }}
    >
      Draft
    </Button>
  );
}

/** The three ranking sources side by side, so the row shows where they disagree even when
 *  only one of them is doing the sorting. */
function SourceCells({ player, active }: { player: RankedPlayer; active?: RankSource }) {
  const cells: { key: RankSource; width: string; text: string; title: string }[] = [
    {
      key: "espn",
      width: "w-7",
      text: `E${player.adp === null ? "–" : Math.round(player.adp)}`,
      title: player.adp === null ? "No ESPN average draft position" : `ESPN ADP #${Math.round(player.adp)}`,
    },
    {
      key: "fp",
      width: "w-8",
      text: `FP${player.fp_rank ?? "–"}`,
      title: player.fp_rank === null ? "No FantasyPros consensus rank" : `FantasyPros consensus #${player.fp_rank}`,
    },
    {
      key: "bc",
      width: "w-5",
      text: `T${player.bc_tier ?? "–"}`,
      title: player.bc_tier === null ? "No Boris Chen tier" : `Boris Chen tier ${player.bc_tier}`,
    },
  ];
  return (
    <span className="flex shrink-0 items-center gap-1">
      {cells.map((c) => (
        <span
          key={c.key}
          title={c.title}
          className={cn("num shrink-0 text-[10px] opacity-70", c.width, c.key === active && "font-semibold opacity-100")}
        >
          {c.text}
        </span>
      ))}
    </span>
  );
}

export function DraftRow({
  player,
  actions,
  rank,
  showPos = false,
  highlight = false,
  taken = false,
  sources = false,
  activeSource,
  onOpenCard,
}: {
  player: RankedPlayer;
  actions: DraftActions;
  rank?: number;
  showPos?: boolean;
  highlight?: boolean;
  /** Already drafted: stays in place, crossed off, with an undo escape hatch. */
  taken?: boolean;
  /** Show the ESPN / FantasyPros / Boris Chen numbers next to the name. */
  sources?: boolean;
  /** Which of the three the list is sorted by; that cell is emphasised. */
  activeSource?: RankSource;
  /** Clicking the name opens the player card. */
  onOpenCard?: (playerId: number) => void;
}) {
  const inj = taken ? null : injuryTag(player.injury_status);
  const at = taken ? actions.pickOf(player.player_id) : undefined;
  return (
    <div
      className={cn(
        "group flex h-7 items-center gap-2 border-b border-background/70 px-1.5 text-xs last:border-b-0",
        taken
          ? "bg-muted/70 text-muted-foreground opacity-70 line-through decoration-red-500 decoration-2 dark:decoration-red-400"
          : tierTint(player.tier),
        highlight && "ring-1 ring-foreground/40 ring-inset",
      )}
    >
      {rank !== undefined && <span className="num w-6 shrink-0 text-right opacity-60">{rank}</span>}
      <span className="num w-11 shrink-0 opacity-70">Tier {player.tier}</span>
      {showPos && <span className="w-9 shrink-0 font-semibold">{player.position}</span>}
      {onOpenCard ? (
        <button
          type="button"
          className="min-w-0 flex-1 truncate text-left font-medium hover:underline focus-visible:underline focus-visible:outline-none"
          title={`Open ${player.name}'s card`}
          onClick={(e) => {
            e.stopPropagation();
            onOpenCard(player.player_id);
          }}
        >
          {player.name}
        </button>
      ) : (
        <span className="min-w-0 flex-1 truncate font-medium">{player.name}</span>
      )}
      {sources && <SourceCells player={player} active={activeSource} />}
      {inj && <span className="shrink-0 text-[9px] font-bold tracking-wide text-destructive uppercase">{inj}</span>}
      <span className="hidden shrink-0 text-[10px] opacity-50 sm:inline">{player.pro_team}</span>
      {taken ? (
        <span className="shrink-0 text-[9px] font-semibold tracking-wide text-red-600 uppercase no-underline dark:text-red-400">
          {at ? `#${at.overall}` : "taken"}
        </span>
      ) : (
        <DraftButton player={player} actions={actions} />
      )}
    </div>
  );
}
