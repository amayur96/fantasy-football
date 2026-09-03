import pytest

from ffdraft.draft import ConflictError, DraftBoard, apply_keepers, apply_pick_trades, build_state, open_slots, snake_order
from ffdraft.models import KeeperEntry, PickTrade, SetupOverrides

IDS = list(range(1, 11))


def test_snake_order_reverses_even_rounds():
    picks = snake_order(IDS, 18)
    assert len(picks) == 180
    assert [p.owner_team_id for p in picks[:10]] == IDS
    assert [p.owner_team_id for p in picks[10:20]] == list(reversed(IDS))
    assert picks[19].overall == 20 and picks[19].round == 2 and picks[19].pick_in_round == 10


def test_pick_trade_reassigns_owner():
    picks = snake_order(IDS, 18)
    trades = [PickTrade(season=2026, round=2, original_team_id=2, owner_team_id=1), PickTrade(season=2027, round=1, original_team_id=2, owner_team_id=1)]
    assert apply_pick_trades(picks, trades, 2026) == []
    r2 = [p for p in picks if p.round == 2]
    assert sum(1 for p in r2 if p.owner_team_id == 1) == 2
    assert sum(1 for p in r2 if p.owner_team_id == 2) == 0
    assert all(p.owner_team_id == p.original_team_id for p in picks if p.round == 1)  # 2027 trade ignored


def test_keeper_consumes_slot_and_falls_back_when_traded():
    picks = snake_order(IDS, 18)
    apply_pick_trades(picks, [PickTrade(season=2026, round=4, original_team_id=3, owner_team_id=8)], 2026)
    names = {i: f"Team {i}" for i in IDS}
    warns = apply_keepers(picks, [KeeperEntry(team_id=3, player_id=500, player_name="X", round=4), KeeperEntry(team_id=1, player_id=501, player_name="Y", round=9)], 18, names)
    mine = [p for p in picks if p.owner_team_id == 3 and p.player_id == 500]
    assert mine and mine[0].round == 5 and mine[0].is_keeper
    assert any("R4" in w and "R5" in w for w in warns)
    t1 = [p for p in picks if p.owner_team_id == 1 and p.round == 9][0]
    assert t1.player_id == 501


def test_board_record_undo_and_turn_counting(settings, tmp_path):
    setup = SetupOverrides(other_keepers=[KeeperEntry(team_id=1, player_id=900, player_name="K", round=1)])
    board = DraftBoard(build_state(settings, setup), tmp_path / "draft.json")
    board.save()
    # team 1's R1 pick is a keeper, so first open pick is team 2's
    assert board.next_open().owner_team_id == 2
    assert board.picks_until_my_turn() == 1  # only team 2's pick before mine (slot 3)
    board.record_pick(10)
    with pytest.raises(ConflictError):
        board.record_pick(11)  # my pick, but "Taken" without force
    board.record_pick(11, mine=True)
    assert board.my_roster_ids() == [11]
    assert board.picks_until_my_turn() == 14  # picks 4..10 and 11..17 => 7 + 7
    board.undo()
    assert board.my_roster_ids() == [] and board.next_open().owner_team_id == 3
    board.undo()
    assert board.taken_ids() == {900}
    assert board.undo() is None  # keepers are never undone
    loaded = DraftBoard.load_or_build(settings, setup, tmp_path / "draft.json")
    assert loaded.state.picks[0].player_id == 900 and loaded.state.picks[0].is_keeper


def test_skip_and_duplicate(settings, tmp_path):
    board = DraftBoard(build_state(settings, SetupOverrides()), tmp_path / "d.json")
    board.skip_pick()
    assert board.next_open().overall == 2
    board.record_pick(5)
    with pytest.raises(ConflictError):
        board.record_pick(5, mine=True, force=True)


def test_open_slots_fills_flex_then_bench():
    slots = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "RB/WR/TE": 1, "D/ST": 1, "K": 1, "BE": 7}
    rem = open_slots(["RB", "RB", "RB", "WR", "RB"], slots)
    assert rem["RB"] == 0 and rem["RB/WR/TE"] == 0 and rem["BE"] == 6 and rem["WR"] == 1


def test_assign_out_of_order_and_undo_restores_exactly(settings, tmp_path):
    """Drafting is order-independent, and undo puts a pick back exactly as it was."""
    board = DraftBoard(build_state(settings, SetupOverrides(my_slot=3)), tmp_path / "d.json")
    board.assign(25, 500)  # jump ahead: pick #25 while #1 is still open
    assert board.picks[24].player_id == 500 and board.picks[24].source == "manual"
    assert board.next_open().overall == 1  # the clock still points at the earliest gap

    board.assign(1, 501)
    with pytest.raises(ConflictError):
        board.assign(2, 500)  # already drafted at #25

    board.assign(25, None)  # a mistake: clear it
    assert board.picks[24].player_id is None
    board.undo()
    assert board.picks[24].player_id == 500
    board.undo()
    assert board.picks[0].player_id is None
    assert board.taken_ids() == {500}


def test_undo_restores_a_cleared_keeper(settings, tmp_path):
    setup = SetupOverrides(my_slot=3, other_keepers=[KeeperEntry(team_id=1, player_id=900, player_name="K", round=1)])
    board = DraftBoard(build_state(settings, setup), tmp_path / "d.json")
    keeper = next(p for p in board.picks if p.is_keeper)
    board.assign(keeper.overall, None)
    assert board.picks[keeper.overall - 1].is_keeper is False
    board.undo()
    restored = board.picks[keeper.overall - 1]
    assert restored.is_keeper and restored.player_id == 900
