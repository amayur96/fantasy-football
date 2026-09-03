from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ffdraft.models import DraftHistoryPick, LeagueSettings, Player, RosterEntry, SetupOverrides, TeamInfo
from ffdraft.value import build_rankings

MY_TEAM = 3
TEAM_IDS = list(range(1, 11))
ROSTER_SLOTS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "RB/WR/TE": 1, "D/ST": 1, "K": 1, "BE": 7}
OWNER_NAMES = {i: f"Owner{i}" for i in range(1, 11)}


@pytest.fixture
def settings() -> LeagueSettings:
    return LeagueSettings(
        league_id=1, league_name="Test League", season=2026, team_count=10, rounds=18,
        roster_slots=ROSTER_SLOTS, scoring=[],
        teams=[TeamInfo(team_id=i, name=f"Team {OWNER_NAMES[i]}", abbrev=OWNER_NAMES[i][:4].upper(), owner_ids=[f"{{SWID-{i}}}"], owner_names=[f"First {OWNER_NAMES[i]}"]) for i in TEAM_IDS],
        my_team_id=MY_TEAM, my_team_name="Team Owner3", draft_order=TEAM_IDS, synced_at=datetime.now(timezone.utc),
    )


def _pool() -> list[Player]:
    """~122 players: projections fall off linearly per position; ADP roughly follows value."""
    spec = {"QB": (14, 380, 12), "RB": (40, 300, 6), "WR": (40, 290, 5.5), "TE": (14, 200, 10), "K": (6, 140, 5), "D/ST": (6, 130, 5)}
    players: list[Player] = []
    pid = 100
    for pos, (n, top, step) in spec.items():
        for i in range(n):
            pid += 1
            players.append(Player(player_id=pid, name=f"{pos} Player {i + 1}", position=pos, pro_team="XX", proj_points=float(top - i * step), percent_owned=99.0))
    # ADP by projection order, K/DST forced late
    order = sorted(players, key=lambda p: (p.position in ("K", "D/ST"), -p.proj_points))
    for i, p in enumerate(order, start=1):
        p.adp = float(i)
    return players


@pytest.fixture
def players() -> list[Player]:
    return _pool()


@pytest.fixture
def rankings(players, settings):
    return build_rankings(players, settings)


def _pick(season: int, team: int, pid: int, rnd: int, keeper: bool = False) -> DraftHistoryPick:
    return DraftHistoryPick(season=season, team_id=team, player_id=pid, player_name=f"P{pid}", round_num=rnd, round_pick=1, keeper_status=keeper)


@pytest.fixture
def drafts() -> dict[int, list[DraftHistoryPick]]:
    # 101 (QB1): drafted by me R6 in 2025, never kept
    # 102 (QB2): drafted 2023 R17, kept 2024 R17, kept 2025 R15 -> chain
    # 103 (QB3): kept in 2025 at R6 (drafted 2024 R6)
    # 115 (RB1): drafted by team 5 in 2025 R5, not kept (I acquired him in-season)
    # 116 (RB2): drafted by me in 2025 R1
    # 120 (RB6): never drafted (waiver pickup)
    return {
        2025: [_pick(2025, MY_TEAM, 101, 6), _pick(2025, MY_TEAM, 102, 15, True), _pick(2025, MY_TEAM, 103, 6, True), _pick(2025, 5, 115, 5), _pick(2025, MY_TEAM, 116, 1)],
        2024: [_pick(2024, MY_TEAM, 102, 17, True), _pick(2024, MY_TEAM, 103, 6)],
        2023: [_pick(2023, MY_TEAM, 102, 17)],
    }


@pytest.fixture
def roster() -> list[RosterEntry]:
    rows = [(101, "QB"), (102, "QB"), (103, "QB"), (115, "RB"), (116, "RB"), (120, "RB")]
    return [RosterEntry(season=2025, team_id=MY_TEAM, player_id=pid, name=f"P{pid}", position=pos) for pid, pos in rows]


@pytest.fixture
def setup() -> SetupOverrides:
    return SetupOverrides(my_slot=3)
