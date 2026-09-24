from datetime import datetime, timezone

from ffdraft.models import UsageWeek, WaiverPlayer
from ffdraft.waivers import (
    SOURCE_FP_ROS, SOURCE_FP_WAIVER, SOURCE_ROTOWIRE, SOURCE_SLEEPER, SOURCE_SNAPS, WaiverWeights, add_score, build_waiver_view, choose_drop,
    drop_candidates, explain_pick, pool_stats, position_targets, roster_need, stream_candidates, tier_of, unavailable,
)

ALL = {SOURCE_FP_ROS, SOURCE_FP_WAIVER, SOURCE_SLEEPER, SOURCE_ROTOWIRE, SOURCE_SNAPS}
SLOTS = {"QB": 2, "RB": 2, "WR": 1, "WR/TE": 1, "TE": 1, "RB/WR/TE": 2, "D/ST": 1, "BE": 8, "IR": 1}


def wx(pid, name, pos, slot="BE", season=100.0, ros=None, ww=None, faab=None, note=None, adds=None, drops=None, inj=None, practice=None,
       usage=(), snap=None, owned=20.0, started=5.0, change=None, rw_add=None, on_my_team=None, bye=None, status=None):
    return WaiverPlayer(
        player_id=pid, name=name, position=pos, slot=slot, season_proj=season, ros_pos_rank=ros, fp_waiver_rank=ww, fp_faab=faab, fp_note=note,
        sleeper_adds=adds, sleeper_drops=drops, injury_status=inj, sleeper_practice=practice,
        usage=[UsageWeek(week=w, targets=t, carries=c) for w, t, c in usage], snap_pct=snap, percent_owned=owned, percent_started=started,
        percent_change=change, rw_add_pct=rw_add, on_my_team=slot != "FA" if on_my_team is None else on_my_team, bye_week=bye, waiver_status=status,
    )


def _roster():
    return [
        wx(1, "QB One", "QB", "QB", 300, ros="QB5"), wx(2, "QB Two", "QB", "QB", 250, ros="QB12"),
        wx(3, "RB One", "RB", "RB", 220, ros="RB4"), wx(4, "RB Two", "RB", "RB", 180, ros="RB12"),
        wx(5, "WR One", "WR", "WR", 210, ros="WR6"), wx(6, "WR Two", "WR", "WR/TE", 170, ros="WR15"), wx(7, "TE One", "TE", "TE", 140, ros="TE4"),
        wx(8, "WR Three", "WR", "RB/WR/TE", 150, ros="WR22"), wx(9, "RB Three", "RB", "RB/WR/TE", 140, ros="RB20"), wx(10, "DST One", "D/ST", "D/ST", 110, ros="DST8"),
        wx(11, "RB Four", "RB", "BE", 60, ros="RB48", started=2.0, drops=800, usage=((1, 0, 3), (2, 1, 2))),
        wx(12, "WR Four", "WR", "BE", 90, ros="WR40", started=8.0), wx(13, "WR Five", "WR", "BE", 70, ros="WR55"),
        wx(14, "TE Two", "TE", "BE", 50, ros=None, started=1.0), wx(15, "RB Five", "RB", "BE", 120, ros="RB28"),
        wx(16, "RB Hurt", "RB", "IR", 150, ros="RB15", inj="INJURY_RESERVE"),
    ]


def _fas():
    return [
        wx(100, "FA Back", "RB", "FA", 160, ros="RB22", ww=1, faab="$25", note="Leads the backfield now. Buy.", adds=120000, owned=35.0,
           usage=((1, 2, 8), (2, 4, 16)), snap=0.71, change=12.0, rw_add=30.0, status="WAIVERS"),
        wx(101, "FA Wideout", "WR", "FA", 130, ros="WR38", ww=6, faab="$8", adds=40000, owned=15.0, usage=((1, 6, 0), (2, 7, 0))),
        wx(102, "FA Passer", "QB", "FA", 230, ros="QB16", adds=5000, owned=20.0),
        wx(103, "FA Broken", "RB", "FA", 170, ros="RB8", ww=3, inj="OUT", adds=30000, owned=30.0, usage=((1, 3, 14), (2, 2, 15)), snap=0.8),
        wx(104, "FA Kicker", "K", "FA", 140), wx(105, "FA Dud", "TE", "FA", 20, ros=None, owned=0.5),
        wx(106, "FA Defense", "D/ST", "FA", 130, ros="DST1", adds=20000, owned=40.0),
    ]


def _view(settings, roster=None, fas=None, loaded=ALL, **kw):
    settings.roster_slots = SLOTS
    return build_waiver_view(roster if roster is not None else _roster(), fas if fas is not None else _fas(), settings, season=2026, week=3,
                             fetched_at=datetime.now(timezone.utc), loaded=loaded, **kw)


def test_position_targets_derive_from_slots(settings):
    settings.roster_slots = SLOTS
    t = position_targets(settings)
    assert t["QB"] == 3 and t["RB"] == 4 and t["WR"] == 4 and t["TE"] == 2 and t["D/ST"] == 1 and "K" not in t


def test_scores_renormalise_over_present_sources(settings):
    settings.roster_slots = SLOTS
    p_full = wx(1, "A", "RB", "FA", 150, ros="RB10", ww=1, adds=1000, usage=((1, 3, 12),), snap=0.8)
    p_bare = wx(2, "B", "RB", "FA", 150)
    stats = pool_stats([p_full, p_bare, wx(3, "C", "RB", "FA", 50)])
    have, want = {}, position_targets(settings)
    s_full, _ = add_score(p_full, stats, ALL, have, want, WaiverWeights())
    s_bare, _ = add_score(p_bare, stats, set(), have, want, WaiverWeights())
    assert 0 < s_full <= 115 and 0 < s_bare <= 115
    assert p_bare.missing == ["ros", "fp_waiver", "momentum", "usage"] and list(p_bare.components) == ["espn"]
    # only ESPN loaded and he is the pool's best projection -> full marks before the need multiplier
    assert abs(s_bare - 100 * WaiverWeights().need_more) < 1e-6
    assert not p_full.missing


def test_two_qb_need_and_surplus(settings):
    settings.roster_slots = SLOTS
    want = position_targets(settings)
    qb = wx(1, "FA QB", "QB", "FA", 200)
    stats = pool_stats([qb])
    short, _ = add_score(qb, stats, set(), {"QB": 2}, want, WaiverWeights())
    fine, _ = add_score(qb, stats, set(), {"QB": 3}, want, WaiverWeights())
    glut, _ = add_score(qb, stats, set(), {"QB": 5}, want, WaiverWeights())
    assert short > fine > glut


def test_tiers_and_health():
    w = WaiverWeights()
    assert tier_of(60, 60, 1.0, w) == "claim"
    assert tier_of(45, 45, 1.0, w) == "stash"
    assert tier_of(45, 45, 1.0, w, delta=20) == "claim"  # a clear upgrade on a bench player is a claim even in a thin pool
    assert tier_of(45, 45, 1.0, w, delta=10) == "stash"
    assert tier_of(22, 63, 0.35, w) == "stash"  # good player, out injured -> stash not start
    assert tier_of(33, 33, 1.0, w) == "watch"
    assert tier_of(10, 10, 1.0, w) is None


def test_drop_rules(settings):
    settings.roster_slots = SLOTS
    roster = _roster()
    roster[13].protected = True  # TE Two is the keeper
    for p in roster:
        p.add_score = 50.0
    roster[10].add_score = 10.0  # RB Four
    roster[11].add_score = 20.0  # WR Four
    roster[13].add_score = 1.0  # TE Two, protected
    cands = drop_candidates(roster)
    names = [c.name for c in cands]
    assert "TE Two" not in names and "RB Hurt" not in names and "DST One" not in names and "QB One" not in names
    assert names[0] == "RB Four"
    w = WaiverWeights()
    fa_rb = wx(100, "FA RB", "RB", "FA"); fa_rb.add_score = 40.0
    assert choose_drop(fa_rb, cands, roster, settings, set(), w).name == "RB Four"
    # same drop can't be reused, next best in the flex group
    assert choose_drop(fa_rb, cands, roster, settings, {11}, w).name == "WR Four"
    # a QB add may only cut a QB when the roster has exactly its two starters -- none on the bench, so nothing
    fa_qb = wx(101, "FA QB", "QB", "FA"); fa_qb.add_score = 90.0
    two_qb = [p for p in roster if p.position != "QB"] + [wx(1, "QB One", "QB", "QB"), wx(2, "QB Two", "QB", "BE")]
    for p in two_qb:
        p.add_score = p.add_score or 30.0
    two_cands = drop_candidates(two_qb)
    fa_wr = wx(102, "FA WR", "WR", "FA"); fa_wr.add_score = 95.0
    chosen = choose_drop(fa_wr, two_cands, two_qb, settings, set(), w)
    assert chosen is not None and chosen.position != "QB"  # a WR add never leaves the 2-QB league with one QB
    # margin: nobody clearly worse -> no drop
    fa_weak = wx(103, "FA Weak", "RB", "FA"); fa_weak.add_score = 12.0
    assert choose_drop(fa_weak, cands, roster, settings, set(), w) is None
    # a defense never swaps for a skill player, only streams over the one you start
    fa_dst = wx(104, "FA Defense", "D/ST", "FA"); fa_dst.add_score = 90.0
    assert choose_drop(fa_dst, cands, roster, settings, set(), w) is None
    streams = stream_candidates(roster)
    assert [c.name for c in streams] == ["DST One"] and choose_drop(fa_dst, streams, roster, settings, set(), w).name == "DST One"


def test_build_view_end_to_end(settings):
    v = _view(settings, keeper_id=14, faab=True, faab_budget=100)
    assert v.available and v.week_label == "NFL Week 3"
    names = [pk.player.name for pk in v.picks]
    assert "FA Kicker" not in names and "FA Dud" not in names
    assert names[0] == "FA Back"
    dst = next(pk for pk in v.picks if pk.player.name == "FA Defense")
    assert dst.drop is not None and dst.drop.name == "DST One" and dst.headline == "Stream FA Defense over DST One"
    back = v.picks[0]
    assert back.tier == "claim" and back.drop is not None and back.drop.name == "RB Four" and back.headline == "Add FA Back, drop RB Four"
    why = back.why
    assert why.startswith("FA Back is a claim-now add at running back, with RB Four the drop.")
    assert "suggests a bid around $25, about 25% of a $100 budget" in why
    assert "FantasyPros' experts have Back RB22" in why and "ahead of Four at RB48" in why
    assert "ESPN's season projection is 160 points against 60 for Four" in why
    assert "waiver panel has him #1 this week: “Leads the backfield now. Buy.”" in why
    assert "6 targets and 24 carries in his last 2 games (15.0 touches a game), playing 71% of the snaps" in why and "rising (20 last week against 10 before)" in why
    assert "added 120,000 times on Sleeper" in why and "up 30% rostered on MyFantasyLeague" in why and "ESPN roster share up 12% to 35%" in why
    assert "RB Four is the drop: RB48 rest of season on FantasyPros, a 60-point ESPN season projection, started in 2% of ESPN leagues, dropped 800 times on Sleeper" in why
    assert "sits on waivers rather than free agency" in why and "should still be there when waivers run" in why
    assert "None" not in why and "nan" not in why
    assert set(back.sources) == {"ESPN", "FantasyPros", "Sleeper", "Rotowire", "nflverse"}
    # the injured back is a stash, the kicker never shows, every drop is unique and never the keeper
    broken = next(pk for pk in v.picks if pk.player.name == "FA Broken")
    assert broken.tier == "stash" and "stash, not a start" in broken.why
    drops = [pk.drop.player_id for pk in v.picks if pk.drop]
    assert len(drops) == len(set(drops)) and 14 not in drops and 16 not in drops
    assert all(d.player.name != "TE Two" for d in v.drops) and v.drops[0].why
    assert any("2-QB" in n or "quarterback" in n for n in v.needs)  # two healthy QBs for two slots is thin


def test_qb_fit_sentence(settings):
    settings.roster_slots = SLOTS
    roster = _roster()
    have = roster_need(roster)
    fa = wx(102, "FA Passer", "QB", "FA", 230, ros="QB16")
    why = explain_pick(fa, None, "watch", roster, have, settings, 3, None, None, WaiverWeights())
    assert "on a 1-QB list, so quarterbacks run deeper in this league" in why
    assert "2 healthy quarterbacks for 2 dedicated starting slots" in why and "third quarterback is a starter-in-waiting" in why


def test_source_failure_degrades(settings):
    # When a source fails nothing is joined from it, so its fields stay None and its sentences never fire.
    roster, fas = _roster(), _fas()
    for p in roster + fas:
        p.ros_pos_rank = None
    v = _view(settings, roster=roster, fas=fas, loaded={SOURCE_SLEEPER}, errors=["FantasyPros rest-of-season: HTTP 503"])
    assert v.picks and v.errors == ["FantasyPros rest-of-season: HTTP 503"]
    assert all("ros" in pk.player.missing for pk in v.picks)
    assert all("FantasyPros' experts" not in pk.why for pk in v.picks)


def test_unavailable_and_empty_pool(settings):
    u = unavailable(2026, 1, "not yet")
    assert not u.available and u.reason == "not yet" and u.picks == []
    v = _view(settings, fas=[])
    assert v.picks == [] and len(v.drops) > 0
