from ffdraft.draft import DraftBoard, build_state
from ffdraft.models import SetupOverrides
from ffdraft.recommend import best_by_position, recommend


def _board(settings, tmp_path, setup=None):
    return DraftBoard(build_state(settings, setup or SetupOverrides(my_slot=3)), tmp_path / "d.json")


def test_no_k_or_dst_early(settings, rankings, tmp_path):
    recs = recommend(_board(settings, tmp_path), rankings, settings)
    assert all(r.player.position not in ("K", "D/ST") for r in recs[:6])
    assert recs[0].reason.startswith("Fills your open")


def test_need_multiplier_prefers_open_slot(settings, rankings, tmp_path):
    board = _board(settings, tmp_path)
    # put the top 5 WRs on my roster (starters + flex + bench target) by filling my first five picks directly
    wrs = [p.player_id for p in rankings.by_pos["WR"][:5]]
    mine = [p for p in board.my_picks()][:5]
    for slot, pid in zip(mine, wrs):
        slot.player_id = pid
    recs = recommend(board, rankings, settings)
    top_wr = next(r for r in recs if r.player.position == "WR")
    assert top_wr.components["need_mult"] < 0.5
    assert "set at WR" in top_wr.reason
    assert recs[0].player.position != "WR"


def test_cliff_bonus_fires_on_last_of_tier(settings, rankings, tmp_path):
    board = _board(settings, tmp_path)
    tier1 = [p for p in rankings.by_pos["TE"] if p.tier == 1]
    for p in tier1[:-1]:  # everyone in TE tier 1 but the last one is gone
        board.record_pick(p.player_id, force=True)
    recs = recommend(board, rankings, settings)
    last = next(r for r in recs if r.player.player_id == tier1[-1].player_id)
    assert last.components["cliff_bonus"] > 0
    assert "Last of TE tier 1" in last.reason


def test_best_by_position_covers_positions(settings, rankings, tmp_path):
    recs = recommend(_board(settings, tmp_path), rankings, settings)
    bp = best_by_position(recs)
    assert {"QB", "RB", "WR", "TE"} <= set(bp)


def test_recommendations_are_ten_deep_with_sources_and_bullets(settings, rankings, tmp_path):
    from ffdraft.recommend import roster_needs, top

    board = _board(settings, tmp_path)
    for p in rankings.overall[:3]:
        p.adp, p.fp_rank, p.fp_pos_rank, p.bc_tier = 5.0, 40, f"{p.position}3", 2  # experts much lower than the market
    recs = recommend(board, rankings, settings)
    assert len(top(recs)) == 10
    r = next(r for r in recs if r.player.fp_rank == 40)
    assert "ESPN ADP #5" in r.sources and "FantasyPros #40" in r.sources and "Boris Chen tier 2" in r.sources
    assert r.fit and r.why and r.why[0] == r.fit
    assert any("paying above the expert price" in w for w in r.why)

    needs = roster_needs(board, rankings, settings)
    assert needs["roster_size"] == 0
    assert "QB" in needs["unfilled_starters"] and "RB" in needs["unfilled_starters"]
    assert set(needs["thin_positions"]) >= {"RB", "WR"}


def test_strategy_explains_roster_and_market(settings, rankings, tmp_path):
    from ffdraft.recommend import market_context, team_open_slots

    board = _board(settings, tmp_path)
    # Rivals load up on RBs; I take none.
    rbs = [p.player_id for p in rankings.by_pos["RB"][:6]]
    for i, pid in enumerate(rbs):
        board.assign(i + 1, pid)  # picks 1-6 belong to other teams at my slot 3... except #3
    m = market_context(board, rankings, settings)
    assert m.run["RB"] == 6 and m.run_window == 6
    assert m.total_rivals == 9
    assert m.rivals_needing["QB"] == 9  # nobody has a QB yet

    recs = recommend(board, rankings, settings)
    qb = next(r for r in recs if r.player.position == "QB")
    assert "still need a starting QB" in qb.strategy_market
    assert qb.strategy_team and "still need to fill" in qb.strategy_team

    rb = next(r for r in recs if r.player.position == "RB")
    assert "of the last 6 picks were RBs" in rb.strategy_market

    slots = team_open_slots(board, rankings, settings)
    assert slots[settings.my_team_id]["QB"] == settings.roster_slots["QB"]
