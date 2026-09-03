"""Keeper cost rules and keeper-value ranking."""
from __future__ import annotations

from statistics import mean

from .models import (
    DraftHistoryPick,
    KeeperHistoryEntry,
    KeeperOption,
    LeagueSettings,
    PickTrade,
    RosterEntry,
    SetupOverrides,
)
from .value import Rankings, adp_round, players_at_pick


def _pick_for(player_id: int, picks: list[DraftHistoryPick]) -> DraftHistoryPick | None:
    for p in picks:
        if p.player_id == player_id:
            return p
    return None


def keeper_history(player_id: int, drafts: dict[int, list[DraftHistoryPick]], season: int) -> list[KeeperHistoryEntry]:
    """Walk back from season-1 while the player keeps appearing as a keeper."""
    out: list[KeeperHistoryEntry] = []
    year = season - 1
    while year in drafts:
        pick = _pick_for(player_id, drafts[year])
        if pick is None:
            break
        out.append(KeeperHistoryEntry(season=year, round=pick.round_num, was_keeper=pick.keeper_status, team_id=pick.team_id))
        if not pick.keeper_status:
            break
        year -= 1
    return out


def compute_keeper_cost(
    player_id: int,
    drafts: dict[int, list[DraftHistoryPick]],
    season: int,
    rounds: int,
    my_team_id: int,
    team_names: dict[int, str],
    override: int | None = None,
) -> tuple[int, str, int, list[KeeperHistoryEntry], list[str]]:
    """Return (cost_round, source, years_kept, history, warnings)."""
    history = keeper_history(player_id, drafts, season)
    years_kept = sum(1 for h in history if h.was_keeper)
    warnings: list[str] = []
    if override is not None:
        return max(1, min(rounds, override)), "override", years_kept, history, warnings
    last = history[0] if history else None
    if last is None:
        return rounds, "undrafted", 0, history, warnings
    if last.was_keeper:
        cost, source = last.round - 2, "kept"
    else:
        cost, source = last.round, "drafted"
    if last.team_id != my_team_id:
        who = team_names.get(last.team_id) or "another team"
        warnings.append(
            f"Drafted by {who} in {last.season} (R{last.round}). In-season pickups keep that round; "
            f"if you traded for him after the season, league precedent is R{max(1, cost - 2)}. Override if so."
        )
    if cost < 1:
        warnings.append("Cost chain reached round 1 (can't go earlier).")
        cost = 1
    return cost, source, years_kept, history, warnings


def my_pick_overall(cost_round: int, my_slot: int, team_count: int) -> int:
    if cost_round % 2 == 1:
        return (cost_round - 1) * team_count + my_slot
    return cost_round * team_count - my_slot + 1


def owned_rounds(team_id: int, trades: list[PickTrade], season: int, rounds: int) -> dict[int, int]:
    """round -> number of picks team owns in that round after trades."""
    owned = {r: 1 for r in range(1, rounds + 1)}
    for t in trades:
        if t.season != season or t.original_team_id == t.owner_team_id:
            continue
        if t.original_team_id == team_id:
            owned[t.round] = owned.get(t.round, 0) - 1
        if t.owner_team_id == team_id:
            owned[t.round] = owned.get(t.round, 0) + 1
    return {r: max(0, n) for r, n in owned.items()}


def keeper_slot_round(team_id: int, cost_round: int, trades: list[PickTrade], season: int, rounds: int) -> tuple[int, str | None]:
    """The round whose pick the keeper actually consumes, plus a warning if it differs."""
    owned = owned_rounds(team_id, trades, season, rounds)
    if owned.get(cost_round, 0) > 0:
        return cost_round, None
    for r in range(cost_round + 1, rounds + 1):
        if owned.get(r, 0) > 0:
            return r, f"You don't own an R{cost_round} pick (traded away); assuming the keeper consumes your R{r} pick. Confirm with the league."
    return cost_round, f"You don't own an R{cost_round} pick or any later pick; confirm with the league how this keeper is charged."


def _explanation(source: str, history: list[KeeperHistoryEntry], rounds: int) -> str:
    if source == "override":
        return "manual override"
    if source == "undrafted":
        return f"undrafted pickup -> last round (R{rounds})"
    last = history[0]
    if source == "kept":
        return f"kept in {last.season} at R{last.round}, so 2 rounds earlier"
    return f"drafted R{last.round} in {last.season}"


def keeper_reason(opt: KeeperOption, rounds: int) -> str:
    """A short written rationale: what he costs, what he's worth, and the verdict."""
    p = opt.player
    name = opt.roster_entry.name
    cost = f"{name} would cost your round {opt.cost_round} pick ({_explanation(opt.cost_source, opt.history, rounds)})."
    if p is None:
        return cost + " He is not in this year's ESPN player pool (retired, unsigned, or renamed), so there is no value estimate and he is not a real option."
    worth = f"ESPN has him as the {p.position}{p.pos_rank}, #{p.overall_rank} overall in this league's scoring"
    if p.adp:
        worth += f", and drafts are taking him around pick {p.adp:.0f} (round {opt.adp_round})"
    worth += "."
    parts = [cost, worth]
    if p.fp_rank:
        experts = f"Expert consensus (FantasyPros) has him {p.fp_pos_rank or p.position} / #{p.fp_rank} overall"
        if p.fp_best and p.fp_worst:
            experts += f" (individual experts range #{p.fp_best} to #{p.fp_worst})"
        if p.bc_tier:
            experts += f", Boris Chen tier {p.bc_tier}"
        experts += "."
        parts.append(experts)
        gap = p.consensus_gap or 0.0
        if gap >= 15:
            parts.append("ESPN's projection is noticeably more optimistic than the experts, so treat the surplus below as a ceiling.")
        elif gap <= -15:
            parts.append("The experts like him more than ESPN's projection does, so the surplus below is probably conservative.")
    if opt.surplus_rounds is not None:
        r = opt.surplus_rounds
        if r >= 3:
            fp_round = adp_round(float(p.fp_rank), 10) if p.fp_rank else None
            sentence = f"That is about {r:.0f} rounds later than where drafts take him, so keeping him is like getting a round {opt.cost_round - int(r)} player for a round {opt.cost_round} pick"
            if fp_round is not None and abs(fp_round - (opt.cost_round - int(r))) >= 2:
                sentence += f" (by the experts' rank he is more of a round {fp_round} player, so call it {opt.cost_round - fp_round:+d} rounds)"
            parts.append(sentence + ".")
        elif r >= 1:
            parts.append(f"That is roughly {r:.0f} round{'s' if r >= 2 else ''} of value: a modest but real discount.")
        elif r > -1:
            if opt.surplus_by_slot and max(opt.surplus_by_slot.values()) - min(opt.surplus_by_slot.values()) > 20:
                lo, hi = min(opt.surplus_by_slot.values()), max(opt.surplus_by_slot.values())
                parts.append(
                    f"He costs about what he is worth, so keeping him depends entirely on your slot: roughly {lo:+.0f} points from the top of the draft "
                    f"(you could just take him) up to {hi:+.0f} from the back (he would be long gone)."
                )
            else:
                parts.append("That is about what he is worth, so keeping him gains you nothing over just drafting a comparable player there.")
        else:
            parts.append(f"That is {abs(r):.0f} round{'s' if abs(r) >= 2 else ''} worse than his market value; you could draft someone better with that pick.")
    if opt.surplus_points is not None and opt.expected_value is not None:
        where = f"at pick {opt.cost_pick_overall}" if opt.cost_pick_overall else f"in round {opt.cost_round} (averaged over the draft slots)"
        ex = f" - think {' or '.join(opt.expected_examples)}" if opt.expected_examples else ""
        parts.append(
            f"In value terms (projected points above a replacement-level starter, blended with ADP and expert rank) he is worth about {p.value:.0f}; "
            f"the best player you could expect {where} is worth about {opt.expected_value:.0f}{ex}. Keeping him therefore nets {opt.surplus_points:+.0f}."
        )
    if opt.years_kept:
        parts.append(f"He has been kept {opt.years_kept} year{'s' if opt.years_kept > 1 else ''} already, so next year he would cost round {max(1, opt.cost_round - 2)}.")
    return " ".join(parts)


def keeper_options(
    roster: list[RosterEntry],
    rankings: Rankings,
    drafts: dict[int, list[DraftHistoryPick]],
    settings: LeagueSettings,
    setup: SetupOverrides,
    curve: list[float],
) -> list[KeeperOption]:
    T = settings.team_count
    names = {t.team_id: t.name for t in settings.teams}
    my_slot = setup.my_slot
    if my_slot is None and setup.order_confirmed and settings.draft_order and settings.my_team_id in settings.draft_order:
        my_slot = settings.draft_order.index(settings.my_team_id) + 1
    if setup.slot_order and settings.my_team_id in setup.slot_order:
        my_slot = setup.slot_order.index(settings.my_team_id) + 1
    out: list[KeeperOption] = []
    for entry in roster:
        cost, source, years, history, warnings = compute_keeper_cost(
            entry.player_id, drafts, settings.season, settings.rounds, settings.my_team_id, names,
            setup.keeper_cost_overrides.get(entry.player_id),
        )
        slot_round, warn = keeper_slot_round(settings.my_team_id, cost, setup.pick_trades, settings.season, settings.rounds)
        if warn:
            warnings.append(warn)
        player = rankings.by_id.get(entry.player_id)
        opt = KeeperOption(
            roster_entry=entry, player=player, cost_round=cost, cost_source=source,
            years_kept=years, history=history, warnings=warnings, slot_known=my_slot is not None,
        )
        if my_slot:
            opt.cost_pick_overall = my_pick_overall(slot_round, my_slot, T)
        if player is not None and player.position in ("K", "D/ST"):
            opt.adp_round = adp_round(player.adp, T)
            opt.value_round = player.value_round
            opt.reason = f"{entry.name} is a {player.position}. Kickers and defenses are replacement-level by definition and can be drafted in the last rounds every year, so they are never worth a keeper slot."
            out.append(opt)
            continue
        if player is not None:
            opt.adp_round = adp_round(player.adp, T)
            opt.value_round = player.value_round
            # Surplus rounds is the simple, visible comparison: cost round vs the ADP round shown in the table.
            # Expert opinion feeds the points-based surplus and the rationale instead.
            ref_round = opt.adp_round if opt.adp_round is not None else player.value_round
            opt.surplus_rounds = float(cost - ref_round)
            if opt.cost_pick_overall and curve:
                idx = min(len(curve), opt.cost_pick_overall) - 1
                opt.surplus_points = player.value - curve[idx]
                opt.expected_value = curve[idx]
                opt.expected_examples = players_at_pick(rankings, opt.cost_pick_overall)
            elif curve:
                lo, hi = (slot_round - 1) * T, min(len(curve), slot_round * T)
                opt.surplus_points = player.value - mean(curve[lo:hi]) if hi > lo else None
                opt.surplus_by_slot = {
                    slot: player.value - curve[min(len(curve), my_pick_overall(slot_round, slot, T)) - 1] for slot in range(1, T + 1)
                }
                opt.expected_value = mean(curve[lo:hi]) if hi > lo else None
                opt.expected_examples = players_at_pick(rankings, my_pick_overall(slot_round, (T + 1) // 2, T))
        opt.reason = keeper_reason(opt, settings.rounds)
        out.append(opt)
    out.sort(key=lambda o: (o.player is not None, o.surplus_points or float("-inf"), o.surplus_rounds or float("-inf")), reverse=True)
    ranked = [o for o in out if o.player is not None and o.surplus_points is not None]
    for i, o in enumerate(ranked):
        parts = []
        if i + 1 < len(ranked):
            parts.append(_compare(o, ranked[i + 1], ahead=True))
        if i > 0:
            parts.append(_compare(o, ranked[i - 1], ahead=False))
        if parts:
            o.reason = (o.reason + " " + " ".join(parts)).strip()
    return out


def _compare(a: KeeperOption, b: KeeperOption, ahead: bool) -> str:
    """One explicit sentence on why `a` ranks ahead of / behind the neighbouring option `b`."""
    assert a.player and b.player and a.surplus_points is not None and b.surplus_points is not None
    an, bn = a.roster_entry.name.split(" ")[-1], b.roster_entry.name.split(" ")[-1]
    va, vb = a.player.value, b.player.value
    ea = a.expected_value if a.expected_value is not None else va - a.surplus_points
    eb = b.expected_value if b.expected_value is not None else vb - b.surplus_points

    def ex(o: KeeperOption) -> str:
        return f" (someone like {' or '.join(o.expected_examples)})" if o.expected_examples else ""

    better, worse = (an, bn) if va >= vb else (bn, an)
    lead = f"Why he ranks {'ahead of' if ahead else 'behind'} {b.roster_entry.name}: "
    body = (
        f"{better} is the better player, {max(va, vb):.0f} vs {min(va, vb):.0f} in value. "
        f"But keeping {an} spends a round {a.cost_round} pick that would otherwise get a player worth about {ea:.0f}{ex(a)}, "
        f"while keeping {bn} spends a round {b.cost_round} pick that would otherwise get about {eb:.0f}{ex(b)}. "
        f"Value minus what the pick would have returned: {an} {va:.0f} - {_num(ea)} = {a.surplus_points:+.0f}, {bn} {vb:.0f} - {_num(eb)} = {b.surplus_points:+.0f}"
        f"{', so ' + an + ' by ' + f'{a.surplus_points - b.surplus_points:.0f}' if ahead else ', so ' + bn + ' by ' + f'{b.surplus_points - a.surplus_points:.0f}'}."
    )
    return lead + body


def _num(x: float) -> str:
    return f"({x:.0f})" if x < 0 else f"{x:.0f}"
