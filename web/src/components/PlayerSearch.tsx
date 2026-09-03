import { useEffect, useState } from "react";
import { ChevronsUpDownIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { PosBadge } from "@/components/PosBadge";
import { useDraftState, usePlayers } from "@/lib/queries";
import type { RankedPlayer } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Props {
  value: { player_id: number; player_name: string };
  onSelect: (p: RankedPlayer) => void;
  className?: string;
}

/** Popover + Command autocomplete over GET /players?q=. */
export function PlayerSearch({ value, onSelect, className }: Props) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 150);
    return () => clearTimeout(t);
  }, [q]);
  const { data, isFetching } = usePlayers({ q: debounced || undefined, limit: 25 }, open);
  const draft = useDraftState();
  const taken = new Set(draft.data?.taken_ids ?? []);
  const takenNames = draft.data?.player_names ?? {};

  const label = value.player_name || (value.player_id ? `#${value.player_id}` : "");
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          role="combobox"
          aria-expanded={open}
          className={cn("w-full justify-between font-normal", !label && "text-muted-foreground", className)}
        >
          <span className="truncate">{label || "Search player…"}</span>
          <ChevronsUpDownIcon className="opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72 p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput placeholder="Type a name…" value={q} onValueChange={setQ} />
          <CommandList>
            <CommandEmpty>{isFetching ? "Searching…" : "No players found."}</CommandEmpty>
            <CommandGroup>
              {(data ?? []).map((p) => {
                const isTaken = taken.has(p.player_id) && p.player_id !== value.player_id;
                return (
                  <CommandItem
                    key={p.player_id}
                    value={String(p.player_id)}
                    onSelect={() => {
                      onSelect(p);
                      setOpen(false);
                      setQ("");
                    }}
                    className={cn(isTaken && "opacity-50")}
                  >
                    <PosBadge pos={p.position} className={cn(isTaken && "saturate-50")} />
                    <span className={cn("truncate", isTaken && "line-through decoration-red-500 decoration-2 dark:decoration-red-400")}>{p.name}</span>
                    {isTaken && (
                      <span className="shrink-0 text-[10px] text-red-600 uppercase dark:text-red-400" title={takenNames[String(p.player_id)] ? "Already on the board" : undefined}>
                        taken
                      </span>
                    )}
                    <span className="ml-auto text-xs text-muted-foreground">{p.pro_team}</span>
                  </CommandItem>
                );
              })}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
