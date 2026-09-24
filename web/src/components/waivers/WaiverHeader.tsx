import { ChevronLeftIcon, ChevronRightIcon, CompassIcon, RefreshCwIcon, TriangleAlertIcon } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { relativeTime } from "@/lib/format";
import type { WaiverView } from "@/lib/types";
import { cn } from "@/lib/utils";

const MIN_WEEK = 1;
const MAX_WEEK = 18;

export interface WaiverHeaderProps {
  view: WaiverView;
  onWeekChange: (week: number) => void;
  onRefresh: () => void;
  refreshing: boolean;
}

function faabLine(view: WaiverView): string {
  if (view.faab === true) return view.faab_budget ? `FAAB league, $${view.faab_budget} budget: bid suggestions are FantasyPros' consensus.` : "FAAB league: bid suggestions are FantasyPros' consensus.";
  if (view.faab === false) return "Priority waivers: FantasyPros' bid sizes show how much of a claim each player deserves.";
  return "Bid sizes are FantasyPros' consensus for FAAB leagues; run a sync-refresh to detect your league's waiver type.";
}

export function WaiverHeader({ view, onWeekChange, onRefresh, refreshing }: WaiverHeaderProps) {
  const fetchedMs = Date.parse(view.fetched_at);
  const fetched = Number.isNaN(fetchedMs) ? null : relativeTime(fetchedMs / 1000);
  const counts = { claim: 0, stash: 0, watch: 0 };
  for (const pk of view.picks) counts[pk.tier] += 1;
  return (
    <Card className="shadow-sm">
      <CardHeader className="gap-2">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <CardTitle>Waiver Wire</CardTitle>
          <div className="flex items-center gap-1">
            <Button size="icon-xs" variant="ghost" aria-label="Previous week" disabled={view.week <= MIN_WEEK} onClick={() => onWeekChange(view.week - 1)}>
              <ChevronLeftIcon />
            </Button>
            <span className="font-heading text-base font-medium">{view.week_label}</span>
            <Button size="icon-xs" variant="ghost" aria-label="Next week" disabled={view.week >= MAX_WEEK} onClick={() => onWeekChange(view.week + 1)}>
              <ChevronRightIcon />
            </Button>
          </div>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button size="icon-sm" variant="outline" className="ml-auto" aria-label="Refresh waiver wire" disabled={refreshing} onClick={onRefresh}>
                <RefreshCwIcon className={cn(refreshing && "animate-spin")} />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Re-pull ESPN, FantasyPros, Sleeper, Rotowire and nflverse. This one takes a while.</TooltipContent>
          </Tooltip>
        </div>
        <CardDescription>
          {counts.claim} to claim now, {counts.stash} to stash, {counts.watch} to watch, ranked against your own bench. {faabLine(view)}
          {fetched && <span className="text-muted-foreground"> ESPN fetched {fetched}.</span>}
        </CardDescription>
      </CardHeader>
      {(view.needs.length > 0 || view.errors.length > 0) && (
        <CardContent className="space-y-3">
          {view.needs.length > 0 && (
            <section className="space-y-1.5">
              <h3 className="flex items-center gap-1.5 text-sm font-medium">
                <CompassIcon className="size-4 text-muted-foreground" />
                Roster fit
              </h3>
              <ul className="list-disc space-y-1 pl-5 text-sm">
                {view.needs.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </section>
          )}
          {view.errors.length > 0 && (
            <Alert className="py-2">
              <TriangleAlertIcon />
              <AlertTitle className="text-sm">Some sources could not be loaded</AlertTitle>
              <AlertDescription className="text-xs">
                <p>The rankings below lean on whatever answered; a missing source is left out of the score rather than counted as zero.</p>
                <ul className="list-disc pl-4">
                  {view.errors.map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          )}
        </CardContent>
      )}
    </Card>
  );
}
