"""The player card behind a click on the draft board: the numbers drafters actually use."""
from __future__ import annotations

import math

from .models import DetailMetric, LeagueSettings, PlayerDetail, RankedPlayer, SeasonPoints
from .value import Rankings


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _fmt(x: float | None, digits: int = 0) -> str:
    return "—" if x is None else f"{x:,.{digits}f}"


def build_metrics(p: RankedPlayer, rankings: Rankings, settings: LeagueSettings, taken: set[int]) -> list[DetailMetric]:
    T = settings.team_count
    pos_list = rankings.by_pos.get(p.position, [])
    available_same_tier = [q for q in pos_list if q.tier == p.tier and q.player_id not in taken]
    starters = rankings.starter_counts.get(p.position, 0)
    baseline = rankings.baselines.get(p.position, 0.0)
    out: list[DetailMetric] = []

    out.append(DetailMetric(
        label="Projected points", value=_fmt(p.proj_points),
        hint=f"ESPN's season projection under your league's scoring. Replacement level at {p.position} is about {_fmt(baseline)}.",
    ))
    out.append(DetailMetric(
        label="Points over replacement", value=f"{p.vorp:+,.0f}",
        hint=f"How many more points than a freely available {p.position}. This is what a pick actually buys you.",
        tone="good" if p.vorp > 20 else "bad" if p.vorp < 0 else "neutral",
    ))
    out.append(DetailMetric(
        label="Position rank", value=f"{p.position}{p.pos_rank}",
        hint=f"Your league starts about {starters} {p.position}s across all teams, so {p.position}{starters} is roughly the last starter.",
        tone="good" if starters and p.pos_rank <= starters else "neutral",
    ))
    out.append(DetailMetric(
        label="Tier", value=f"Tier {p.tier}" + (f" (Boris Chen)" if p.bc_tier else ""),
        hint=f"{len(available_same_tier)} player{'s' if len(available_same_tier) != 1 else ''} left in this tier at {p.position}. "
             "When a tier empties, the next one is a real drop in expected points.",
        tone="bad" if len(available_same_tier) <= 2 else "neutral",
    ))
    if p.adp:
        out.append(DetailMetric(
            label="ADP", value=f"#{p.adp:.0f} (round {p.adp_round})",
            hint="Where ESPN drafters are actually taking him. Your own pick has to come before this to get him.",
        ))
    if p.fp_rank:
        spread = (p.fp_worst - p.fp_best) if (p.fp_best and p.fp_worst) else None
        out.append(DetailMetric(
            label="Expert consensus", value=f"#{p.fp_rank}" + (f" · {p.fp_pos_rank}" if p.fp_pos_rank else ""),
            hint="FantasyPros consensus across their expert panel for your scoring format.",
        ))
        if spread is not None:
            out.append(DetailMetric(
                label="Expert disagreement", value=f"#{p.fp_best}–#{p.fp_worst} ({spread} spots)",
                hint="How far apart the experts are. A wide spread means a boom-or-bust call, not a safe floor.",
                tone="bad" if spread >= 60 else "good" if spread <= 20 else "neutral",
            ))
    if p.adp and p.fp_rank:
        gap = p.adp - p.fp_rank
        out.append(DetailMetric(
            label="Market vs experts", value=f"{gap:+.0f} spots",
            hint="Positive means drafters let him slide past where experts rank him, so he is a value. Negative means he is being reached for.",
            tone="good" if gap >= 12 else "bad" if gap <= -12 else "neutral",
        ))
    if p.consensus_gap is not None:
        out.append(DetailMetric(
            label="ESPN vs experts", value=f"{p.consensus_gap:+.0f} spots",
            hint="Positive means ESPN's projection is higher on him than the experts are.",
            tone="neutral",
        ))
    if p.bye_week:
        out.append(DetailMetric(label="Bye week", value=str(p.bye_week), hint="The week he scores nothing. Avoid stacking byes at one position."))
    if p.percent_owned:
        out.append(DetailMetric(label="Rostered", value=f"{p.percent_owned:.0f}%", hint="Share of ESPN leagues where he is on a roster."))
    if p.injury_status and p.injury_status.upper() not in ("ACTIVE", "NORMAL"):
        out.append(DetailMetric(label="Injury", value=p.injury_status.replace("_", " ").title(), hint="ESPN's current designation.", tone="bad"))
    return out


def build_notes(p: RankedPlayer, history: list[SeasonPoints], rankings: Rankings, settings: LeagueSettings) -> list[str]:
    notes: list[str] = []
    played = [h for h in history if h.games]
    if played:
        best, worst = max(played, key=lambda h: h.avg), min(played, key=lambda h: h.avg)
        notes.append(
            f"Last {len(played)} season{'s' if len(played) > 1 else ''}: "
            + ", ".join(f"{h.season} {h.points:.0f} pts in {h.games} games ({h.avg:.1f}/g)" for h in played)
            + "."
        )
        if len(played) > 1 and best.avg > worst.avg * 1.6:
            notes.append(f"Uneven year to year: {best.avg:.1f} per game in {best.season} against {worst.avg:.1f} in {worst.season}.")
        missed = [h for h in played if h.games <= 13]
        if missed:
            notes.append(f"Missed time in {', '.join(str(h.season) for h in missed)} — durability is part of the price.")
    else:
        notes.append("No scoring history in this league's data, so he is a projection-only bet (rookie, or new to the league).")
    if p.adp and p.value_round and p.adp_round and p.adp_round > p.value_round + 1:
        notes.append(f"Your model values him around round {p.value_round} while drafters wait until round {p.adp_round}; you can likely get him later than you think.")
    if p.adp and p.adp_round and p.value_round and p.value_round > p.adp_round + 1:
        notes.append(f"Drafters take him in round {p.adp_round}, earlier than his round {p.value_round} value here — taking him is paying the market, not finding a bargain.")
    return notes


def build_detail(
    p: RankedPlayer, history: list[SeasonPoints], rankings: Rankings, settings: LeagueSettings,
    taken: set[int], taken_at: int | None = None, taken_by: str | None = None, history_error: str | None = None,
) -> PlayerDetail:
    return PlayerDetail(
        player=p, history=sorted(history, key=lambda h: -h.season),
        metrics=build_metrics(p, rankings, settings, taken),
        notes=build_notes(p, history, rankings, settings),
        taken_at=taken_at, taken_by=taken_by, history_error=history_error,
    )
