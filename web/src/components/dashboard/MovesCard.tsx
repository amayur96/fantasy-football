import { ArrowLeftRightIcon, TriangleAlertIcon, WavesIcon } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { fmtSigned } from "@/lib/format";
import type { LineupMove, WeekView } from "@/lib/types";
import { cn } from "@/lib/utils";

function deltaText(m: LineupMove): string {
  return m.kind === "waiver" ? `${fmtSigned(m.delta, 0)} ROS pts` : `${fmtSigned(m.delta)} proj`;
}

function MoveBlock({ move }: { move: LineupMove }) {
  const up = move.delta >= 0;
  return (
    <li className="space-y-1 rounded-lg border bg-card px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">{move.headline}</span>
        <span
          className={cn(
            "num inline-flex h-5 items-center rounded-full px-2 text-xs font-medium",
            up ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300" : "bg-rose-500/15 text-rose-700 dark:text-rose-300",
          )}
        >
          {deltaText(move)}
        </span>
      </div>
      {move.quant && <p className="text-sm">{move.quant}</p>}
      {move.qual && <p className="text-sm text-muted-foreground">{move.qual}</p>}
    </li>
  );
}

function Section({ icon, title, moves, empty }: { icon: React.ReactNode; title: string; moves: LineupMove[]; empty: string }) {
  return (
    <section className="space-y-2">
      <h3 className="flex items-center gap-1.5 text-sm font-medium">
        {icon}
        {title}
      </h3>
      {moves.length === 0 ? (
        <p className="text-sm text-muted-foreground">{empty}</p>
      ) : (
        <ul className="space-y-2">
          {moves.map((m, i) => (
            <MoveBlock key={`${m.kind}-${m.slot}-${m.player_in.player_id}-${i}`} move={m} />
          ))}
        </ul>
      )}
    </section>
  );
}

export function MovesCard({ view }: { view: WeekView }) {
  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle>Recommended moves</CardTitle>
        <CardDescription>Start/sit changes for {view.week_label} and waiver pickups that upgrade your roster for the rest of the season.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {view.errors.length > 0 && (
          <Alert className="py-2">
            <TriangleAlertIcon />
            <AlertTitle className="text-sm">Some data could not be loaded</AlertTitle>
            <AlertDescription className="text-xs">
              <ul className="list-disc pl-4">
                {view.errors.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        )}
        <div className="grid gap-4 lg:grid-cols-2">
          <Section
            icon={<ArrowLeftRightIcon className="size-4 text-muted-foreground" />}
            title="Start/sit"
            moves={view.moves}
            empty="Your lineup already matches the recommendation."
          />
          <Section
            icon={<WavesIcon className="size-4 text-muted-foreground" />}
            title="Waiver wire"
            moves={view.waivers}
            empty="No clear waiver upgrades right now."
          />
        </div>
      </CardContent>
    </Card>
  );
}
