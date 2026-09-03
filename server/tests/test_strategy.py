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
