import { GitCompareArrowsIcon, LoaderCircleIcon } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useResolveConflict } from "@/lib/queries";
import type { SheetConflict } from "@/lib/types";

function Row({ c, busy, onChoose }: { c: SheetConflict; busy: boolean; onChoose: (choice: "sheet" | "board") => void }) {
  return (
    <div className="grid gap-2 rounded-md border bg-background p-3 sm:grid-cols-[1fr_auto] sm:items-center">
      <div className="min-w-0">
        <div className="text-sm font-medium">
          Round {c.round} · {c.team_name}
          <span className="ml-2 font-normal text-muted-foreground">pick #{c.overall}</span>
        </div>
        <div className="mt-1 grid gap-0.5 text-sm">
          <div>
            <span className="text-muted-foreground">You entered </span>
            <span className="font-medium">{c.board_player_name ?? "(empty)"}</span>
          </div>
          <div>
            <span className="text-muted-foreground">The sheet says </span>
            <span className="font-medium">{c.sheet_player_name}</span>
            {c.kind === "move" && c.from_round !== null && (
              <span className="text-muted-foreground">
                {" "}— you have him at round {c.from_round} (pick #{c.from_overall})
              </span>
            )}
          </div>
        </div>
      </div>
      <div className="flex gap-2 sm:justify-end">
        <Button size="sm" variant="outline" disabled={busy} onClick={() => onChoose("board")}>
          Keep mine
        </Button>
        <Button size="sm" disabled={busy} onClick={() => onChoose("sheet")}>
          Use sheet
        </Button>
      </div>
    </div>
  );
}

/** Shown only when the sheet wants to change something a human typed. */
export function ConflictsCard({ conflicts }: { conflicts: SheetConflict[] }) {
  const resolve = useResolveConflict();
  if (conflicts.length === 0) return null;
  return (
    <Alert className="border-amber-500/50 bg-amber-50/60 dark:bg-amber-950/20">
      <GitCompareArrowsIcon className="text-amber-600 dark:text-amber-400" />
      <AlertTitle className="flex items-center gap-2">
        {conflicts.length} pick{conflicts.length === 1 ? "" : "s"} need your decision
        {resolve.isPending && <LoaderCircleIcon className="size-3.5 animate-spin" />}
      </AlertTitle>
      <AlertDescription className="grid gap-2">
        <p className="text-muted-foreground">
          The sheet disagrees with something you entered by hand. Nothing has been changed — pick which is right.
        </p>
        {conflicts.map((c) => (
          <Row
            key={c.key}
            c={c}
            busy={resolve.isPending}
            onChoose={(choice) => resolve.mutate({ key: c.key, choice })}
          />
        ))}
      </AlertDescription>
    </Alert>
  );
}
