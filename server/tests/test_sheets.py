from datetime import datetime, timezone

from ffdraft.board import apply_grid, board_view, resolve_columns, set_cell
from ffdraft.draft import DraftBoard, build_state
from ffdraft.models import KeeperEntry, SetupOverrides, SheetCell, SheetGrid
from ffdraft.sheets import parse_rows

HEADERS = [f"Owner{i}" for i in range(1, 11)]


def _rows():
    rows = [["", *HEADERS]]
    for r in range(1, 19):
        rows.append([f"Round {r}"] + [""] * 10)
    rows[1][1] = "RB Player 1"      # Owner1 R1
    rows[1][3] = "QB Player 1"      # Owner3 (me) R1
    rows[2][2] = "Nobody Real"      # Owner2 R2 -> unmatched
    rows[9][1] = "WR Player 2"      # Owner1 R9
    rows.append(["Keepers", "WR Player 2", "", "", "", "", "", "", "", "", ""])
    return rows


def _colors(rows):
    cols = [[None] * 11 for _ in rows]
    for c in range(1, 11):
        cols[0][c] = f"#c{c:02d}000"
    cols[2][1] = "#c08000"  # Owner1's R2 pick colored like Owner8 -> traded
    return cols


def test_parse_rows_finds_header_rounds_and_keepers():
    grid = parse_rows(_rows(), _colors(_rows()), source="oauth")
    assert grid.headers == HEADERS
    assert grid.header_colors[0] == "#c01000"
    assert grid.keepers[0] == "WR Player 2"
    by = {(c.round, c.col): c for c in grid.cells}
    assert by[(1, 0)].text == "RB Player 1" and by[(1, 2)].text == "QB Player 1"
    assert by[(2, 0)].color == "#c08000" and by[(2, 0)].text == ""


def test_parse_rows_with_two_header_rows():
    rows = [["", "First", "Second", "Third", "Fourth"], ["", "A", "B", "C", "D"], ["Round 1", "x", "", "", ""], ["Round 2", "", "", "", ""]]
    grid = parse_rows(rows, None)
    assert grid.headers == ["A", "B", "C", "D"] and grid.source == "csv"


def test_resolve_columns_guesses_and_last_one_standing(settings):
    grid = parse_rows(_rows(), None)
    setup = SetupOverrides()

    def guess(h):  # pretend Owner3 (me) has an unrecognizable header
        return 0 if h == "Owner3" else int(h.replace("Owner", ""))

    m = resolve_columns(grid, settings, setup, guess)
    assert m[2] == 3 and len(m) == 10


def test_apply_grid_sets_picks_owners_and_reports(settings, players, tmp_path):
    setup = SetupOverrides(my_slot=3)
    board = DraftBoard(build_state(settings, setup), tmp_path / "d.json")
    rows = _rows()
    grid = parse_rows(rows, _colors(rows), source="oauth")
    mapping = {i: i + 1 for i in range(10)}
    rep = apply_grid(board, grid, mapping, settings, setup, players)
    assert rep.applied == 3 and rep.owner_changes == 1
    assert [u.text for u in rep.unmatched] == ["Nobody Real"]
    picks = {(p.original_team_id, p.round): p for p in board.picks}
    assert picks[(1, 1)].player_id == 115 and picks[(1, 1)].source == "sheet"
    assert picks[(3, 1)].player_id == 101
    assert picks[(2, 2)].unknown and picks[(2, 2)].raw_name == "Nobody Real"
    assert picks[(1, 2)].owner_team_id == 8
    assert any(t.round == 2 and t.original_team_id == 1 and t.owner_team_id == 8 for t in setup.pick_trades)
    assert setup.team_colors[1] == "#c01000"
    # clock skips the filled/unknown picks
    assert board.next_open().overall == 2 and board.next_open().owner_team_id == 2
    # re-applying is idempotent; clearing a cell in the sheet clears a sheet-sourced pick
    rep2 = apply_grid(board, grid, mapping, settings, setup, players)
    assert rep2.applied == 0
    rows[1][1] = ""
    rep3 = apply_grid(board, parse_rows(rows, None), mapping, settings, setup, players)
    assert rep3.cleared == 1 and picks[(1, 1)].player_id is None


def test_set_cell_and_board_view(settings, players, tmp_path):
    setup = SetupOverrides(my_slot=3, other_keepers=[KeeperEntry(team_id=1, player_id=117, player_name="RB Player 3", round=9)])
    board = DraftBoard(build_state(settings, setup), tmp_path / "d.json")
    set_cell(board, setup, 2026, original_team_id=3, rnd=4, owner_team_id=8)
    assert any(t.round == 4 and t.owner_team_id == 8 for t in setup.pick_trades)
    set_cell(board, setup, 2026, original_team_id=1, rnd=1, player_id=115)
    view = board_view(board, settings, setup, {p.player_id: p for p in players})
    cells = {(c.original_team_id, c.round): c for c in view.cells}
    assert cells[(1, 1)].player_name == "RB Player 1" and cells[(1, 1)].source == "manual"
    assert cells[(3, 4)].owner_team_id == 8 and cells[(1, 9)].is_keeper
    assert len(view.columns) == 10 and all(c.color.startswith("#") for c in view.columns)
    assert view.on_the_clock is not None and view.on_the_clock.overall == 2
    set_cell(board, setup, 2026, original_team_id=1, rnd=1, clear=True)
    assert board.picks[0].player_id is None


def test_board_columns_follow_the_draft_order(settings, players, tmp_path):
    """Reordering the draft reorders the board left to right."""
    setup = SetupOverrides(slot_order=[5, 3, 1, 2, 4, 6, 7, 8, 9, 10])
    board = DraftBoard(build_state(settings, setup), tmp_path / "d.json")
    view = board_view(board, settings, setup, {p.player_id: p for p in players})
    assert [c.team_id for c in view.columns] == [5, 3, 1, 2, 4, 6, 7, 8, 9, 10]
    assert view.columns[1].is_me  # my team is 3, now in the second column

    # a stale sheet column mapping must not override it
    setup.sheet_columns = {f"Owner{i}": i for i in range(1, 11)}
    board2 = DraftBoard(build_state(settings, setup), tmp_path / "d2.json")
    view2 = board_view(board2, settings, setup, {p.player_id: p for p in players})
    assert [c.team_id for c in view2.columns] == [5, 3, 1, 2, 4, 6, 7, 8, 9, 10]


def test_sheet_moves_a_manual_pick_but_never_a_keeper(settings, players, tmp_path):
    """The sheet is the source of truth once it catches up; keepers are the exception."""
    setup = SetupOverrides(my_slot=3)
    board = DraftBoard(build_state(settings, setup), tmp_path / "d.json")
    rb1 = next(p for p in players if p.name == "RB Player 1")
    board.assign(50, rb1.player_id)  # entered by hand while the sheet lagged

    rows = _rows()  # the sheet has RB Player 1 at Owner1's round 1
    rep = apply_grid(board, parse_rows(rows, None), {i: i + 1 for i in range(10)}, settings, setup, players)
    assert board.picks[49].player_id is None  # the manual entry was vacated
    assert any(p.player_id == rb1.player_id and p.round == 1 for p in board.picks)
    assert any("RB Player 1" in m for m in rep.moved)

    # a keeper is never moved
    board2 = DraftBoard(build_state(settings, SetupOverrides(my_slot=3, other_keepers=[
        KeeperEntry(team_id=5, player_id=rb1.player_id, player_name="RB Player 1", round=9)])), tmp_path / "d2.json")
    rep2 = apply_grid(board2, parse_rows(rows, None), {i: i + 1 for i in range(10)}, settings, setup, players)
    assert any("keeper" in u.reason for u in rep2.unmatched)
    assert any(p.player_id == rb1.player_id and p.is_keeper for p in board2.picks)
