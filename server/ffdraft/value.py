"""Value-over-replacement rankings, ADP blending, and tiering."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import mean, pstdev

from .models import POSITIONS, LeagueSettings, Player, Position, RankedPlayer

FLEX_MAP: dict[str, list[Position]] = {
    "RB/WR/TE": ["RB", "WR", "TE"],
    "RB/WR": ["RB", "WR"],
    "WR/TE": ["WR", "TE"],
    "OP": ["QB", "RB", "WR", "TE"],
    "FLEX": ["RB", "WR", "TE"],
}


@dataclass
class ValueWeights:
    w_proj: float = 0.4  # ESPN projection VORP
    w_adp: float = 0.2  # ESPN ADP-implied VORP
    w_fp: float = 0.4  # FantasyPros consensus-rank-implied VORP (renormalised away when missing)
    baseline_smooth: int = 3
    tier_gap_k: float = 1.0
    tier_min_gap: dict[str, float] = field(
        default_factory=lambda: {"QB": 8, "RB": 8, "WR": 8, "TE": 6, "K": 4, "D/ST": 4}
    )
    tier_max_size: int = 8
    tier_depth: dict[str, int] = field(
        default_factory=lambda: {"QB": 24, "RB": 60, "WR": 70, "TE": 24, "K": 14, "D/ST": 14}
    )


@dataclass
class Rankings:
    overall: list[RankedPlayer]
    by_pos: dict[str, list[RankedPlayer]]
    baselines: dict[str, float]
    starter_counts: dict[str, int]
    by_id: dict[int, RankedPlayer] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.by_id = {p.player_id: p for p in self.overall}


def starter_counts(settings: LeagueSettings, players: list[Player]) -> dict[str, int]:
    """Dedicated starter slots × teams, then allocate flex slots greedily by projection."""
    T = settings.team_count
    counts: dict[str, int] = {pos: settings.roster_slots.get(pos, 0) * T for pos in POSITIONS}
    sorted_by_pos: dict[str, list[Player]] = {pos: [] for pos in POSITIONS}
    for p in sorted(players, key=lambda x: x.proj_points, reverse=True):
        sorted_by_pos[p.position].append(p)
    for slot, eligible in FLEX_MAP.items():
        n = settings.roster_slots.get(slot, 0) * T
        if n <= 0:
            continue
        pool: list[tuple[float, str, int]] = []
        for pos in eligible:
            for idx, p in enumerate(sorted_by_pos[pos]):
                if idx >= counts[pos]:
                    pool.append((p.proj_points, pos, idx))
        pool.sort(reverse=True)
        taken: dict[str, int] = {pos: 0 for pos in eligible}
        for _, pos, _ in pool[:n]:
            taken[pos] += 1
        for pos, k in taken.items():
            counts[pos] += k
    return counts


def replacement_levels(players: list[Player], counts: dict[str, int], w: ValueWeights) -> dict[str, float]:
    out: dict[str, float] = {}
    for pos in POSITIONS:
        projs = sorted((p.proj_points for p in players if p.position == pos), reverse=True)
        n = counts.get(pos, 0)
        window = projs[n : n + w.baseline_smooth]
        if not window:
            window = projs[-w.baseline_smooth :] if projs else [0.0]
        out[pos] = mean(window)
    return out


def adp_round(adp: float | None, team_count: int) -> int | None:
    if adp is None or adp <= 0:
        return None
    return max(1, math.ceil(adp / team_count))


def value_round(overall_rank: int, team_count: int) -> int:
    return max(1, math.ceil(overall_rank / team_count))


def _interp(curve: list[float], x: float) -> float:
    """Value at fractional rank x (1-based) on a descending curve."""
    if not curve:
        return 0.0
    if x <= 1:
        return curve[0]
    if x >= len(curve):
        return curve[-1]
    lo = int(math.floor(x))
    frac = x - lo
    return curve[lo - 1] * (1 - frac) + curve[lo] * frac


def _gap_tiers(players: list[RankedPlayer], pos: str, w: ValueWeights, start: int = 1) -> int:
    """Number `players` into tiers by value gaps, beginning at `start`. Returns the last tier used."""
    if not players:
        return start - 1
    gaps = [players[i - 1].value - players[i].value for i in range(1, len(players))]
    if gaps:
        threshold = max(w.tier_min_gap.get(pos, 6), mean(gaps) + w.tier_gap_k * pstdev(gaps))
    else:
        threshold = w.tier_min_gap.get(pos, 6)
    tier, size = start, 0
    for i, p in enumerate(players):
        if i > 0 and (gaps[i - 1] > threshold or size >= w.tier_max_size):
            tier += 1
            size = 0
        p.tier = tier
        size += 1
    return tier


def assign_tiers(pos_players: list[RankedPlayer], pos: str, w: ValueWeights) -> None:
    """Boris Chen's tiers where he ranks a player, then keep tiering the tail by value gaps.

    His files only cover the top 20-60 per position, but drafts run 18 rounds, so everyone
    below him still needs a real tier rather than one giant bucket.
    """
    if not pos_players:
        return
    bc = [p.bc_tier for p in pos_players if p.bc_tier]
    if len(bc) >= 5:
        for p in pos_players:
            if p.bc_tier:
                p.tier = p.bc_tier
        rest = [p for p in pos_players if not p.bc_tier]
        _gap_tiers(rest, pos, w, start=max(bc) + 1)
        return
    _gap_tiers(pos_players, pos, w, start=1)


def build_rankings(players: list[Player], settings: LeagueSettings, w: ValueWeights | None = None) -> Rankings:
    w = w or ValueWeights()
    counts = starter_counts(settings, players)
    baselines = replacement_levels(players, counts, w)
    ranked = [RankedPlayer(**p.model_dump()) for p in players]
    for p in ranked:
        p.vorp = p.proj_points - baselines[p.position]
    # Rank-implied VORP: what a player at this ADP / expert rank is "worth" on the projection curve.
    by_vorp = sorted(ranked, key=lambda x: x.vorp, reverse=True)
    curve = [p.vorp for p in by_vorp]
    proj_rank = {p.player_id: i for i, p in enumerate(by_vorp, start=1)}
    for p in ranked:
        p.adp_vorp = _interp(curve, p.adp) if p.adp else p.vorp
        p.fp_vorp = _interp(curve, float(p.fp_rank)) if p.fp_rank else p.vorp
        parts = [(w.w_proj, p.vorp)]
        if p.adp:
            parts.append((w.w_adp, p.adp_vorp))
        if p.fp_rank:
            parts.append((w.w_fp, p.fp_vorp))
        total = sum(wt for wt, _ in parts) or 1.0
        p.value = sum(wt * v for wt, v in parts) / total
        p.adp_round = adp_round(p.adp, settings.team_count)
        p.consensus_gap = float(p.fp_rank - proj_rank[p.player_id]) if p.fp_rank else None
    ranked.sort(key=lambda x: (x.value, x.proj_points), reverse=True)
    by_pos: dict[str, list[RankedPlayer]] = {pos: [] for pos in POSITIONS}
    for i, p in enumerate(ranked, start=1):
        p.overall_rank = i
        p.value_round = value_round(i, settings.team_count)
        by_pos[p.position].append(p)
        p.pos_rank = len(by_pos[p.position])
    for pos, lst in by_pos.items():
        assign_tiers(lst, pos, w)
    return Rankings(overall=ranked, by_pos=by_pos, baselines=baselines, starter_counts=counts)


def pick_curve(rankings: Rankings, total_picks: int) -> list[float]:
    """Expected best-available value at overall pick k (1-based): mean value of the
    players whose ADP-ordered rank is in [k, k+2]. Players without ADP go by value rank."""
    with_adp = sorted((p for p in rankings.overall if p.adp), key=lambda p: p.adp or 0)
    without = [p for p in rankings.overall if not p.adp]
    ordered = with_adp + without
    vals = [p.value for p in ordered]
    curve: list[float] = []
    for k in range(total_picks):
        window = vals[k : k + 3]
        curve.append(mean(window) if window else (vals[-1] if vals else 0.0))
    return curve


def players_at_pick(rankings: Rankings, pick: int, n: int = 2) -> list[str]:
    """Names of players typically still available at overall pick `pick` (ADP order, projection-value fallback)."""
    with_adp = sorted((p for p in rankings.overall if p.adp), key=lambda p: p.adp or 0)
    without = [p for p in rankings.overall if not p.adp]
    ordered = with_adp + without
    k = max(0, min(len(ordered) - 1, pick - 1))
    return [p.name for p in ordered[k : k + n]]
