import { Skeleton } from "@/components/ui/skeleton";
import { KeeperCard } from "@/components/dashboard/KeeperCard";
import { SlotCard } from "@/components/dashboard/SlotCard";
import { NotReady } from "@/components/NotReady";
import { useSettings, useSetup } from "@/lib/queries";

export function Keeper() {
  const setup = useSetup();
  const settings = useSettings();
  const teamCount = settings.data?.settings?.team_count ?? 0;
  return (
    <div className="space-y-5">
      {setup.isLoading && <Skeleton className="h-40 w-full" />}
      {setup.error && <NotReady error={setup.error} />}
      {setup.data && (
        <>
          <KeeperCard />
          <SlotCard setup={setup.data} teamCount={teamCount} />
        </>
      )}
    </div>
  );
}
