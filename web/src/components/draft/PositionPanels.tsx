import { useMemo } from "react";
import { LayoutListIcon } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { DraftRow, useDraftActions } from "@/components/draft/DraftRow";
import type { CheatSheetResponse, DraftView, Position, RankedPlayer } from "@/lib/types";


/** Order + Boris Chen's headings. */
const PANELS: { pos: Position; title: string }[] = [
  { pos: "RB", title: "Runningbacks" },
  { pos: "WR", title: "Wide Receivers" },
  { pos: "QB", title: "Quarterbacks" },
  { pos: "TE", title: "Tightends" },
  { pos: "D/ST", title: "Defenses" },
  { pos: "K", title: "Kickers" },
];

interface Row {
  player: RankedPlayer;
  taken: boolean;
}

/** The full ranking for a position, in order. Drafted players stay crossed off in place so the
 *  tiers deplete visibly, and the list runs all the way down for late-round picks. */
function panelRows(sheet: CheatSheetResponse | undefined, pos: Position, taken: Set<number>): Row[] {
  const out: Row[] = [];
  for (const tier of sheet?.by_pos[pos] ?? []) {
    for (const player of tier) out.push({ player, taken: taken.has(player.player_id) });
  }
  return out;
}

export function PositionPanels({
  view,
  sheet,
  isLoading,
  onOpenCard,
}: {
  view: DraftView;
  sheet: CheatSheetResponse | undefined;
  isLoading: boolean;
  onOpenCard: (playerId: number) => void;
}) {
  const actions = useDraftActions(view);
  const panels = useMemo(() => {
    const taken = new Set(view.taken_ids);
    return PANELS.map((p) => ({ ...p, rows: panelRows(sheet, p.pos, taken) }));
  }, [sheet, view.taken_ids]);

  return (
    <section className="flex max-h-[70vh] min-h-0 flex-1 flex-col overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10 lg:max-h-none">
      <header className="flex h-9 shrink-0 items-center justify-center gap-2 bg-muted px-3 text-sm font-semibold">
        <LayoutListIcon className="size-4 text-muted-foreground" />
        Rankings by Position
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {isLoading ? (
          <div className="grid gap-3 lg:grid-cols-2">
            {PANELS.map((p) => (
              <Skeleton key={p.pos} className="h-72" />
            ))}
          </div>
        ) : (
          <div className="grid gap-3 lg:grid-cols-2">
            {panels.map((panel) => (
              <div key={panel.pos} className="flex max-h-[60vh] flex-col overflow-hidden rounded-lg ring-1 ring-foreground/10">
                <div className="flex shrink-0 items-baseline justify-center gap-2 border-b px-2 py-1.5 text-center text-sm font-bold">
                  {panel.title}
                  <span className="num text-[10px] font-normal text-muted-foreground">
                    {panel.rows.filter((r) => !r.taken).length} left
                  </span>
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto">
                {panel.rows.length === 0 ? (
                  <p className="p-2 text-xs text-muted-foreground">Nobody left.</p>
                ) : (
                  panel.rows.map((r) => (
                    <DraftRow
                      key={r.player.player_id}
                      player={r.player}
                      actions={actions}
                      taken={r.taken}
                      onOpenCard={onOpenCard}
                    />
                  ))
                )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
