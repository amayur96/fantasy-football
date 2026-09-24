"""Sleeper's public API: what millions of managers are adding and dropping, plus injury/practice notes.

No auth, no key. The player map is ~15 MB and carries ESPN ids, so it is trimmed to the fields
we use and cached for a day; the trending lists are cached for an hour.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import Settings
from .store import read_json, write_json

log = logging.getLogger(__name__)
BASE = "https://api.sleeper.app/v1"
PLAYERS_TTL = timedelta(days=1)
TREND_TTL = timedelta(hours=1)
KEEP = ("full_name", "position", "team", "espn_id", "rotowire_id", "injury_status", "injury_body_part", "injury_notes", "practice_participation", "practice_description", "depth_chart_order", "news_updated", "search_rank")
PLAYERS_VERSION = 2  # bump when KEEP grows, so a day-old cache without the new fields is refetched


def _get(url: str, timeout: int = 30) -> Any:
    import requests

    r = requests.get(url, headers={"Accept": "application/json"}, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} from {url}")
    return r.json()


def _fresh(cached: dict[str, Any] | None, ttl: timedelta) -> bool:
    if not cached or "fetched_at" not in cached:
        return False
    return datetime.now(timezone.utc) - datetime.fromisoformat(cached["fetched_at"]) < ttl


def load_or_fetch_players(cfg: Settings, refresh: bool = False) -> dict[str, dict[str, Any]]:
    """Sleeper id -> trimmed player record. Only players with a fantasy position are kept."""
    path = cfg.data_path / "sleeper_players.json"
    cached = read_json(path)
    if _fresh(cached, PLAYERS_TTL) and not refresh and cached.get("version") == PLAYERS_VERSION:
        return cached["players"]
    try:
        raw = _get(f"{BASE}/players/nfl", timeout=90)
    except Exception:
        if cached:
            return cached["players"]
        raise
    players = {
        pid: {k: v for k, v in rec.items() if k in KEEP}
        for pid, rec in raw.items()
        if isinstance(rec, dict) and rec.get("position") in ("QB", "RB", "WR", "TE", "K", "DEF")
    }
    write_json(path, {"fetched_at": datetime.now(timezone.utc).isoformat(), "version": PLAYERS_VERSION, "players": players})
    return players


def load_or_fetch_trending(cfg: Settings, kind: str, refresh: bool = False, hours: int = 48, limit: int = 50) -> list[dict[str, Any]]:
    """[{player_id, count}] for kind 'add' or 'drop', most-added first."""
    path = cfg.data_path / f"sleeper_trending_{kind}.json"
    cached = read_json(path)
    if _fresh(cached, TREND_TTL) and not refresh:
        return cached["rows"]
    try:
        rows = _get(f"{BASE}/players/nfl/trending/{kind}?lookback_hours={hours}&limit={limit}")
    except Exception:
        if cached:
            return cached["rows"]
        raise
    write_json(path, {"fetched_at": datetime.now(timezone.utc).isoformat(), "rows": rows})
    return rows


def by_espn_id(players: dict[str, dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {int(rec["espn_id"]): rec for rec in players.values() if rec.get("espn_id")}


def by_rotowire_id(players: dict[str, dict[str, Any]]) -> dict[int, int]:
    """Rotowire id -> ESPN id, the bridge for Rotowire's tables."""
    out: dict[int, int] = {}
    for rec in players.values():
        if rec.get("rotowire_id") and rec.get("espn_id"):
            try:
                out[int(rec["rotowire_id"])] = int(rec["espn_id"])
            except (TypeError, ValueError):
                continue
    return out
