from ffdraft.strategy import build_guide, position_rows


def test_guide_is_written_from_this_league(settings, rankings):
    """The advice must follow the league's own slots, not a generic template."""
    settings.roster_slots = {"QB": 2, "RB": 2, "WR": 1, "WR/TE": 1, "TE": 1, "RB/WR/TE": 2, "D/ST": 1, "BE": 8, "IR": 1}
    from ffdraft.models import ScoringRule

    settings.scoring = [ScoringRule(stat_id=53, abbr="REC", label="Each reception", points=0.5)]
    g = build_guide(rankings, settings)
    assert "superflex" in g.headline
    assert "no kicker" in g.league_summary and "half PPR" in g.league_summary
    titles = [s.title for s in g.sections]
    assert any("Quarterbacks first" in t for t in titles)
    assert any("never draft a kicker" in b for s in g.sections for b in s.bullets)
    assert g.round_plan and "quarterbacks" in g.round_plan[0]
    assert g.metrics and any("replacement" in m.label.lower() for m in g.metrics)


def test_one_qb_league_says_wait(settings, rankings):
    settings.roster_slots = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "RB/WR/TE": 1, "D/ST": 1, "K": 1, "BE": 7}
    g = build_guide(rankings, settings)
    assert "one-quarterback" in g.headline
    assert any("Wait on quarterback" == s.title for s in g.sections)
    assert any("last pick" in b for s in g.sections for b in s.bullets)  # kicker advice flips


def test_cliff_stays_inside_the_startable_range(settings, rankings):
    rows = {r.position: r for r in position_rows(rankings, settings)}
    for r in rows.values():
        if r.cliff_after is not None:
            assert r.cliff_after <= max(8, r.starters_league_wide + 6)


# ---- roster shape --------------------------------------------------------
def test_roster_targets_account_for_every_round(rankings, settings):
    """The plan must be draftable: one pick per round, no more, no fewer."""
    g = build_guide(rankings, settings)
    assert sum(r.total for r in g.roster_targets) == settings.rounds
    assert all(r.total == r.starters + r.bench for r in g.roster_targets)
    assert all(r.bench >= 0 for r in g.roster_targets)


def test_starters_match_the_lineup_you_actually_field(rankings, settings):
    starting_slots = sum(n for slot, n in settings.roster_slots.items() if slot not in ("BE", "IR"))
    g = build_guide(rankings, settings)
    assert sum(r.starters for r in g.roster_targets) == starting_slots


def test_bench_is_whatever_the_rounds_leave_over(rankings, settings):
    """Bench comes from spare rounds, not the BE count - a league can draft deeper than it rosters."""
    g = build_guide(rankings, settings)
    starters = sum(r.starters for r in g.roster_targets)
    assert sum(r.bench for r in g.roster_targets) == settings.rounds - starters


def test_flex_is_shared_between_rb_and_wr_not_given_to_te(settings):
    from ffdraft.strategy import flex_share

    share = flex_share(settings)
    assert share["TE"] == 0
    assert share["RB"] + share["WR"] == sum(
        n for slot, n in settings.roster_slots.items() if slot in ("RB/WR/TE", "RB/WR", "WR/TE", "FLEX")
    )


def test_superflex_adds_a_third_quarterback(players, settings):
    from ffdraft.value import build_rankings

    settings.roster_slots = {**settings.roster_slots, "QB": 2}
    g = build_guide(build_rankings(players, settings), settings)
    qb = next(r for r in g.roster_targets if r.position == "QB")
    assert qb.starters == 2 and qb.bench == 1 and qb.total == 3


def test_single_qb_league_drafts_fewer_quarterbacks(rankings, settings):
    g = build_guide(rankings, settings)
    qb = next(r for r in g.roster_targets if r.position == "QB")
    assert qb.total < 3  # no superflex premium


def test_no_kicker_slot_means_no_kicker_row(rankings, settings):
    g = build_guide(rankings, settings)
    assert "K" not in [r.position for r in g.roster_targets] or settings.roster_slots.get("K", 0) > 0
