import { CheckCircle2Icon, LightbulbIcon, TriangleAlertIcon, XCircleIcon } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { fmt, fmtSigned } from "@/lib/format";
import type { RecapNote, RecapPlayer, WeekRecap } from "@/lib/types";
import { cn } from "@/lib/utils";

function ScoreLine({ r }: { r: WeekRecap }) {
  const won = r.result === "W";
  const lost = r.result === "L";
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <span
        className={cn(
          "inline-flex h-7 items-center rounded-md px-2.5 text-sm font-semibold",
          won && "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
          lost && "bg-rose-500/15 text-rose-700 dark:text-rose-300",
          !won && !lost && "bg-muted text-foreground",
        )}
      >
        {won ? "Win" : lost ? "Loss" : "Tie"}
      </span>
      <span className="font-heading text-lg font-semibold">
        <span className="num">{fmt(r.my_score)}</span>
        <span className="mx-2 text-muted-foreground">–</span>
        <span className="num">{fmt(r.opp_score)}</span>
      </span>
      <span className="text-sm text-muted-foreground">vs {r.opponent}</span>
      <span className="text-sm text-muted-foreground">
        projected <span className="num">{fmt(r.my_projected)}</span>–<span className="num">{fmt(r.opp_projected)}</span>
      </span>
      {r.record && <Badge variant="outline">{r.record}</Badge>}
      {r.bench_points_left >= 1 && (
        <span className="text-sm text-muted-foreground">
          best possible <span className="num font-medium text-foreground">{fmt(r.optimal_score)}</span>
          {r.would_have_won !== null && (
            <span className={cn("ml-1", r.would_have_won ? "text-emerald-700 dark:text-emerald-300" : "")}>
              ({r.would_have_won ? "would have won" : "still a loss"})
            </span>
          )}
        </span>
      )}
    </div>
  );
}

function Note({ n }: { n: RecapNote }) {
  return (
    <li className="space-y-1 rounded-lg border bg-card px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">{n.headline}</span>
        <Badge variant="outline" className="h-5 text-[10px] font-medium text-muted-foreground">
          {n.source}
        </Badge>
      </div>
      <p className="max-w-prose text-sm leading-6 text-foreground">{n.detail}</p>
    </li>
  );
}

function NoteList({ icon, title, notes, empty }: { icon: React.ReactNode; title: string; notes: RecapNote[]; empty: string }) {
  return (
    <section className="space-y-2">
      <h3 className="flex items-center gap-1.5 text-sm font-medium">
        {icon}
        {title}
      </h3>
      {notes.length === 0 ? (
        <p className="text-sm text-muted-foreground">{empty}</p>
      ) : (
        <ul className="space-y-2">
          {notes.map((n, i) => (
            <Note key={`${n.headline}-${i}`} n={n} />
          ))}
        </ul>
      )}
    </section>
  );
}

function LineupTable({ title, lineup }: { title: string; lineup: RecapPlayer[] }) {
  const starters = lineup.filter((p) => p.slot !== "BE" && p.slot !== "IR");
  const bench = lineup.filter((p) => p.slot === "BE");
  const rows = [...starters, ...bench];
  return (
    <div className="min-w-0">
      <h4 className="mb-1.5 text-xs font-semibold tracking-wide text-muted-foreground uppercase">{title}</h4>
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b bg-muted/40 text-left text-muted-foreground">
              <th className="px-2 py-1 font-medium">Slot</th>
              <th className="px-2 py-1 font-medium">Player</th>
              <th className="px-2 py-1 text-right font-medium">Pts</th>
              <th className="px-2 py-1 text-right font-medium">Proj</th>
              <th className="px-2 py-1 text-right font-medium">+/-</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const d = p.points - p.projected;
              const bench = p.slot === "BE";
              return (
                <tr key={`${p.slot}-${p.player_id}`} className={cn("border-b last:border-0", bench && "text-muted-foreground")}>
                  <td className="px-2 py-1 font-medium">{p.slot === "RB/WR/TE" || p.slot === "RB/WR" ? "FLEX" : p.slot}</td>
                  <td className="px-2 py-1">
                    {p.name}
                    {p.opponent && <span className="ml-1 text-muted-foreground">vs {p.opponent}</span>}
                  </td>
                  <td className="num px-2 py-1 text-right">{fmt(p.points)}</td>
                  <td className="num px-2 py-1 text-right text-muted-foreground">{fmt(p.projected)}</td>
                  <td
                    className={cn(
                      "num px-2 py-1 text-right",
                      !bench && d >= 5 && "text-emerald-700 dark:text-emerald-300",
                      !bench && d <= -5 && "text-rose-700 dark:text-rose-300",
                    )}
                  >
                    {fmtSigned(d)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function RecapCard({ recap, isLoading, error }: { recap: WeekRecap | undefined; isLoading: boolean; error: unknown }) {
  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (error || !recap) return null; // the lineup card already shows the not-synced / server error state
  if (!recap.available) {
    return (
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle>{recap.week_label} recap</CardTitle>
          <CardDescription>{recap.reason}{recap.week > 1 ? " Use ‹ above to read an earlier week's recap." : ""}</CardDescription>
        </CardHeader>
      </Card>
    );
  }
  return (
    <Card className="shadow-sm">
      <CardHeader className="gap-2">
        <CardTitle>{recap.week_label} recap</CardTitle>
        <CardDescription>What happened, why, and what to carry into next week.</CardDescription>
        <ScoreLine r={recap} />
      </CardHeader>
      <CardContent className="space-y-5">
        {recap.errors.length > 0 && (
          <Alert className="py-2">
            <TriangleAlertIcon />
            <AlertTitle className="text-sm">Some sources could not be loaded</AlertTitle>
            <AlertDescription className="text-xs">
              <ul className="list-disc pl-4">
                {recap.errors.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        )}
        <p className="max-w-prose text-sm leading-7 text-foreground">{recap.summary}</p>
        <div className="grid gap-4 lg:grid-cols-2">
          <NoteList
            icon={<CheckCircle2Icon className="size-4 text-emerald-600 dark:text-emerald-400" />}
            title="What went right"
            notes={recap.right}
            empty="Nobody meaningfully beat his projection."
          />
          <NoteList
            icon={<XCircleIcon className="size-4 text-rose-600 dark:text-rose-400" />}
            title="What went wrong"
            notes={recap.wrong}
            empty="No starter fell badly short of his projection."
          />
        </div>
        <NoteList
          icon={<LightbulbIcon className="size-4 text-amber-600 dark:text-amber-400" />}
          title="Keep in mind for next week and beyond"
          notes={recap.lessons}
          empty="Nothing stands out — same plan next week."
        />
        <div className="grid gap-4 lg:grid-cols-2">
          <LineupTable title={`Your lineup (${recap.my_team})`} lineup={recap.my_lineup} />
          <LineupTable title={recap.opponent} lineup={recap.opp_lineup} />
        </div>
        <p className="text-xs text-muted-foreground">
          Sources: ESPN box score and injury tags
          {recap.sources.sleeper ? `; Sleeper trends and practice reports (${recap.sources.sleeper})` : ""}. Hindsight lineups use the same slot
          rules as the recommendations above.
        </p>
      </CardContent>
    </Card>
  );
}
