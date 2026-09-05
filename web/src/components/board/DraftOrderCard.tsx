import { useState, type CSSProperties } from "react";
import { ChevronDownIcon, ChevronUpIcon, GripVerticalIcon, RotateCcwIcon, SaveIcon, TriangleAlertIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CollapsibleCard } from "@/components/CollapsibleCard";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { ApiError } from "@/lib/api";
import { useSaveSlot, useSetup } from "@/lib/queries";
import { cn } from "@/lib/utils";

/** Reorder the draft slots by hand. Saving writes the full order, which the whole app then treats as confirmed. */
export function DraftOrderCard() {
  const setup = useSetup();
  const save = useSaveSlot();
  // Note: only sync when the server array actually exists, and compare by reference to the
  // query's own array. A `?? []` fallback allocates a new array every render and loops forever.
  const server = setup.data?.slot_order;
  const [order, setOrder] = useState<number[]>([]);
  const [seen, setSeen] = useState<number[] | undefined>(undefined);
  const [dirty, setDirty] = useState(false);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  // Set when the server refuses because recorded picks would be discarded.
  const [needsForce, setNeedsForce] = useState<string | null>(null);
  if (server && seen !== server) {
    setSeen(server);
    if (!dirty) setOrder(server);
  }
  if (!setup.data) return null;

  const teams = new Map(setup.data.teams.map((t) => [t.team_id, t]));
  // The board can be running an older order than the one saved here, if a rebuild was
  // refused. Without this the Save button stays disabled and there is no way to apply it.
  const boardOrder = setup.data.board_slot_order;
  const outOfSync = !!boardOrder && (boardOrder.length !== order.length || boardOrder.some((id, i) => id !== order[i]));
  const myId = setup.data.my_team_id;
  const confirmed = setup.data.setup.slot_order !== null || setup.data.setup.order_confirmed;

  const move = (i: number, dir: -1 | 1) => {
    const j = i + dir;
    if (j < 0 || j >= order.length) return;
    const next = [...order];
    [next[i], next[j]] = [next[j], next[i]];
    setOrder(next);
    setDirty(true);
  };

  /** Live reorder while dragging: the dragged row swaps into whatever slot it hovers. */
  const onDragEnter = (i: number) => {
    if (dragIndex === null || dragIndex === i) return;
    const next = [...order];
    const [moved] = next.splice(dragIndex, 1);
    next.splice(i, 0, moved);
    setOrder(next);
    setDragIndex(i);
    setDirty(true);
  };

  const mySlot = order.indexOf(myId) + 1;
  return (
    <CollapsibleCard
      title="Draft order"
      badge={<Badge variant={confirmed ? "secondary" : "outline"}>{confirmed ? "set" : "unconfirmed"}</Badge>}
      summary={mySlot > 0 ? `you pick ${mySlot} of ${order.length}` : `${order.length} teams`}
      actions={dirty ? <Badge variant="outline">unsaved</Badge> : undefined}
    >
      <p className="text-sm text-muted-foreground">
        The order isn't published yet, so set it here as the league decides. Drag a team to a new slot, or use the arrows, then save.
        This drives the board, whose pick is on the clock, and your keeper values.
      </p>
        <ol
          // Fill down the first column (1-5) before starting the second (6-10).
          className="grid gap-1 sm:grid-cols-2 sm:[grid-auto-flow:column] sm:[grid-template-rows:repeat(var(--order-rows),auto)]"
          style={{ "--order-rows": Math.ceil(order.length / 2) } as CSSProperties}
        >
          {order.map((id, i) => {
            const t = teams.get(id);
            return (
              <li
                key={id}
                draggable
                onDragStart={(e) => {
                  setDragIndex(i);
                  e.dataTransfer.effectAllowed = "move";
                  e.dataTransfer.setData("text/plain", String(id));
                }}
                onDragEnter={() => onDragEnter(i)}
                onDragOver={(e) => e.preventDefault()}
                onDragEnd={() => setDragIndex(null)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragIndex(null);
                }}
                className={cn(
                  "flex cursor-grab items-center gap-2 rounded-md border px-2 py-1.5 text-sm active:cursor-grabbing",
                  id === myId && "border-foreground/40 bg-muted/60",
                  dragIndex === i && "opacity-50 ring-2 ring-foreground/40",
                )}
              >
                <GripVerticalIcon className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                <span className="num w-6 text-right text-xs text-muted-foreground">{i + 1}.</span>
                <span className="min-w-0 flex-1 leading-tight">
                  <span className={cn("block truncate", id === myId && "font-semibold")}>
                    {t?.name ?? `Team ${id}`}
                    {id === myId && <span className="ml-1 text-[10px] font-medium uppercase text-muted-foreground">you</span>}
                  </span>
                  {t?.owner_names?.[0] && <span className="block truncate text-xs text-muted-foreground">{t.owner_names[0]}</span>}
                </span>
                <span className="flex shrink-0">
                  <Button size="icon-xs" variant="ghost" disabled={i === 0} onClick={() => move(i, -1)} aria-label="Move up">
                    <ChevronUpIcon />
                  </Button>
                  <Button size="icon-xs" variant="ghost" disabled={i === order.length - 1} onClick={() => move(i, 1)} aria-label="Move down">
                    <ChevronDownIcon />
                  </Button>
                </span>
              </li>
            );
          })}
        </ol>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            disabled={(!dirty && !outOfSync) || save.isPending}
            onClick={() =>
              save.mutate(
                { my_slot: null, slot_order: order, order_confirmed: true },
                {
                  onSuccess: () => {
                    setDirty(false);
                    setNeedsForce(null);
                  },
                  onError: (err) =>
                    setNeedsForce(err instanceof ApiError && err.status === 409 ? err.message : null),
                },
              )
            }
          >
            <SaveIcon /> Save order
          </Button>
          {dirty && (
            <Button size="sm" variant="ghost" onClick={() => { setOrder(server ?? []); setDirty(false); }}>
              <RotateCcwIcon /> Reset
            </Button>
          )}
          <span className="text-xs text-muted-foreground">You pick {mySlot || "?"} of {order.length}</span>
        </div>
        {outOfSync && !needsForce && !dirty && (
          <Alert>
            <TriangleAlertIcon />
            <AlertTitle>The board is on a different order</AlertTitle>
            <AlertDescription>
              <p>
                This order is saved, but the board is still built on the previous one, so the columns and whose pick is
                on the clock are wrong. Save again to apply it to the board.
              </p>
            </AlertDescription>
          </Alert>
        )}
        {needsForce && (
          <Alert variant="destructive">
            <TriangleAlertIcon />
            <AlertTitle>Order not saved</AlertTitle>
            <AlertDescription className="grid gap-2">
              <p>
                {needsForce} Changing who picks where moves every pick number, so the board has to be rebuilt and the
                picks already recorded on it cannot be kept.
              </p>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="destructive"
                  disabled={save.isPending}
                  onClick={() =>
                    save.mutate(
                      { my_slot: null, slot_order: order, order_confirmed: true, force: true },
                      {
                        onSuccess: () => {
                          setDirty(false);
                          setNeedsForce(null);
                        },
                      },
                    )
                  }
                >
                  Clear the board and save
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setNeedsForce(null)}>
                  Keep the picks
                </Button>
              </div>
            </AlertDescription>
          </Alert>
        )}
    </CollapsibleCard>
  );
}
