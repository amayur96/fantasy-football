import { Badge } from "@/components/ui/badge";
import { posClass } from "@/lib/format";
import { cn } from "@/lib/utils";

export function PosBadge({ pos, className }: { pos: string; className?: string }) {
  return (
    <Badge variant="secondary" className={cn("px-1.5 font-semibold", posClass(pos), className)}>
      {pos}
    </Badge>
  );
}

export function InjuryBadge({ status }: { status: string | null | undefined }) {
  if (!status || status === "ACTIVE" || status === "NORMAL") return null;
  return (
    <Badge variant="destructive" className="px-1.5 text-[10px] uppercase">
      {status.replace(/_/g, " ")}
    </Badge>
  );
}
