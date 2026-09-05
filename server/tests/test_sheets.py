from datetime import datetime, timezone

from ffdraft.board import apply_conflict, apply_grid, board_view, resolve_columns, set_cell
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


def test_sheet_holds_back_rather_than_moving_a_manual_pick(settings, players, tmp_path):
    """A hand-typed entry is never silently relocated; the disagreement is raised instead."""
    setup = SetupOverrides(my_slot=3)
    board = DraftBoard(build_state(settings, setup), tmp_path / "d.json")
    rb1 = next(p for p in players if p.name == "RB Player 1")
    board.assign(50, rb1.player_id)  # entered by hand while the sheet lagged

    rows = _rows()  # the sheet has RB Player 1 at Owner1's round 1
    rep = apply_grid(board, parse_rows(rows, None), {i: i + 1 for i in range(10)}, settings, setup, players)

    assert board.picks[49].player_id == rb1.player_id  # still where you typed him
    assert not any(p.player_id == rb1.player_id and p.round == 1 for p in board.picks)
    assert rep.moved == []
    c = next(c for c in rep.conflicts if c.sheet_player_id == rb1.player_id)
    assert c.kind == "move" and c.from_overall == 50 and c.round == 1
    assert c.sheet_player_name == "RB Player 1" and c.header == "Owner1"


def test_sheet_holds_back_rather_than_replacing_a_manual_pick(settings, players, tmp_path):
    setup = SetupOverrides(my_slot=3)
    board = DraftBoard(build_state(settings, setup), tmp_path / "d.json")
    other = next(p for p in players if p.name == "RB Player 5")
    owner1_r1 = next(p for p in board.picks if p.original_team_id == 1 and p.round == 1)
    board.assign(owner1_r1.overall, other.player_id)  # you typed a different player in that slot

    rep = apply_grid(board, parse_rows(_rows(), None), {i: i + 1 for i in range(10)}, settings, setup, players)

    assert owner1_r1.player_id == other.player_id  # untouched
    c = next(c for c in rep.conflicts if c.key == f"1:{owner1_r1.round}")
    assert c.kind == "replace"
    assert c.board_player_name == "RB Player 5" and c.sheet_player_name == "RB Player 1"


def test_unmatched_sheet_name_does_not_replace_a_manual_pick(settings, players, tmp_path):
    setup = SetupOverrides(my_slot=3)
    board = DraftBoard(build_state(settings, setup), tmp_path / "d.json")
    manual = next(p for p in players if p.name == "RB Player 5")
    owner2_r2 = next(p for p in board.picks if p.original_team_id == 2 and p.round == 2)
    board.assign(owner2_r2.overall, manual.player_id)

    rep = apply_grid(board, parse_rows(_rows(), None), {i: i + 1 for i in range(10)}, settings, setup, players)

    assert [u.text for u in rep.unmatched] == ["Nobody Real"]
    assert owner2_r2.player_id == manual.player_id
    assert owner2_r2.source == "manual"
    assert not owner2_r2.unknown


def test_sheet_to_sheet_edits_still_apply_without_asking(settings, players, tmp_path):
    """Correcting a typo in the spreadsheet must not interrupt a live draft."""
    setup = SetupOverrides(my_slot=3)
    board = DraftBoard(build_state(settings, setup), tmp_path / "d.json")
    cols = {i: i + 1 for i in range(10)}
    apply_grid(board, parse_rows(_rows(), None), cols, settings, setup, players)

    rows = _rows()
    rows[1][1] = "RB Player 7"  # the sheet changes its own entry
    rep = apply_grid(board, parse_rows(rows, None), cols, settings, setup, players)

    assert rep.conflicts == []
    rb7 = next(p for p in players if p.name == "RB Player 7")
    assert any(p.player_id == rb7.player_id and p.round == 1 for p in board.picks)


def test_dismissed_conflict_is_not_raised_again(settings, players, tmp_path):
    setup = SetupOverrides(my_slot=3)
    board = DraftBoard(build_state(settings, setup), tmp_path / "d.json")
    mine = next(p for p in players if p.name == "RB Player 5")
    owner1_r1 = next(p for p in board.picks if p.original_team_id == 1 and p.round == 1)
    board.assign(owner1_r1.overall, mine.player_id)
    cols = {i: i + 1 for i in range(10)}

    rep = apply_grid(board, parse_rows(_rows(), None), cols, settings, setup, players)
    key = rep.conflicts[0].key
    dismissed = {key: rep.conflicts[0].sheet_text}  # you chose "keep mine"

    again = apply_grid(board, parse_rows(_rows(), None), cols, settings, setup, players, dismissed)
    assert not any(c.key == key for c in again.conflicts)
    assert owner1_r1.player_id == mine.player_id

    # but if the sheet changes to something else, that is a new disagreement worth raising
    rows = _rows()
    rows[1][1] = "RB Player 7"
    third = apply_grid(board, parse_rows(rows, None), cols, settings, setup, players, dismissed)
    assert any(c.key == key and c.sheet_player_name == "RB Player 7" for c in third.conflicts)


def test_apply_conflict_takes_the_sheets_side(settings, players, tmp_path):
    setup = SetupOverrides(my_slot=3)
    board = DraftBoard(build_state(settings, setup), tmp_path / "d.json")
    rb1 = next(p for p in players if p.name == "RB Player 1")
    board.assign(50, rb1.player_id)
    rep = apply_grid(board, parse_rows(_rows(), None), {i: i + 1 for i in range(10)}, settings, setup, players)

    pick = apply_conflict(board, rep.conflicts[0])

    assert pick.player_id == rb1.player_id and pick.round == 1 and pick.source == "sheet"
    assert board.picks[49].player_id is None  # vacated only once you said so
    assert board.state.history  # and it is undoable

    board.undo()

    assert board.picks[pick.overall - 1].player_id is None
    assert board.picks[49].player_id == rb1.player_id


def test_keeper_is_never_moved_by_the_sheet(settings, players, tmp_path):
    setup = SetupOverrides(my_slot=3)
    rb1 = next(p for p in players if p.name == "RB Player 1")
    board = DraftBoard(build_state(settings, SetupOverrides(my_slot=3, other_keepers=[
        KeeperEntry(team_id=5, player_id=rb1.player_id, player_name="RB Player 1", round=9)])), tmp_path / "d2.json")
    rep = apply_grid(board, parse_rows(_rows(), None), {i: i + 1 for i in range(10)}, settings, setup, players)
    assert any("keeper" in u.reason for u in rep.unmatched)
    assert any(p.player_id == rb1.player_id and p.is_keeper for p in board.picks)
    assert rep.conflicts == []  # a keeper clash is reported, not a decision to make
