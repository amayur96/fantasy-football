"""Expert rankings: FantasyPros consensus (ECR) and Boris Chen tiers.

Both are public pages read for personal use, cached for a day in data/external_{season}.json.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import Settings
from .espn.parse import match_player_by_name
from .models import ExternalData, ExternalRank, LeagueSettings, Player, Position
from .store import load_model, write_json

log = logging.getLogger(__name__)

BC_BASE = "https://s3-us-west-1.amazonaws.com/fftiers/out/text_{key}.txt"
FP_BASE = "https://www.fantasypros.com/nfl/rankings/{slug}-cheatsheets.php"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
TIER_RE = re.compile(r"^\s*Tier\s+(\d+)\s*:\s*(.*)$")
ECR_RE = re.compile(r"var ecrData = (\{.*?\});", re.S)
STALE_AFTER = timedelta(hours=24)

FP_POS: dict[str, Position] = {"QB": "QB", "RB": "RB", "WR": "WR", "TE": "TE", "K": "K", "DST": "D/ST"}
BC_KEYS: dict[Position, str] = {"QB": "QB", "RB": "RB", "WR": "WR", "TE": "TE", "K": "K", "D/ST": "DST"}
FORMAT_SUFFIX = {"HALF": "-HALF", "PPR": "-PPR", "STD": ""}
FP_SLUG = {"HALF": "half-point-ppr", "PPR": "ppr", "STD": "standard"}

# Full NFL team names (as Boris Chen / FantasyPros print defenses) -> ESPN abbreviations.
TEAM_ABBREV: dict[str, str] = {
    "arizona cardinals": "ARI", "atlanta falcons": "ATL", "baltimore ravens": "BAL", "buffalo bills": "BUF",
    "carolina panthers": "CAR", "chicago bears": "CHI", "cincinnati bengals": "CIN", "cleveland browns": "CLE",
    "dallas cowboys": "DAL", "denver broncos": "DEN", "detroit lions": "DET", "green bay packers": "GB",
    "houston texans": "HOU", "indianapolis colts": "IND", "jacksonville jaguars": "JAX", "kansas city chiefs": "KC",
    "las vegas raiders": "LV", "los angeles chargers": "LAC", "los angeles rams": "LAR", "miami dolphins": "MIA",
    "minnesota vikings": "MIN", "new england patriots": "NE", "new orleans saints": "NO", "new york giants": "NYG",
    "new york jets": "NYJ", "philadelphia eagles": "PHI", "pittsburgh steelers": "PIT", "san francisco 49ers": "SF",
    "seattle seahawks": "SEA", "tampa bay buccaneers": "TB", "tennessee titans": "TEN", "washington commanders": "WSH",
}
ABBREV_ALIASES = {"WAS": "WSH", "LA": "LAR", "JAC": "JAX"}


# ---- league format ---------------------------------------------------------------

def scoring_format(settings: LeagueSettings) -> str:
    for r in settings.scoring:
        if r.abbr.upper() == "REC" or r.label.lower().startswith("each reception"):
            if r.points >= 1:
                return "PPR"
            if r.points > 0:
                return "HALF"
            return "STD"
    return "STD"


def is_superflex(settings: LeagueSettings) -> bool:
    return settings.roster_slots.get("QB", 0) >= 2 or settings.roster_slots.get("OP", 0) > 0


# ---- fetch + parse -----------------------------------------------------------------

def parse_borischen(text: str) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for line in text.splitlines():
        m = TIER_RE.match(line)
        if not m:
            continue
        tier = int(m.group(1))
        for name in m.group(2).split(","):
            if name.strip():
                out.append((name.strip(), tier))
    return out


def fetch_borischen(fmt: str) -> dict[Position, list[tuple[str, int]]]:
    import requests

    out: dict[Position, list[tuple[str, int]]] = {}
    for pos, key in BC_KEYS.items():
        suffix = FORMAT_SUFFIX.get(fmt, "") if pos in ("RB", "WR", "TE") else ""
        r = requests.get(BC_BASE.format(key=key + suffix), timeout=20)
        if r.status_code != 200:
            raise RuntimeError(f"Boris Chen {key}{suffix}: HTTP {r.status_code}")
        out[pos] = parse_borischen(r.text)
    return out


def parse_fantasypros(html: str) -> dict[str, Any]:
    m = ECR_RE.search(html)
    if not m:
        raise RuntimeError("FantasyPros page has no embedded ecrData (layout changed or blocked)")
    return json.loads(m.group(1))


def fp_page_slug(fmt: str, superflex: bool) -> str:
    return FP_SLUG.get(fmt, "standard") + ("-superflex" if superflex else "")


def fetch_fantasypros(fmt: str, superflex: bool) -> dict[str, Any]:
    import requests

    url = FP_BASE.format(slug=fp_page_slug(fmt, superflex))
    r = requests.get(url, headers={"User-Agent": UA, "Accept": "text/html"}, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"FantasyPros: HTTP {r.status_code}")
    return parse_fantasypros(r.text)


# ---- matching --------------------------------------------------------------------------

def _dst_by_team(players: list[Player]) -> dict[str, Player]:
    return {p.pro_team.upper(): p for p in players if p.position == "D/ST"}


def _to_int(v: Any) -> int | None:
    try:
        return int(float(v)) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _to_float(v: Any) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def match_external(
    players: list[Player], bc: dict[Position, list[tuple[str, int]]] | None, fp: dict[str, Any] | None
) -> tuple[dict[int, ExternalRank], dict[str, list[str]], dict[str, int]]:
    ranks: dict[int, ExternalRank] = {}
    unmatched: dict[str, list[str]] = {"fantasypros": [], "borischen": []}
    matched = {"fantasypros": 0, "borischen": 0}
    dst = _dst_by_team(players)

    def find(name: str, pos: Position | None, team: str | None = None) -> Player | None:
        if pos == "D/ST":
            abbr = ABBREV_ALIASES.get((team or "").upper(), (team or "").upper()) or TEAM_ABBREV.get(name.lower(), "")
            return dst.get(abbr)
        return match_player_by_name(name, players, pos)

    if fp:
        for row in fp.get("players", []):
            pos = FP_POS.get(str(row.get("player_position_id", "")).upper())
            if pos is None:
                continue
            hit = find(str(row.get("player_name", "")), pos, str(row.get("player_team_id", "")))
            if hit is None:
                unmatched["fantasypros"].append(f"{row.get('player_name')} ({pos})")
                continue
            er = ranks.setdefault(hit.player_id, ExternalRank())
            er.fp_rank = _to_int(row.get("rank_ecr"))
            er.fp_pos_rank = row.get("pos_rank") or None
            er.fp_tier = _to_int(row.get("tier"))
            er.fp_rank_ave = _to_float(row.get("rank_ave"))
            er.fp_rank_std = _to_float(row.get("rank_std"))
            er.fp_best = _to_int(row.get("rank_min"))
            er.fp_worst = _to_int(row.get("rank_max"))
            er.fp_bye = _to_int(row.get("player_bye_week"))
            matched["fantasypros"] += 1
    if bc:
        for pos, rows in bc.items():
            for name, tier in rows:
                hit = find(name, pos)
                if hit is None:
                    unmatched["borischen"].append(f"{name} ({pos})")
                    continue
                er = ranks.setdefault(hit.player_id, ExternalRank())
                if er.bc_tier is None:
                    er.bc_tier = tier
                    matched["borischen"] += 1
    return ranks, unmatched, matched


# ---- cache ----------------------------------------------------------------------------

def cache_path(cfg: Settings) -> Path:
    return cfg.data_path / f"external_{cfg.season}.json"


def load_cached(cfg: Settings) -> ExternalData | None:
    return load_model(cache_path(cfg), ExternalData)


def is_stale(data: ExternalData | None) -> bool:
    if data is None:
        return True
    fetched = data.fetched_at if data.fetched_at.tzinfo else data.fetched_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - fetched > STALE_AFTER


def fetch_all(cfg: Settings, settings: LeagueSettings, players: list[Player]) -> ExternalData:
    fmt = scoring_format(settings)
    sf = is_superflex(settings)
    errors: list[str] = []
    fp: dict[str, Any] | None = None
    bc: dict[Position, list[tuple[str, int]]] | None = None
    try:
        fp = fetch_fantasypros(fmt, sf)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"FantasyPros: {exc}")
    try:
        bc = fetch_borischen(fmt)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Boris Chen: {exc}")
    ranks, unmatched, matched = match_external(players, bc, fp)
    data = ExternalData(
        season=cfg.season, scoring=fmt, superflex=sf,
        fp_experts=int((fp or {}).get("total_experts") or 0), fp_updated=str((fp or {}).get("last_updated") or ""),
        fp_page=fp_page_slug(fmt, sf), fetched_at=datetime.now(timezone.utc),
        ranks=ranks, errors=errors, unmatched=unmatched, matched=matched,
    )
    if not ranks:
        raise RuntimeError("; ".join(errors) or "No expert rankings matched")
    write_json(cache_path(cfg), data)
    return data


def load_or_fetch(cfg: Settings, settings: LeagueSettings, players: list[Player], refresh: bool = False) -> ExternalData | None:
    cached = load_cached(cfg)
    if cached is not None and not refresh and not is_stale(cached):
        return cached
    try:
        return fetch_all(cfg, settings, players)
    except Exception as exc:  # noqa: BLE001
        log.warning("Expert rankings refresh failed: %s", exc)
        if cached is not None:
            cached.errors = [f"refresh failed, using cached copy: {exc}"]
            return cached
        return None


def apply_to_players(players: list[Player], data: ExternalData | None) -> None:
    fields = ExternalRank.model_fields.keys()
    for p in players:
        er = data.ranks.get(p.player_id) if data else None
        for f in fields:
            setattr(p, f, getattr(er, f) if er else None)
