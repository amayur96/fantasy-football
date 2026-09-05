"""Color-coded draft board: view model, direct cell edits, and applying a Google Sheet grid."""
from __future__ import annotations

from datetime import datetime, timezone

from .draft import ConflictError, DraftBoard
from .espn.parse import match_player_by_name
from .models import (
    BoardCell,
    BoardColumn,
    BoardView,
    DraftPick,
    LeagueSettings,
    PickTrade,
    Player,
    SetupOverrides,
    SheetConflict,
    SheetGrid,
    SheetSyncReport,
    SheetUnmatched,
)

PALETTE = ["#4bc0c0", "#ea9999", "#f9cb9c", "#b6d7a8", "#ffe599", "#e06666", "#cfe2f3", "#6fa8dc", "#b4a7d6", "#d5a6bd"]


def team_color(team_id: int, settings: LeagueSettings, setup: SetupOverrides) -> str:
    if team_id in setup.team_colors:
        return setup.team_colors[team_id]
    ids = [t.team_id for t in settings.teams]
    return PALETTE[ids.index(team_id) % len(PALETTE)] if team_id in ids else "#dddddd"


def column_order(settings: LeagueSettings, setup: SetupOverrides, board: DraftBoard) -> list[int]:
    """Columns follow the draft order, so reordering the draft reorders the board left to right.

    The sheet's own column mapping is still used to match sheet columns to teams during a pull;
    it just doesn't dictate how the board is laid out.
    """
    order = list(board.state.slot_order)
    missing = [t.team_id for t in settings.teams if t.team_id not in order]
    return order + missing


def board_view(
    board: DraftBoard,
    settings: LeagueSettings,
    setup: SetupOverrides,
    players_by_id: dict[int, Player],
    conflicts: list[SheetConflict] | None = None,
) -> BoardView:
    header_for = {tid: h for h, tid in setup.sheet_columns.items() if tid}
    names = {t.team_id: t.name for t in settings.teams}
    owners = {t.team_id: (t.owner_names[0] if t.owner_names else "") for t in settings.teams}
    cols = [
        BoardColumn(
            team_id=tid, name=names.get(tid, str(tid)), owner=owners.get(tid, ""), color=team_color(tid, settings, setup),
            header=header_for.get(tid, ""), is_me=tid == settings.my_team_id,
        )
        for tid in column_order(settings, setup, board)
    ]
    clock = board.next_open()
    cells: list[BoardCell] = []
    for p in board.picks:
        pl = players_by_id.get(p.player_id) if p.player_id else None
        cells.append(BoardCell(
            overall=p.overall, round=p.round, original_team_id=p.original_team_id, owner_team_id=p.owner_team_id,
            player_id=p.player_id, player_name=pl.name if pl else None, position=pl.position if pl else None,
            raw_name=p.raw_name, is_keeper=p.is_keeper, unknown=p.unknown, source=p.source,
            on_clock=clock is not None and clock.overall == p.overall,
        ))
    return BoardView(
        season=settings.season, my_team_id=settings.my_team_id, rounds=settings.rounds, columns=cols, cells=cells,
        on_the_clock=clock, picks_until_my_turn=board.picks_until_my_turn(), warnings=board.state.warnings,
        conflicts=conflicts or [],
    )


def _pick_at(board: DraftBoard, original_team_id: int, rnd: int) -> DraftPick:
    for p in board.picks:
        if p.original_team_id == original_team_id and p.round == rnd:
            return p
    raise LookupError(f"No pick for team {original_team_id} in round {rnd}")


def record_trade(setup: SetupOverrides, season: int, rnd: int, original_team_id: int, owner_team_id: int) -> None:
    """Persist an ownership change as a PickTrade so board rebuilds keep it."""
    setup.pick_trades = [t for t in setup.pick_trades if not (t.season == season and t.round == rnd and t.original_team_id == original_team_id)]
    if owner_team_id != original_team_id:
        setup.pick_trades.append(PickTrade(season=season, round=rnd, original_team_id=original_team_id, owner_team_id=owner_team_id))


def set_cell(
    board: DraftBoard, setup: SetupOverrides, season: int, original_team_id: int, rnd: int,
    player_id: int | None = None, owner_team_id: int | None = None, clear: bool = False, raw_name: str | None = None,
) -> DraftPick:
    pick = _pick_at(board, original_team_id, rnd)
    board._push(pick)
    if owner_team_id is not None and owner_team_id != pick.owner_team_id:
        pick.owner_team_id = owner_team_id
        record_trade(setup, season, rnd, original_team_id, owner_team_id)
    if clear:
        pick.player_id, pick.raw_name, pick.unknown, pick.source, pick.taken_at = None, None, False, None, None
        pick.is_keeper = False
    elif player_id is not None:
        dup = next((q for q in board.picks if q.player_id == player_id and q.overall != pick.overall), None)
        if dup is not None:
            raise ConflictError(f"That player is already on the board at pick {dup.overall} (R{dup.round})")
        pick.player_id, pick.unknown, pick.source, pick.taken_at = player_id, False, "manual", datetime.now(timezone.utc)
        pick.raw_name = raw_name
    board.save()
    return pick


def resolve_columns(grid: SheetGrid, settings: LeagueSettings, setup: SetupOverrides, guess: "callable") -> dict[int, int]:
    """col index -> team_id using saved mapping, then name guessing, then last-one-standing."""
    out: dict[int, int] = {}
    for i, h in enumerate(grid.headers):
        tid = setup.sheet_columns.get(h) or (guess(h) if h else 0)
        if tid:
            out[i] = tid
    used = set(out.values())
    free_cols = [i for i in range(len(grid.headers)) if i not in out and grid.headers[i]]
    free_teams = [t.team_id for t in settings.teams if t.team_id not in used]
    if len(free_cols) == 1 and len(free_teams) == 1:
        out[free_cols[0]] = free_teams[0]
    return out


def apply_grid(
    board: DraftBoard, grid: SheetGrid, col_team: dict[int, int], settings: LeagueSettings, setup: SetupOverrides,
    pool: list[Player], dismissed: dict[str, str] | None = None,
) -> SheetSyncReport:
    """Pull the sheet onto the board.

    Anything the sheet would change that a human typed by hand is held back as a
    SheetConflict instead of being overwritten; `dismissed` maps a cell key to the sheet
    text the user has already rejected, so the same disagreement is not raised twice.
    """
    dismissed = dismissed or {}
    names = {t.team_id: t.name for t in settings.teams}
    by_id = {p.player_id: p for p in pool}
    report = SheetSyncReport(source=grid.source, fetched_at=grid.fetched_at)
    report.unmapped_columns = [h for i, h in enumerate(grid.headers) if i not in col_team and h]
    # colors: header color -> team, learned into setup.team_colors
    color_team: dict[str, int] = {}
    for i, c in enumerate(grid.header_colors):
        if c and i in col_team:
            color_team[c] = col_team[i]
            setup.team_colors[col_team[i]] = c
    seen: dict[tuple[int, int], SheetCellLike] = {}
    for cell in grid.cells:
        if cell.col not in col_team or cell.round < 1 or cell.round > settings.rounds:
            continue
        seen[(cell.col, cell.round)] = cell
    for col, tid in col_team.items():
        for rnd in range(1, settings.rounds + 1):
            try:
                pick = _pick_at(board, tid, rnd)
            except LookupError:
                continue
            cell = seen.get((col, rnd))
            header = grid.headers[col]
            # ownership from cell color
            if cell is not None and cell.color and cell.color in color_team:
                owner = color_team[cell.color]
                if owner != pick.owner_team_id:
                    pick.owner_team_id = owner
                    record_trade(setup, settings.season, rnd, tid, owner)
                    report.owner_changes += 1
            text = cell.text if cell else ""
            if not text:
                if pick.source == "sheet" and not pick.is_keeper:
                    pick.player_id, pick.raw_name, pick.unknown, pick.source, pick.taken_at = None, None, False, None, None
                    report.cleared += 1
                continue
            if pick.raw_name == text and (pick.player_id is not None or pick.unknown):
                continue  # already applied
            player = match_player_by_name(text, pool)
            if player is None:
                report.unmatched.append(SheetUnmatched(round=rnd, header=header, text=text, reason="no ESPN player matches this name"))
                if pick.player_id is not None and pick.source == "manual":
                    continue
                pick.raw_name, pick.unknown, pick.source, pick.taken_at = text, True, "sheet", datetime.now(timezone.utc)
                if not pick.is_keeper:
                    pick.player_id = None
                continue
            dup = next((q for q in board.picks if q.player_id == player.player_id and q.overall != pick.overall), None)
            # The sheet is the source of truth once it catches up, so it may move a player who was
            # entered by hand while we were waiting. Keepers are the one thing it never moves.
            if dup is not None and dup.is_keeper:
                report.unmatched.append(
                    SheetUnmatched(round=rnd, header=header, text=text, reason=f"{player.name} is a keeper at pick {dup.overall}")
                )
                pick.raw_name, pick.unknown, pick.source = text, True, "sheet"
                continue
            # Hold back anything that would overwrite or relocate a hand-typed entry.
            # Sheet-to-sheet edits still apply, so normal drafting stays quiet.
            key = f"{tid}:{rnd}"
            clash: str | None = None
            if pick.player_id is not None and pick.source == "manual" and pick.player_id != player.player_id:
                clash = "replace"
            elif dup is not None and dup.source == "manual":
                clash = "move"
            if clash is not None:
                if dismissed.get(key) != text:  # already decided against this exact sheet value
                    board_pl = by_id.get(pick.player_id) if pick.player_id else None
                    report.conflicts.append(SheetConflict(
                        key=key, kind=clash, overall=pick.overall, round=rnd, original_team_id=tid,
                        team_name=names.get(tid, str(tid)), header=header,
                        board_player_id=pick.player_id, board_player_name=board_pl.name if board_pl else None,
                        sheet_text=text, sheet_player_id=player.player_id, sheet_player_name=player.name,
                        from_overall=dup.overall if clash == "move" and dup else None,
                        from_round=dup.round if clash == "move" and dup else None,
                        detected_at=datetime.now(timezone.utc),
                    ))
                continue
            if dup is not None:
                report.moved.append(f"{player.name}: pick {dup.overall} \u2192 {pick.overall} (sheet)")
                dup.player_id, dup.raw_name, dup.unknown, dup.source, dup.taken_at = None, None, False, None, None
            pick.player_id, pick.raw_name, pick.unknown, pick.taken_at = player.player_id, text, False, datetime.now(timezone.utc)
            pick.source = "keeper" if pick.is_keeper else "sheet"
            report.applied += 1
    board.save()
    return report


def apply_conflict(board: DraftBoard, conflict: SheetConflict) -> DraftPick:
    """Take the sheet's side of a held-back disagreement, and record it as undoable."""
    pick = _pick_at(board, conflict.original_team_id, conflict.round)
    # For a "move", the sheet's player is still sitting in the cell you typed him into.
    sources = [
        q for q in board.picks
        if q.player_id == conflict.sheet_player_id and q.overall != pick.overall
    ]
    keeper = next((q for q in sources if q.is_keeper), None)
    if keeper is not None:
        raise ConflictError(f"{conflict.sheet_player_name} is a keeper at pick {keeper.overall}")
    board._push_many(pick, *sources)
    for source in sources:
        source.player_id, source.raw_name, source.unknown, source.source, source.taken_at = None, None, False, None, None
    pick.player_id, pick.raw_name, pick.unknown = conflict.sheet_player_id, conflict.sheet_text, False
    pick.source = "keeper" if pick.is_keeper else "sheet"
    pick.taken_at = datetime.now(timezone.utc)
    board.save()
    return pick


SheetCellLike = object  # typing alias for readability above
