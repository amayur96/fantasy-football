import { useState } from "react";
import { TriangleAlertIcon } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { BoardGrid } from "@/components/board/BoardGrid";
import { ConflictsCard } from "@/components/board/ConflictsCard";
import { DraftOrderCard } from "@/components/board/DraftOrderCard";
import { GradesDialog } from "@/components/board/GradesDialog";
import { SheetPanel } from "@/components/board/SheetPanel";
import { NotReady } from "@/components/NotReady";
import { useBoard, useSettings } from "@/lib/queries";
import type { BoardView, TeamInfo } from "@/lib/types";

function Summary({ view }: { view: BoardView }) {
  const otc = view.on_the_clock;
  const until = view.picks_until_my_turn;
  const owner = otc ? view.columns.find((c) => c.team_id === otc.owner_team_id) : undefined;
  const mine = otc !== null && otc.owner_team_id === view.my_team_id;
  return (
    <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
      <div className="text-base font-semibold">
        {otc ? (
          <>
            Round {otc.round}, Pick {otc.pick_in_round} · #{otc.overall} overall —{" "}
            <span className={mine ? "text-emerald-600 dark:text-emerald-400" : undefined}>
              {mine ? "You" : (owner?.name ?? `Team ${otc.owner_team_id}`)}
            </span>
            {otc.owner_team_id !== otc.original_team_id && (
              <span className="ml-1 text-xs font-normal text-muted-foreground">
                (via {view.columns.find((c) => c.team_id === otc.original_team_id)?.name ?? `Team ${otc.original_team_id}`})
              </span>
            )}
          </>
        ) : (
          "Draft complete"
        )}
      </div>
      <div className="text-sm text-muted-foreground">
        {until === null
          ? "No picks remaining for you."
          : until === 0
            ? "It is your pick."
            : `${until} pick${until === 1 ? "" : "s"} until your turn`}
      </div>
    </div>
  );
}

export function Board() {
  const [query, setQuery] = useState("");
  const board = useBoard();
  const settings = useSettings();
  const teams: TeamInfo[] =
    settings.data?.settings?.teams ??
    board.data?.columns.map((c) => ({ team_id: c.team_id, name: c.name, abbrev: "", owner_ids: [], owner_names: [] })) ??
    [];

  if (board.error) return <NotReady error={board.error} />;
  return (
    <div className="space-y-4">
      <DraftOrderCard />
      <SheetPanel />
      {board.isLoading || !board.data ? (
        <Skeleton className="h-96 w-full" />
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Summary view={board.data} />
            <GradesDialog />
          </div>
          <ConflictsCard conflicts={board.data.conflicts} />
          {board.data.warnings.length > 0 && (
            <div className="space-y-2">
              {board.data.warnings.map((w, i) => (
                <Alert key={i} className="py-1.5">
                  <TriangleAlertIcon />
                  <AlertDescription>{w}</AlertDescription>
                </Alert>
              ))}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <Input
              placeholder="Find a drafted player on the board…"
              className="h-8 w-72 text-sm"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            {query.trim() !== "" && (
              <span className="text-xs text-muted-foreground">
                {(() => {
                  const q = query.trim().toLowerCase();
                  const hits = board.data.cells.filter((c) => `${c.player_name ?? ""} ${c.raw_name ?? ""}`.toLowerCase().includes(q));
                  if (hits.length === 0) return "No drafted player matches — they may still be available.";
                  const names = new Map(board.data.columns.map((c) => [c.team_id, c.name]));
                  return hits
                    .slice(0, 3)
                    .map((c) => `${c.player_name ?? c.raw_name} — R${c.round} to ${names.get(c.owner_team_id) ?? c.owner_team_id}`)
                    .join(" · ");
                })()}
              </span>
            )}
          </div>
          <BoardGrid view={board.data} teams={teams} query={query} />
          <p className="text-xs text-muted-foreground">
            Cells are colored by the team that owns the pick, so a traded pick shows as an off-color cell in the original team's column.
            Click any cell to set the player or reassign the pick.
          </p>
        </>
      )}
    </div>
  );
}
