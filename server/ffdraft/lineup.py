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


def _fact_bits(p: WeekPlayer) -> list[str]:
    bits = []
    if p.espn_proj is not None:
        bits.append(f"ESPN {p.espn_proj:.1f}")
    if p.fp_proj is not None:
        bits.append(f"FantasyPros {p.fp_proj:.1f}")
    if p.fp_pos_rank:
        bits.append(f"{p.fp_pos_rank}" + (f" ({p.fp_grade})" if p.fp_grade else ""))
    if p.bc_tier:
        bits.append(f"Boris tier {p.bc_tier}")
    return bits


def _qual(p: WeekPlayer) -> str:
    """'Herbert faces DAL (32nd vs QB: soft matchup)' plus injury/bye notes."""
    who = p.name.split()[-1]
    notes = []
    st = (p.injury_status or "").upper()
    if p.on_bye:
        notes.append(f"{who} is on bye")
    elif st in ZERO_STATUS:
        notes.append(f"{who} is listed {st.replace('_', ' ').lower()}")
    elif st in INJURY_MULT:
        notes.append(f"{who} is listed {st.lower()}")
    if p.opponent:
        if p.opp_rank_vs_pos:
            r = p.opp_rank_vs_pos
            kind = "soft" if r >= 20 else "tough" if r <= 8 else "average"
            notes.append(f"{who} faces {p.opponent} ({ORDINAL(r)} vs {p.position}: {kind} matchup)")
        else:
            notes.append(f"{who} faces {p.opponent}")
    return "; ".join(notes)


def _tier_note(a: WeekPlayer, b: WeekPlayer) -> str:
    if a.position == b.position and a.bc_tier and b.bc_tier and a.bc_tier != b.bc_tier:
        n = abs(a.bc_tier - b.bc_tier)
        return f"Boris Chen has {a.name.split()[-1]} {n} tier{'s' if n > 1 else ''} {'above' if a.bc_tier < b.bc_tier else 'below'} {b.name.split()[-1]}"
    return ""


def start_sit_moves(players: list[WeekPlayer], settings: LeagueSettings, w: LineupWeights | None = None) -> tuple[list[LineupMove], dict[str, int], float, float]:
    w = w or LineupWeights()
    by_id = {p.player_id: p for p in players}
    cur = current_lineup(players, settings)
    opt = optimal_lineup(players, settings, w)
    cur_total = sum(by_id[i].score for i in cur.values() if i in by_id)
    opt_total = sum(by_id[i].score for i in opt.values() if i in by_id)
    cur_ids, opt_ids = set(cur.values()), set(opt.values())
    outs = sorted((by_id[i] for i in cur_ids - opt_ids), key=lambda p: p.score)
    ins = sorted((by_id[i] for i in opt_ids - cur_ids), key=lambda p: p.score, reverse=True)
    moves: list[LineupMove] = []
    for pin in ins:
        slot_key = next((k for k, v in opt.items() if v == pin.player_id), "")
        # the bench-bound player this one effectively replaces: same position first, else the weakest remaining
        pout = next((o for o in outs if o.position == pin.position), None) or (outs[0] if outs else None)
        if pout is not None:
            outs.remove(pout)
        delta = pin.score - (pout.score if pout else 0.0)
        if pout is not None and delta < w.swap_threshold and pout.score > 0:
            continue
        slot = _slot_of(slot_key)
        head = f"Start {pin.name} over {pout.name} at {slot}" if pout else f"Start {pin.name} at {slot} (empty slot)"
        quant = f"{pin.name.split()[-1]}: {', '.join(_fact_bits(pin))}"
        if pout:
            quant += f" vs {pout.name.split()[-1]}: {', '.join(_fact_bits(pout)) or 'no projection'}"
        quant += f". Net {delta:+.1f} projected points."
        qual_parts = [x for x in (_qual(pin), _qual(pout) if pout else "", _tier_note(pin, pout) if pout else "") if x]
        moves.append(LineupMove(kind="start", slot=slot, player_in=pin, player_out=pout, delta=delta, headline=head, quant=quant, qual=". ".join(qual_parts) + ("." if qual_parts else "")))
    return moves, opt, cur_total, opt_total


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
        quant = (
            f"Rest of season: {fa.name.split()[-1]} projects {fa.season_proj:.0f} pts vs {drop.name.split()[-1]} {drop.season_proj or 0:.0f} ({delta:+.0f}). "
            f"This week: {', '.join(_fact_bits(fa)) or 'no projection'} vs {', '.join(_fact_bits(drop)) or 'no projection'}."
        )
        qual = f"{fa.name.split()[-1]} is owned in {fa.percent_owned or 0:.0f}% of ESPN leagues"
        if fa.fp_rank and drop.fp_rank:
            qual += f"; experts rank him #{fa.fp_rank} this week vs #{drop.fp_rank} for {drop.name.split()[-1]}"
        tn = _tier_note(fa, drop)
        if tn:
            qual += f"; {tn}"
        moves.append(LineupMove(kind="waiver", slot=fa.position, player_in=fa, player_out=drop, delta=delta, headline=f"Add {fa.name}, drop {drop.name}", quant=quant, qual=qual + "."))
        if len(moves) >= w.max_waivers:
            break
    return moves


SLOT_ORDER = ["QB", "RB", "WR", "WR/TE", "TE", "RB/WR", "RB/WR/TE", "FLEX", "OP", "D/ST", "K", "BE", "IR"]
SLOT_LABEL = {"RB/WR/TE": "FLEX", "RB/WR": "FLEX", "OP": "OP", "WR/TE": "WR/TE", "BE": "Bench"}


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
