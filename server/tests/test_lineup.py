from ffdraft.lineup import LineupWeights, current_lineup, optimal_lineup, slot_rows, start_sit_moves, waiver_moves, weekly_score
from ffdraft.models import WeekPlayer


def wp(pid, name, pos, slot="BE", espn=None, fp=None, inj=None, bye=False, season=100.0, opp=None, opp_rank=None, grade=None, tier=None, owned=50.0):
    return WeekPlayer(player_id=pid, name=name, position=pos, slot=slot, espn_proj=espn, fp_proj=fp, injury_status=inj, on_bye=bye,
                      season_proj=season, opponent=opp, opp_rank_vs_pos=opp_rank, fp_grade=grade, bc_tier=tier, percent_owned=owned)


def test_weekly_score_blends_and_zeroes_out():
    assert weekly_score(wp(1, "A", "RB", espn=10, fp=14)) == 12
    assert weekly_score(wp(2, "B", "RB", espn=10)) == 10
    assert weekly_score(wp(3, "C", "RB", espn=10, inj="OUT")) == 0
    assert weekly_score(wp(4, "D", "RB", espn=10, bye=True)) == 0
    assert abs(weekly_score(wp(5, "E", "RB", espn=10, inj="QUESTIONABLE")) - 9) < 1e-9


def _roster():
    ps = [
        wp(1, "QB One", "QB", "QB", espn=20), wp(2, "QB Two", "QB", "QB", espn=16), wp(3, "QB Three", "QB", "BE", espn=18),
        wp(4, "RB One", "RB", "RB", espn=15, tier=2), wp(5, "RB Two", "RB", "RB", espn=9, fp=8, tier=5, opp="CLE", opp_rank=3),
        wp(6, "RB Three", "RB", "BE", espn=13, fp=14, tier=2, opp="DEN", opp_rank=28, grade="A"),
        wp(7, "WR One", "WR", "WR", espn=14), wp(8, "WR Two", "WR", "WR/TE", espn=12), wp(9, "TE One", "TE", "TE", espn=8),
        wp(10, "WR Three", "WR", "RB/WR/TE", espn=11), wp(11, "WR Four", "WR", "RB/WR/TE", espn=10), wp(12, "DST One", "D/ST", "D/ST", espn=7),
        wp(13, "WR Five", "WR", "BE", espn=6), wp(14, "RB Four", "RB", "BE", espn=4, season=40), wp(15, "TE Two", "TE", "BE", espn=5, season=60),
    ]
    for p in ps:
        p.score = weekly_score(p)
    return ps


def test_optimal_and_current_lineup(settings):
    settings.roster_slots = {"QB": 2, "RB": 2, "WR": 1, "WR/TE": 1, "TE": 1, "RB/WR/TE": 2, "D/ST": 1, "BE": 8, "IR": 1}
    ps = _roster()
    cur = current_lineup(ps, settings)
    assert cur["QB1"] == 1 and cur["RB2"] == 5 and cur["D/ST1"] == 12
    opt = optimal_lineup(ps, settings)
    assert {opt["QB1"], opt["QB2"]} == {1, 3}  # QB Three (18) over QB Two (16)
    assert {opt["RB1"], opt["RB2"]} == {4, 6}  # RB Three (13.5) over RB Two (8.5)
    assert 5 not in opt.values() and 2 not in opt.values()


def test_start_sit_moves_explain(settings):
    settings.roster_slots = {"QB": 2, "RB": 2, "WR": 1, "WR/TE": 1, "TE": 1, "RB/WR/TE": 2, "D/ST": 1, "BE": 8, "IR": 1}
    ps = _roster()
    moves, opt, cur_total, opt_total = start_sit_moves(ps, settings)
    assert opt_total > cur_total
    heads = [m.headline for m in moves]
    assert any("Start RB Three over RB Two at RB" in h for h in heads)
    assert any("Start QB Three over QB Two at QB" in h for h in heads)
    rb = next(m for m in moves if m.player_in.player_id == 6)
    assert "ESPN 13.0" in rb.quant and "FantasyPros 14.0" in rb.quant and "Net +5.0" in rb.quant
    assert "DEN" in rb.qual and "soft" in rb.qual and "Boris Chen" in rb.qual and "3 tiers above" in rb.qual


def test_no_move_below_threshold(settings):
    settings.roster_slots = {"QB": 1, "RB": 1, "BE": 2}
    ps = [wp(1, "A", "QB", "QB", espn=20), wp(2, "B", "RB", "RB", espn=10.5), wp(3, "C", "RB", "BE", espn=11)]
    for p in ps:
        p.score = weekly_score(p)
    moves, *_ = start_sit_moves(ps, settings, LineupWeights(swap_threshold=1.0))
    assert moves == []


def test_waiver_moves(settings):
    settings.roster_slots = {"QB": 2, "RB": 2, "WR": 1, "WR/TE": 1, "TE": 1, "RB/WR/TE": 2, "D/ST": 1, "BE": 8, "IR": 1}
    ps = _roster()
    fas = [wp(100, "FA Stud", "RB", "FA", espn=12, season=150, owned=40), wp(101, "FA Meh", "WR", "FA", espn=3, season=45, owned=2), wp(102, "FA Kicker", "K", "FA", espn=9, season=140)]
    for p in fas:
        p.score = weekly_score(p)
    moves = waiver_moves(ps, fas, settings)
    assert len(moves) == 1 and moves[0].headline == "Add FA Stud, drop RB Four"
    assert "150 pts vs Four 40" in moves[0].quant and "40% of ESPN leagues" in moves[0].qual


def test_slot_rows_cover_every_slot(settings):
    settings.roster_slots = {"QB": 2, "RB": 2, "WR": 1, "WR/TE": 1, "TE": 1, "RB/WR/TE": 2, "D/ST": 1, "BE": 8, "IR": 1}
    ps = _roster()
    rows = slot_rows(ps, settings, optimal_lineup(ps, settings))
    assert [r.label for r in rows[:10]] == ["QB", "QB", "RB", "RB", "WR", "WR/TE", "TE", "FLEX", "FLEX", "D/ST"]
    assert sum(1 for r in rows if r.label == "Bench") == 8 and rows[-1].label == "IR"
    assert rows[0].player and rows[0].player.name == "QB One" and rows[-1].player is None
    assert sum(1 for r in rows if r.player) == len(ps)
    assert slot_rows([], settings, {})[0].player is None and len(slot_rows([], settings, {})) == 19


def test_ir_players_are_never_recommended(settings):
    settings.roster_slots = {"QB": 1, "RB": 1, "BE": 1, "IR": 1}
    ps = [wp(1, "A", "QB", "QB", espn=20), wp(2, "B", "RB", "RB", espn=5), wp(3, "C", "RB", "IR", espn=15)]
    for p in ps:
        p.score = weekly_score(p)
    opt = optimal_lineup(ps, settings)
    assert opt["RB1"] == 2
