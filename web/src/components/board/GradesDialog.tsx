import { useState } from "react";
import { TrophyIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { NotReady } from "@/components/NotReady";
import { useBoardGrades } from "@/lib/queries";
import type { TeamGrade } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Green for a strong draft through to red for a weak one, on the same scale as the score. */
function scoreTone(score: number): string {
  if (score >= 90) return "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30";
  if (score >= 80) return "bg-lime-500/15 text-lime-700 dark:text-lime-400 border-lime-500/30";
  if (score >= 72) return "bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30";
  return "bg-red-500/15 text-red-700 dark:text-red-400 border-red-500/30";
}

function TeamRow({ t }: { t: TeamGrade }) {
  return (
    <li className={cn("rounded-lg border p-3", t.is_me && "border-foreground/40 bg-muted/40")}>
      <div className="flex items-start gap-3">
        <span className="num w-6 shrink-0 pt-1 text-right text-sm text-muted-foreground">{t.rank}</span>
        <div
          className={cn(
            "flex w-14 shrink-0 flex-col items-center rounded-md border py-1 leading-none",
            scoreTone(t.score),
          )}
        >
          <span className="num text-lg font-semibold">{t.score}</span>
          <span className="text-[10px] font-medium">{t.grade}</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className={cn("truncate font-medium", t.is_me && "font-semibold")}>{t.name}</span>
            {t.is_me && <span className="text-[10px] font-medium uppercase text-muted-foreground">you</span>}
            {t.owner && <span className="truncate text-xs text-muted-foreground">{t.owner}</span>}
            <span className="num ml-auto shrink-0 text-xs text-muted-foreground">
              {t.picks_made} pick{t.picks_made === 1 ? "" : "s"} · {t.edge >= 0 ? "+" : ""}
              {t.edge.toFixed(0)} vs expected
            </span>
          </div>
          <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
            {t.reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      </div>
    </li>
  );
}

/** Grade every team's draft, 0-100, with the reasoning behind each score. */
export function GradesDialog() {
  const [open, setOpen] = useState(false);
  const { data, isLoading, error } = useBoardGrades(open);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="xs" variant="outline" className="shrink-0">
          <TrophyIcon /> Draft grades
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[88vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Draft grades</DialogTitle>
          <DialogDescription>
            {data ? `${data.graded_picks} of ${data.total_picks} picks graded` : "Scoring every team's draft…"}
          </DialogDescription>
        </DialogHeader>

        {isLoading && <Skeleton className="h-72 w-full" />}
        {error && <NotReady error={error} />}

        {data && (
          <div className="space-y-3 text-sm">
            {!data.complete && data.note && (
              <p className="rounded-lg border border-amber-500/40 bg-amber-50/60 p-2.5 text-xs dark:bg-amber-950/20">
                {data.note}
              </p>
            )}
            {data.teams.length === 0 ? (
              <p className="text-muted-foreground">{data.note || "Nothing to grade yet."}</p>
            ) : (
              <ol className="space-y-2">
                {data.teams.map((t) => (
                  <TeamRow key={t.team_id} t={t} />
                ))}
              </ol>
            )}
            <p className="border-t pt-2 text-xs text-muted-foreground">
              <Badge variant="outline" className="mr-1.5">
                How it works
              </Badge>
              {data.method}
            </p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
