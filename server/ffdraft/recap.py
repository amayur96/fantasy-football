"""What happened last week and why: the matchup, the lineup you could have played, and what to carry forward.

Everything here is computed from the finished box score (both lineups, actual vs projected), the
season's week-by-week history that comes with it, ESPN's injury tags and bye weeks, and Sleeper's
add/drop trends and practice reports. Every sentence is skipped when its data is missing.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .lineup import LineupWeights, SLOT_LABEL, POS_WORD, ORDINAL, optimal_lineup, start_sit_moves
from .models import LeagueSettings, LineupMove, Player, RecapNote, RecapPlayer, WeekPlayer, WeekRecap, WeekView

BIG_MISS = 5.0  # points under projection that count as "what went wrong"
BIG_HIT = 5.0
TREND_WEEKS = 2  # consecutive weeks under/over projection before it is called a trend
TREND_MARGIN = 3.0


SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v"}


def _who(p: RecapPlayer | WeekPlayer) -> str:
    """Surname for prose; 'Kyle Pitts Sr.' is Pitts, not Sr."""
    if p.position == "D/ST":
        return p.name
    parts = [x for x in p.name.split() if x.lower() not in SUFFIXES]
    return parts[-1] if parts else p.name


def _sentence(text: str) -> str:
    text = text.strip()
    return (text[0].upper() + text[1:] + ".") if text else ""


def _matchup(p: RecapPlayer) -> str:
    """'against PIT, 25th vs running backs (soft)' or '' when unknown."""
    if not p.opponent:
        return ""
    r = p.opp_rank_vs_pos
    if not r:
        return f"against {p.opponent}"
    kind = "soft" if r >= 20 else "tough" if r <= 8 else "average"
    return f"against {p.opponent}, {ORDINAL(r)} vs {POS_WORD.get(p.position, p.position)} ({kind})"


def _as_week_player(p: RecapPlayer) -> WeekPlayer:
    """The lineup optimiser scores WeekPlayers; here the 'score' is what he actually did."""
    return WeekPlayer(player_id=p.player_id, name=p.name, position=p.position, pro_team=p.pro_team, slot=p.slot, on_bye=p.on_bye,
                      injury_status=p.injury_status, espn_proj=p.projected, points=p.points, score=p.points)


def _starters(lineup: list[RecapPlayer]) -> list[RecapPlayer]:
    return [p for p in lineup if p.slot not in ("BE", "IR")]


def hindsight(lineup: list[RecapPlayer], settings: LeagueSettings) -> tuple[float, list[LineupMove]]:
    """Best possible score from this roster, and the swaps that would have got there."""
    players = [_as_week_player(p) for p in lineup]
    # Every point counts in hindsight, so no threshold; the optimiser's own eligibility rules still apply.
    moves, recommended, _, best = start_sit_moves(players, settings, LineupWeights(swap_threshold=0.0))
    return best, moves


def _streak(p: RecapPlayer, under: bool) -> int:
    """Consecutive weeks (ending this week) under (or over) projection by TREND_MARGIN."""
    n = 0
    for _, pts, proj in reversed(p.history):
        if (proj - pts >= TREND_MARGIN) if under else (pts - proj >= TREND_MARGIN):
            n += 1
        else:
            break
    return n


def _performance_notes(mine: list[RecapPlayer]) -> tuple[list[RecapNote], list[RecapNote]]:
    right: list[RecapNote] = []
    wrong: list[RecapNote] = []
    for p in sorted(_starters(mine), key=lambda p: p.points - p.projected, reverse=True):
        diff = p.points - p.projected
        who = _who(p)
        where = _matchup(p)
        if diff >= BIG_HIT:
            detail = f"{p.name} scored {p.points:.1f} against a {p.projected:.1f} projection {where}".rstrip()
            streak = _streak(p, under=False)
            if streak >= TREND_WEEKS:
                detail += f"; that is {streak} straight weeks over projection"
            right.append(RecapNote(headline=f"{who} {p.points:.1f} ({diff:+.1f})", detail=_sentence(detail), player_id=p.player_id, tone="good"))
        elif diff <= -BIG_MISS or (p.projected >= 5 and p.points <= 0.35 * p.projected):
            if p.on_bye:
                detail = f"{p.name} was on bye and started anyway, so the slot scored nothing"
            elif p.injury_status in ("OUT", "IR", "INJURY_RESERVE", "SUSPENSION") or (p.points == 0 and not p.game_played):
                detail = f"{p.name} did not play ({(p.injury_status or 'inactive').lower()}) and the slot scored {p.points:.1f}"
            else:
                detail = f"{p.name} managed {p.points:.1f} against a {p.projected:.1f} projection {where}".rstrip()
                if p.opp_rank_vs_pos and p.opp_rank_vs_pos <= 8:
                    detail += "; the matchup was the warning sign"
                streak = _streak(p, under=True)
                if streak >= TREND_WEEKS:
                    detail += f"; that is {streak} straight weeks under projection"
            wrong.append(RecapNote(headline=f"{who} {p.points:.1f} ({diff:+.1f})", detail=_sentence(detail), player_id=p.player_id, tone="bad"))
    wrong.reverse()  # the loop ran best-to-worst; the reader wants the worst first
    return right, wrong


def _summary(r: WeekRecap, my_act: float, my_proj: float, opp_act: float, opp_proj: float, moves: list[LineupMove], mine: list[RecapPlayer], theirs: list[RecapPlayer]) -> str:
    margin = r.my_score - r.opp_score
    proj_margin = my_proj - opp_proj
    my_miss = my_act - my_proj
    opp_surprise = opp_act - opp_proj
    if r.result == "W":
        s = [f"You beat {r.opponent} {r.my_score:.1f} to {r.opp_score:.1f}, a {margin:.1f}-point win"]
    elif r.result == "L":
        s = [f"You lost to {r.opponent} {r.my_score:.1f} to {r.opp_score:.1f}, a {-margin:.1f}-point loss"]
    else:
        s = [f"You tied {r.opponent} at {r.my_score:.1f}"]
    if abs(proj_margin) >= 1:
        favoured = "you" if proj_margin > 0 else "them"
        s[0] += f", in a matchup the projections had {favoured} winning by {abs(proj_margin):.1f} ({my_proj:.1f} to {opp_proj:.1f})"
    else:
        s[0] += f", in a matchup projected as a coin flip ({my_proj:.1f} to {opp_proj:.1f})"
    s[0] += "."
    # Where the margin actually came from. actual margin == projected margin + my miss - their surprise.
    yours = f"your starters {'beat' if my_miss >= 0 else 'fell short of'} their projection by {abs(my_miss):.1f}"
    theirs_ = f"theirs {'beat' if opp_surprise >= 0 else 'came in under'} projection by {abs(opp_surprise):.1f}"
    s.append(_sentence(f"{yours} and {theirs_}"))
    # The named culprits and heroes on each side, from the box score.
    my_st = sorted(_starters(mine), key=lambda p: p.points - p.projected)
    op_st = sorted(_starters(theirs), key=lambda p: p.points - p.projected, reverse=True)
    if r.result == "L":
        busts = [p for p in my_st if p.projected - p.points >= BIG_MISS][:3]
        if busts:
            s.append(_sentence("the damage was " + ", ".join(f"{_who(p)} ({p.points:.1f} vs {p.projected:.1f} projected)" for p in busts)))
        heroes = [p for p in op_st if p.points - p.projected >= BIG_HIT][:2]
        if heroes:
            s.append(_sentence("on their side, " + " and ".join(f"{_who(p)} went for {p.points:.1f} on a {p.projected:.1f} projection" for p in heroes) + (", which alone covered the margin" if heroes[0].points - heroes[0].projected >= -margin else "")))
    else:
        heroes = [p for p in reversed(my_st) if p.points - p.projected >= BIG_HIT][:3]
        if heroes:
            s.append(_sentence("the week was carried by " + ", ".join(f"{_who(p)} ({p.points:.1f} vs {p.projected:.1f} projected)" for p in heroes)))
        their_busts = [p for p in reversed(op_st) if p.projected - p.points >= BIG_MISS][:2]
        if their_busts and r.result == "W":
            s.append(_sentence("they got nothing from " + " and ".join(f"{_who(p)} ({p.points:.1f} vs {p.projected:.1f})" for p in their_busts)))
    # The lineup you could have played.
    left = r.optimal_score - my_act
    worth = [m for m in moves if m.player_out and m.delta >= 2][:3]
    if left >= 1 and worth:
        swaps = ", ".join(f"{m.player_in.name} ({m.player_in.points:.1f}) over {m.player_out.name} ({m.player_out.points:.1f}) at {SLOT_LABEL.get(m.slot, m.slot)}" for m in worth)
        tail = f"your best lineup would have scored {r.optimal_score:.1f} by starting {swaps}"
        if r.result == "L":
            tail += f", which would have {'won it by ' + format(r.optimal_score - r.opp_score, '.1f') if r.would_have_won else 'still lost by ' + format(r.opp_score - r.optimal_score, '.1f')}"
        elif r.result == "W":
            tail += ", so the win did not need it"
        s.append(_sentence(tail))
    elif r.result == "L":
        s.append("Your lineup was already the best this roster could do, so this one was on the players, not the decisions.")
    return " ".join(x for x in s if x)


def _lessons(
    r: WeekRecap, mine: list[RecapPlayer], moves: list[LineupMove], current: WeekView | None, players_by_id: dict[int, Player],
    sleeper: dict[int, dict[str, Any]], trending_add: list[tuple[dict[str, Any], int]], trending_drop: list[tuple[dict[str, Any], int]],
    league_fa_ids: set[int],
) -> list[RecapNote]:
    out: list[RecapNote] = []
    cur_by_id = {p.player_id: p for p in (current.starters + current.bench)} if current else {}
    cur_moves = {(m.player_in.player_id, m.player_out.player_id) for m in current.moves if m.player_out} if current else set()

    # 1. Bench decisions, cross-checked against what this week's projections say.
    for m in moves[:3]:
        if not m.player_out or m.delta < 3:
            continue
        pin, pout = m.player_in, m.player_out
        detail = f"{pin.name} outscored {pout.name} from the bench, {pin.points:.1f} to {pout.points:.1f} at {SLOT_LABEL.get(m.slot, m.slot)}."
        if (pin.player_id, pout.player_id) in cur_moves:
            detail += " This week's projections agree, and the recommended moves above already make that change."
        elif pin.player_id in cur_by_id and pout.player_id in cur_by_id:
            ci, co = cur_by_id[pin.player_id], cur_by_id[pout.player_id]
            if ci.score > co.score:
                detail += f" This week's projections now lean {_who(ci)} too ({ci.score:.1f} to {co.score:.1f})."
            else:
                detail += f" The projections still favour {_who(co)} this week ({co.score:.1f} to {ci.score:.1f}), so treat it as one week, not a trend, unless it repeats."
        out.append(RecapNote(headline=f"Bench check: {_who(pin)} over {_who(pout)}", detail=detail, player_id=pin.player_id, source="hindsight", tone="neutral"))

    # 2. Trends across the season so far.
    for p in _starters(mine):
        under, over = _streak(p, True), _streak(p, False)
        if under >= TREND_WEEKS:
            out.append(RecapNote(headline=f"{_who(p)} is trending down", detail=f"{p.name} has finished {TREND_MARGIN:.0f}+ points under projection {under} weeks running ({', '.join(f'{pts:.1f} vs {proj:.1f}' for _, pts, proj in p.history[-under:])}). Projections lag; do not assume the number is the floor.", player_id=p.player_id, source="ESPN", tone="bad"))
        elif over >= TREND_WEEKS:
            out.append(RecapNote(headline=f"{_who(p)} keeps beating the number", detail=f"{p.name} has beaten projection by {TREND_MARGIN:.0f}+ {over} weeks running ({', '.join(f'{pts:.1f} vs {proj:.1f}' for _, pts, proj in p.history[-over:])}). Keep him in every week and consider him a buy if the projections have not caught up.", player_id=p.player_id, source="ESPN", tone="good"))

    # 3. Byes coming up for the people you rely on.
    for ahead in (1, 2):
        wk = r.week + ahead
        byes = [p for p in _starters(mine) if (players_by_id.get(p.player_id).bye_week if players_by_id.get(p.player_id) else None) == wk]
        if byes:
            names = ", ".join(p.name for p in byes)
            out.append(RecapNote(headline=f"Week {wk} byes: {', '.join(_who(p) for p in byes)}", detail=f"{names} {'is' if len(byes) == 1 else 'are'} off in week {wk}{' (next week)' if ahead == 1 else ''}; line up the replacement{'s' if len(byes) > 1 else ''} before waivers run.", source="ESPN", tone="neutral"))

    # 4. Health, from ESPN's tag and Sleeper's practice report.
    for p in mine:
        if p.slot == "IR":
            continue
        sl = sleeper.get(p.player_id) or {}
        sl_status = (sl.get("injury_status") or "").upper()
        if not p.injury_status and not sl_status:
            continue
        bits = []
        if p.injury_status:
            bits.append(f"ESPN lists him {p.injury_status.replace('_', ' ').lower()}")
        if sl_status:
            part = f" ({sl['injury_body_part'].lower()})" if sl.get("injury_body_part") else ""
            bits.append(f"Sleeper has him {sl_status.lower()}{part}")
        if sl.get("practice_participation"):
            bits.append(f"practice: {sl['practice_participation']}" + (f" — {sl['practice_description']}" if sl.get("practice_description") else ""))
        if sl.get("injury_notes"):
            bits.append(str(sl["injury_notes"])[:160])
        detail = "; ".join(bits)
        if sl.get("news_updated"):
            try:
                age = datetime.now(timezone.utc) - datetime.fromtimestamp(int(sl["news_updated"]) / 1000, tz=timezone.utc)
                detail += f" (updated {age.days}d ago)" if age.days else " (updated today)"
            except (TypeError, ValueError, OSError):
                pass
        out.append(RecapNote(headline=f"{_who(p)}: {(sl_status or p.injury_status or '').replace('_', ' ').title()}", detail=_sentence(detail), player_id=p.player_id, source="ESPN + Sleeper" if sl_status and p.injury_status else ("Sleeper" if sl_status else "ESPN"), tone="bad"))

    # 5. Waiver buzz: what managers everywhere are grabbing, filtered to what is actually available in your league.
    mine_ids = {p.player_id for p in mine}
    picks = [(rec, n) for rec, n in trending_add if rec.get("espn_id") in league_fa_ids][:3]
    if picks:
        detail = "; ".join(f"{rec['full_name']} ({rec.get('position')}, {rec.get('team') or 'FA'}) added {n:,} times in the last two days" for rec, n in picks)
        out.append(RecapNote(headline="Most-added and still available in your league", detail=_sentence(detail + ". Check the Waiver wire section above for whether any of them beats your bench"), player_id=int(picks[0][0]["espn_id"]), source="Sleeper", tone="good"))
    drops = [(rec, n) for rec, n in trending_drop if rec.get("espn_id") in mine_ids][:2]
    for rec, n in drops:
        out.append(RecapNote(headline=f"Managers are dropping {rec['full_name'].split()[-1]}", detail=f"{rec['full_name']} was dropped {n:,} times on Sleeper in the last two days. That is sentiment, not a verdict, but if he is your bench cut it will not be a controversial one.", player_id=int(rec["espn_id"]), source="Sleeper", tone="neutral"))
    return out


def build_recap(
    box: dict[str, Any], settings: LeagueSettings, *, current: WeekView | None = None, players_by_id: dict[int, Player] | None = None,
    sleeper: dict[int, dict[str, Any]] | None = None, trending_add: list[tuple[dict[str, Any], int]] | None = None,
    trending_drop: list[tuple[dict[str, Any], int]] | None = None, league_fa_ids: set[int] | None = None,
    sources: dict[str, str] | None = None, errors: list[str] | None = None,
) -> WeekRecap:
    mine = [RecapPlayer(**p) for p in box["my_lineup"]]
    theirs = [RecapPlayer(**p) for p in box["opp_lineup"]]
    my_act = sum(p.points for p in _starters(mine))
    opp_act = sum(p.points for p in _starters(theirs))
    my_proj = sum(p.projected for p in _starters(mine))
    opp_proj = sum(p.projected for p in _starters(theirs))
    my_score, opp_score = float(box["my_score"]), float(box["opp_score"])
    result = "W" if my_score > opp_score else "L" if my_score < opp_score else "T"
    best, moves = hindsight(mine, settings)
    r = WeekRecap(
        season=int(box["season"]), week=int(box["week"]), week_label=f"NFL Week {box['week']}",
        result=result, my_team=box.get("my_team", ""), opponent=box.get("opponent", ""), record=box.get("record", ""),
        my_score=my_score, opp_score=opp_score, my_projected=my_proj, opp_projected=opp_proj,
        optimal_score=best, bench_points_left=max(0.0, best - my_act), would_have_won=(best > opp_score) if result == "L" else None,
        my_lineup=mine, opp_lineup=theirs, sources=sources or {}, errors=errors or [],
    )
    r.right, r.wrong = _performance_notes(mine)
    r.summary = _summary(r, my_act, my_proj, opp_act, opp_proj, moves, mine, theirs)
    r.lessons = _lessons(r, mine, moves, current, players_by_id or {}, sleeper or {}, trending_add or [], trending_drop or [], league_fa_ids or set())
    return r


def unavailable(season: int, week: int, reason: str) -> WeekRecap:
    return WeekRecap(season=season, week=week, week_label=f"NFL Week {week}", available=False, reason=reason)
