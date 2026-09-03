import { CheckIcon, UndoIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useSaveSlot } from "@/lib/queries";
import type { SetupResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

export function SlotCard({ setup, teamCount }: { setup: SetupResponse; teamCount: number }) {
  const save = useSaveSlot();
  const names = new Map(setup.teams.map((t) => [t.team_id, t.name]));
  const mySlot = setup.slot_order.indexOf(setup.my_team_id) + 1;
  const count = teamCount || setup.teams.length;
  const confirmed = setup.setup.order_confirmed;
  const manualSlot = setup.setup.my_slot;
  const espnPresent = setup.espn_order_present;
  const slotKnown = confirmed || manualSlot !== null || setup.setup.slot_order !== null;

  let status: { badge: string; text: string };
  if (manualSlot !== null) {
    status = { badge: `slot ${manualSlot} (manual)`, text: "You entered your slot by hand. Clear it once the league confirms the real order." };
  } else if (espnPresent && confirmed) {
    status = { badge: "order confirmed", text: "The league confirmed ESPN's draft order. Keeper math uses your exact pick numbers." };
  } else if (espnPresent) {
    status = {
      badge: "unconfirmed",
      text: "ESPN shows an order below, but the league hasn't confirmed it. Until you confirm it or pick a slot, keeper values assume an average slot and show a range across all slots.",
    };
  } else {
    status = { badge: "no order yet", text: "ESPN has no draft order yet. Pick your slot once the league sets it; until then keeper values assume an average slot." };
  }

  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Draft slot
          <Badge variant={slotKnown ? "secondary" : "outline"}>{status.badge}</Badge>
        </CardTitle>
        <CardDescription>{status.text}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          {espnPresent && !confirmed && manualSlot === null && (
            <Button size="sm" disabled={save.isPending} onClick={() => save.mutate({ my_slot: null, slot_order: null, order_confirmed: true })}>
              <CheckIcon /> Confirm ESPN's order (I'm slot {mySlot})
            </Button>
          )}
          {confirmed && manualSlot === null && (
            <Button size="sm" variant="outline" disabled={save.isPending} onClick={() => save.mutate({ my_slot: null, slot_order: null, order_confirmed: false })}>
              <UndoIcon /> Mark unconfirmed
            </Button>
          )}
          <Select
            value={manualSlot !== null ? String(manualSlot) : ""}
            disabled={save.isPending}
            onValueChange={(v) => save.mutate({ my_slot: Number(v), slot_order: null, order_confirmed: false })}
          >
            <SelectTrigger className="w-40">
              <SelectValue placeholder="Set my slot by hand" />
            </SelectTrigger>
            <SelectContent>
              {Array.from({ length: count }, (_, i) => i + 1).map((n) => (
                <SelectItem key={n} value={String(n)}>
                  Slot {n}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {manualSlot !== null && (
            <Button size="sm" variant="ghost" disabled={save.isPending} onClick={() => save.mutate({ my_slot: null, slot_order: null })}>
              Clear manual slot
            </Button>
          )}
        </div>
        <ol className={cn("grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-3 lg:grid-cols-5", !slotKnown && "opacity-70")}>
          {setup.slot_order.map((id, i) => (
            <li key={`${id}-${i}`} className={cn("flex items-baseline gap-2", id === setup.my_team_id && "font-semibold")}>
              <span className="num w-5 text-right text-xs text-muted-foreground">{i + 1}.</span>
              <span className="truncate">{names.get(id) ?? `Team ${id}`}</span>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}
