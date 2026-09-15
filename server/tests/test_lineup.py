from ffdraft.lineup import LineupWeights, current_lineup, explain_start, optimal_lineup, slot_rows, start_sit_moves, waiver_moves, weekly_score
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
    why = rb.why
    # quantitative: both projection sources and the blended edge
    assert "ESPN projects Three for 13.0 against 9.0 for Two" in why and "FantasyPros has 14.0 to 8.0" in why and "5.0 more points" in why
    # qualitative: expert grade, tier gap, and both matchups with a read on each
    assert "A start grade" in why and "Boris Chen has Three 3 tiers higher (tier 2 vs 5)" in why
    assert "The matchups point the same way" in why and "DEN, 28th against running backs (soft)" in why and "CLE, 3rd against running backs (tough)" in why
    assert why.startswith("RB Three is the clear start over RB Two at RB this week.")


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
    why = moves[0].why
    assert why.startswith("FA Stud is worth a claim, with RB Four the drop.")
    assert "Stud for 150 points against 40 for Four, a +110 swing" in why
    assert "rostered in 40% of ESPN leagues, so he should still be there when waivers run" in why


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


def _tints(rows, recommended):
    """What the dashboard highlights: starters whose slot changes, bench players promoted."""
    promoted = set(recommended.values())
    amber = [r.key for r in rows if r.slot not in ("BE", "IR") and r.recommended_player_id is not None
             and r.recommended_player_id != (r.player.player_id if r.player else None)]
    green = [r.key for r in rows if r.slot == "BE" and r.player and r.player.player_id in promoted]
    return amber, green


def test_reshuffling_the_same_starters_is_not_a_recommendation(settings):
    """A player sitting in WR instead of WR/TE scores exactly the same, so nothing should light up."""
    settings.roster_slots = {"WR": 1, "WR/TE": 1, "BE": 2}
    ps = [wp(1, "WR Weaker", "WR", "WR", espn=12), wp(2, "WR Better", "WR", "WR/TE", espn=14)]
    for p in ps:
        p.score = weekly_score(p)
    moves, recommended, cur_total, rec_total = start_sit_moves(ps, settings)
    assert moves == []
    assert cur_total == rec_total  # a permutation cannot gain a point
    amber, green = _tints(slot_rows(ps, settings, recommended), recommended)
    assert amber == [] and green == []


def test_a_swap_too_small_to_recommend_is_not_highlighted(settings):
    settings.roster_slots = {"QB": 1, "RB": 1, "BE": 2}
    ps = [wp(1, "A", "QB", "QB", espn=20), wp(2, "B", "RB", "RB", espn=10.5), wp(3, "C", "RB", "BE", espn=11)]
    for p in ps:
        p.score = weekly_score(p)
    moves, recommended, _, _ = start_sit_moves(ps, settings, LineupWeights(swap_threshold=1.0))
    assert moves == []
    amber, green = _tints(slot_rows(ps, settings, recommended), recommended)
    assert amber == [] and green == []


def test_every_recommended_move_is_highlighted(settings):
    settings.roster_slots = {"QB": 2, "RB": 2, "WR": 1, "WR/TE": 1, "TE": 1, "RB/WR/TE": 2, "D/ST": 1, "BE": 8, "IR": 1}
    ps = _roster()
    moves, recommended, cur_total, rec_total = start_sit_moves(ps, settings)
    assert moves and rec_total > cur_total
    amber, green = _tints(slot_rows(ps, settings, recommended), recommended)
    # one amber starter row and one green bench row for each move, and nothing else
    assert len(amber) == len(moves) and len(green) == len(moves)
    assert {m.player_in.player_id for m in moves} == {r.recommended_player_id for r in slot_rows(ps, settings, recommended) if r.key in amber}


def test_a_replacement_must_be_eligible_for_the_slot_it_takes(settings):
    """The bench RB cannot be 'started over' the D/ST — he is not allowed in that slot."""
    settings.roster_slots = {"RB": 1, "D/ST": 1, "BE": 2}
    ps = [wp(1, "RB Starter", "RB", "RB", espn=14), wp(2, "DST One", "D/ST", "D/ST", espn=2), wp(3, "RB Bench", "RB", "BE", espn=20)]
    for p in ps:
        p.score = weekly_score(p)
    moves, recommended, _, _ = start_sit_moves(ps, settings)
    for m in moves:
        assert m.player_out is None or m.player_out.position != "D/ST"
    assert recommended.get("D/ST1") == 2


def _pair(**kw):
    """A starter (out) and a bench player (in) at the same position, with overridable fields."""
    pin = wp(1, "Bench Guy", "RB", "BE", espn=kw.pop("in_espn", 15), fp=kw.pop("in_fp", 15), **{k[3:]: v for k, v in kw.items() if k.startswith("in_")})
    pout = wp(2, "Starter Guy", "RB", "RB", espn=kw.pop("out_espn", 8), fp=kw.pop("out_fp", 8), **{k[4:]: v for k, v in kw.items() if k.startswith("out_")})
    for p in (pin, pout):
        p.score = weekly_score(p)
    return pin, pout


def test_explanation_verdict_scales_with_the_edge():
    pin, pout = _pair()
    assert explain_start(pin, pout, "RB", 7.0).startswith("Bench Guy is the clear start over Starter Guy at RB this week.")
    assert explain_start(pin, pout, "RB", 3.0).startswith("Bench Guy is the better play than Starter Guy at RB this week.")
    assert explain_start(pin, pout, "RB", 1.2).startswith("Bench Guy has a slight edge on Starter Guy at RB this week.")
    assert explain_start(pin, None, "RB/WR/TE", 15.0).startswith("Bench Guy should go into the empty FLEX slot.")


def test_explanation_says_when_the_sources_disagree():
    pin, pout = _pair(in_espn=12, in_fp=9, out_espn=8, out_fp=11)  # ESPN likes the bench guy, FantasyPros the starter
    why = explain_start(pin, pout, "RB", 1.0)
    assert "the two sources split, but the blend still favours Bench Guy by 1.0" in why


def test_explanation_leads_with_a_bye_or_injury():
    pin, pout = _pair(out_bye=True)
    assert explain_start(pin, pout, "RB", pin.score).startswith("Starter Guy is on bye, so Bench Guy should take his RB spot.")
    pin, pout = _pair(out_inj="OUT")
    assert "Starter Guy is listed out, so Bench Guy should take his RB spot." in explain_start(pin, pout, "RB", pin.score)
    pin, pout = _pair(in_inj="QUESTIONABLE")
    assert "Bench Guy is listed questionable, which is already discounted in his projection." in explain_start(pin, pout, "RB", 5.0)


def test_explanation_flags_a_matchup_that_cuts_the_other_way():
    pin, pout = _pair(in_opp="BUF", in_opp_rank=2, out_opp="CAR", out_opp_rank=30)
    why = explain_start(pin, pout, "RB", 5.0)
    assert "The matchup is the one argument for Starter Guy: Bench Guy faces BUF, 2nd against running backs (tough), while Starter Guy faces CAR, 30th against running backs (soft)." in why


def test_explanation_only_claims_what_the_data_supports():
    pin = wp(1, "Bench Guy", "RB", "BE", espn=15)
    pout = wp(2, "Starter Guy", "RB", "RB", espn=8)
    for p in (pin, pout):
        p.score = weekly_score(p)
    why = explain_start(pin, pout, "RB", 7.0)
    assert "FantasyPros" not in why and "Boris" not in why and "faces" not in why and "%" not in why
    assert why == "Bench Guy is the clear start over Starter Guy at RB this week. ESPN projects Bench Guy for 15.0 against 8.0 for Starter Guy \u2014 7.0 more points in the blended projection."


def test_explanation_uses_surnames_when_they_do_not_collide():
    pin = wp(1, "Breece Hall", "RB", "BE", espn=15)
    pout = wp(2, "Stefon Diggs", "WR", "RB/WR/TE", espn=8)
    for p in (pin, pout):
        p.score = weekly_score(p)
    assert "ESPN projects Hall for 15.0 against 8.0 for Diggs" in explain_start(pin, pout, "RB/WR/TE", 7.0)
