from ffdraft.history import detect_my_column, history_from_grid, resolve_history_columns, roster_from_grid
from ffdraft.sheets import parse_rows


def _grid():
    rows = [["", "First", "Second", "Third"], ["", "Alex", "Owner1", "Owner2"]]
    rows.append(["Round 1", "RB Player 1", "QB Player 1", "WR Player 1"])
    rows.append(["Round 2", "RB Player 2", "QB Player 2", "WR Player 2"])
    rows.append(["Round 3", "RB Player 3", "QB Player 3", "WR Player 3"])
    rows.append(["Round 4", "RB Player 4", "", ""])
    rows.append(["", "RB Player 9", "", "WR Player 9"])  # in-season pickups, no round label
    rows.append(["Keepers", "RB Plaaayer 2", "QB Player 1, QB Player 3", "NONE"])
    return parse_rows(rows, None)


def test_history_from_grid_rounds_and_keepers(players):
    grid = _grid()
    picks = history_from_grid(grid, 2025, {0: 3, 1: 1, 2: 2}, players)
    by = {(p.team_id, p.round_num): p for p in picks}
    assert by[(3, 2)].player_name == "RB Player 2" and by[(3, 2)].keeper_status  # joke spelling still matches
    assert by[(3, 1)].keeper_status is False
    assert by[(1, 1)].keeper_status and by[(1, 3)].keeper_status and not by[(1, 2)].keeper_status  # comma-separated
    assert by[(2, 1)].keeper_status is False
    assert len(picks) == 10


def test_detect_my_column_by_overlap(players):
    grid = _grid()
    ids = {p.player_id for p in players if p.name in ("RB Player 1", "RB Player 2", "RB Player 3", "Nobody")}
    assert detect_my_column(grid, ids, players) == 0
    assert detect_my_column(grid, {1}, players) is None


def test_resolve_history_columns_prefers_overlap_for_me(players):
    grid = _grid()
    ids = {p.player_id for p in players if p.name.startswith("RB Player")}
    m = resolve_history_columns(grid, 3, ids, players, {"Owner1": 1}, lambda h: 2 if h == "Owner2" else 0)
    assert m == {0: 3, 1: 1, 2: 2}


def test_extras_and_roster_from_grid(players):
    grid = _grid()
    assert [(c.col, c.text) for c in grid.extras] == [(0, "RB Player 9"), (2, "WR Player 9")]
    roster = roster_from_grid(grid, 2025, 0, 3, players)
    assert [r.name for r in roster] == ["RB Player 1", "RB Player 2", "RB Player 3", "RB Player 4", "RB Player 9"]
    assert all(r.team_id == 3 for r in roster)
    # extras are not draft picks
    assert all(p.round_num >= 1 for p in history_from_grid(grid, 2025, {0: 3}, players))


def test_roster_from_grid_skips_traded_away_cells(players):
    grid = _grid()
    grid.header_colors = ["#aaa", "#bbb", "#ccc"]
    for c in grid.cells:
        c.color = "#bbb" if (c.col == 0 and c.round == 3) else "#aaa" if c.col == 0 else None
    roster = roster_from_grid(grid, 2025, 0, 3, players)
    assert "RB Player 3" not in [r.name for r in roster]
