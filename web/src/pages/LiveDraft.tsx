import { useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { NotReady } from "@/components/NotReady";
import { DraftTopBar } from "@/components/draft/DraftTopBar";
import { OverallRankings, type RankSource } from "@/components/draft/OverallRankings";
import { PlayerCard } from "@/components/draft/PlayerCard";
import { PositionPanels } from "@/components/draft/PositionPanels";
import { RecommendationsPanel } from "@/components/draft/RecommendationsPanel";
import { errorMessage } from "@/lib/api";
import { useCheatSheet, useDraftState } from "@/lib/queries";

const SOURCE_KEY = "ffdraft-rank-source";
const SOURCES: RankSource[] = ["espn", "fp", "bc"];

function readSource(): RankSource {
  try {
    const stored = localStorage.getItem(SOURCE_KEY);
    if (stored && (SOURCES as string[]).includes(stored)) return stored as RankSource;
  } catch {
    // private mode / storage disabled: fall through to the default
  }
  return "fp";
}

export function LiveDraft() {
  const { data, error, isLoading } = useDraftState();
  const sheet = useCheatSheet();
  const [source, setSource] = useState<RankSource>(readSource);
  const [cardPlayerId, setCardPlayerId] = useState<number | null>(null);

  const changeSource = (s: RankSource) => {
    setSource(s);
    try {
      localStorage.setItem(SOURCE_KEY, s);
    } catch {
      // ignore
    }
  };

  if (error) return <NotReady error={error} />;
  if (isLoading || !data) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-12" />
        <div className="flex gap-3">
          <Skeleton className="h-[70vh] w-1/3" />
          <Skeleton className="h-[70vh] flex-1" />
        </div>
      </div>
    );
  }

  // Header (3rem) + main's vertical padding (2.5rem): the two panes own the rest of the viewport.
  return (
    <div className="flex flex-col gap-3 lg:h-[calc(100vh-5.5rem)]">
      <DraftTopBar view={data} />
      {sheet.error && <p className="text-sm text-destructive">{errorMessage(sheet.error)}</p>}
      <RecommendationsPanel view={data} onOpenCard={setCardPlayerId} />
      <div className="flex min-h-0 flex-1 flex-col gap-3 lg:flex-row">
        <OverallRankings
          view={data}
          sheet={sheet.data}
          isLoading={sheet.isLoading}
          source={source}
          onSourceChange={changeSource}
          onOpenCard={setCardPlayerId}
        />
        <PositionPanels view={data} sheet={sheet.data} isLoading={sheet.isLoading} onOpenCard={setCardPlayerId} />
      </div>
      <PlayerCard playerId={cardPlayerId} onOpenChange={(o) => !o && setCardPlayerId(null)} />
    </div>
  );
}
