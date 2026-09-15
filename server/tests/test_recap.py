from ffdraft.models import Player, RecapPlayer, WeekPlayer, WeekView
from ffdraft.recap import build_recap, hindsight, unavailable
from datetime import datetime, timezone

SLOTS = {"QB": 1, "RB": 1, "WR": 1, "WR/TE": 1, "D/ST": 1, "BE": 3, "IR": 1}


def rp(pid, name, pos, slot, pts, proj, opp=None, rank=None, inj=None, bye=False, hist=None, team="XX"):
    return dict(player_id=pid, name=name, position=pos, pro_team=team, slot=slot, points=pts, projected=proj, opponent=opp,
                opp_rank_vs_pos=rank, injury_status=inj, on_bye=bye, game_played=True, history=hist or [(1, pts, proj)])


def _box(my_score=None, opp_score=None):
    mine = [
        rp(1, "Jalen Hurts", "QB", "QB", 24.7, 21.4, "WSH", 25),
        rp(2, "Bijan Robinson", "RB", "RB", 27.3, 17.1, "PIT", 25),
        rp(3, "Davante Adams", "WR", "WR", 4.1, 12.0, "SF", 5),
        rp(4, "Kyle Pitts Sr.", "TE", "WR/TE", 0.0, 7.7, "PIT", 1),
        rp(5, "Texans D/ST", "D/ST", "D/ST", -4.0, 5.2, "BUF", 3),
        rp(6, "Stefon Diggs", "WR", "BE", 13.5, 7.6, "PHI", 23),
        rp(7, "Geno Smith", "QB", "BE", 9.3, 14.1),
        rp(8, "Mark Andrews", "TE", "BE", 6.9, 8.4),
    ]
    theirs = [
        rp(11, "Josh Allen", "QB", "QB", 22.0, 22.5), rp(12, "Jonathan Taylor", "RB", "RB", 23.6, 16.6), rp(13, "Trey McBride", "TE", "WR/TE", 20.0, 11.3),
        rp(14, "Some Receiver", "WR", "WR", 3.0, 11.0), rp(15, "Bills D/ST", "D/ST", "D/ST", 8.0, 6.0),
    ]
    ms = sum(p["points"] for p in mine if p["slot"] not in ("BE", "IR"))
    os_ = sum(p["points"] for p in theirs if p["slot"] not in ("BE", "IR"))
    return {"season": 2026, "week": 1, "current_week": 2, "complete": True, "my_team": "Math Guys", "opponent": "Commish", "record": "0-1",
            "my_score": my_score if my_score is not None else ms, "opp_score": opp_score if opp_score is not None else os_,
            "my_projected": 0, "opp_projected": 0, "my_lineup": mine, "opp_lineup": theirs, "fetched_at": "2026-09-15T00:00:00+00:00"}


def test_loss_summary_explains_the_margin_and_the_lineup_you_could_have_played(settings):
    settings.roster_slots = SLOTS
    r = build_recap(_box(), settings)
    assert r.result == "L" and r.my_score == 52.1 and r.opp_score == 76.6
    assert r.summary.startswith("You lost to Commish 52.1 to 76.6, a 24.5-point loss, in a matchup the projections had them winning by 4.0")
    assert "Your starters fell short of their projection by 11.3 and theirs beat projection by 9.2." in r.summary
    # worst busts named with their numbers, suffix stripped
    assert "The damage was Texans D/ST (-4.0 vs 5.2 projected), Adams (4.1 vs 12.0 projected), Pitts (0.0 vs 7.7 projected)." in r.summary
    assert "On their side, McBride went for 20.0 on a 11.3 projection and Taylor went for 23.6 on a 16.6 projection." in r.summary
    # hindsight: Diggs over Adams is worth naming; the optimiser also puts Andrews over Pitts
    assert "Stefon Diggs (13.5) over Davante Adams (4.1) at WR" in r.summary
    assert r.optimal_score > r.my_score and r.would_have_won is False and "still lost by" in r.summary


def test_win_summary_names_who_carried_it(settings):
    settings.roster_slots = SLOTS
    r = build_recap(_box(opp_score=40.0), settings)
    assert r.result == "W" and r.would_have_won is None
    assert "a 12.1-point win" in r.summary and "The week was carried by Robinson (27.3 vs 17.1 projected)" in r.summary
    assert "so the win did not need it" in r.summary


def test_right_and_wrong_notes(settings):
    settings.roster_slots = SLOTS
    r = build_recap(_box(), settings)
    assert [n.headline for n in r.right] == ["Robinson 27.3 (+10.2)"]
    assert "against PIT, 25th vs running backs (soft)" in r.right[0].detail
    # worst first, suffix stripped, tough-matchup warning attached
    assert r.wrong[0].headline == "Texans D/ST -4.0 (-9.2)"
    pitts = next(n for n in r.wrong if n.player_id == 4)
    assert pitts.headline.startswith("Pitts 0.0") and "the matchup was the warning sign" in pitts.detail
    assert not any(n.player_id == 1 for n in r.wrong)


def test_hindsight_respects_slot_eligibility(settings):
    settings.roster_slots = SLOTS
    best, moves = hindsight([RecapPlayer(**p) for p in _box()["my_lineup"]], settings)
    # Geno (9.3) cannot replace Adams at WR; he can only replace Hurts, who outscored him, so no QB move
    assert not any(m.player_in.player_id == 7 for m in moves)
    assert any(m.player_in.player_id == 6 and m.player_out.player_id == 3 for m in moves)
    assert abs(best - (24.7 + 27.3 + 13.5 + 6.9 - 4.0)) < 1e-6


def _week_view(moves_pairs=(), scores=None):
    scores = scores or {}
    def wp(pid, name, pos, slot):
        return WeekPlayer(player_id=pid, name=name, position=pos, slot=slot, score=scores.get(pid, 0.0))
    starters = [wp(3, "Davante Adams", "WR", "WR")]
    bench = [wp(6, "Stefon Diggs", "WR", "BE")]
    from ffdraft.models import LineupMove
    moves = [LineupMove(kind="start", slot="WR", player_in=bench[0], player_out=starters[0], delta=1.0, headline="", why="") for a, b in moves_pairs if (a, b) == (6, 3)]
    return WeekView(season=2026, week=2, week_label="NFL Week 2", fetched_at=datetime.now(timezone.utc), starters=starters, bench=bench, moves=moves)


def test_bench_lesson_cross_checks_this_weeks_projections(settings):
    settings.roster_slots = SLOTS
    r = build_recap(_box(), settings, current=_week_view(scores={3: 11.6, 6: 8.8}))
    lesson = next(n for n in r.lessons if n.headline == "Bench check: Diggs over Adams")
    assert "13.5 to 4.1 at WR" in lesson.detail and "still favour Adams this week (11.6 to 8.8)" in lesson.detail
    r = build_recap(_box(), settings, current=_week_view(moves_pairs=[(6, 3)]))
    lesson = next(n for n in r.lessons if n.headline == "Bench check: Diggs over Adams")
    assert "recommended moves above already make that change" in lesson.detail


def test_trend_bye_health_and_waiver_lessons(settings):
    settings.roster_slots = SLOTS
    box = _box()
    # Adams under projection three weeks running
    box["my_lineup"][2]["history"] = [(1, 5.0, 12.0), (2, 4.0, 11.0), (3, 4.1, 12.0)]
    players = {2: Player(player_id=2, name="Bijan Robinson", position="RB", pro_team="ATL", bye_week=2)}
    sleeper = {4: {"full_name": "Kyle Pitts Sr.", "injury_status": "Questionable", "injury_body_part": "Knee", "practice_participation": "Limited"}}
    adds = [({"full_name": "Mike Gesicki", "position": "TE", "team": "CIN", "espn_id": 900}, 603544), ({"full_name": "Rostered Guy", "position": "WR", "team": "KC", "espn_id": 901}, 500000)]
    drops = [({"full_name": "Mark Andrews", "position": "TE", "team": "BAL", "espn_id": 8}, 105183)]
    r = build_recap(box, settings, players_by_id=players, sleeper=sleeper, trending_add=adds, trending_drop=drops, league_fa_ids={900})
    heads = [n.headline for n in r.lessons]
    assert "Adams is trending down" in heads
    assert "Week 2 byes: Robinson" in heads and any("(next week)" in n.detail for n in r.lessons if n.headline.startswith("Week 2 byes"))
    health = next(n for n in r.lessons if n.headline == "Pitts: Questionable")
    assert health.source == "Sleeper" and "Sleeper has him questionable (knee); practice: Limited" in health.detail
    waiver = next(n for n in r.lessons if n.headline == "Most-added and still available in your league")
    assert "Gesicki" in waiver.detail and "Rostered Guy" not in waiver.detail  # not a free agent in this league
    assert "Managers are dropping Andrews" in heads


def test_unavailable_recap_carries_the_reason():
    r = unavailable(2026, 2, "NFL Week 2 is still in progress")
    assert r.available is False and r.week == 2 and r.reason.startswith("NFL Week 2")
