import type { ExternalScoring, Position } from "./types";

export function relativeTime(epochSecs: number, now = Date.now()): string {
  const diff = Math.max(0, now / 1000 - epochSecs);
  if (diff < 60) return "just now";
  const m = Math.floor(diff / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}d ago`;
  return new Date(epochSecs * 1000).toLocaleDateString();
}

export function fmt(n: number | null | undefined, digits = 1): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "–";
  return n.toFixed(digits);
}

export function fmtInt(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "–";
  return String(Math.round(n));
}

export function fmtSigned(n: number | null | undefined, digits = 1): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "–";
  const s = n.toFixed(digits);
  return n > 0 ? `+${s}` : s;
}

/** Tailwind classes for a position badge. */
export function posClass(pos: Position | string): string {
  switch (pos) {
    case "QB":
      return "bg-rose-500/15 text-rose-700 dark:text-rose-300";
    case "RB":
      return "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300";
    case "WR":
      return "bg-sky-500/15 text-sky-700 dark:text-sky-300";
    case "TE":
      return "bg-amber-500/15 text-amber-700 dark:text-amber-300";
    case "K":
      return "bg-violet-500/15 text-violet-700 dark:text-violet-300";
    case "D/ST":
      return "bg-slate-500/15 text-slate-700 dark:text-slate-300";
    default:
      return "bg-muted text-muted-foreground";
  }
}

export function teamName(names: Record<string, string> | undefined, id: number | null | undefined): string {
  if (id === null || id === undefined) return "?";
  return names?.[String(id)] ?? `Team ${id}`;
}

/** Seconds-granularity relative time for live indicators ("12s ago"). */
export function secondsAgo(epochMs: number, now = Date.now()): string {
  const s = Math.max(0, Math.floor((now - epochMs) / 1000));
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s ago`;
  return relativeTime(epochMs / 1000, now);
}

/** Dark or light text that stays readable on an arbitrary hex background (sheet colors are pastels). */
export function readableTextOn(hex: string | null | undefined): string {
  const m = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec((hex ?? "").trim());
  if (!m) return "inherit";
  let h = m[1];
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  const lum = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
  return lum > 0.4 ? "#1a1a1a" : "#fafafa";
}

/** Human label for the FantasyPros scoring format. */
export function scoringLabel(s: ExternalScoring | string): string {
  switch (s) {
    case "HALF":
      return "Half-PPR";
    case "PPR":
      return "PPR";
    case "STD":
      return "Standard";
    default:
      return s;
  }
}

/** "#12 · RB4" style expert-rank text; null when FantasyPros has no rank for the player. */
export function fpRankText(p: { fp_rank: number | null; fp_pos_rank: string | null }, sep = " · "): string | null {
  if (p.fp_rank === null) return null;
  return p.fp_pos_rank ? `#${p.fp_rank}${sep}${p.fp_pos_rank}` : `#${p.fp_rank}`;
}
