"""Score each team's draft 0-100, and say why in plain terms.

The only honest way to grade a pick is against what that pick slot was worth. Taking the
best player available at #1 overall is not skill; taking him at #40 is. So every pick is
measured against the league's own value curve — what the players typically still on the
board at that overall pick are worth — and a team's grade is how far above or below that
expectation it drafted, adjusted for whether it actually filled a lineup.
"""
from __future__ import annotations

from statistics import mean, pstdev

from .draft import DraftBoard, open_slots
from .models import BoardGrades, GradePick, LeagueSettings, SetupOverrides, TeamGrade
from .value import FLEX_MAP, Rankings, pick_curve

# How much of the score comes from beating the curve, versus from fielding a legal lineup.
VALUE_WEIGHT, FIT_WEIGHT = 0.8, 0.2
# Two standard deviations from the league mean is the top and bottom of the scale.
SPREAD = 2.0
# Someone always finishes last in a ten-team league, and that is not an F. The scale is
# centred so an average draft reads as a C+ and the worst honest draft as a D-.
FLOOR, RANGE = 50, 48

LETTERS = [(97, "A+"), (93, "A"), (90, "A-"), (87, "B+"), (83, "B"), (80, "B-"),
           (77, "C+"), (73, "C"), (70, "C-"), (67, "D+"), (63, "D"), (60, "D-")]


def letter(score: int) -> str:
    return next((l for cut, l in LETTERS if score >= cut), "F")


def _starter_slots(settings: LeagueSettings) -> int:
    return sum(n for slot, n in settings.roster_slots.items() if slot not in ("BE", "IR"))


def _needs(open_now: dict[str, int]) -> str:
    gaps = [f"{n} {slot}" for slot, n in open_now.items() if slot not in ("BE",) and n > 0]
    return ", ".join(gaps)


def grade_board(board: DraftBoard, settings: LeagueSettings, setup: SetupOverrides, rankings: Rankings) -> BoardGrades:
    total_picks = settings.rounds * settings.team_count
    curve = pick_curve(rankings, total_picks)
    filled = [p for p in board.picks if p.player_id is not None and p.player_id in rankings.by_id]

    grades = BoardGrades(
        graded_picks=len(filled), total_picks=total_picks,
        complete=len(filled) >= total_picks - settings.team_count,
        method=(
            "Every pick is compared with what that overall pick slot typically returns, so a late "
            "steal counts for more than an obvious pick at the top. Score is 80% value beaten and "
            "20% whether the roster can actually field a lineup."
        ),
    )
    if not filled:
        grades.note = "Nothing has been drafted yet, so there is nothing to grade."
        return grades

    names = {t.team_id: t.name for t in settings.teams}
    owners = {t.team_id: (t.owner_names[0] if t.owner_names else "") for t in settings.teams}
    slots_total = _starter_slots(settings)

    rows: list[TeamGrade] = []
    for team in settings.teams:
        mine = [p for p in filled if p.owner_team_id == team.team_id]
        picks: list[GradePick] = []
        for p in mine:
            rp = rankings.by_id[p.player_id]  # type: ignore[index]
            expected = curve[p.overall - 1] if p.overall - 1 < len(curve) else (curve[-1] if curve else 0.0)
            picks.append(GradePick(
                overall=p.overall, round=p.round, player_id=rp.player_id, player_name=rp.name,
                position=rp.position, value=rp.value, expected=expected, edge=rp.value - expected,
            ))
        positions = [rankings.by_id[p.player_id].position for p in mine]  # type: ignore[index]
        remaining = open_slots(positions, settings.roster_slots)
        open_starters = {k: v for k, v in remaining.items() if k != "BE" and v > 0}
        row = TeamGrade(
            team_id=team.team_id, name=names.get(team.team_id, str(team.team_id)),
            owner=owners.get(team.team_id, ""), is_me=team.team_id == settings.my_team_id,
            picks_made=len(picks),
            total_value=sum(g.value for g in picks), expected_value=sum(g.expected for g in picks),
            edge=sum(g.edge for g in picks),
            edge_per_pick=(sum(g.edge for g in picks) / len(picks)) if picks else 0.0,
            starter_slots=slots_total, starters_filled=slots_total - sum(open_starters.values()),
            open_starters=open_starters,
            best=max(picks, key=lambda g: g.edge) if picks else None,
            worst=min(picks, key=lambda g: g.edge) if picks else None,
        )
        rows.append(row)

    drafting = [r for r in rows if r.picks_made]
    per_pick = [r.edge_per_pick for r in drafting]
    centre = mean(per_pick)
    spread = pstdev(per_pick) or 1.0
    fits = [r.starters_filled / r.starter_slots if r.starter_slots else 1.0 for r in drafting]
    best_fit = max(fits) or 1.0

    for r in rows:
        if not r.picks_made:
            r.score, r.grade = 0, "-"
            r.reasons = ["No picks recorded yet."]
            continue
        z = (r.edge_per_pick - centre) / spread
        value_norm = (max(-SPREAD, min(SPREAD, z)) / SPREAD + 1) / 2  # 0..1
        # Fit is judged against the best-filled roster, so nobody is punished for the draft
        # simply being early.
        fit_ratio = (r.starters_filled / r.starter_slots) / best_fit if r.starter_slots and best_fit else 1.0
        fit_norm = max(0.0, min(1.0, fit_ratio))
        quality = VALUE_WEIGHT * value_norm + FIT_WEIGHT * fit_norm
        r.score = int(round(max(0, min(100, FLOOR + RANGE * quality))))
        r.grade = letter(r.score)
        r.reasons = _reasons(r)

    rows.sort(key=lambda r: (-r.score, -r.edge))
    for i, r in enumerate(rows, start=1):
        r.rank = i
    grades.teams = rows
    if not grades.complete:
        grades.note = (
            f"Only {len(filled)} of {total_picks} picks are in, so these move a lot with every round. "
            "They compare teams against each other right now, not against a finished draft."
        )
    return grades


def _reasons(r: TeamGrade) -> list[str]:
    out: list[str] = []
    verb = "above" if r.edge >= 0 else "below"
    out.append(
        f"{abs(r.edge):.0f} points {verb} what these {r.picks_made} pick slots usually return "
        f"({r.edge_per_pick:+.0f} per pick)."
    )
    if r.best and r.best.edge > 0:
        out.append(
            f"Best value: {r.best.player_name} ({r.best.position}) at #{r.best.overall} in round "
            f"{r.best.round}, {r.best.edge:+.0f} over that slot."
        )
    if r.worst and r.worst.edge < 0:
        out.append(
            f"Biggest reach: {r.worst.player_name} ({r.worst.position}) at #{r.worst.overall} in round "
            f"{r.worst.round}, {r.worst.edge:+.0f} against that slot."
        )
    gaps = _needs(r.open_starters)
    if gaps:
        out.append(f"Lineup still missing: {gaps}.")
    else:
        out.append("Every starting slot is filled.")
    return out
