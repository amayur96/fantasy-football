"""Draft history rebuilt from the league's Google Sheet tabs (one per season).

The league enters its draft into ESPN after the fact, so ESPN's rounds and keeper flags are unreliable.
The sheet is the source of truth: 'Round N' rows give the round, the 'Keepers' row says who was kept
into that season.
"""
from __future__ import annotations

import re
from typing import Callable

from .espn.parse import match_player_by_name, normalize_name
from .models import DraftHistoryPick, Player, RosterEntry, SheetGrid


def _squash(s: str) -> str:
    """'PPPPuuka' -> 'puka', 'Taylllllor' -> 'taylor' (the sheet's keeper row has joke spellings)."""
    return re.sub(r"(.)\1+", r"\1", normalize_name(s))


def _keeper_names(cell: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,/&]| and ", cell) if part.strip() and part.strip().lower() != "none"]


def _is_keeper(player: Player, keeper_cells: list[str], pool: list[Player]) -> bool:
    target = _squash(player.name)
    last = target.split(" ")[-1]
    for text in keeper_cells:
        hit = match_player_by_name(text, pool)
        if hit is not None and hit.player_id == player.player_id:
            return True
        sq = _squash(text)
        if sq == target or (len(sq) >= 4 and (sq == last or sq.split(" ")[-1] == last)):
            return True
    return False


def detect_my_column(grid: SheetGrid, my_player_ids: set[int], pool: list[Player]) -> int | None:
    """Which column is mine: the one whose names overlap most with my ESPN picks that season."""
    if not my_player_ids:
        return None
    best, best_n = None, 0
    for col in range(len(grid.headers)):
        ids = set()
        for c in grid.cells:
            if c.col == col and c.text:
                hit = match_player_by_name(c.text, pool)
                if hit:
                    ids.add(hit.player_id)
        n = len(ids & my_player_ids)
        if n > best_n:
            best, best_n = col, n
    return best if best_n >= 3 else None


def history_from_grid(grid: SheetGrid, year: int, col_team: dict[int, int], pool: list[Player]) -> list[DraftHistoryPick]:
    out: list[DraftHistoryPick] = []
    keepers_by_col: dict[int, list[str]] = {i: _keeper_names(k) for i, k in enumerate(grid.keepers)}
    seen: set[int] = set()
    for cell in sorted(grid.cells, key=lambda c: (c.round, c.col)):
        if not cell.text:
            continue
        player = match_player_by_name(cell.text, pool)
        if player is None or player.player_id in seen:
            continue
        seen.add(player.player_id)
        out.append(
            DraftHistoryPick(
                season=year,
                team_id=col_team.get(cell.col, 0),
                player_id=player.player_id,
                player_name=player.name,
                round_num=cell.round,
                round_pick=cell.col + 1,
                keeper_status=_is_keeper(player, keepers_by_col.get(cell.col, []), pool),
            )
        )
    return out


def resolve_history_columns(
    grid: SheetGrid, my_team_id: int, my_espn_pick_ids: set[int], pool: list[Player], saved: dict[str, int], guess: Callable[[str], int]
) -> dict[int, int]:
    """Column -> team for a past season's tab: saved header mapping, name guess, and my column by roster overlap."""
    out: dict[int, int] = {}
    for i, h in enumerate(grid.headers):
        tid = saved.get(h) or (guess(h) if h else 0)
        if tid:
            out[i] = tid
    mine = detect_my_column(grid, my_espn_pick_ids, pool)
    if mine is not None:
        for i in [i for i, t in out.items() if t == my_team_id and i != mine]:
            del out[i]
        out[mine] = my_team_id
    return out


def roster_from_grid(grid: SheetGrid, year: int, my_col: int, my_team_id: int, pool: list[Player]) -> list[RosterEntry]:
    """Everything in my column (drafted rounds plus the unlabeled pickup rows). When the sheet gives cell
    colors, cells tinted another team's color were traded away and are skipped."""
    my_color = grid.header_colors[my_col] if my_col < len(grid.header_colors) else None
    out: list[RosterEntry] = []
    seen: set[int] = set()
    for cell in sorted(grid.cells + grid.extras, key=lambda c: (c.round or 99, c.col)):
        if cell.col != my_col or not cell.text:
            continue
        if my_color and cell.color and cell.color != my_color:
            continue
        player = match_player_by_name(cell.text, pool)
        if player is None or player.player_id in seen:
            continue
        seen.add(player.player_id)
        out.append(RosterEntry(season=year, team_id=my_team_id, player_id=player.player_id, name=player.name, position=player.position, pro_team=player.pro_team))
    return out
