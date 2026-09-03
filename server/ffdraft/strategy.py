"""A draft strategy guide written against this league's actual settings and player pool.

Generic advice ("take running backs early") is often wrong for a specific league. Everything
here is computed from the roster slots, scoring, and current rankings, so the numbers are real.
"""
from __future__ import annotations

from .external import is_superflex, scoring_format
from .models import DetailMetric, LeagueSettings, StrategyGuide, StrategyPosition, StrategySection
from .value import FLEX_MAP, Rankings

def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


SCORING_NAME = {"PPR": "full PPR", "HALF": "half PPR", "STD": "standard (no PPR)"}


def _cliff(players: list, starters: int) -> tuple[int | None, float | None]:
    """The biggest value drop inside the part of a position anyone will actually start.

    Searching deeper finds real gaps that no drafter can act on: a cliff after QB35 is
    meaningless when only 20 quarterbacks start.
    """
    depth = max(8, min(len(players), starters + 6))
    top = players[:depth]
    if len(top) < 3:
        return None, None
    gaps = [(top[i - 1].value - top[i].value, i) for i in range(1, len(top))]
    size, idx = max(gaps)
    return idx, size


def position_rows(rankings: Rankings, settings: LeagueSettings) -> list[StrategyPosition]:
    rows: list[StrategyPosition] = []
    for pos, players in rankings.by_pos.items():
        if not players or settings.roster_slots.get(pos, 0) == 0 and rankings.starter_counts.get(pos, 0) == 0:
            continue
        starters = rankings.starter_counts.get(pos, 0)
        last = players[min(starters, len(players)) - 1] if starters else players[0]
        idx, size = _cliff(players, starters)
        rows.append(StrategyPosition(
            position=pos, starters_league_wide=starters, replacement_points=rankings.baselines.get(pos, 0.0),
            top_vorp=players[0].vorp, last_starter_vorp=last.vorp,
            above_replacement=sum(1 for p in players if p.vorp > 0), cliff_after=idx, cliff_size=size,
        ))
    order = {"QB": 0, "RB": 1, "WR": 2, "TE": 3, "D/ST": 4, "K": 5}
    rows.sort(key=lambda r: order.get(r.position, 9))
    return rows


def build_guide(rankings: Rankings, settings: LeagueSettings) -> StrategyGuide:
    T = settings.team_count
    fmt = scoring_format(settings)
    sf = is_superflex(settings)
    slots = settings.roster_slots
    qb_slots = slots.get("QB", 0)
    flex = sum(n for slot, n in slots.items() if slot in FLEX_MAP and n)
    bench = slots.get("BE", 0)
    has_k = slots.get("K", 0) > 0
    rows = position_rows(rankings, settings)
    by_pos = {r.position: r for r in rows}
    starters_total = sum(n for slot, n in slots.items() if slot not in ("BE", "IR"))
    drafted = settings.rounds * T
    pool = len(rankings.overall)

    league_summary = (
        f"{T} teams · {settings.rounds} rounds · {SCORING_NAME.get(fmt, fmt)} · "
        f"{starters_total} starters ({qb_slots} QB, {slots.get('RB', 0)} RB, {slots.get('WR', 0)} WR, "
        f"{slots.get('TE', 0)} TE, {flex} flex, {slots.get('D/ST', 0)} D/ST"
        + (f", {slots.get('K', 0)} K" if has_k else ", no kicker")
        + f") · {bench} bench"
    )

    headline = (
        "This is a superflex league, which flips the usual advice: quarterbacks are the scarcest thing on the board."
        if sf
        else "This is a one-quarterback league, so running backs and receivers carry the draft."
    )

    sections: list[StrategySection] = []
    qb = by_pos.get("QB")
    rb = by_pos.get("RB")

    # 0. What "replacement" means, since every other number here is built on it.
    if qb and rb:
        qb_repl, rb_repl = qb.replacement_points, rb.replacement_points
        sections.append(StrategySection(
            title="First, what \u201creplacement\u201d means",
            body=(
                "Replacement level is what the best free player at a position scores \u2014 the one nobody drafted, "
                "sitting on waivers. If you never draft a quarterback you will still start someone, and replacement "
                "level is what that someone gives you.\n\n"
                f"In this league {qb.starters_league_wide} quarterbacks start every week "
                f"({qb_slots} per team \u00d7 {T} teams), so roughly the {_ordinal(qb.starters_league_wide + 1)}-best quarterback "
                f"is the one you could always pick up. He projects for about {qb_repl:.0f} points. That number is the "
                "quarterback replacement level.\n\n"
                f"So drafting a quarterback who scores {qb_repl + 43:.0f} does not gain you {qb_repl + 43:.0f} points. "
                f"It gains you {43:.0f}, because without him you would have started the free guy for {qb_repl:.0f}. "
                "That gap is the only thing your pick actually bought."
            ),
            bullets=[
                f"Every position has its own replacement level: {', '.join(f'{r.position} {r.replacement_points:.0f}' for r in rows)}",
                f"Quarterbacks score the most raw points but start from the highest floor ({qb_repl:.0f}), "
                f"while running backs start from {rb_repl:.0f} \u2014 which is why raw point totals mislead",
                f"A {rb_repl + 75:.0f}-point running back ({75:+.0f} over replacement) is worth more than a "
                f"{qb_repl + 43:.0f}-point quarterback ({43:+.0f} over replacement), even though the quarterback scores more",
                "The app calls this \u201cpoints over replacement\u201d, and it is the number every ranking and "
                "recommendation here is sorted by",
            ],
        ))

    # 1. The one idea that matters
    sections.append(StrategySection(
        title="How the positions actually compare",
        body=(
            "Now compare the positions on that basis. Replacement level sits at "
            + ", ".join(f"{r.position} {r.replacement_points:.0f} pts" for r in rows if r.position in ("QB", "RB", "WR", "TE"))
            + ". The steeper the drop from the best player to the last starter, the more a early pick at that "
            "position is worth, because the alternative is so much worse."
        ),
        bullets=[
            f"{r.position}: top player is {r.top_vorp:+.0f} over replacement, the last starter is {r.last_starter_vorp:+.0f}, "
            f"and only {r.above_replacement} are above replacement at all"
            for r in rows if r.position in ("QB", "RB", "WR", "TE")
        ],
    ))

    # 2. Superflex / QB
    if sf and qb:
        sections.append(StrategySection(
            title="Quarterbacks first, and it is not close",
            body=(
                f"Starting {qb_slots} quarterbacks means {qb.starters_league_wide} QB starting spots across the league, "
                f"and only about {qb.above_replacement} quarterbacks are worth more than a waiver-wire arm. "
                "There are fewer usable quarterbacks than starting spots, so the last few teams start someone who actively loses them games. "
                "Take two quarterbacks early. The common mistake in superflex is treating it like a normal league and waiting."
            ),
            bullets=[
                f"The top QB is {qb.top_vorp:+.0f} over replacement; the {qb.starters_league_wide}th is {qb.last_starter_vorp:+.0f}",
                "Two of your 18 picks have to be quarterbacks no matter what, so paying early is cheaper than paying late",
                "A third quarterback is a real asset here, both as insurance and as trade leverage",
            ],
        ))
    elif qb:
        sections.append(StrategySection(
            title="Wait on quarterback",
            body=(
                f"Only {qb.starters_league_wide} quarterbacks start league-wide but {qb.above_replacement} are above replacement, "
                "so the position is deep. The gap between the best quarterback and a mid-round one is small compared with the gap "
                "at running back. Let someone else pay."
            ),
        ))

    # 3. Scarcity and tiers
    cliff_bits = [
        f"{r.position} after {r.position}{r.cliff_after} (a {r.cliff_size:.0f} point drop)"
        for r in rows if r.cliff_after and r.cliff_size and r.cliff_size > 5
    ]
    sections.append(StrategySection(
        title="Draft the last player in a tier, not the first in the next",
        body=(
            "Players inside a tier are close to interchangeable, so there is no reason to reach within one. "
            "The pick that matters is the last one before a drop. When a tier is about to empty before your next turn, "
            "take from it now; when it is deep, take the scarcer position and come back."
        ),
        bullets=(["The steepest drops on the board right now: " + "; ".join(cliff_bits)] if cliff_bits else [])
        + [
            "The app marks the last player in a tier in the recommendations, with how many are left",
            f"You pick every {T} picks, so ask how many players at that position will go in the {T - 1} picks between your turns",
        ],
    ))

    # 4. Flex and scoring
    sections.append(StrategySection(
        title=f"What {SCORING_NAME.get(fmt, fmt)} and {flex} flex spots reward",
        body=(
            ("Half a point per catch narrows the gap between running backs and receivers, and it rewards pass-catching backs "
             "and high-volume slot receivers over touchdown-dependent players. " if fmt == "HALF" else
             "A full point per catch pushes receivers and pass-catching backs well up the board over touchdown-dependent players. "
             if fmt == "PPR" else
             "With no points for receptions, volume on the ground and touchdowns matter most; pass-catching specialists lose value. ")
            + f"With {flex} flex spots, you effectively start "
            + f"{by_pos['RB'].starters_league_wide // T if 'RB' in by_pos else 0} running backs and "
            + f"{by_pos['WR'].starters_league_wide // T if 'WR' in by_pos else 0} receivers on an average team, "
            "so depth at both is what fills your lineup, not a third tight end."
        ),
    ))

    # 5. What not to spend on
    dst = by_pos.get("D/ST")
    te = by_pos.get("TE")
    late_bullets = []
    if not has_k:
        late_bullets.append("This league has no kicker slot, so never draft a kicker at all")
    else:
        late_bullets.append("Kickers are noise year to year; take one with your last pick")
    if dst:
        late_bullets.append(
            f"The best defense is only {dst.top_vorp:+.0f} over replacement and the {dst.starters_league_wide}th is "
            f"{dst.last_starter_vorp:+.0f}, so one late pick is the right price and streaming works"
        )
    if te and te.cliff_after:
        late_bullets.append(
            f"Tight end falls off after TE{te.cliff_after}; either get one of the top few or wait a long time, "
            "because the middle of that position is worth about the same as the end of it"
        )
    sections.append(StrategySection(
        title="Where not to spend picks",
        body=(
            "Every pick spent on a position with a flat curve is a pick not spent on one with a steep curve. "
            f"With {bench} bench spots and {pool - drafted} players left undrafted league-wide, the waiver wire will "
            "always have usable bodies, so do not hoard depth at positions you can replace."
        ),
        bullets=late_bullets,
    ))

    # 6. Risk
    sections.append(StrategySection(
        title="Read the risk, not just the projection",
        body=(
            "A projection is an average of outcomes. Two players with the same number can carry very different risk, "
            "and the expert spread and injury history tell you which is which. Early picks should be safe floors; "
            "late picks should be the volatile upside swings, because a late bust costs you nothing."
        ),
        bullets=[
            "A wide expert range (say #20 to #80) means the panel disagrees, which is upside and bust in one player",
            "Games missed in past seasons is the most honest durability signal available here",
            "Bye weeks only matter once you are stacking several at one position",
        ],
    ))

    # Round plan derived from the actual roster shape
    plan: list[str] = []
    if sf:
        plan.append("Rounds 1-3: two of these three picks should be quarterbacks, plus the best running back or receiver available.")
        plan.append("Rounds 4-7: fill running back and receiver with the last player in each tier before it breaks.")
    else:
        plan.append("Rounds 1-3: best running backs and receivers by value over replacement; do not reach for a quarterback.")
        plan.append("Rounds 4-7: keep taking running backs and receivers; consider a top tight end only if one of the top few is still there.")
    plan.append(f"Rounds 8-{settings.rounds - 4}: flex depth and upside; target players the experts rank well above their draft position.")
    plan.append(
        f"Rounds {settings.rounds - 3}-{settings.rounds}: one defense"
        + (", one kicker, " if has_k else ", ")
        + "and lottery tickets: backups behind fragile starters and rookies with a path to touches."
    )

    metrics = [
        DetailMetric(label="Points over replacement", value="the main number",
                     hint="Projected points minus what a freely available player at that position scores. Compare this across positions, never raw points."),
        DetailMetric(label="Tier", value="when to act",
                     hint="Players in a tier are interchangeable. Take the last one before a drop; never reach inside a tier."),
        DetailMetric(label="ADP vs expert rank", value="where the value is",
                     hint="When drafters take someone later than the experts rank him, that gap is free value. The reverse means you are paying a premium."),
        DetailMetric(label="Expert spread", value="risk",
                     hint="The distance between the highest and lowest expert rank. Wide means boom or bust; narrow means a reliable floor."),
        DetailMetric(label="Games missed", value="durability",
                     hint="Past missed games predict future ones better than any injury narrative."),
        DetailMetric(label="Picks until your turn", value="urgency",
                     hint=f"You pick every {T} picks. Multiply that by how many rivals need the position to see whether you can wait."),
    ]

    return StrategyGuide(
        league_summary=league_summary, headline=headline, positions=rows,
        sections=sections, round_plan=plan, metrics=metrics,
    )
