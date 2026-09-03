import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { TeamInfo } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Props {
  teams: TeamInfo[];
  value: number;
  onChange: (id: number) => void;
  placeholder?: string;
  className?: string;
  invalid?: boolean;
}

export function TeamSelect({ teams, value, onChange, placeholder = "Team…", className, invalid }: Props) {
  return (
    <Select value={value ? String(value) : ""} onValueChange={(v) => onChange(Number(v))}>
      <SelectTrigger size="sm" className={cn("w-full", className)} aria-invalid={invalid || undefined}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {teams.map((t) => (
          <SelectItem key={t.team_id} value={String(t.team_id)}>
            {t.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
