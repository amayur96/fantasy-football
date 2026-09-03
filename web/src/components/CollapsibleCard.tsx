import { useState, type ReactNode } from "react";
import { ChevronDownIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/** A card that stays one line until you open it. `summary` and `actions` remain visible when collapsed. */
export function CollapsibleCard({
  title,
  icon,
  badge,
  summary,
  actions,
  defaultOpen = false,
  children,
}: {
  title: string;
  icon?: ReactNode;
  badge?: ReactNode;
  summary?: ReactNode;
  actions?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  // `defaultOpen` often arrives false and flips true once data loads (e.g. "needs attention").
  // Booleans are stable, so syncing during render is safe here.
  const [seenDefault, setSeenDefault] = useState(defaultOpen);
  if (seenDefault !== defaultOpen) {
    setSeenDefault(defaultOpen);
    if (defaultOpen) setOpen(true);
  }
  return (
    <Card className="gap-0 py-0 shadow-sm">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          <ChevronDownIcon className={cn("size-4 shrink-0 text-muted-foreground transition-transform", !open && "-rotate-90")} />
          {icon}
          <span className="font-semibold">{title}</span>
          {badge}
          {summary && <span className="min-w-0 truncate text-xs text-muted-foreground">{summary}</span>}
        </button>
        {actions && <div className="flex shrink-0 items-center gap-3">{actions}</div>}
      </div>
      {open && <CardContent className="space-y-3 px-4 pt-0 pb-4">{children}</CardContent>}
    </Card>
  );
}
