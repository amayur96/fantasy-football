import { useMemo, useState } from "react";
import { LayoutListIcon } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { DraftRow, useDraftActions } from "@/components/draft/DraftRow";
import { useSettings } from "@/lib/queries";
import type { CheatSheetResponse, DraftView, Position, RankedPlayer } from "@/lib/types";
import { cn } from "@/lib/utils";


/** Quarterbacks lead: this league starts two of them, so they are the scarcest thing on the board. */
const PANELS: { pos: Position; title: string }[] = [
  { pos: "QB", title: "Quarterbacks" },
  { pos: "RB", title: "Runningbacks" },
  { pos: "WR", title: "Wide Receivers" },
  { pos: "TE", title: "Tightends" },
  { pos: "D/ST", title: "Defenses" },
  { pos: "K", title: "Kickers" },
];

/** Positions this league actually starts, directly or through a flex spot. */
function draftablePositions(rosterSlots: Record<string, number> | undefined): Set<Position> {
  if (!rosterSlots) return new Set(PANELS.map((p) => p.pos));
  const out = new Set<Position>();
  for (const [slot, n] of Object.entries(rosterSlots)) {
    if (!n || slot === "BE" || slot === "IR") continue;
    for (const part of slot.split("/")) {
      const pos = (part === "DST" ? "D/ST" : part) as Position;
      if (PANELS.some((p) => p.pos === pos)) out.add(pos);
    }
    if (slot === "D/ST") out.add("D/ST");
  }
  return out;
}

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
  const settings = useSettings();
  const [only, setOnly] = useState<string>("ALL");
  const draftable = useMemo(
    () => draftablePositions(settings.data?.settings?.roster_slots),
    [settings.data?.settings?.roster_slots],
  );
  const panels = useMemo(() => {
    const taken = new Set(view.taken_ids);
    return PANELS.filter((p) => draftable.has(p.pos)).map((p) => ({ ...p, rows: panelRows(sheet, p.pos, taken) }));
  }, [sheet, view.taken_ids, draftable]);
  const shown = only === "ALL" ? panels : panels.filter((p) => p.pos === only);
  const single = only !== "ALL";

  return (
    <section className="flex max-h-[70vh] min-h-0 flex-1 flex-col overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10 lg:max-h-none">
      <header className="flex shrink-0 flex-wrap items-center justify-center gap-x-3 gap-y-1 bg-muted px-3 py-1.5 text-sm font-semibold">
        <span className="flex items-center gap-2">
          <LayoutListIcon className="size-4 text-muted-foreground" />
          Rankings by Position
        </span>
        <ToggleGroup
          type="single"
          size="sm"
          variant="outline"
          value={only}
          onValueChange={(v) => v && setOnly(v)}
          className="text-xs font-normal"
        >
          <ToggleGroupItem value="ALL" className="px-2 text-xs">
            All
          </ToggleGroupItem>
          {panels.map((p) => (
            <ToggleGroupItem key={p.pos} value={p.pos} className="px-2 text-xs" title={p.title}>
              {p.pos}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {isLoading ? (
          <div className="grid gap-3 lg:grid-cols-2">
            {PANELS.slice(0, 4).map((p) => (
              <Skeleton key={p.pos} className="h-72" />
            ))}
          </div>
        ) : (
          <div className={cn("grid gap-3", single ? "grid-cols-1" : "lg:grid-cols-2 2xl:grid-cols-3")}>
            {shown.map((panel) => (
              <div
                key={panel.pos}
                className={cn(
                  "flex flex-col overflow-hidden rounded-lg ring-1 ring-foreground/10",
                  single ? "max-h-[72vh]" : "max-h-[34vh]",
                )}
              >
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
