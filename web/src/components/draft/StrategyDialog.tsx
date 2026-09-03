import { BookOpenIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { NotReady } from "@/components/NotReady";
import { useStrategy } from "@/lib/queries";

/** How to think about this specific league's draft. Every number comes from its own settings and pool. */
export function StrategyDialog() {
  const { data, isLoading, error } = useStrategy();
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button size="xs" variant="outline" className="shrink-0">
          <BookOpenIcon /> Strategy
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[88vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>How to draft this league</DialogTitle>
          <DialogDescription>{data?.league_summary ?? "Loading your league's settings…"}</DialogDescription>
        </DialogHeader>

        {isLoading && <Skeleton className="h-72 w-full" />}
        {error && <NotReady error={error} />}

        {data && (
          <div className="space-y-5 text-sm">
            <p className="rounded-lg border border-primary/30 bg-primary/5 p-3 font-medium">{data.headline}</p>

            <section className="space-y-1.5">
              <h3 className="text-xs font-semibold text-muted-foreground uppercase">Scarcity by position</h3>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Pos</TableHead>
                      <TableHead className="text-right">Starters league-wide</TableHead>
                      <TableHead className="text-right">
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="cursor-help underline decoration-dotted underline-offset-4">Replacement pts</span>
                          </TooltipTrigger>
                          <TooltipContent className="max-w-xs">
                            What the best free player at this position scores. Draft nobody there and this is roughly what you
                            still get, so it is the floor every pick is measured against.
                          </TooltipContent>
                        </Tooltip>
                      </TableHead>
                      <TableHead className="text-right">Best over repl.</TableHead>
                      <TableHead className="text-right">Last starter</TableHead>
                      <TableHead className="text-right">Above repl.</TableHead>
                      <TableHead>Biggest drop</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.positions.map((r) => (
                      <TableRow key={r.position}>
                        <TableCell className="font-medium">{r.position}</TableCell>
                        <TableCell className="num text-right">{r.starters_league_wide}</TableCell>
                        <TableCell className="num text-right">{r.replacement_points.toFixed(0)}</TableCell>
                        <TableCell className="num text-right text-emerald-600 dark:text-emerald-400">
                          {r.top_vorp >= 0 ? "+" : ""}
                          {r.top_vorp.toFixed(0)}
                        </TableCell>
                        <TableCell className="num text-right">
                          {r.last_starter_vorp >= 0 ? "+" : ""}
                          {r.last_starter_vorp.toFixed(0)}
                        </TableCell>
                        <TableCell className="num text-right">{r.above_replacement}</TableCell>
                        <TableCell className="num text-xs text-muted-foreground">
                          {r.cliff_after ? `after ${r.position}${r.cliff_after} (${r.cliff_size?.toFixed(0)} pts)` : "—"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </section>

            {data.sections.map((s) => (
              <section key={s.title} className="space-y-1.5">
                <h3 className="font-semibold">{s.title}</h3>
                {s.body.split("\n\n").map((para, i) => (
                  <p key={i} className="text-muted-foreground">
                    {para}
                  </p>
                ))}
                {s.bullets.length > 0 && (
                  <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">
                    {s.bullets.map((b, i) => (
                      <li key={i}>{b}</li>
                    ))}
                  </ul>
                )}
              </section>
            ))}

            <section className="space-y-1.5">
              <h3 className="font-semibold">A rough plan</h3>
              <ol className="space-y-1">
                {data.round_plan.map((r, i) => (
                  <li key={i} className="flex gap-2 text-muted-foreground">
                    <Badge variant="outline" className="num shrink-0">
                      {i + 1}
                    </Badge>
                    <span>{r}</span>
                  </li>
                ))}
              </ol>
            </section>

            <section className="space-y-1.5">
              <h3 className="font-semibold">The metrics that decide picks</h3>
              <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
                {data.metrics.map((m) => (
                  <div key={m.label}>
                    <dt className="text-xs font-medium">
                      {m.label} <span className="text-muted-foreground">· {m.value}</span>
                    </dt>
                    <dd className="text-xs text-muted-foreground">{m.hint}</dd>
                  </div>
                ))}
              </dl>
            </section>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
