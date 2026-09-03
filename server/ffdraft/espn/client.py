"""ESPN access via espn_api plus a couple of raw views; everything cached to data/*.json."""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

from ..config import Settings
from ..models import DraftHistoryPick, LeagueSettings, Player, RosterEntry, SeasonPoints, SyncReport
from ..store import cached, load_model, write_json
from . import parse

log = logging.getLogger(__name__)

KONA_FILTER: dict[str, Any] = {
    "players": {
        "filterStatus": {"value": ["FREEAGENT", "WAIVERS", "ONTEAM"]},
        "limit": 1200,  # ESPN caps out around 978; ask for more so nobody is trimmed
        "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
    }
}


class EspnClient:
    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self.data = cfg.data_path

    # ---- raw access -------------------------------------------------------
    @lru_cache(maxsize=8)
    def _league(self, year: int) -> Any:
        from espn_api.football import League

        if not self.cfg.has_credentials:
            raise RuntimeError("LEAGUE_ID, ESPN_S2 and SWID must be set in .env to talk to ESPN")
        return League(league_id=self.cfg.league_id, year=year, espn_s2=self.cfg.espn_s2, swid=self.cfg.swid)

    def _raw_view(self, year: int, view: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        league = self._league(year)
        headers = {"x-fantasy-filter": json.dumps(filters)} if filters else None
        return league.espn_request.league_get(params={"view": view}, headers=headers)

    def _pro_teams(self, year: int) -> dict[str, Any]:
        league = self._league(year)
        return league.espn_request.get(params={"view": "proTeamSchedules_wl"})

    # ---- cached fetches ---------------------------------------------------
    def fetch_draft_order(self, refresh: bool = False) -> tuple[list[int] | None, bool]:
        path = self.data / "draft_order.json"

        def load() -> dict[str, Any]:
            raw = self._raw_view(self.cfg.season, "mSettings")
            return {"pick_order": parse.parse_draft_order(raw)}

        value, from_cache = cached(path, refresh, load, dict)
        return value.get("pick_order"), from_cache

    def fetch_settings(self, refresh: bool = False) -> tuple[LeagueSettings, bool]:
        path = self.data / "settings.json"
        order, _ = self.fetch_draft_order(refresh)

        def load() -> LeagueSettings:
            return parse.parse_settings(self._league(self.cfg.season), self.cfg.swid, self.cfg.season, order)

        return cached(path, refresh, load, LeagueSettings)

    def fetch_player_pool(self, refresh: bool = False) -> tuple[list[Player], bool]:
        path = self.data / f"players_{self.cfg.season}.json"

        def load() -> list[Player]:
            byes: dict[int, int] = {}
            try:
                byes = parse.parse_bye_weeks(self._pro_teams(self.cfg.season))
            except Exception as exc:  # noqa: BLE001
                log.warning("Bye weeks unavailable: %s", exc)
            raw = self._raw_view(self.cfg.season, "kona_player_info", KONA_FILTER)
            players = [parse.parse_kona_player(e, self.cfg.season, byes) for e in raw.get("players", [])]
            out = [p for p in players if p is not None]
            if not out:
                raise RuntimeError("ESPN returned no players for kona_player_info")
            return out

        return cached(path, refresh, load, list[Player])

    def fetch_roster(self, year: int, refresh: bool = False) -> tuple[list[RosterEntry], bool]:
        path = self.data / f"roster_{year}.json"

        def load() -> list[RosterEntry]:
            league = self._league(year)
            team = parse.find_my_team(league, self.cfg.swid)
            return parse.parse_roster(team, year)

        return cached(path, refresh, load, list[RosterEntry])

    def fetch_draft(self, year: int, refresh: bool = False) -> tuple[list[DraftHistoryPick], bool]:
        path = self.data / f"draft_{year}.json"

        def load() -> list[DraftHistoryPick]:
            picks = parse.parse_draft(self._league(year), year)
            if not picks:
                raise RuntimeError(f"ESPN has no draft data for {year}")
            return picks

        return cached(path, refresh, load, list[DraftHistoryPick])

    def fetch_points_history(self, player_ids: list[int], years: list[int], refresh: bool = False) -> dict[int, list[SeasonPoints]]:
        """Actual season totals per player for the given past seasons (league scoring of that season)."""
        path = self.data / f"points_{self.cfg.season}.json"
        cached = load_model(path, dict[int, list[SeasonPoints]]) or {}
        missing = [pid for pid in player_ids if pid not in cached] if not refresh else list(player_ids)
        if not missing:
            return {pid: cached.get(pid, []) for pid in player_ids}
        out: dict[int, list[SeasonPoints]] = {pid: [] for pid in missing}
        for year in years:
            try:
                league = self._league(year)
                players = league.player_info(playerId=missing) or []
            except Exception as exc:  # noqa: BLE001
                log.warning("points history %s: %s", year, exc)
                continue
            if not isinstance(players, list):
                players = [players]
            for p in players:
                weeks = [k for k, v in p.stats.items() if k != 0 and v.get("points") is not None and v.get("breakdown")]
                out[int(p.playerId)].append(SeasonPoints(season=year, points=float(p.total_points or 0), avg=float(p.avg_points or 0), games=len(weeks)))
        for pid, rows in out.items():
            cached[pid] = sorted(rows, key=lambda r: -r.season)
        write_json(path, cached)
        return {pid: cached.get(pid, []) for pid in player_ids}

    def sync_all(self, refresh: bool = False) -> SyncReport:
        from_cache: list[str] = []
        errors: list[str] = []
        settings, fc = self.fetch_settings(refresh)
        if fc:
            from_cache.append("settings")
        players, fc = self.fetch_player_pool(refresh)
        if fc:
            from_cache.append("players")
        prev = self.cfg.season - 1
        try:
            roster, fc = self.fetch_roster(prev, refresh)
            if fc:
                from_cache.append(f"roster_{prev}")
        except Exception as exc:  # noqa: BLE001
            roster = []
            errors.append(f"roster_{prev}: {exc}")
        years: list[int] = []
        for year in range(prev, self.cfg.first_history_year - 1, -1):
            try:
                _, fc = self.fetch_draft(year, refresh)
                years.append(year)
                if fc:
                    from_cache.append(f"draft_{year}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"draft_{year}: {exc}")
                if year < prev:
                    break  # league probably didn't exist yet
        return SyncReport(
            settings=settings,
            players=len(players),
            roster_prev=len(roster),
            draft_years=years,
            from_cache=from_cache,
            errors=errors,
        )

    # ---- offline loaders (no network) -------------------------------------
    def load_cached_settings(self) -> LeagueSettings | None:
        return load_model(self.data / "settings.json", LeagueSettings)

    def load_cached_players(self) -> list[Player]:
        return load_model(self.data / f"players_{self.cfg.season}.json", list[Player]) or []

    def load_cached_roster(self, year: int) -> list[RosterEntry]:
        return load_model(self.data / f"roster_{year}.json", list[RosterEntry]) or []

    def load_cached_drafts(self) -> dict[int, list[DraftHistoryPick]]:
        out: dict[int, list[DraftHistoryPick]] = {}
        for path in sorted(self.data.glob("draft_*.json")):
            try:
                year = int(path.stem.split("_")[1])
            except ValueError:
                continue
            picks = load_model(path, list[DraftHistoryPick])
            if picks:
                out[year] = picks
        return out
