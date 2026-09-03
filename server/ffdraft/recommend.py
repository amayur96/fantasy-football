"""Best-available recommendations adjusted for roster need, tier cliffs, and wait risk."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .draft import DraftBoard, open_slots
from .models import POSITIONS, LeagueSettings, Position, RankedPlayer, Recommendation
from .value import FLEX_MAP, Rankings


@dataclass
class RecommendWeights:
    need_starter: float = 1.0
    need_flex: float = 0.9
    need_bench: float = 0.7
    need_saturated: float = 0.35
    backup_qb_te: float = 0.45
    kdst_early_mult: float = 0.05
    kdst_last_rounds: int = 3
    # Extra bodies to carry beyond the starters this league actually uses.
    depth_beyond_starters: dict[str, int] = field(default_factory=lambda: {"RB": 2, "WR": 2, "QB": 1, "TE": 1, "K": 0, "D/ST": 0})
    cliff_weight: float = 0.8
    cliff_sigma_picks: float = 1.0
    wait_weight: float = 0.3
    wait_sigma: float = 5.0
    injury_mult: dict[str, float] = field(
        default_factory=lambda: {"OUT": 0.3, "INJURY_RESERVE": 0.2, "IR": 0.2, "SUSPENSION": 0.5, "DOUBTFUL": 0.7, "QUESTIONABLE": 0.95}
    )
    top_n: int = 10


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def team_open_slots(board: DraftBoard, rankings: Rankings, settings: LeagueSettings) -> dict[int, dict[str, int]]:
    """Starter slots each team still has to fill, from what they have drafted so far."""
    rosters: dict[int, list[str]] = {t.team_id: [] for t in settings.teams}
    for pick in board.picks:
        if pick.player_id is None:
            continue
        p = rankings.by_id.get(pick.player_id)
        if p is not None and pick.owner_team_id in rosters:
            rosters[pick.owner_team_id].append(p.position)
    return {tid: open_slots(pos_list, settings.roster_slots) for tid, pos_list in rosters.items()}


def _fills(pos: str, slots: dict[str, int]) -> bool:
    """Can this position fill any starter slot this team still has open?"""
    if slots.get(pos, 0) > 0:
        return True
    return any(n > 0 and pos in FLEX_MAP.get(slot, []) for slot, n in slots.items())


@dataclass
class MarketContext:
    """What everyone else is doing, so a pick can be argued against the room."""
    run: dict[str, int] = field(default_factory=dict)  # positions taken in the last 10 picks
    run_window: int = 0
    rivals_needing: dict[str, int] = field(default_factory=dict)  # other teams still missing a starter there
    before_me: int = 0  # picks between now and my next turn
    rivals_before_me_needing: dict[str, int] = field(default_factory=dict)
    total_rivals: int = 0


def market_context(board: DraftBoard, rankings: Rankings, settings: LeagueSettings) -> MarketContext:
    me = settings.my_team_id
    slots_by_team = team_open_slots(board, rankings, settings)
    filled = [p for p in board.picks if p.player_id is not None and not p.is_keeper]
    filled.sort(key=lambda p: p.overall)
    window = filled[-10:]
    run: dict[str, int] = {}
    for pick in window:
        pos = rankings.by_id[pick.player_id].position if pick.player_id in rankings.by_id else None
        if pos:
            run[pos] = run.get(pos, 0) + 1
    nxt = board.my_next_pick()
    upcoming = [p for p in board.picks if p.player_id is None and not p.unknown and (nxt is None or p.overall < nxt.overall)]
    rivals_needing: dict[str, int] = {}
    before_needing: dict[str, int] = {}
    upcoming_teams = {p.owner_team_id for p in upcoming if p.owner_team_id != me}
    for pos in POSITIONS:
        rivals_needing[pos] = sum(1 for tid, sl in slots_by_team.items() if tid != me and _fills(pos, sl))
        before_needing[pos] = sum(1 for tid in upcoming_teams if _fills(pos, slots_by_team.get(tid, {})))
    return MarketContext(
        run=run, run_window=len(window), rivals_needing=rivals_needing, before_me=len(upcoming),
        rivals_before_me_needing=before_needing, total_rivals=len(settings.teams) - 1,
    )


def bench_targets(settings: LeagueSettings, w: RecommendWeights) -> dict[str, int]:
    """How many of each position to end up with, derived from this league's starting slots.

    A superflex league that starts two quarterbacks should want three, not one.
    """
    out: dict[str, int] = {}
    for pos in POSITIONS:
        starters = settings.roster_slots.get(pos, 0)
        out[pos] = starters + w.depth_beyond_starters.get(pos, 0)
    return out


def _need(p: RankedPlayer, slots: dict[str, int], counts: dict[str, int], rounds_left: int, settings: LeagueSettings, w: RecommendWeights, targets: dict[str, int] | None = None) -> tuple[float, str]:
    pos = p.position
    if pos in ("K", "D/ST"):
        if rounds_left > w.kdst_last_rounds:
            return w.kdst_early_mult, f"Kickers/defenses: wait until the last {w.kdst_last_rounds} rounds"
        if slots.get(pos, 0) > 0:
            return w.need_starter, f"Fills your open {pos} slot"
        return w.need_saturated, f"You already have a {pos}"
    if slots.get(pos, 0) > 0:
        n_slots = settings.roster_slots.get(pos, 0)
        idx = n_slots - slots[pos] + 1
        return w.need_starter, f"Fills your open {pos}{idx if n_slots > 1 else ''} slot"
    for slot, eligible in FLEX_MAP.items():
        if slots.get(slot, 0) > 0 and pos in eligible:
            return w.need_flex, f"Fills your open {slot} slot"
    if pos in ("QB", "TE") and settings.roster_slots.get(pos, 0) == 1:
        return w.backup_qb_te, f"Backup {pos} only (your starter is set)"
    have, target = counts.get(pos, 0), (targets or bench_targets(settings, w)).get(pos, 0)
    if have < target:
        return w.need_bench, f"Adds {pos} depth (you have {have}, target {target})"
    return w.need_saturated, f"You're set at {pos}; this is value-only"


def recommend(board: DraftBoard, rankings: Rankings, settings: LeagueSettings, w: RecommendWeights | None = None) -> list[Recommendation]:
    w = w or RecommendWeights()
    taken = board.taken_ids()
    my_ids = board.my_roster_ids()
    my_players = [rankings.by_id[i] for i in my_ids if i in rankings.by_id]
    slots = open_slots([p.position for p in my_players], settings.roster_slots)
    counts: dict[str, int] = {pos: 0 for pos in POSITIONS}
    for p in my_players:
        counts[p.position] += 1
    clock = board.next_open()
    current_round = clock.round if clock else settings.rounds
    rounds_left = settings.rounds - current_round + 1
    nxt = board.my_next_pick()
    n_until = board.picks_until_my_turn() or 0
    available = [p for p in rankings.overall if p.player_id not in taken]
    # positional share of the next 2n picks by ADP
    horizon = sorted((p for p in available if p.adp), key=lambda p: p.adp or 0)[: max(2 * n_until, 1)]
    share: dict[str, float] = {pos: 0.0 for pos in POSITIONS}
    for p in horizon:
        share[p.position] += 1.0 / len(horizon)
    avail_by_pos: dict[str, list[RankedPlayer]] = {pos: [] for pos in POSITIONS}
    for p in available:
        avail_by_pos[p.position].append(p)

    targets = bench_targets(settings, w)
    market = market_context(board, rankings, settings)
    have_summary = ", ".join(f"{n} {pos}" for pos, n in counts.items() if n) or "nothing yet"
    out: list[Recommendation] = []
    for p in available[:120]:
        need_mult, need_txt = _need(p, slots, counts, rounds_left, settings, w, targets)
        same_pos = avail_by_pos[p.position]
        remaining_tier = sum(1 for q in same_pos if q.tier <= p.tier)
        expected_taken = n_until * share.get(p.position, 0.0)
        next_tier = [q for q in same_pos if q.tier > p.tier]
        next_top = next_tier[0].value if next_tier else 0.0
        cliff = 0.0
        if nxt is not None and remaining_tier <= expected_taken + w.cliff_sigma_picks:
            cliff = w.cliff_weight * max(0.0, p.value - next_top)
            cliff_txt = f"Last of {p.position} tier {p.tier} ({remaining_tier} left, ~{expected_taken:.0f} {p.position}s likely go before your pick #{nxt.overall})"
        else:
            cliff_txt = f"Tier {p.tier} still has {remaining_tier} {p.position}s, no rush" if nxt is not None else ""
        if p.adp and nxt is not None:
            p_avail = _sigmoid((p.adp - nxt.overall) / w.wait_sigma)
            wait_txt = f"ADP #{p.adp:.0f}, " + ("likely still there next turn, could wait" if p_avail > 0.6 else "probably gone by your next turn")
        else:
            p_avail, wait_txt = 0.0, ""
        wait_discount = 1 - w.wait_weight * p_avail
        inj = w.injury_mult.get((p.injury_status or "").upper(), 1.0)
        score = (p.value * need_mult + cliff) * wait_discount * inj
        src_bits = []
        if p.adp:
            src_bits.append(f"ESPN ADP #{p.adp:.0f}")
        elif p.espn_rank:
            src_bits.append(f"ESPN #{p.espn_rank}")
        if p.fp_rank:
            src_bits.append(f"FantasyPros #{p.fp_rank}" + (f" ({p.fp_pos_rank})" if p.fp_pos_rank else ""))
        if p.bc_tier:
            src_bits.append(f"Boris Chen tier {p.bc_tier}")
        sources = " · ".join(src_bits)

        why = [need_txt]
        if cliff > 0 and cliff_txt:
            why.append(cliff_txt)
        why.append(f"Projected {p.proj_points:.0f} pts, {p.vorp:+.0f} over a replacement {p.position}")
        if p.adp and p.fp_rank:
            gap = p.adp - p.fp_rank
            if gap >= 12:
                why.append(f"Drafters let him fall to #{p.adp:.0f} while experts rank him #{p.fp_rank}, so he is going later than he should")
            elif gap <= -12:
                why.append(f"He goes at #{p.adp:.0f} but experts have him #{p.fp_rank}, so taking him here is paying above the expert price")
        if wait_txt:
            why.append(wait_txt)
        if inj < 1.0:
            why.append(f"Listed {p.injury_status}, which discounts his projection here")
        clauses = [need_txt, cliff_txt, f"Projected {p.proj_points:.0f} pts, {p.vorp:+.0f} over replacement", wait_txt]
        if inj < 1.0:
            clauses.append(f"Listed {p.injury_status}")
        reason = ". ".join(c for c in clauses if c) + "."
        # Why this fits the roster I have already built.
        pos_have = counts.get(p.position, 0)
        if slots.get(p.position, 0) > 0 or any(slots.get(sl, 0) > 0 and p.position in el for sl, el in FLEX_MAP.items()):
            team_txt = (
                f"You have {have_summary} and still need to fill {need_txt.replace('Fills your open ', '').replace(' slot', '')}. "
                f"Taking him now means the rest of your draft is free to chase value instead of filling holes."
            )
        elif pos_have < targets.get(p.position, 0):
            team_txt = (
                f"Your starters are set at {p.position} but you only carry {pos_have}; a {p.position} injury or bye would cost you a week. "
                f"He is depth that can start when it happens."
            )
        else:
            team_txt = (
                f"You already carry {pos_have} {p.position}s, more than the {targets.get(p.position, 0)} this roster needs, "
                f"so he is a pure value pick or trade bait rather than a need."
            )

        # Why it fits what the rest of the room is doing.
        run_n = market.run.get(p.position, 0)
        rivals = market.rivals_needing.get(p.position, 0)
        before = market.rivals_before_me_needing.get(p.position, 0)
        bits: list[str] = []
        if market.run_window and run_n:
            bits.append(f"{run_n} of the last {market.run_window} picks were {p.position}s")
        if rivals:
            bits.append(f"{rivals} of {market.total_rivals} rivals still need a starting {p.position}")
        if nxt is not None and before:
            bits.append(f"{before} of the {market.before_me} teams picking before your #{nxt.overall} still need one")
        if bits:
            pressure = before >= 3 or run_n >= 4
            market_txt = ". ".join(bits) + (
                ", so this position is thinning fast and waiting is a real risk."
                if pressure
                else ", so there is no rush at this position; you can take the best player instead."
            )
        else:
            market_txt = f"Nobody else is short at {p.position}, so you are competing with no one for him."

        out.append(Recommendation(
            player=p, score=score, reason=reason, fit=need_txt, sources=sources, why=[b for b in why if b],
            strategy_team=team_txt, strategy_market=market_txt,
            components={"need_mult": need_mult, "cliff_bonus": cliff, "wait_discount": wait_discount, "injury_mult": inj, "p_avail_next": p_avail},
        ))
    out.sort(key=lambda r: r.score, reverse=True)
    return out


def top(recs: list[Recommendation], n: int = 10) -> list[Recommendation]:
    return recs[:n]


def best_by_position(recs: list[Recommendation]) -> dict[str, Recommendation]:
    out: dict[str, Recommendation] = {}
    for r in recs:
        out.setdefault(r.player.position, r)
    return out


def roster_needs(board: DraftBoard, rankings: Rankings, settings: LeagueSettings, w: RecommendWeights | None = None) -> dict[str, object]:
    """What the roster is still missing, in the same terms the recommendations use."""
    w = w or RecommendWeights()
    my = [rankings.by_id[i] for i in board.my_roster_ids() if i in rankings.by_id]
    slots = open_slots([p.position for p in my], settings.roster_slots)
    counts: dict[str, int] = {pos: 0 for pos in POSITIONS}
    for p in my:
        counts[p.position] += 1
    unfilled = [slot for slot, n in slots.items() if n > 0 and slot not in ("BE", "IR") for _ in range(n)]
    targets = bench_targets(settings, w)
    thin = [pos for pos, target in targets.items() if target and counts.get(pos, 0) < target and pos not in ("K", "D/ST")]
    m = market_context(board, rankings, settings)
    return {
        "market": {
            "run": m.run, "run_window": m.run_window, "rivals_needing": m.rivals_needing,
            "before_me": m.before_me, "rivals_before_me_needing": m.rivals_before_me_needing, "total_rivals": m.total_rivals,
        },
        "open_slots": {k: v for k, v in slots.items() if v > 0},
        "unfilled_starters": unfilled,
        "roster_counts": counts,
        "thin_positions": thin,
        "roster_size": len(my),
    }
