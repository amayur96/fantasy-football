import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { PosBadge } from "@/components/PosBadge";
import { teamName } from "@/lib/format";
import { POSITIONS, type DraftPick, type DraftView } from "@/lib/types";
import { cn } from "@/lib/utils";

function pickLabel(p: DraftPick) {
  return `Round ${p.round} · Pick ${p.pick_in_round} · #${p.overall} overall`;
}

export function PickClock({ view }: { view: DraftView }) {
  const otc = view.on_the_clock;
  const mine = otc !== null && otc.owner_team_id === view.state.my_team_id;
  const until = view.picks_until_my_turn;
  return (
    <Card className={cn("gap-2 shadow-sm", mine && "ring-2 ring-emerald-500/60")}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          On the clock
          {view.state.provisional_order && <Badge variant="outline">provisional order</Badge>}
        </CardTitle>
        <CardDescription>{otc ? pickLabel(otc) : "Draft complete"}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-1.5 text-sm">
        {otc && (
          <div className="text-lg font-semibold">
            {mine ? "You" : teamName(view.team_names, otc.owner_team_id)}
            {otc.owner_team_id !== otc.original_team_id && (
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                (via {teamName(view.team_names, otc.original_team_id)})
              </span>
            )}
          </div>
        )}
        <div className="text-muted-foreground">
          {until === null
            ? "No picks remaining for you."
            : until === 0
              ? "It is your pick."
              : `${until} pick${until === 1 ? "" : "s"} until your turn`}
        </div>
        {view.my_next_pick && (
          <div className="text-muted-foreground">
            Your next pick: <span className="num font-medium text-foreground">#{view.my_next_pick.overall}</span> (round{" "}
            {view.my_next_pick.round}, pick {view.my_next_pick.pick_in_round})
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function RosterPanel({ view, className }: { view: DraftView; className?: string }) {
  const byPos = new Map<string, DraftView["my_roster"]>();
  for (const p of view.my_roster) {
    const arr = byPos.get(p.position) ?? [];
    arr.push(p);
    byPos.set(p.position, arr);
  }
  const open = Object.entries(view.open_slots).filter(([, n]) => n > 0);
  return (
    <Card className={cn("gap-2 shadow-sm", className)}>
      <CardHeader>
        <CardTitle>My roster</CardTitle>
        <CardDescription>{view.my_roster.length} players</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {POSITIONS.map((pos) => {
          const list = byPos.get(pos);
          if (!list?.length) return null;
          return (
            <div key={pos} className="flex gap-2">
              <PosBadge pos={pos} className="mt-0.5 shrink-0" />
              <ul className="min-w-0 flex-1">
                {list.map((p) => (
                  <li key={p.player_id} className="flex items-baseline gap-2">
                    <span className="truncate">{p.name}</span>
                    <span className="text-xs text-muted-foreground">{p.pro_team}</span>
                    {p.bye_week !== null && <span className="num ml-auto text-xs text-muted-foreground">bye {p.bye_week}</span>}
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
        {view.my_roster.length === 0 && <p className="text-muted-foreground">No players yet.</p>}
        <Separator />
        <div>
          <div className="mb-1 text-xs font-medium text-muted-foreground">Open slots</div>
          <div className="flex flex-wrap gap-1">
            {open.length === 0 && <span className="text-xs text-muted-foreground">Roster full.</span>}
            {open.map(([slot, n]) => (
              <Badge key={slot} variant="secondary" className="gap-1">
                {slot} <span className="num">{n}</span>
              </Badge>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export function RecentPicks({ view, className }: { view: DraftView; className?: string }) {
  const recent = [...view.recent].slice(-10).reverse();
  return (
    <Card className={cn("gap-2 shadow-sm", className)}>
      <CardHeader>
        <CardTitle>Recent picks</CardTitle>
      </CardHeader>
      <CardContent>
        {recent.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing recorded yet.</p>
        ) : (
          <ol className="space-y-1 text-sm">
            {recent.map((p) => {
              const mine = p.owner_team_id === view.state.my_team_id;
              return (
                <li key={p.overall} className="flex items-baseline gap-2">
                  <span className="num w-8 shrink-0 text-right text-xs text-muted-foreground">#{p.overall}</span>
                  <span className={cn("w-24 shrink-0 truncate text-xs", mine ? "font-medium text-foreground" : "text-muted-foreground")}>
                    {mine ? "You" : teamName(view.team_names, p.owner_team_id)}
                  </span>
                  <span className={cn("min-w-0 flex-1 truncate", p.unknown && "text-muted-foreground italic")}>
                    {p.unknown ? "skipped" : p.player_id !== null ? (view.player_names[String(p.player_id)] ?? `#${p.player_id}`) : "?"}
                  </span>
                  {p.is_keeper && (
                    <Badge variant="outline" className="shrink-0">
                      keeper
                    </Badge>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
