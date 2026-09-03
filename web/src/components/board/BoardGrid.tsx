import { useState } from "react";
import { EraserIcon, SaveIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverDescription, PopoverHeader, PopoverTitle, PopoverTrigger } from "@/components/ui/popover";
import { PlayerSearch } from "@/components/PlayerSearch";
import { PosBadge } from "@/components/PosBadge";
import { TeamSelect } from "@/components/TeamSelect";
import { readableTextOn } from "@/lib/format";
import { useSetCell } from "@/lib/queries";
import type { BoardCell, BoardColumn, BoardView, TeamInfo } from "@/lib/types";
import { cn } from "@/lib/utils";

const EMPTY_COLOR = "#e5e7eb";

function CellEditor({
  cell,
  columns,
  teams,
  onDone,
}: {
  cell: BoardCell;
  columns: Map<number, BoardColumn>;
  teams: TeamInfo[];
  onDone: () => void;
}) {
  const setCell = useSetCell();
  const [player, setPlayer] = useState<{ player_id: number; player_name: string }>({
    player_id: cell.player_id ?? 0,
    player_name: cell.player_name ?? "",
  });
  const [owner, setOwner] = useState(cell.owner_team_id);
  const playerChanged = player.player_id !== 0 && player.player_id !== cell.player_id;
  const ownerChanged = owner !== cell.owner_team_id;
  const dirty = playerChanged || ownerChanged;
  const name = (id: number) => columns.get(id)?.name ?? `Team ${id}`;

  const save = () =>
    setCell.mutate(
      {
        original_team_id: cell.original_team_id,
        round: cell.round,
        ...(playerChanged ? { player_id: player.player_id } : {}),
        ...(ownerChanged ? { owner_team_id: owner } : {}),
      },
      { onSuccess: onDone },
    );
  const clear = () =>
    setCell.mutate(
      {
        original_team_id: cell.original_team_id,
        round: cell.round,
        clear: true,
        ...(ownerChanged ? { owner_team_id: owner } : {}),
      },
      { onSuccess: onDone },
    );
  const hasContent = cell.player_id !== null || cell.unknown || cell.raw_name;

  return (
    <>
      <PopoverHeader>
        <PopoverTitle className="flex items-center gap-2">
          R{cell.round} · Pick #{cell.overall}
          {cell.is_keeper && <Badge variant="outline">keeper</Badge>}
          {cell.source && (
            <Badge variant="secondary" className="font-normal">
              via {cell.source}
            </Badge>
          )}
        </PopoverTitle>
        <PopoverDescription>
          original: {name(cell.original_team_id)} · owner: {name(cell.owner_team_id)}
        </PopoverDescription>
      </PopoverHeader>
      {cell.unknown && cell.raw_name && (
        <p className="rounded bg-muted px-2 py-1 text-xs text-muted-foreground">
          Sheet text <span className="font-medium text-foreground">“{cell.raw_name}”</span> did not match a player. Pick the right one below.
        </p>
      )}
      <div className="space-y-1">
        <div className="text-xs font-medium text-muted-foreground">Player</div>
        <PlayerSearch value={player} onSelect={(p) => setPlayer({ player_id: p.player_id, player_name: p.name })} />
      </div>
      <div className="space-y-1">
        <div className="text-xs font-medium text-muted-foreground">Pick owner</div>
        <TeamSelect teams={teams} value={owner} onChange={setOwner} />
      </div>
      <div className="flex items-center justify-between gap-2 pt-1">
        <Button size="sm" variant="outline" disabled={!hasContent || setCell.isPending} onClick={clear}>
          <EraserIcon /> Clear
        </Button>
        <Button size="sm" disabled={!dirty || setCell.isPending} onClick={save}>
          <SaveIcon /> Save
        </Button>
      </div>
    </>
  );
}

function Cell({ cell, columns, teams, match }: { cell: BoardCell; columns: Map<number, BoardColumn>; teams: TeamInfo[]; match?: boolean | null }) {
  const [open, setOpen] = useState(false);
  const owner = columns.get(cell.owner_team_id);
  const bg = owner?.color || EMPTY_COLOR;
  const fg = readableTextOn(bg);
  const traded = cell.owner_team_id !== cell.original_team_id;
  const label = cell.player_name ?? (cell.unknown ? (cell.raw_name ?? "unknown") : "");
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          style={{ backgroundColor: bg, color: fg }}
          title={
            `R${cell.round} · #${cell.overall}` +
            (traded ? ` · traded to ${owner?.name ?? cell.owner_team_id}${owner?.owner ? ` (${owner.owner})` : ""}` : "") +
            (label ? ` · ${label}` : "")
          }
          className={cn(
            "relative flex h-14 w-full min-w-32 flex-col items-start justify-center gap-0.5 px-1.5 py-1 text-left text-xs leading-tight transition-[filter] outline-none hover:brightness-95 focus-visible:z-10 focus-visible:ring-2 focus-visible:ring-ring dark:hover:brightness-110",
            cell.on_clock &&
              "after:pointer-events-none after:absolute after:inset-0.5 after:animate-pulse after:rounded-sm after:ring-2 after:ring-foreground/80 after:content-['']",
            match === true &&
              "after:pointer-events-none after:absolute after:inset-0 after:rounded-sm after:ring-2 after:ring-foreground after:content-['']",
            match === false && "opacity-35",
          )}
        >
          {label && (
            <span className="flex w-full items-center gap-1">
              <span className={cn("min-w-0 flex-1 truncate", cell.unknown ? "italic opacity-80" : "font-semibold")}>{label}</span>
              {cell.is_keeper && (
                <span className="shrink-0 rounded-sm bg-black/15 px-1 font-mono text-[9px] font-bold leading-4" title="Keeper">
                  K
                </span>
              )}
            </span>
          )}
          {(cell.position || cell.unknown) && (
            <span className="flex items-center gap-1">
              {cell.unknown ? (
                <span className="rounded-sm bg-black/15 px-1 font-mono text-[9px] font-bold leading-4" title="Unmatched sheet text">
                  ?
                </span>
              ) : (
                <PosBadge pos={cell.position!} className="h-4 px-1 text-[9px]" />
              )}
            </span>
          )}
          {traded && (
            <span className="flex w-full min-w-0 flex-col font-bold leading-tight">
              <span className="truncate text-[10px]">
                <span className="opacity-70">&rarr; </span>
                {owner?.name ?? `Team ${cell.owner_team_id}`}
              </span>
              {owner?.owner && <span className="truncate text-[10px] opacity-85">{owner.owner}</span>}
            </span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80">
        {open && <CellEditor cell={cell} columns={columns} teams={teams} onDone={() => setOpen(false)} />}
      </PopoverContent>
    </Popover>
  );
}

export function BoardGrid({ view, teams, query = "" }: { view: BoardView; teams: TeamInfo[]; query?: string }) {
  const columns = new Map(view.columns.map((c) => [c.team_id, c]));
  // (round, original_team_id) -> cell
  const byKey = new Map(view.cells.map((c) => [`${c.round}:${c.original_team_id}`, c]));
  const rounds = Array.from({ length: view.rounds }, (_, i) => i + 1);
  const q = query.trim().toLowerCase();
  const matches = (c: BoardCell) =>
    !q ? null : `${c.player_name ?? ""} ${c.raw_name ?? ""}`.toLowerCase().includes(q);

  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full border-separate border-spacing-0 text-xs">
        <thead>
          <tr>
            <th className="sticky left-0 z-20 w-16 min-w-16 border-r border-b bg-background px-1.5 py-1 text-left text-[10px] font-medium text-muted-foreground uppercase">
              Round
            </th>
            {view.columns.map((col) => (
              <th
                key={col.team_id}
                style={{ backgroundColor: col.color || EMPTY_COLOR, color: readableTextOn(col.color || EMPTY_COLOR) }}
                className={cn(
                  "sticky top-0 z-10 min-w-32 border-r border-b border-background/60 px-1.5 py-1 text-left align-top leading-tight",
                  col.is_me && "ring-2 ring-inset ring-foreground/70",
                )}
              >
                <div className={cn("truncate", col.is_me ? "font-bold" : "font-semibold")}>
                  {col.name}
                  {col.is_me && <span className="ml-1 text-[9px] font-medium uppercase opacity-70">you</span>}
                </div>
                {col.owner && <div className="truncate text-[10px] font-normal opacity-75">{col.owner}</div>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rounds.map((r) => (
            <tr key={r}>
              <th className="sticky left-0 z-10 border-r border-b bg-background px-1.5 py-1 text-left font-medium whitespace-nowrap text-muted-foreground">
                Round {r}
              </th>
              {view.columns.map((col) => {
                const cell = byKey.get(`${r}:${col.team_id}`);
                return (
                  <td
                    key={col.team_id}
                    className={cn("border-r border-b border-background/60 p-0 align-top", col.is_me && "ring-1 ring-inset ring-foreground/30")}
                  >
                    {cell ? <Cell cell={cell} columns={columns} teams={teams} match={matches(cell)} /> : <div className="h-14 min-w-32 bg-muted/40" />}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
