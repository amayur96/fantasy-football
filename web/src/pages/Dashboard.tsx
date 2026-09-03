import { useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { LineupCard } from "@/components/dashboard/LineupCard";
import { MovesCard } from "@/components/dashboard/MovesCard";
import { NotReady } from "@/components/NotReady";
import { errorMessage, isNotSynced } from "@/lib/api";
import { useRefreshWeek, useWeek } from "@/lib/queries";

export function Dashboard() {
  // undefined = whatever ESPN says is the current week; a number once the user pages around.
  const [week, setWeek] = useState<number | undefined>(undefined);
  const wk = useWeek(week);
  const refresh = useRefreshWeek(week);

  return (
    <div className="space-y-5">
      {wk.isLoading && (
        <div className="space-y-5">
          <Skeleton className="h-96 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      )}
      {wk.error && isNotSynced(wk.error) && <NotReady error={wk.error} />}
      {wk.error && !isNotSynced(wk.error) && (
        <Alert variant="destructive">
          <AlertTitle>Could not load this week</AlertTitle>
          <AlertDescription>{errorMessage(wk.error)}</AlertDescription>
        </Alert>
      )}

      {wk.data && (
        <>
          <LineupCard view={wk.data} onWeekChange={setWeek} onRefresh={() => refresh.mutate()} refreshing={refresh.isPending} />
          <MovesCard view={wk.data} />
        </>
      )}
    </div>
  );
}
