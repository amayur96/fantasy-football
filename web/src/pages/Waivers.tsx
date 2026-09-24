import { useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { DropsCard } from "@/components/waivers/DropsCard";
import { PicksTable } from "@/components/waivers/PicksTable";
import { SourcesFooter } from "@/components/waivers/SourcesFooter";
import { WaiverHeader } from "@/components/waivers/WaiverHeader";
import { NotReady } from "@/components/NotReady";
import { errorMessage, isNotSynced } from "@/lib/api";
import { useRefreshWaivers, useWaivers } from "@/lib/queries";

export function Waivers() {
  // undefined = whatever ESPN says is the current week; a number once the user pages around.
  const [week, setWeek] = useState<number | undefined>(undefined);
  const wv = useWaivers(week);
  const refresh = useRefreshWaivers(week);

  return (
    <div className="space-y-5">
      {wv.isLoading && (
        <div className="space-y-5">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-96 w-full" />
          <p className="text-center text-sm text-muted-foreground">Pulling expert rankings, trends and snap counts. The first load after a while can take a moment.</p>
        </div>
      )}
      {wv.error && isNotSynced(wv.error) && <NotReady error={wv.error} />}
      {wv.error && !isNotSynced(wv.error) && (
        <Alert variant="destructive">
          <AlertTitle>Could not load the waiver wire</AlertTitle>
          <AlertDescription>{errorMessage(wv.error)}</AlertDescription>
        </Alert>
      )}

      {wv.data && (
        <>
          <WaiverHeader view={wv.data} onWeekChange={setWeek} onRefresh={() => refresh.mutate()} refreshing={refresh.isPending} />
          {wv.data.available ? (
            <>
              <PicksTable picks={wv.data.picks} />
              <DropsCard drops={wv.data.drops} />
            </>
          ) : (
            <Alert>
              <AlertTitle>Nothing to show yet</AlertTitle>
              <AlertDescription>{wv.data.reason}</AlertDescription>
            </Alert>
          )}
          <SourcesFooter view={wv.data} />
        </>
      )}
    </div>
  );
}
