"""Waiver-wire engine: who to add, who to drop, and why, from every source that loaded.

Pure. Takes WaiverPlayers that context.waiver_view() has already joined the sources onto, plus the
set of sources that actually loaded, so a missing source shows up as an absent component (weights
renormalise) rather than as a zero that quietly drags a player down.

Free agents and bench players are scored with the same function on the same 0-100 scale, so
"add X, drop Y" means X's number beats Y's by a margin, not that X looks good in isolation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from statistics import median
from typing import Any

from .lineup import INJURY_MULT, ORDINAL, POS_WORD, ZERO_STATUS, _names, _sentence  # noqa: F401
from .models import DropCandidate, LeagueSettings, WaiverLink, WaiverPick, WaiverPlayer, WaiverTier, WaiverView
from .value import FLEX_MAP

SOURCE_FP_ROS = "fp_ros"
SOURCE_FP_WAIVER = "fp_waiver"
SOURCE_SLEEPER = "sleeper"
SOURCE_ROTOWIRE = "rotowire"
SOURCE_SNAPS = "snaps"
FLEX_GROUP = ("RB", "WR", "TE")


@dataclass
class WaiverWeights:
    w_ros: float = 0.30  # FantasyPros rest-of-season consensus
    w_espn: float = 0.20  # ESPN season projection, relative to the position's pool
    w_fp_waiver: float = 0.15  # FantasyPros' weekly waiver panel
    w_momentum: float = 0.15  # Sleeper adds/drops, Rotowire add/drop %, ESPN roster-share change
    w_usage: float = 0.20  # touches or attempts per game, trend, snap share
    pos_depth: dict[str, int] = field(default_factory=lambda: {"QB": 36, "RB": 50, "WR": 60, "TE": 24, "D/ST": 16})  # ROS position rank worth ~0 (fallback)
    overall_depth: float = 1.25  # overall ROS rank worth ~0, as a multiple of the league's rostered-player count
    opp_norm: dict[str, float] = field(default_factory=lambda: {"QB": 32.0, "RB": 16.0, "WR": 9.0, "TE": 7.0})  # a full workload per game
    snap_norm: float = 0.75
    injury_mult: dict[str, float] = field(default_factory=lambda: {"OUT": 0.35, "IR": 0.25, "INJURY_RESERVE": 0.25, "SUSPENSION": 0.35, "DOUBTFUL": 0.6, "QUESTIONABLE": 0.9})
    dnp_mult: float = 0.85  # did not practice
    dst_mult: float = 0.7  # defenses are streamed, not built around
    need_more: float = 1.15  # roster is short at the position
    need_surplus: float = 0.9  # roster already carries more than it wants
    claim_min: float = 55.0  # a claim on his own merits (open spot)
    claim_delta: float = 15.0  # or: beats the drop by this much
    stash_min: float = 40.0
    watch_min: float = 30.0
    drop_margin: float = 8.0  # the add must beat the drop by this many points
    flex_share: dict[str, float] = field(default_factory=lambda: {"RB": 0.5, "WR": 0.5, "TE": 0.2})  # how much of a flex slot a position usually fills
    max_picks: int = 25
    per_pos_min: int = 3  # keep at least this many qualified picks per position in view


# ---- roster shape ------------------------------------------------------------------------

def position_targets(settings: LeagueSettings, w: WaiverWeights | None = None) -> dict[str, int]:
    """How many healthy players of each position the roster wants: dedicated starters, the share of
    each flex slot the position usually fills, and one backup at QB/RB/WR (the positions that get
    hurt and rotate). Tight ends rarely fill a flex, so they get a small share and no backup."""
    w = w or WaiverWeights()
    want: dict[str, float] = {}
    for slot, n in settings.roster_slots.items():
        if slot in ("BE", "IR", "K") or n <= 0:
            continue
        if slot in FLEX_MAP:
            for pos in FLEX_MAP[slot]:
                want[pos] = want.get(pos, 0.0) + n * w.flex_share.get(pos, 0.5)
        else:
            want[slot] = want.get(slot, 0.0) + n
    return {pos: math.ceil(v - 1e-9) + (1 if pos in ("QB", "RB", "WR") else 0) for pos, v in want.items() if v > 0}


def starter_slots(settings: LeagueSettings, pos: str) -> int:
    return int(settings.roster_slots.get(pos, 0))


def _healthy(p: WaiverPlayer) -> bool:
    st = (p.injury_status or p.sleeper_injury or "").upper()
    return p.slot != "IR" and st not in ZERO_STATUS


def roster_need(roster: list[WaiverPlayer]) -> dict[str, int]:
    have: dict[str, int] = {}
    for p in roster:
        if _healthy(p):
            have[p.position] = have.get(p.position, 0) + 1
    return have


# ---- scoring ---------------------------------------------------------------------------

def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _rank_num(pos_rank: str | None) -> int | None:
    if not pos_rank:
        return None
    digits = "".join(ch for ch in pos_rank if ch.isdigit())
    return int(digits) if digits else None


def _proj_group(pos: str) -> str:
    """RB/WR/TE compete for the same flex slots, so their projections are compared on one scale."""
    return "FLEX" if pos in FLEX_GROUP else pos


def pool_stats(players: list[WaiverPlayer], settings: LeagueSettings | None = None) -> dict[str, Any]:
    """Projection spread per group plus the trending maxima, so components can be normalised."""
    by_group: dict[str, list[float]] = {}
    for p in players:
        if p.season_proj:
            by_group.setdefault(_proj_group(p.position), []).append(float(p.season_proj))
    proj = {g: (median(v), max(v)) for g, v in by_group.items()}
    rostered = settings.team_count * sum(n for s, n in settings.roster_slots.items() if s != "IR") if settings else 170
    return {
        "proj": proj,
        "rostered": rostered,
        "two_qb": bool(settings and starter_slots(settings, "QB") >= 2),
        "max_adds": max((p.sleeper_adds or 0 for p in players), default=0),
        "max_drops": max((p.sleeper_drops or 0 for p in players), default=0),
        "max_rw_add": max((p.rw_add_pct or 0 for p in players), default=0.0),
        "max_rw_drop": max((p.rw_drop_pct or 0 for p in players), default=0.0),
        "waiver_len": max((p.fp_waiver_rank or 0 for p in players), default=0),
    }


def _opps(p: WaiverPlayer) -> list[float]:
    """Opportunities per played week: attempts for a QB, targets plus carries for everyone else."""
    out = []
    for u in p.usage:
        if p.position == "QB":
            out.append(float(u.pass_att or 0) + float(u.carries or 0))
        else:
            out.append(float(u.targets or 0) + float(u.carries or 0))
    return out


def components(p: WaiverPlayer, stats: dict[str, Any], loaded: set[str], w: WaiverWeights) -> tuple[dict[str, float], list[str]]:
    comp: dict[str, float] = {}
    missing: list[str] = []
    # rest of season: the overall consensus is the cross-position truth, scaled to how deep this
    # league rosters; the position rank is the fallback, and for a 2-QB league's quarterbacks (whom
    # a 1-QB list under-ranks) whichever of the two is kinder.
    if SOURCE_FP_ROS in loaded:
        overall = _clamp(1 - (p.ros_rank - 1) / (w.overall_depth * stats["rostered"])) if p.ros_rank else None
        n = _rank_num(p.ros_pos_rank)
        by_pos = _clamp(1 - (n - 1) / w.pos_depth.get(p.position, 40)) if n else None
        if overall is not None and by_pos is not None and p.position == "QB" and stats.get("two_qb"):
            comp["ros"] = max(overall, by_pos)
        elif p.position == "D/ST" and by_pos is not None:
            comp["ros"] = by_pos  # defenses are streamed against each other; their overall rank says little
        else:
            comp["ros"] = overall if overall is not None else (by_pos if by_pos is not None else 0.0)
    else:
        missing.append("ros")
    # espn projection relative to the pool of players competing for the same slots
    group = _proj_group(p.position)
    if p.season_proj and group in stats["proj"]:
        med, mx = stats["proj"][group]
        comp["espn"] = _clamp((p.season_proj - med) / (mx - med)) if mx > med else (1.0 if p.season_proj >= med else 0.0)
    else:
        missing.append("espn")
    # waiver panel: only free agents can be on it, so for a rostered player it is absent, not zero,
    # otherwise every drop candidate would start 15 points behind every add
    if SOURCE_FP_WAIVER not in loaded:
        missing.append("fp_waiver")
    elif p.on_my_team and not p.fp_waiver_rank:
        pass
    else:
        n = stats.get("waiver_len") or 0
        comp["fp_waiver"] = _clamp(1 - (p.fp_waiver_rank - 1) / n) if p.fp_waiver_rank and n else 0.0
    # momentum: each part in [-1, 1]
    parts: list[float] = []
    if SOURCE_SLEEPER in loaded and (stats["max_adds"] or stats["max_drops"]):
        up = math.log1p(p.sleeper_adds or 0) / math.log1p(stats["max_adds"]) if stats["max_adds"] else 0.0
        down = math.log1p(p.sleeper_drops or 0) / math.log1p(stats["max_drops"]) if stats["max_drops"] else 0.0
        parts.append(up - down)
    if SOURCE_ROTOWIRE in loaded and (stats["max_rw_add"] or stats["max_rw_drop"]):
        up = (p.rw_add_pct or 0) / stats["max_rw_add"] if stats["max_rw_add"] else 0.0
        down = (p.rw_drop_pct or 0) / stats["max_rw_drop"] if stats["max_rw_drop"] else 0.0
        parts.append(_clamp(up - down, -1, 1))
    if p.percent_change is not None:
        parts.append(_clamp(p.percent_change / 20.0, -1, 1))
    if parts:
        comp["momentum"] = (sum(parts) / len(parts) + 1) / 2
    else:
        missing.append("momentum")
    # usage
    if p.position == "D/ST":
        pass  # a defense's usage is its schedule, which the ROS and weekly ranks already carry
    else:
        uparts: list[float] = []
        opps = _opps(p)
        norm = w.opp_norm.get(p.position, 10.0)
        if opps:
            uparts.append(_clamp(sum(opps) / len(opps) / norm))
            if len(opps) >= 2:
                prior = sum(opps[:-1]) / (len(opps) - 1)
                diff = opps[-1] - prior
                uparts.append(1.0 if diff > 0.1 * norm else 0.0 if diff < -0.1 * norm else 0.5)
        if p.snap_pct is not None:
            uparts.append(_clamp(p.snap_pct / w.snap_norm))
        if uparts:
            comp["usage"] = sum(uparts) / len(uparts)
        else:
            missing.append("usage")
    return comp, missing


def health_mult(p: WaiverPlayer, w: WaiverWeights) -> float:
    st = (p.injury_status or p.sleeper_injury or "").upper()
    m = w.injury_mult.get(st, 1.0)
    if (p.sleeper_practice or "").upper() == "DNP":
        m *= w.dnp_mult
    return m


def need_mult(pos: str, have: dict[str, int], want: dict[str, int], w: WaiverWeights) -> float:
    target = want.get(pos)
    if target is None:
        return 1.0
    h = have.get(pos, 0)
    if h < target:
        return w.need_more
    if h > target:
        return w.need_surplus
    return 1.0


def add_score(p: WaiverPlayer, stats: dict[str, Any], loaded: set[str], have: dict[str, int], want: dict[str, int], w: WaiverWeights) -> tuple[float, float]:
    """Returns (score, score before the health multiplier). Stores components/missing on the player."""
    comp, missing = components(p, stats, loaded, w)
    weights = {"ros": w.w_ros, "espn": w.w_espn, "fp_waiver": w.w_fp_waiver, "momentum": w.w_momentum, "usage": w.w_usage}
    total = sum(weights[k] for k in comp)
    base = 100.0 * sum(weights[k] * v for k, v in comp.items()) / total if total else 0.0
    base *= need_mult(p.position, have, want, w)
    if p.position == "D/ST":
        base *= w.dst_mult
    p.components, p.missing = comp, missing
    score = base * health_mult(p, w)
    p.add_score = round(score, 1)
    return score, base


def tier_of(score: float, pre_health: float, hm: float, w: WaiverWeights, delta: float | None = None) -> WaiverTier | None:
    """`delta` is the margin over the chosen drop (None when there is no drop). A claim is either a
    clear upgrade on someone you would cut, or a strong player on his own merits."""
    if score >= w.watch_min and delta is not None and delta >= w.claim_delta:
        return "claim"
    if score >= w.claim_min:
        return "claim"
    if score >= w.stash_min or (pre_health >= w.claim_min and hm < 0.7):
        return "stash"
    if score >= w.watch_min:
        return "watch"
    return None


# ---- drops -----------------------------------------------------------------------------

def drop_candidates(roster: list[WaiverPlayer]) -> list[WaiverPlayer]:
    """Bench players who could be cut, most droppable first. Starters, IR, the keeper and the only defense stay."""
    dst_count = sum(1 for p in roster if p.position == "D/ST")
    out = [p for p in roster if p.slot in ("BE", "") and not p.protected and p.position != "K" and not (p.position == "D/ST" and dst_count <= 1)]
    return sorted(out, key=lambda p: p.add_score)


def stream_candidates(roster: list[WaiverPlayer]) -> list[WaiverPlayer]:
    """Defenses are streamed, so a D/ST add may replace the one you start, not a skill player."""
    return sorted((p for p in roster if p.position == "D/ST" and not p.protected and p.slot != "IR"), key=lambda p: p.add_score)


def choose_drop(fa: WaiverPlayer, cands: list[WaiverPlayer], roster: list[WaiverPlayer], settings: LeagueSettings, used: set[int], w: WaiverWeights) -> WaiverPlayer | None:
    """The weakest bench player the add can replace: same position preferred, never leaving fewer
    players at a position than it has starting slots (a 2-QB league keeps its QB2), by a clear margin."""
    counts: dict[str, int] = {}
    for p in roster:
        if p.slot != "IR":
            counts[p.position] = counts.get(p.position, 0) + 1

    def allowed(c: WaiverPlayer) -> bool:
        if c.player_id in used:
            return False
        if c.position == fa.position:
            return True
        if "D/ST" in (c.position, fa.position):
            return False  # a defense only ever swaps for a defense
        return counts.get(c.position, 0) - 1 >= starter_slots(settings, c.position)

    ranked = sorted((c for c in cands if allowed(c)), key=lambda c: c.add_score + (0.0 if c.position == fa.position else 5.0))
    for c in ranked:
        if fa.add_score >= c.add_score + w.drop_margin:
            return c
    return None


# ---- prose -----------------------------------------------------------------------------

POS_ONE = {"QB": "quarterback", "RB": "running back", "WR": "receiver", "TE": "tight end", "D/ST": "defense", "K": "kicker"}


def _trim_note(note: str, limit: int = 240) -> str:
    if len(note) <= limit:
        return note
    cut = note[:limit]
    for mark in (". ", "; "):
        i = cut.rfind(mark)
        if i > limit // 2:
            return cut[: i + 1]
    return cut.rstrip() + "…"


def _usage_bits(p: WaiverPlayer) -> tuple[str, int]:
    """('31 targets and 12 carries in his last 3 games (14.3 touches a game)', games) or ('', 0)."""
    if not p.usage or p.position == "D/ST":
        return "", 0
    n = len(p.usage)
    games = f"his last {n} games" if n > 1 else "his last game"
    if p.position == "QB":
        att = sum(u.pass_att or 0 for u in p.usage)
        return f"{att} pass attempts in {games} ({att / n:.0f} a game)", n
    tg = sum(u.targets or 0 for u in p.usage)
    ca = sum(u.carries or 0 for u in p.usage)
    parts = []
    if tg or p.position != "RB":
        parts.append(f"{tg} targets")
    if ca or p.position == "RB":
        parts.append(f"{ca} {'carry' if ca == 1 else 'carries'}")
    return f"{' and '.join(parts)} in {games} ({(tg + ca) / n:.1f} touches a game)", n


def _trend_word(p: WaiverPlayer, w: WaiverWeights) -> str:
    opps = _opps(p)
    if len(opps) < 2:
        return ""
    prior = sum(opps[:-1]) / (len(opps) - 1)
    norm = w.opp_norm.get(p.position, 10.0)
    diff = opps[-1] - prior
    if diff > 0.1 * norm:
        return f"rising ({opps[-1]:.0f} last week against {prior:.0f} before)"
    if diff < -0.1 * norm:
        return f"falling ({opps[-1]:.0f} last week against {prior:.0f} before)"
    return "steady week to week"


def _momentum_sentence(p: WaiverPlayer, who: str) -> str:
    bits = []
    if p.sleeper_adds:
        bits.append(f"added {p.sleeper_adds:,} times on Sleeper in the last two days")
    if p.rw_add_pct:
        bits.append(f"up {p.rw_add_pct:.0f}% rostered on MyFantasyLeague this week per Rotowire")
    if p.percent_change is not None and p.percent_change >= 1 and p.percent_owned is not None:
        bits.append(f"ESPN roster share up {p.percent_change:.0f}% to {p.percent_owned:.0f}%")
    if not bits:
        if p.percent_change is not None and p.percent_change <= -1 and p.percent_owned is not None:
            return _sentence(f"{who}'s ESPN roster share has slipped {abs(p.percent_change):.0f}% to {p.percent_owned:.0f}%, so managers elsewhere are losing patience")
        return ""
    text = f"Managers are moving on {who}: {'; '.join(bits)}"
    if p.sleeper_drops and p.sleeper_adds and p.sleeper_drops > p.sleeper_adds:
        text += f", although {p.sleeper_drops:,} Sleeper managers dropped him in the same window"
    return _sentence(text)


def _health_sentence(p: WaiverPlayer, who: str) -> str:
    espn = (p.injury_status or "").upper()
    sl = (p.sleeper_injury or "").upper()
    if not espn and not sl and not p.rw_injury:
        return ""
    bits = []
    if espn:
        bits.append(f"ESPN lists {who} {espn.replace('_', ' ').lower()}")
    if sl:
        part = f" ({p.sleeper_body_part.lower()})" if p.sleeper_body_part else ""
        bits.append(f"Sleeper has him {sl.lower()}{part}" if espn else f"Sleeper lists {who} {sl.lower()}{part}")
    if p.sleeper_practice:
        bits.append(f"practice: {p.sleeper_practice}")
    if p.rw_injury and p.rw_status:
        bits.append(f"Rotowire: {p.rw_injury}, {p.rw_status.lower()}")
    if p.sleeper_notes:
        bits.append(str(p.sleeper_notes)[:160])
    return _sentence("; ".join(bits))


def _fit_sentence(fa: WaiverPlayer, roster: list[WaiverPlayer], have: dict[str, int], want: dict[str, int], settings: LeagueSettings, week: int) -> str:
    pos = fa.position
    slots = starter_slots(settings, pos)
    word = POS_WORD.get(pos, pos)
    if pos == "D/ST":
        return ""
    h = have.get(pos, 0)
    text = f"your roster {'already ' if h > want.get(pos, h) else ''}carries {h} healthy {word} for {slots} dedicated starting slot{'s' if slots != 1 else ''}"
    if pos in FLEX_GROUP:
        flex = sum(n for s, n in settings.roster_slots.items() if s in FLEX_MAP and pos in FLEX_MAP[s])
        if flex:
            text += f" plus {flex} flex"
    if h > want.get(pos, h):
        text += ", more than it needs, so he would have to earn the spot from one of them"
    elif h < want.get(pos, 0):
        text += ", fewer than it wants"
    byes = [p for p in roster if p.position == pos and p.bye_week == week and p.slot != "IR"]
    if byes:
        text += f", and {', '.join(p.name for p in byes)} {'is' if len(byes) == 1 else 'are'} on bye this week"
    out = _sentence(text)
    if pos == "QB" and slots >= 2 and have.get("QB", 0) <= slots:
        out += " In a 2-QB league a third quarterback is a starter-in-waiting, not a luxury."
    return out


def _drop_sentence(drop: WaiverPlayer, b: str) -> str:
    bits = [f"{drop.ros_pos_rank} rest of season on FantasyPros" if drop.ros_pos_rank else "unranked rest of season on FantasyPros"]
    if drop.season_proj:
        bits.append(f"a {drop.season_proj:.0f}-point ESPN season projection")
    if drop.percent_started is not None:
        bits.append(f"started in {drop.percent_started:.0f}% of ESPN leagues")
    if drop.sleeper_drops:
        bits.append(f"dropped {drop.sleeper_drops:,} times on Sleeper")
    usage, _ = _usage_bits(drop)
    if usage:
        bits.append(usage)
    st = (drop.injury_status or drop.sleeper_injury or "").upper()
    if st:
        bits.append(f"listed {st.replace('_', ' ').lower()}")
    return _sentence(f"{drop.name} is the drop: {', '.join(bits)}")


def _availability_sentence(fa: WaiverPlayer, a: str) -> str:
    if fa.percent_owned is None:
        return ""
    owned = fa.percent_owned
    text = f"{a} is rostered in {owned:.0f}% of ESPN leagues"
    if (fa.waiver_status or "").upper() == "WAIVERS":
        text += " and sits on waivers rather than free agency"
    text += ", so expect competition for the claim" if owned >= 50 else ", so he should still be there when waivers run"
    return _sentence(text)


def _sources_used(fa: WaiverPlayer, drop: WaiverPlayer | None) -> list[str]:
    out = ["ESPN"]
    ps = [fa] + ([drop] if drop else [])
    if any(p.ros_pos_rank or p.fp_waiver_rank for p in ps):
        out.append("FantasyPros")
    if any(p.sleeper_adds or p.sleeper_drops or p.sleeper_injury or p.sleeper_practice for p in ps):
        out.append("Sleeper")
    if any(p.rw_add_pct or p.rw_drop_pct or p.rw_injury for p in ps):
        out.append("Rotowire")
    if any(p.snap_pct is not None for p in ps):
        out.append("nflverse")
    return out


def explain_pick(fa: WaiverPlayer, drop: WaiverPlayer | None, tier: WaiverTier, roster: list[WaiverPlayer], have: dict[str, int], settings: LeagueSettings, week: int,
                 faab: bool | None, faab_budget: int | None, w: WaiverWeights, open_spot: bool = False, want: dict[str, int] | None = None) -> str:
    want = want if want is not None else position_targets(settings, w)
    a, b = _names(fa, drop)
    pos = POS_ONE.get(fa.position, fa.position)
    hm = health_mult(fa, w)
    tail = f", with {drop.name} the drop" if drop else (" and there is an open roster spot for him" if open_spot else "")
    if tier == "claim":
        verdict = f"{fa.name} is a claim-now add at {pos}{tail}."
    elif tier == "stash":
        verdict = f"{fa.name} is a stash at {pos}{tail or ' if you can make room'}."
    else:
        verdict = f"{fa.name} is one to watch at {pos}{tail}."
    if fa.fp_faab:
        try:
            bid = int(fa.fp_faab.strip("$"))
        except ValueError:
            bid = None
        if faab and faab_budget and bid is not None:
            verdict += f" FantasyPros' waiver panel suggests a bid around {fa.fp_faab}, about {100 * bid / faab_budget:.0f}% of a ${faab_budget} budget."
        elif faab is False:
            verdict += f" FantasyPros' waiver panel would bid {fa.fp_faab} in FAAB leagues, so he is worth a priority claim rather than a free-agent add."
        else:
            verdict += f" FantasyPros' waiver panel suggests a bid around {fa.fp_faab} in FAAB leagues."
    # rest of season
    ros = ""
    same_pos = drop is not None and drop.position == fa.position
    if fa.ros_pos_rank:
        ros = f"rest of season, FantasyPros' experts have {a} {fa.ros_pos_rank}"
        if fa.ros_best and fa.ros_worst:
            ros += f" (overall range {fa.ros_best}-{fa.ros_worst})"
        if drop and same_pos and drop.ros_pos_rank:
            fa_n, drop_n = _rank_num(fa.ros_pos_rank) or 0, _rank_num(drop.ros_pos_rank) or 0
            ros += f", {'ahead of' if fa_n <= drop_n else 'behind'} {b} at {drop.ros_pos_rank}"
        elif drop and fa.ros_rank and drop.ros_rank:
            ros += f", {ORDINAL(fa.ros_rank)} overall {'against' if fa.ros_rank <= drop.ros_rank else 'behind'} {ORDINAL(drop.ros_rank)} for {b}"
        elif drop:
            ros += f", while {b} is unranked"
        if fa.position == "QB" and starter_slots(settings, "QB") >= 2:
            ros += ", on a 1-QB list, so quarterbacks run deeper in this league"
    if fa.season_proj:
        seg = f"ESPN's season projection is {fa.season_proj:.0f} points" + (f" against {drop.season_proj:.0f} for {b}" if drop and same_pos and drop.season_proj else "")
        ros = f"{ros}; {seg}" if ros else seg
    ros = _sentence(ros)
    # waiver panel
    panel = ""
    if fa.fp_waiver_rank:
        panel = f"FantasyPros' waiver panel has him #{fa.fp_waiver_rank} this week"
        if fa.fp_note:
            panel += f": “{_trim_note(fa.fp_note)}”"
        panel = _sentence(panel)
    # usage
    usage = ""
    ub, _ = _usage_bits(fa)
    if ub:
        usage = f"he has {ub}"
        if fa.snap_pct is not None:
            wk = max((u.week for u in fa.usage if u.snap_pct is not None), default=None)
            usage += f", playing {100 * fa.snap_pct:.0f}% of the snaps" + (f" in week {wk}" if wk else " most recently")
        tw = _trend_word(fa, w)
        if tw:
            usage += f", {tw}"
    elif fa.snap_pct is not None:
        usage = f"he played {100 * fa.snap_pct:.0f}% of the snaps most recently"
    usage = _sentence(usage)
    health = _health_sentence(fa, a)
    if health and tier == "stash" and hm < 0.7:
        health += " That makes him a stash, not a start."
    sentences = [
        verdict, ros, panel, usage, _momentum_sentence(fa, a), health,
        _fit_sentence(fa, roster, have, want, settings, week),
        _drop_sentence(drop, b) if drop else "",
        _availability_sentence(fa, a),
    ]
    return " ".join(x for x in sentences if x)


def explain_drop(p: WaiverPlayer) -> str:
    bits = [f"{p.ros_pos_rank} rest of season on FantasyPros" if p.ros_pos_rank else "unranked rest of season on FantasyPros"]
    if p.season_proj:
        bits.append(f"ESPN projects {p.season_proj:.0f} points for the season")
    if p.percent_started is not None:
        bits.append(f"started in {p.percent_started:.0f}% of ESPN leagues")
    if p.sleeper_drops:
        bits.append(f"dropped {p.sleeper_drops:,} times on Sleeper in two days")
    ub, _ = _usage_bits(p)
    if ub:
        bits.append(ub)
    st = (p.injury_status or p.sleeper_injury or "").upper()
    if st:
        bits.append(f"listed {st.replace('_', ' ').lower()}" + (f" ({p.sleeper_body_part.lower()})" if p.sleeper_body_part else ""))
    if p.bye_week:
        bits.append(f"bye in week {p.bye_week}")
    return _sentence(", ".join(bits))


def needs_sentences(roster: list[WaiverPlayer], have: dict[str, int], want: dict[str, int], settings: LeagueSettings, week: int) -> list[str]:
    out: list[str] = []
    for pos in ("QB", "RB", "WR", "TE", "D/ST"):
        target = want.get(pos)
        if not target:
            continue
        h = have.get(pos, 0)
        slots = starter_slots(settings, pos)
        word = POS_WORD.get(pos, pos)
        if h < slots:
            out.append(f"You are short at {POS_ONE.get(pos, pos)}: {h} healthy {word} for {slots} starting slot{'s' if slots != 1 else ''}.")
        elif h < target:
            out.append(f"{word.capitalize()} are thin: {h} healthy for {slots} starting slot{'s' if slots != 1 else ''}" + (" in a 2-QB league" if pos == "QB" and slots >= 2 else "") + ", so a pickup there is worth a bench spot.")
        elif h > target + 1:
            out.append(f"You carry {h} {word} against a target of {target}, so that is where a drop should come from.")
    for ahead in (0, 1):
        wk = week + ahead
        byes = [p for p in roster if p.bye_week == wk and p.slot not in ("BE", "IR", "")]
        if byes:
            out.append(f"{', '.join(p.name for p in byes)} {'is' if len(byes) == 1 else 'are'} on bye in week {wk}{' (this week)' if ahead == 0 else ' (next week)'}.")
    return out


# ---- assembly -------------------------------------------------------------------------

def unavailable(season: int, week: int, reason: str, fetched_at: datetime | None = None) -> WaiverView:
    return WaiverView(season=season, week=week, week_label=f"NFL Week {week}", fetched_at=fetched_at or datetime.now(), available=False, reason=reason)


def build_waiver_view(
    roster: list[WaiverPlayer], free_agents: list[WaiverPlayer], settings: LeagueSettings, *, season: int, week: int, fetched_at: datetime,
    loaded: set[str], keeper_id: int | None = None, links: list[WaiverLink] | None = None, sources: dict[str, str] | None = None,
    errors: list[str] | None = None, faab: bool | None = None, faab_budget: int | None = None, w: WaiverWeights | None = None,
) -> WaiverView:
    w = w or WaiverWeights()
    roster = [p for p in roster if p.position != "K"]
    fas = [p for p in free_agents if p.position != "K"]
    for p in roster:
        p.protected = keeper_id is not None and p.player_id == keeper_id
    have, want = roster_need(roster), position_targets(settings, w)
    stats = pool_stats(roster + fas, settings)
    for p in roster:
        add_score(p, stats, loaded, have, want, w)
    scored: list[tuple[WaiverPlayer, float, float]] = []
    for p in fas:
        score, pre = add_score(p, stats, loaded, have, want, w)
        scored.append((p, score, pre))
    scored.sort(key=lambda t: t[1], reverse=True)
    cands = drop_candidates(roster)
    streams = stream_candidates(roster)
    non_ir = sum(n for s, n in settings.roster_slots.items() if s != "IR")
    open_spots = max(0, non_ir - sum(1 for p in roster if p.slot != "IR"))
    used: set[int] = set()
    qualified: list[WaiverPick] = []
    for p, score, pre in scored:
        hm = health_mult(p, w)
        if tier_of(score, pre, hm, w) is None:
            continue
        drop = choose_drop(p, streams if p.position == "D/ST" else cands, roster, settings, used, w)
        tier = tier_of(score, pre, hm, w, delta=(score - drop.add_score) if drop else None) or "watch"
        open_spot = drop is None and open_spots > 0
        if drop is None and not open_spot and tier != "watch":
            # Nobody on the bench is clearly worse, so he does not improve this roster right now.
            tier = "stash" if tier == "claim" and pre >= w.claim_min else "watch"
        if drop is not None:
            used.add(drop.player_id)
        head = (f"Stream {p.name} over {drop.name}" if p.position == "D/ST" else f"Add {p.name}, drop {drop.name}") if drop else (f"Add {p.name} to the open spot" if open_spot else f"{'Stash' if tier == 'stash' else 'Watch'} {p.name}")
        why = explain_pick(p, drop, tier, roster, have, settings, week, faab, faab_budget, w, open_spot=open_spot, want=want)
        qualified.append(WaiverPick(tier=tier, player=p, drop=drop, delta=round(score - (drop.add_score if drop else 0.0), 1), headline=head, why=why, sources=_sources_used(p, drop)))
    picks = qualified[: w.max_picks]
    chosen = {pk.player.player_id for pk in picks}
    for pos in ("QB", "RB", "WR", "TE", "D/ST"):
        have_n = sum(1 for pk in picks if pk.player.position == pos)
        for pk in qualified:
            if have_n >= w.per_pos_min:
                break
            if pk.player.position == pos and pk.player.player_id not in chosen:
                picks.append(pk)
                chosen.add(pk.player.player_id)
                have_n += 1
    order = {"claim": 0, "stash": 1, "watch": 2}
    picks.sort(key=lambda pk: (order[pk.tier], -pk.player.add_score))
    drops = [DropCandidate(player=c, droppability=round(100 - c.add_score, 1), why=explain_drop(c)) for c in cands]
    return WaiverView(
        season=season, week=week, week_label=f"NFL Week {week}", fetched_at=fetched_at, faab=faab, faab_budget=faab_budget,
        picks=picks, drops=drops, needs=needs_sentences(roster, have, want, settings, week), links=links or [], sources=sources or {}, errors=errors or [],
    )
