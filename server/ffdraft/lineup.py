"""Weekly lineup optimiser and move recommendations with explanations."""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import LeagueSettings, LineupMove, Position, WeekPlayer
from .value import FLEX_MAP

ZERO_STATUS = {"OUT", "INJURY_RESERVE", "IR", "SUSPENSION"}
INJURY_MULT = {"DOUBTFUL": 0.4, "QUESTIONABLE": 0.9}
ORDINAL = lambda n: f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"  # noqa: E731


@dataclass
class LineupWeights:
    w_espn: float = 0.5
    w_fp: float = 0.5
    swap_threshold: float = 1.0  # projected points a swap must gain to be recommended
    waiver_margin: float = 0.15  # FA must beat the drop candidate's season projection by this fraction
    max_waivers: int = 3
    flex_order: list[str] = field(default_factory=lambda: ["WR/TE", "RB/WR", "RB/WR/TE", "FLEX", "OP"])


def weekly_score(p: WeekPlayer, w: LineupWeights | None = None) -> float:
    w = w or LineupWeights()
    if p.on_bye or (p.injury_status or "").upper() in ZERO_STATUS:
        return 0.0
    parts = []
    if p.espn_proj is not None:
        parts.append((w.w_espn, p.espn_proj))
    if p.fp_proj is not None:
        parts.append((w.w_fp, p.fp_proj))
    if not parts:
        return 0.0
    base = sum(wt * v for wt, v in parts) / sum(wt for wt, _ in parts)
    return base * INJURY_MULT.get((p.injury_status or "").upper(), 1.0)


def slot_keys(settings: LeagueSettings) -> list[str]:
    """Ordered starter slot keys like QB1, QB2, RB1, RB2, WR1, TE1, WR/TE1, RB/WR/TE1, RB/WR/TE2, D/ST1."""
    keys: list[str] = []
    for slot, n in settings.roster_slots.items():
        if slot in ("BE", "IR"):
            continue
        for i in range(1, n + 1):
            keys.append(f"{slot}{i}")
    return keys


def _slot_of(key: str) -> str:
    return key.rstrip("0123456789")


def eligible(p: WeekPlayer, slot: str) -> bool:
    if slot == p.position:
        return True
    return p.position in FLEX_MAP.get(slot, [])


def optimal_lineup(players: list[WeekPlayer], settings: LeagueSettings, w: LineupWeights | None = None) -> dict[str, int]:
    """Greedy: dedicated slots take the best remaining at that position, then flex slots from most to least restrictive."""
    w = w or LineupWeights()
    pool = sorted((p for p in players if p.slot != "IR"), key=lambda p: p.score, reverse=True)
    used: set[int] = set()
    out: dict[str, int] = {}
    keys = slot_keys(settings)
    dedicated = [k for k in keys if _slot_of(k) not in FLEX_MAP]
    flex = sorted([k for k in keys if _slot_of(k) in FLEX_MAP], key=lambda k: (len(FLEX_MAP[_slot_of(k)]), w.flex_order.index(_slot_of(k)) if _slot_of(k) in w.flex_order else 99))
    for key in dedicated + flex:
        slot = _slot_of(key)
        pick = next((p for p in pool if p.player_id not in used and eligible(p, slot)), None)
        if pick is not None:
            out[key] = pick.player_id
            used.add(pick.player_id)
    return out


def current_lineup(players: list[WeekPlayer], settings: LeagueSettings) -> dict[str, int]:
    """Map ESPN's current lineup slots onto slot keys."""
    out: dict[str, int] = {}
    counters: dict[str, int] = {}
    for p in sorted(players, key=lambda p: p.score, reverse=True):
        if p.slot in ("BE", "IR", "") or p.slot not in settings.roster_slots:
            continue
        counters[p.slot] = counters.get(p.slot, 0) + 1
        if counters[p.slot] <= settings.roster_slots[p.slot]:
            out[f"{p.slot}{counters[p.slot]}"] = p.player_id
    return out


SLOT_ORDER = ["QB", "RB", "WR", "WR/TE", "TE", "RB/WR", "RB/WR/TE", "FLEX", "OP", "D/ST", "K", "BE", "IR"]
SLOT_LABEL = {"RB/WR/TE": "FLEX", "RB/WR": "FLEX", "OP": "OP", "WR/TE": "WR/TE", "BE": "Bench"}
POS_WORD = {"QB": "quarterbacks", "RB": "running backs", "WR": "receivers", "TE": "tight ends", "K": "kickers", "D/ST": "defenses"}


# ---- move explanations ----------------------------------------------------------
# One paragraph per move, written for a person deciding whether to click "move" in ESPN:
# what the projections say, whether the experts agree, how the matchups compare, and
# anything about health or usage that should colour the numbers. Each sentence is skipped
# when the data behind it is missing, so the paragraph never asserts what it cannot back.


SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v"}


def _surname(name: str) -> str:
    """'Michael Pittman Jr.' -> 'Pittman'; a defense keeps its whole name."""
    parts = name.split()
    if not parts or "D/ST" in parts:
        return name
    while len(parts) > 1 and parts[-1].lower() in SUFFIXES:
        parts.pop()
    return parts[-1]


def _names(pin: WeekPlayer, pout: WeekPlayer | None) -> tuple[str, str]:
    """Surnames for the pair, or full names when the surnames collide and would read as one man."""
    a = _surname(pin.name)
    b = _surname(pout.name) if pout else ""
    if pout is not None and a == b:
        return pin.name, pout.name
    return a, b


def _sentence(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    ends = text[-1] in ".!?" or (text[-1] in "\u201d\"" and len(text) > 1 and text[-2] in ".!?")
    return text[0].upper() + text[1:] + ("" if ends else ".")


def _status(p: WeekPlayer, who: str) -> str:
    """'Diggs is on bye' / 'Diggs is listed questionable' / '' when healthy and playing."""
    st = (p.injury_status or "").upper()
    if p.on_bye:
        return f"{who} is on bye"
    if st in ("IR", "INJURY_RESERVE"):
        return f"{who} is on injured reserve"
    if st in ZERO_STATUS or st in INJURY_MULT:
        return f"{who} is listed {st.lower()}"
    return ""


def _matchup(p: WeekPlayer) -> tuple[str, str]:
    """('faces GB, 19th against running backs', 'average'); kind is '' when the rank is unknown."""
    if not p.opponent:
        return "", ""
    r = p.opp_rank_vs_pos
    if not r:
        return f"faces {p.opponent}", ""
    kind = "soft" if r >= 20 else "tough" if r <= 8 else "average"
    return f"faces {p.opponent}, {ORDINAL(r)} against {POS_WORD.get(p.position, p.position)}", kind


def _projection_sentence(pin: WeekPlayer, pout: WeekPlayer | None, a: str, b: str, delta: float) -> str:
    parts = []
    if pin.espn_proj is not None:
        parts.append(f"ESPN projects {a} for {pin.espn_proj:.1f}" + (f" against {pout.espn_proj:.1f} for {b}" if pout and pout.espn_proj is not None else ""))
    if pin.fp_proj is not None:
        parts.append(f"FantasyPros has {pin.fp_proj:.1f}" + (f" to {pout.fp_proj:.1f}" if pout and pout.fp_proj is not None else ""))
    if not parts:
        return ""
    text = " and ".join(parts)
    if pout is None:
        return _sentence(text)
    both = pin.espn_proj is not None and pout.espn_proj is not None and pin.fp_proj is not None and pout.fp_proj is not None
    if both and (pin.espn_proj - pout.espn_proj) * (pin.fp_proj - pout.fp_proj) < 0:
        return _sentence(f"{text}, so the two sources split, but the blend still favours {a} by {delta:.1f}")
    return _sentence(f"{text} \u2014 {delta:.1f} more points in the blended projection")


def _experts_sentence(pin: WeekPlayer, pout: WeekPlayer | None, a: str, b: str) -> str:
    bits = []
    if pin.fp_pos_rank or pin.fp_grade:
        seg = f"FantasyPros' experts rank {a} {pin.fp_pos_rank or 'outside the top tiers'}" + (f" with a {pin.fp_grade} start grade" if pin.fp_grade else "")
        if pout and (pout.fp_pos_rank or pout.fp_grade):
            seg += f" versus {pout.fp_pos_rank or 'unranked'}" + (f" ({pout.fp_grade})" if pout.fp_grade else "") + f" for {b}"
        if pout and pin.fp_worst and pout.fp_best and pin.fp_worst < pout.fp_best:
            seg += f"; even the lowest expert on {a} has him above the highest on {b}"
        bits.append(seg)
    if pin.bc_tier and pout and pout.bc_tier:
        if pin.position == pout.position:
            gap = pout.bc_tier - pin.bc_tier
            if gap > 0:
                bits.append(f"Boris Chen has {a} {gap} tier{'s' if gap > 1 else ''} higher (tier {pin.bc_tier} vs {pout.bc_tier})")
            elif gap == 0:
                bits.append(f"Boris Chen has both in tier {pin.bc_tier}, so his tiers do not separate them")
            else:
                bits.append(f"Boris Chen actually has {b} {-gap} tier{'s' if gap < -1 else ''} higher (tier {pout.bc_tier} vs {pin.bc_tier})")
        else:
            bits.append(f"Boris Chen has {a} in {pin.position} tier {pin.bc_tier} and {b} in {pout.position} tier {pout.bc_tier}")
    elif pin.bc_tier:
        bits.append(f"Boris Chen has {a} in tier {pin.bc_tier}")
    return _sentence("; ".join(bits))


def _matchup_sentence(pin: WeekPlayer, pout: WeekPlayer | None, a: str, b: str) -> str:
    m_in, k_in = _matchup(pin)
    if not m_in:
        return ""
    if pout is None or not _matchup(pout)[0]:
        return _sentence(f"{a} {m_in}" + (f" ({k_in} matchup)" if k_in else ""))
    m_out, k_out = _matchup(pout)
    if k_in == "soft" and k_out == "tough":
        lead = "The matchups point the same way: "
    elif k_in == "tough" and k_out == "soft":
        lead = f"The matchup is the one argument for {b}: "
    else:
        lead = "On matchups, "
    return _sentence(f"{lead}{a} {m_in}" + (f" ({k_in})" if k_in else "") + f", while {b} {m_out}" + (f" ({k_out})" if k_out else ""))


def _usage_sentence(pin: WeekPlayer, pout: WeekPlayer | None, a: str, b: str) -> str:
    bits = []
    if pin.percent_started is not None and pout and pout.percent_started is not None:
        bits.append(f"{a} is started in {pin.percent_started:.0f}% of ESPN leagues versus {pout.percent_started:.0f}% for {b}")
    if pin.last_points is not None:
        who = "he" if bits else a
        bits.append(f"{who} scored {pin.last_points:.1f} last week" + (f" to {b}'s {pout.last_points:.1f}" if pout and pout.last_points is not None else ""))
    return _sentence(", and ".join(bits))


def explain_start(pin: WeekPlayer, pout: WeekPlayer | None, slot: str, delta: float) -> str:
    label = SLOT_LABEL.get(slot, slot)
    a, b = _names(pin, pout)
    out_status = _status(pout, b) if pout else ""
    if pout is None:
        verdict = f"{pin.name} should go into the empty {label} slot."
    elif out_status and pout.score == 0:
        verdict = f"{out_status}, so {pin.name} should take his {label} spot."
        out_status = ""  # already said
    elif delta >= 5:
        verdict = f"{pin.name} is the clear start over {pout.name} at {label} this week."
    elif delta >= 2:
        verdict = f"{pin.name} is the better play than {pout.name} at {label} this week."
    else:
        verdict = f"{pin.name} has a slight edge on {pout.name} at {label} this week."
    in_status = _status(pin, a)
    if in_status:
        in_status = _sentence(in_status + (", which is already discounted in his projection" if pin.score > 0 else ""))
    sentences = [
        verdict,
        _projection_sentence(pin, pout, a, b, delta),
        _experts_sentence(pin, pout, a, b),
        _matchup_sentence(pin, pout, a, b),
        in_status,
        _sentence(out_status),
        _usage_sentence(pin, pout, a, b),
    ]
    return " ".join(x for x in sentences if x)


def explain_waiver(fa: WeekPlayer, drop: WeekPlayer, delta: float) -> str:
    a, b = _names(fa, drop)
    sentences = [f"{fa.name} is worth a claim, with {drop.name} the drop."]
    if fa.season_proj is not None:
        sentences.append(_sentence(
            f"Rest of season, ESPN projects {a} for {fa.season_proj:.0f} points against {drop.season_proj or 0:.0f} for {b}, a {delta:+.0f} swing on your bench"
        ))
    week = []
    if fa.espn_proj is not None:
        week.append(f"ESPN {fa.espn_proj:.1f}" + (f" vs {drop.espn_proj:.1f}" if drop.espn_proj is not None else ""))
    if fa.fp_proj is not None:
        week.append(f"FantasyPros {fa.fp_proj:.1f}" + (f" vs {drop.fp_proj:.1f}" if drop.fp_proj is not None else ""))
    if week:
        sentences.append(_sentence(f"this week the projections are {' and '.join(week)}"))
    sentences.append(_experts_sentence(fa, drop, a, b))
    owned = fa.percent_owned or 0
    availability = "so he is unlikely to clear waivers unnoticed" if owned >= 50 else "so he should still be there when waivers run"
    sentences.append(_sentence(f"{a} is rostered in {owned:.0f}% of ESPN leagues, {availability}"))
    if drop.percent_started is not None and drop.percent_started < 10:
        sentences.append(_sentence(f"{b} is started in only {drop.percent_started:.0f}% of leagues, so little is lost by cutting him"))
    return " ".join(x for x in sentences if x)


def start_sit_moves(players: list[WeekPlayer], settings: LeagueSettings, w: LineupWeights | None = None) -> tuple[list[LineupMove], dict[str, int], float, float]:
    """Returns (moves, recommended_lineup, current_total, recommended_total).

    The second element is the current lineup with the recommended moves applied — NOT the
    theoretical optimum. The dashboard highlights rows by diffing it against what ESPN has,
    so anything the optimiser wants that did not survive into `moves` must not appear in it
    either; otherwise a row lights up with no move to explain it. Two things get dropped on
    the way: swaps worth less than `swap_threshold`, and pure slot permutations, where the
    same players start in a different arrangement for exactly the same points.
    """
    w = w or LineupWeights()
    by_id = {p.player_id: p for p in players}
    cur = current_lineup(players, settings)
    opt = optimal_lineup(players, settings, w)
    cur_total = sum(by_id[i].score for i in cur.values() if i in by_id)
    cur_ids, opt_ids = set(cur.values()), set(opt.values())
    outs = sorted((by_id[i] for i in cur_ids - opt_ids), key=lambda p: p.score)
    ins = sorted((by_id[i] for i in opt_ids - cur_ids), key=lambda p: p.score, reverse=True)
    key_of = {pid: k for k, pid in cur.items()}
    recommended = dict(cur)
    moves: list[LineupMove] = []
    for pin in ins:
        # He can only replace a starter whose slot he is allowed to occupy: a bench RB does
        # not "start over" the D/ST. Same position first, else the weakest eligible starter.
        cands = [o for o in outs if eligible(pin, _slot_of(key_of[o.player_id]))]
        pout = next((o for o in cands if o.position == pin.position), None) or (cands[0] if cands else None)
        if pout is not None:
            slot_key = key_of[pout.player_id]
        else:  # nobody to displace: he is filling a starter slot ESPN left empty
            slot_key = next((k for k in slot_keys(settings) if k not in recommended and eligible(pin, _slot_of(k))), "")
            if not slot_key:
                continue
        delta = pin.score - (pout.score if pout else 0.0)
        if pout is not None and delta < w.swap_threshold and pout.score > 0:
            continue  # too small to be worth a move; leave pout open to a bigger upgrade below
        if pout is not None:
            outs.remove(pout)
        slot = _slot_of(slot_key)
        head = f"Start {pin.name} over {pout.name} at {SLOT_LABEL.get(slot, slot)}" if pout else f"Start {pin.name} at {SLOT_LABEL.get(slot, slot)} (empty slot)"
        moves.append(LineupMove(kind="start", slot=slot, player_in=pin, player_out=pout, delta=delta, headline=head, why=explain_start(pin, pout, slot, delta)))
        recommended[slot_key] = pin.player_id
    rec_total = sum(by_id[i].score for i in recommended.values() if i in by_id)
    return moves, recommended, cur_total, rec_total


def waiver_moves(roster: list[WeekPlayer], free_agents: list[WeekPlayer], settings: LeagueSettings, w: LineupWeights | None = None) -> list[LineupMove]:
    """Add/drop suggestions: a free agent whose season outlook clearly beats my weakest bench player at a position he can replace."""
    w = w or LineupWeights()
    bench = [p for p in roster if p.slot in ("BE", "") and p.position not in ("K", "D/ST")]  # IR stays put
    if not bench:
        return []
    moves: list[LineupMove] = []
    fas = sorted((f for f in free_agents if f.position not in ("K", "D/ST")), key=lambda f: (f.season_proj or 0), reverse=True)
    used_drops: set[int] = set()
    for fa in fas:
        cands = [b for b in bench if b.player_id not in used_drops and (b.position == fa.position or b.position in ("RB", "WR", "TE") and fa.position in ("RB", "WR", "TE"))]
        if not cands:
            continue
        drop = min(cands, key=lambda b: (b.season_proj or 0))
        if (fa.season_proj or 0) < (drop.season_proj or 0) * (1 + w.waiver_margin) + 5:
            continue
        used_drops.add(drop.player_id)
        delta = (fa.season_proj or 0) - (drop.season_proj or 0)
        moves.append(LineupMove(kind="waiver", slot=fa.position, player_in=fa, player_out=drop, delta=delta, headline=f"Add {fa.name}, drop {drop.name}", why=explain_waiver(fa, drop, delta)))
        if len(moves) >= w.max_waivers:
            break
    return moves


def slot_rows(players: list[WeekPlayer], settings: LeagueSettings, optimal: dict[str, int]) -> list["SlotRow"]:
    """Every slot in ESPN order (starters, bench, IR), empties included, with the current occupant."""
    from .models import SlotRow

    remaining = sorted(players, key=lambda p: p.score, reverse=True)
    rows: list[SlotRow] = []
    ordered = [s for s in SLOT_ORDER if settings.roster_slots.get(s, 0) > 0] + [s for s in settings.roster_slots if s not in SLOT_ORDER and settings.roster_slots[s] > 0]
    for slot in ordered:
        for i in range(1, settings.roster_slots[slot] + 1):
            key = f"{slot}{i}"
            occupant = next((p for p in remaining if p.slot == slot), None)
            if occupant is not None:
                remaining.remove(occupant)
            rows.append(SlotRow(slot=slot, label=SLOT_LABEL.get(slot, slot), key=key, player=occupant, recommended_player_id=optimal.get(key)))
    # anything ESPN put in a slot we don't know about lands on the bench display
    for p in remaining:
        rows.append(SlotRow(slot="BE", label="Bench", key=f"BE{len(rows)}", player=p))
    return rows
