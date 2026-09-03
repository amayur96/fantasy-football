import { useEffect, useRef, useState } from "react";
import { FileSpreadsheetIcon, RefreshCwIcon, TriangleAlertIcon } from "lucide-react";
import { toast } from "sonner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CollapsibleCard } from "@/components/CollapsibleCard";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { errorMessage } from "@/lib/api";
import { relativeTime, secondsAgo } from "@/lib/format";
import { useSheetStatus, useSheetSync } from "@/lib/queries";
import type { SheetStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const FOLLOW_KEY = "ffdraft-follow-sheet";
const MAX_FAILURES = 3;

function readFollow(): boolean {
  try {
    return localStorage.getItem(FOLLOW_KEY) === "1";
  } catch {
    return false;
  }
}

function useFollowSheet(status: SheetStatus | undefined) {
  const [follow, setFollowState] = useState<boolean>(readFollow);
  const [lastPulled, setLastPulled] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [pollError, setPollError] = useState<string | null>(null);
  const failures = useRef(0);
  const poll = useSheetSync({ silent: true });
  const pollRef = useRef(poll);
  useEffect(() => {
    pollRef.current = poll;
  });

  const setFollow = (on: boolean) => {
    setFollowState(on);
    failures.current = 0;
    if (on) setPollError(null);
    try {
      localStorage.setItem(FOLLOW_KEY, on ? "1" : "0");
    } catch {
      // ignore
    }
  };

  const enabled = follow && !!status?.configured;
  const period = Math.max(2, status?.poll_seconds ?? 15) * 1000;

  useEffect(() => {
    if (!enabled) return;
    let stopped = false;
    const tick = async () => {
      if (stopped || pollRef.current.isPending) return;
      try {
        await pollRef.current.mutateAsync();
        failures.current = 0;
        setPollError(null);
        setLastPulled(Date.now());
      } catch (err) {
        failures.current += 1;
        setPollError(errorMessage(err));
        if (failures.current >= MAX_FAILURES) {
          setFollow(false);
          toast.error("Stopped following the sheet", {
            description: `${MAX_FAILURES} pulls in a row failed: ${errorMessage(err)}`,
          });
        }
      }
    };
    void tick();
    const id = setInterval(() => void tick(), period);
    return () => {
      stopped = true;
      clearInterval(id);
    };
  }, [enabled, period]);

  // Tick the "Xs ago" label once a second while following.
  useEffect(() => {
    if (!enabled) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [enabled]);

  return { follow, setFollow, enabled, lastPulled, now, pollError, polling: poll.isPending };
}


export function SheetPanel() {
  const { data: status, isLoading, error } = useSheetStatus();
  const sync = useSheetSync();
  const f = useFollowSheet(status);
  const last = status?.last ?? null;
  const lastAt = f.lastPulled ?? (last ? Date.parse(last.fetched_at) : null);

  const summary = !status?.configured
    ? "not configured"
    : `tab ${status.tab || "first"} · ` +
      (lastAt === null ? "never pulled" : f.enabled ? `pulled ${secondsAgo(lastAt, f.now)}` : `pulled ${relativeTime(lastAt / 1000)}`);

  return (
    <CollapsibleCard
      title="Google Sheet"
      icon={<FileSpreadsheetIcon className="size-4 text-muted-foreground" />}
      badge={
        status?.configured ? (
          <Badge variant="outline">{status.auth === "oauth" ? "Google account" : status.auth === "csv" ? "public CSV" : "no auth"}</Badge>
        ) : undefined
      }
      summary={summary}
      defaultOpen={
        !!error ||
        (!!status && (!status.configured || status.auth === "none")) ||
        !!last?.error ||
        (last?.unmatched.length ?? 0) > 0 ||
        (last?.unmapped_columns.length ?? 0) > 0
      }
      actions={
        status?.configured ? (
          <>
            <label className="flex items-center gap-2 text-sm">
              <Switch checked={f.follow} onCheckedChange={f.setFollow} aria-label="Follow sheet" />
              <span className="flex items-center gap-1.5">
                {f.enabled && (
                  <span className={cn("inline-block size-2 rounded-full", f.pollError ? "bg-amber-500" : "bg-emerald-500", f.polling && "animate-pulse")} />
                )}
                Follow
              </span>
            </label>
            <Button size="sm" disabled={sync.isPending} onClick={() => sync.mutate()}>
              <RefreshCwIcon className={cn(sync.isPending && "animate-spin")} /> Pull now
            </Button>
          </>
        ) : undefined
      }
    >

        {isLoading && <Skeleton className="h-16 w-full" />}
        {error && (
          <Alert variant="destructive">
            <AlertTitle>Cannot read sheet status</AlertTitle>
            <AlertDescription>{errorMessage(error)}</AlertDescription>
          </Alert>
        )}
        {status && !status.configured && (
          <Alert>
            <TriangleAlertIcon />
            <AlertTitle>No Google Sheet configured</AlertTitle>
            <AlertDescription>
              Set <code className="rounded bg-muted px-1">GOOGLE_SHEET_ID</code> (and optionally{" "}
              <code className="rounded bg-muted px-1">GOOGLE_SHEET_TAB</code>) in <code className="rounded bg-muted px-1">.env</code> in the
              project root and restart the server. See the README for the OAuth vs. public-CSV setup. You can still fill the board by
              clicking cells.
            </AlertDescription>
          </Alert>
        )}
        {status?.configured && status.auth === "none" && (
          <Alert variant="destructive">
            <AlertTitle>Sheet is not readable</AlertTitle>
            <AlertDescription>
              No Google credentials file found and the sheet is not published as CSV. Add credentials or share the sheet publicly. See the
              README.
            </AlertDescription>
          </Alert>
        )}
        {status?.configured && (
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span>
              {lastAt === null
                ? "Never pulled"
                : f.enabled
                  ? `Last pulled ${secondsAgo(lastAt, f.now)}`
                  : `Last pulled ${relativeTime(lastAt / 1000)}`}
            </span>
            {last && (
              <>
                <span>
                  <span className="num font-medium text-foreground">{last.applied}</span> applied
                </span>
                <span>
                  <span className="num font-medium text-foreground">{last.cleared}</span> cleared
                </span>
                <span>
                  <span className="num font-medium text-foreground">{last.owner_changes}</span> owner change{last.owner_changes === 1 ? "" : "s"}
                </span>
                <span>source: {last.source}</span>
              </>
            )}
          </div>
        )}
        {(sync.error || f.pollError || last?.error) && (
          <Alert variant="destructive">
            <AlertTitle>Sheet pull failed</AlertTitle>
            <AlertDescription>{sync.error ? errorMessage(sync.error) : (f.pollError ?? last?.error)}</AlertDescription>
          </Alert>
        )}
        {last && last.unmapped_columns.length > 0 && (
          <Alert>
            <TriangleAlertIcon />
            <AlertTitle>Unmapped sheet columns</AlertTitle>
            <AlertDescription>
              {last.unmapped_columns.join(", ")} — these sheet columns didn't match a team, so their picks aren't on the board.
            </AlertDescription>
          </Alert>
        )}
        {last && last.unmatched.length > 0 && (
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground">
              {last.unmatched.length} cell{last.unmatched.length === 1 ? "" : "s"} could not be matched — click them on the grid to fix.
            </div>
            <div className="max-h-48 overflow-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-14">Round</TableHead>
                    <TableHead>Column</TableHead>
                    <TableHead>Sheet text</TableHead>
                    <TableHead>Reason</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {last.unmatched.map((u, i) => (
                    <TableRow key={i}>
                      <TableCell className="num py-1">{u.round}</TableCell>
                      <TableCell className="py-1">{u.header}</TableCell>
                      <TableCell className="py-1 italic">{u.text}</TableCell>
                      <TableCell className="py-1 text-muted-foreground">{u.reason}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        )}
    </CollapsibleCard>
  );
}
