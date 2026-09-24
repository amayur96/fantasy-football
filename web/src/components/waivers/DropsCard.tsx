import { ScissorsIcon, ShieldIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { InjuryBadge, PosBadge } from "@/components/PosBadge";
import type { DropCandidate } from "@/lib/types";
import { ScoreBar } from "./ScoreBar";

export function DropsCard({ drops }: { drops: DropCandidate[] }) {
  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5">
          <ScissorsIcon className="size-4 text-muted-foreground" />
          Your bench, most droppable first
        </CardTitle>
        <CardDescription>Scored the same way as the pickups. Starters, IR, your keeper and your only defense are never offered as a drop.</CardDescription>
      </CardHeader>
      <CardContent>
        {drops.length === 0 ? (
          <p className="text-sm text-muted-foreground">No bench players could be dropped right now.</p>
        ) : (
          <ol className="space-y-2">
            {drops.map((d, i) => (
              <li key={d.player.player_id} className="space-y-1.5 rounded-lg border bg-card px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="num w-5 text-xs text-muted-foreground">{i + 1}.</span>
                  <span className="font-semibold">{d.player.name}</span>
                  <span className="text-xs text-muted-foreground">{d.player.pro_team || "--"}</span>
                  <PosBadge pos={d.player.position} className="h-4 text-[10px]" />
                  <InjuryBadge status={d.player.injury_status ?? d.player.sleeper_injury} />
                  {d.player.protected && (
                    <Badge variant="outline" className="h-5 gap-1 text-[10px]">
                      <ShieldIcon className="size-3" />
                      keeper
                    </Badge>
                  )}
                  <ScoreBar score={d.player.add_score} className="ml-auto" />
                </div>
                <p className="max-w-prose text-sm leading-6 text-foreground">{d.why}</p>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
