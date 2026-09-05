import { useEffect, useMemo, useRef, useState } from "react";
import { SearchIcon, XIcon } from "lucide-react";
import { Input } from "@/components/ui/input";
import { PosBadge } from "@/components/PosBadge";
import { teamName } from "@/lib/format";
import { usePlayers } from "@/lib/queries";
import type { DraftView, RankedPlayer } from "@/lib/types";
import { cn } from "@/lib/utils";

const LIMIT = 12;

interface Props {
  view: DraftView;
  onOpenCard: (playerId: number) => void;
}

/** "Is he gone?" — the question you ask most during a draft, answered without leaving the page. */
export function AvailabilitySearch({ view, onOpenCard }: Props) {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 150);
    return () => clearTimeout(t);
  }, [q]);

  // Where each drafted player actually went, so a hit can say round and team.
  const pickOf = useMemo(() => {
    const m = new Map<number, DraftView["state"]["picks"][number]>();
    for (const p of view.state.picks) if (p.player_id !== null) m.set(p.player_id, p);
    return m;
  }, [view.state.picks]);

  const { data, isFetching } = usePlayers({ q: debounced || undefined, limit: LIMIT }, debounced.length > 0);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const results = debounced ? (data ?? []) : [];
  const showPanel = open && debounced.length > 0;

  return (
    <div ref={box} className="relative w-56 shrink-0">
      <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
      <Input
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        placeholder="Search"
        aria-label="Search for a player to see if he is available or drafted"
        className="h-8 pr-8 pl-8 text-sm"
      />
      {q && (
        <button
          type="button"
          aria-label="Clear search"
          className="absolute top-1/2 right-2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          onClick={() => {
            setQ("");
            setOpen(false);
          }}
        >
          <XIcon className="size-3.5" />
        </button>
      )}

      {showPanel && (
        <div className="absolute top-9 left-0 z-30 w-[26rem] max-w-[calc(100vw-2rem)] overflow-hidden rounded-lg border bg-popover shadow-lg">
          {results.length === 0 ? (
            <p className="px-3 py-2.5 text-sm text-muted-foreground">
              {isFetching ? "Searching…" : `No player matches “${debounced}”.`}
            </p>
          ) : (
            <ul className="max-h-[45vh] overflow-y-auto py-1">
              {results.map((p: RankedPlayer) => {
                const pick = pickOf.get(p.player_id);
                const mine = pick && pick.owner_team_id === view.state.my_team_id;
                return (
                  <li key={p.player_id}>
                    <button
                      type="button"
                      className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-sm hover:bg-muted"
                      onClick={() => {
                        onOpenCard(p.player_id);
                        setOpen(false);
                      }}
                    >
                      <PosBadge pos={p.position} className={cn(pick && "saturate-50")} />
                      <span className={cn("min-w-0 flex-1 truncate", pick && "text-muted-foreground")}>{p.name}</span>
                      <span className="shrink-0 text-xs text-muted-foreground">{p.pro_team}</span>
                      {pick ? (
                        <span className="shrink-0 text-xs font-medium text-red-600 dark:text-red-400">
                          Drafted
                          <span className="ml-1 font-normal text-muted-foreground">
                            R{pick.round} · {mine ? "you" : teamName(view.team_names, pick.owner_team_id)}
                          </span>
                        </span>
                      ) : (
                        <span className="shrink-0 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                          Available
                          {p.adp_round !== null && <span className="ml-1 font-normal text-muted-foreground">ADP R{p.adp_round}</span>}
                        </span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
