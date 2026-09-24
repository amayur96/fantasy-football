import { ExternalLinkIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { WaiverView } from "@/lib/types";

const SOURCE_LABEL: Record<string, string> = {
  espn: "ESPN",
  fantasypros_week: "FantasyPros weekly",
  fantasypros_ros: "FantasyPros rest of season",
  fantasypros_waiver: "FantasyPros waiver panel",
  sleeper: "Sleeper",
  rotowire: "Rotowire",
  nflverse: "nflverse snap counts",
};

export function SourcesFooter({ view }: { view: WaiverView }) {
  const entries = Object.entries(view.sources);
  return (
    <div className="space-y-2 text-xs text-muted-foreground">
      {entries.length > 0 && (
        <p>
          Sources:{" "}
          {entries.map(([k, v], i) => (
            <span key={k}>
              {i > 0 && " · "}
              <span className="text-foreground">{SOURCE_LABEL[k] ?? k}</span> {k === "espn" ? "" : v}
            </span>
          ))}
        </p>
      )}
      {view.links.length > 0 && (
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span>Read more:</span>
          {view.links.map((l) => (
            <a key={l.url} href={l.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-foreground underline-offset-4 hover:underline">
              {l.label}
              <ExternalLinkIcon className="size-3" />
              {l.note && (
                <Badge variant="outline" className="h-4 px-1 text-[10px] font-normal text-muted-foreground">
                  {l.note}
                </Badge>
              )}
            </a>
          ))}
        </p>
      )}
    </div>
  );
}
