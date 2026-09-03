import { CloudDownloadIcon, KeyRoundIcon, RefreshCwIcon, SparklesIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { errorMessage } from "@/lib/api";
import { relativeTime, scoringLabel } from "@/lib/format";
import { useRefreshExternal, useSettings, useSync } from "@/lib/queries";

export function SyncCard() {
  const { data, isLoading, error } = useSettings();
  const sync = useSync();
  const refreshExternal = useRefreshExternal();
  const s = data?.settings;
  const ext = data?.external ?? null;
  const extMatched = ext ? (ext.matched.fantasypros ?? 0) + (ext.matched.borischen ?? 0) : 0;
  const mtimes = data ? Object.values(data.cache_files) : [];
  const lastSynced = mtimes.length ? Math.max(...mtimes) : null;

  return (
    <Card className="border-0 shadow-none">
      <CardHeader>
        <CardTitle>League sync</CardTitle>
        <CardDescription>
          {s ? (
            <>
              <span className="font-medium text-foreground">{s.league_name}</span> · {s.team_count} teams · {s.rounds} rounds ·
              season {s.season} · you are <span className="font-medium text-foreground">{s.my_team_name}</span>
            </>
          ) : isLoading ? (
            "Loading…"
          ) : (
            `No league data loaded for ${data?.season ?? "this season"}. Sync to fetch it from ESPN.`
          )}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading && <Skeleton className="h-8 w-full" />}
        {error && (
          <Alert variant="destructive">
            <AlertTitle>Cannot reach the server</AlertTitle>
            <AlertDescription>{errorMessage(error)}. Is the backend running on :8000?</AlertDescription>
          </Alert>
        )}
        {data && !data.has_credentials && (
          <Alert>
            <KeyRoundIcon />
            <AlertTitle>ESPN credentials missing</AlertTitle>
            <AlertDescription>
              Copy <code className="rounded bg-muted px-1">.env.example</code> to <code className="rounded bg-muted px-1">.env</code> in
              the project root and fill in LEAGUE_ID, ESPN_S2 and SWID (from your espn.com cookies), then restart the server.
              Sync from cache still works if cache files exist.
            </AlertDescription>
          </Alert>
        )}
        {data && (
          <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
            <span>
              {lastSynced === null ? "Not synced yet" : `Last synced ${relativeTime(lastSynced)}`}
            </span>
            <span>{data.players} players</span>
            <span>{data.roster_prev} prior-season roster entries</span>
            <span>draft history: {data.draft_years.length ? data.draft_years.join(", ") : "none"}</span>
          </div>
        )}
        {data && (
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            {ext === null ? (
              <span>Expert rankings: not loaded yet</span>
            ) : (
              <>
                {ext.superflex ? (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="cursor-help underline decoration-dotted underline-offset-4">
                        Experts: FantasyPros {scoringLabel(ext.scoring)} superflex
                      </span>
                    </TooltipTrigger>
                    <TooltipContent className="max-w-xs">
                      Your league starts two QBs, so the superflex expert list is used; it values quarterbacks accordingly.
                    </TooltipContent>
                  </Tooltip>
                ) : (
                  <span>Experts: FantasyPros {scoringLabel(ext.scoring)}</span>
                )}
                <span>· {ext.fp_experts} experts</span>
                <span>· updated {ext.fp_updated || "unknown"}</span>
                <span>· Boris Chen tiers</span>
                <span>· {extMatched} players matched</span>
                {ext.stale && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Badge variant="outline" className="cursor-help text-amber-700 dark:text-amber-300">
                        stale
                      </Badge>
                    </TooltipTrigger>
                    <TooltipContent className="max-w-xs">
                      Downloaded more than a day ago. Refresh rankings (or sync) to pull the latest consensus.
                    </TooltipContent>
                  </Tooltip>
                )}
              </>
            )}
          </div>
        )}
        {ext && ext.errors.length > 0 && (
          <Alert className="py-2">
            <AlertTitle className="text-sm">Expert rankings loaded with problems</AlertTitle>
            <AlertDescription className="text-xs">
              <ul className="list-disc pl-4">
                {ext.errors.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        )}
        {sync.error && (
          <Alert variant="destructive">
            <AlertTitle>Sync failed</AlertTitle>
            <AlertDescription>{errorMessage(sync.error)}</AlertDescription>
          </Alert>
        )}
        {sync.data && sync.data.errors.length > 0 && (
          <Alert>
            <AlertTitle>Sync finished with warnings</AlertTitle>
            <AlertDescription>
              <ul className="list-disc pl-4">
                {sync.data.errors.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        )}
        <div className="flex flex-wrap gap-2">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button size="sm" disabled={sync.isPending} onClick={() => sync.mutate(false)}>
                {sync.isPending && sync.variables === false ? <RefreshCwIcon className="animate-spin" /> : <RefreshCwIcon />}
                Load saved data
              </Button>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs">
              Uses the copy already saved on this computer and only contacts ESPN for anything missing. Instant and works
              offline, so use this on draft day.
            </TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button size="sm" variant="outline" disabled={sync.isPending} onClick={() => sync.mutate(true)}>
                {sync.isPending && sync.variables === true ? <RefreshCwIcon className="animate-spin" /> : <CloudDownloadIcon />}
                Refresh from ESPN
              </Button>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs">
              Re-downloads everything from ESPN: projections, ADP, injuries, your roster, and draft history. Takes ~10s and
              needs valid cookies. Do this the day before the draft so rankings reflect the latest news.
            </TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button size="sm" variant="outline" disabled={refreshExternal.isPending || sync.isPending} onClick={() => refreshExternal.mutate()}>
                {refreshExternal.isPending ? <RefreshCwIcon className="animate-spin" /> : <SparklesIcon />}
                Refresh rankings
              </Button>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs">
              Re-downloads FantasyPros consensus and Boris Chen tiers. ESPN data is untouched. They're cached for a day and
              refreshed automatically on sync.
            </TooltipContent>
          </Tooltip>
        </div>
      </CardContent>
    </Card>
  );
}
