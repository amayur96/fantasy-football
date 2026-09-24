"""Waiver-wire sources beyond ESPN: FantasyPros' waiver panel and rest-of-season consensus, Rotowire's
add/drop and injury tables, and nflverse snap counts. Establish The Run and PFF are paywalled, so
they only appear as links.

Same split as weekly.py: `load_or_fetch_*` touch the network (own TTL, stale fallback, never called
from ctx.load()), while `parse_*` / `apply_*` are pure and join already-fetched rows onto
WaiverPlayers by id where a source carries one, and by name within position otherwise.
"""
from __future__ import annotations

import csv
import html
import io
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import Settings
from .espn.parse import match_player_by_name, normalize_name
from .external import ABBREV_ALIASES, FP_POS, TEAM_ABBREV, UA, parse_fantasypros, scoring_format
from .models import LeagueSettings, Player, Position, WaiverLink, WaiverPlayer
from .store import read_json, write_json

log = logging.getLogger(__name__)

FP_BASE = "https://www.fantasypros.com/nfl/rankings/{slug}.php"
FP_DELAY = 2.0  # seconds between FantasyPros pages (their robots.txt asks for a crawl delay)
FP_WAIVER_TTL = timedelta(hours=6)
FP_ROS_TTL = timedelta(hours=12)
RW_MOVES_URL = "https://www.rotowire.com/football/tables/mfl-add-drops.php?type={kind}&week={week}"
RW_INJURY_URL = "https://www.rotowire.com/football/tables/injury-report.php?team=ALL&pos=ALL"
RW_REFERER = "https://www.rotowire.com/football/"
RW_MOVES_TTL = timedelta(hours=6)
RW_INJURY_TTL = timedelta(hours=3)
SNAPS_URL = "https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_{season}.csv"
SNAPS_TTL = timedelta(hours=24)
SNAP_POSITIONS = ("QB", "RB", "WR", "TE")
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def _fresh(cached: dict[str, Any] | None, ttl: timedelta) -> bool:
    if not cached or "fetched_at" not in cached:
        return False
    return datetime.now(timezone.utc) - datetime.fromisoformat(cached["fetched_at"]) < ttl


def _stamp(data: dict[str, Any]) -> dict[str, Any]:
    data["fetched_at"] = datetime.now(timezone.utc).isoformat()
    return data


def _load_or_fetch(path: Any, ttl: timedelta, refresh: bool, fetch: Any) -> dict[str, Any]:
    cached = read_json(path)
    if _fresh(cached, ttl) and not refresh:
        return cached
    try:
        data = _stamp(fetch())
    except Exception:
        if cached:
            return cached
        raise
    write_json(path, data)
    return data


def _get_text(url: str, referer: str | None = None, timeout: int = 20) -> str:
    import requests

    headers = {"User-Agent": UA, "Accept": "text/html,application/json,text/csv,*/*"}
    if referer:
        headers["Referer"] = referer
    r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    return r.text


def clean_note(text: Any) -> str | None:
    """FantasyPros notes arrive as HTML fragments; keep the prose."""
    if not text:
        return None
    s = WS_RE.sub(" ", html.unescape(TAG_RE.sub(" ", str(text)))).strip()
    return s or None


# ---- FantasyPros -------------------------------------------------------------------------

def fp_waiver_slugs(fmt: str) -> list[str]:
    """Candidates in order; the format-specific page is a guess, so the plain one is the fallback."""
    prefix = {"HALF": "half-point-ppr-", "PPR": "ppr-", "STD": ""}.get(fmt, "")
    return [f"waiver-wire-{prefix}overall", "waiver-wire-overall"] if prefix else ["waiver-wire-overall"]


def fp_ros_slug(fmt: str) -> str:
    # ros-superflex redirects to ros-overall, so there is no 2-QB rest-of-season list to ask for.
    prefix = {"HALF": "half-point-ppr-", "PPR": "ppr-", "STD": ""}.get(fmt, "")
    return f"ros-{prefix}overall" if prefix else "ros-overall"


def fetch_fp_waiver(fmt: str) -> dict[str, Any]:
    errors: list[str] = []
    for slug in fp_waiver_slugs(fmt):
        try:
            d = parse_fantasypros(_get_text(FP_BASE.format(slug=slug)))
            players = d.get("players") or []
            if players:
                return {"slug": slug, "players": players, "week": d.get("week"), "experts": d.get("total_experts"), "updated": d.get("last_updated"), "errors": errors}
            errors.append(f"FantasyPros {slug}: empty list")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"FantasyPros {slug}: {exc}")
        time.sleep(FP_DELAY)
    raise RuntimeError("; ".join(errors) or "no waiver page")


def fetch_fp_ros(fmt: str) -> dict[str, Any]:
    slug = fp_ros_slug(fmt)
    try:
        d = parse_fantasypros(_get_text(FP_BASE.format(slug=slug)))
    except Exception as exc:  # noqa: BLE001
        if slug == "ros-overall":
            raise
        time.sleep(FP_DELAY)
        log.info("FantasyPros %s: %s; falling back to ros-overall", slug, exc)
        slug = "ros-overall"
        d = parse_fantasypros(_get_text(FP_BASE.format(slug=slug)))
    players = d.get("players") or []
    if not players:
        raise RuntimeError(f"FantasyPros {slug}: empty list")
    return {"slug": slug, "players": players, "experts": d.get("total_experts"), "updated": d.get("last_updated"), "errors": []}


def load_or_fetch_fp_waiver(cfg: Settings, settings: LeagueSettings, refresh: bool = False) -> dict[str, Any]:
    fmt = scoring_format(settings)
    return _load_or_fetch(cfg.data_path / f"fp_waiver_{cfg.season}.json", FP_WAIVER_TTL, refresh, lambda: fetch_fp_waiver(fmt))


def load_or_fetch_fp_ros(cfg: Settings, settings: LeagueSettings, refresh: bool = False) -> dict[str, Any]:
    fmt = scoring_format(settings)
    return _load_or_fetch(cfg.data_path / f"fp_ros_{cfg.season}.json", FP_ROS_TTL, refresh, lambda: fetch_fp_ros(fmt))


def _fp_find(row: dict[str, Any], by_pos: dict[Position, list[WaiverPlayer]], dst: dict[str, WaiverPlayer], by_id: dict[int, WaiverPlayer]) -> WaiverPlayer | None:
    pos = FP_POS.get(str(row.get("player_position_id", "")).upper())
    if pos == "D/ST":
        team = str(row.get("player_team_id", "")).upper()
        return dst.get(ABBREV_ALIASES.get(team, team)) or dst.get(TEAM_ABBREV.get(str(row.get("player_name", "")).lower(), ""))
    cands = by_pos.get(pos, []) if pos else [p for ps in by_pos.values() for p in ps]
    hit = match_player_by_name(str(row.get("player_name", "")), cands, None)  # type: ignore[arg-type]
    return by_id.get(hit.player_id) if hit else None


def _index(players: list[WaiverPlayer]) -> tuple[dict[Position, list[WaiverPlayer]], dict[str, WaiverPlayer], dict[int, WaiverPlayer]]:
    by_pos: dict[Position, list[WaiverPlayer]] = {}
    for p in players:
        by_pos.setdefault(p.position, []).append(p)
    dst = {p.pro_team.upper(): p for p in players if p.position == "D/ST"}
    return by_pos, dst, {p.player_id: p for p in players}


def apply_fp_ros(players: list[WaiverPlayer], fp: dict[str, Any]) -> int:
    """Overall ROS rank plus a position rank derived by ordering within the position, so one page serves all."""
    by_pos, dst, by_id = _index(players)
    rows = sorted((r for r in fp.get("players", []) if r.get("rank_ecr")), key=lambda r: int(r["rank_ecr"]))
    counters: dict[str, int] = {}
    n = 0
    for row in rows:
        pos_key = str(row.get("player_position_id", "")).upper()
        counters[pos_key] = counters.get(pos_key, 0) + 1
        wp = _fp_find(row, by_pos, dst, by_id)
        if wp is None:
            continue
        wp.ros_rank = int(row["rank_ecr"])
        wp.ros_pos_rank = str(row.get("pos_rank") or f"{wp.position if wp.position != 'D/ST' else 'DST'}{counters[pos_key]}")
        wp.ros_best = int(row.get("rank_min") or 0) or None
        wp.ros_worst = int(row.get("rank_max") or 0) or None
        n += 1
    return n


def apply_fp_waiver(players: list[WaiverPlayer], fp: dict[str, Any]) -> int:
    by_pos, dst, by_id = _index(players)
    n = 0
    for row in fp.get("players", []):
        wp = _fp_find(row, by_pos, dst, by_id)
        if wp is None:
            continue
        wp.fp_waiver_rank = int(row.get("rank_ecr") or 0) or None
        tag = str(row.get("tag") or "").strip()
        wp.fp_faab = tag if tag.startswith("$") else None
        wp.fp_note = clean_note(row.get("note"))
        owned = row.get("player_owned_avg")
        wp.fp_waiver_owned = float(owned) if owned not in (None, "") else None
        n += 1
    return n


# ---- Sleeper -------------------------------------------------------------------------------

SLEEPER_POS = {"DEF": "D/ST"}


def sleeper_index(sleeper: dict[str, dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """(normalized name, position) -> record, for the half of Sleeper's records that carry no espn_id.
    A name shared by two active players is dropped rather than guessed."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    dupes: set[tuple[str, str]] = set()
    for rec in sleeper.values():
        if not rec.get("full_name") or not rec.get("team"):
            continue  # free agents and retired players share names with active ones
        key = (normalize_name(str(rec["full_name"])), SLEEPER_POS.get(str(rec.get("position")), str(rec.get("position"))))
        if key in out:
            dupes.add(key)
        out[key] = rec
    for key in dupes:
        out.pop(key, None)
    return out


def apply_sleeper(players: list[WaiverPlayer], by_espn: dict[int, dict[str, Any]], adds: list[dict[str, Any]], drops: list[dict[str, Any]], sleeper: dict[str, dict[str, Any]]) -> int:
    """Injury/practice notes by espn_id, else by name within position; trending counts by Sleeper id
    (D/ST rows carry the team abbreviation instead)."""
    dst = {p.pro_team.upper(): p for p in players if p.position == "D/ST"}
    by_id = {p.player_id: p for p in players}
    by_name = sleeper_index(sleeper)
    matched: dict[int, WaiverPlayer] = {}  # id(rec) -> player, so trending rows resolve the same way
    n = 0
    for p in players:
        rec = by_espn.get(p.player_id) or (by_name.get((normalize_name(p.name), p.position)) if p.position != "D/ST" else None)
        if not rec:
            continue
        matched[id(rec)] = p
        n += 1
        p.sleeper_injury = (rec.get("injury_status") or None) and str(rec["injury_status"]).upper()
        p.sleeper_body_part = rec.get("injury_body_part") or None
        p.sleeper_practice = rec.get("practice_participation") or None
        p.sleeper_notes = rec.get("injury_notes") or None
        try:
            p.depth_chart_order = int(rec["depth_chart_order"]) if rec.get("depth_chart_order") is not None else None
        except (TypeError, ValueError):
            p.depth_chart_order = None

    def target(row: dict[str, Any]) -> WaiverPlayer | None:
        pid = str(row.get("player_id", ""))
        if pid.isdigit():
            rec = sleeper.get(pid)
            if not rec:
                return None
            if id(rec) in matched:
                return matched[id(rec)]
            espn = rec.get("espn_id")
            return by_id.get(int(espn)) if espn else None
        return dst.get(ABBREV_ALIASES.get(pid.upper(), pid.upper()))

    for row in adds:
        wp = target(row)
        if wp is not None:
            wp.sleeper_adds = int(row.get("count") or 0)
    for row in drops:
        wp = target(row)
        if wp is not None:
            wp.sleeper_drops = int(row.get("count") or 0)
    return n


# ---- Rotowire ------------------------------------------------------------------------------

def _float(v: Any) -> float | None:
    try:
        return float(str(v).replace("%", "").replace("+", "")) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def parse_rotowire_moves(rows: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        rid = r.get("playerID") or r.get("ID") or r.get("id")
        name = r.get("player") or " ".join(x for x in (r.get("firstname"), r.get("lastname")) if x)
        team = str(r.get("team") or "").upper()
        out.append({"rotowire_id": int(rid) if str(rid).isdigit() else None, "name": str(name), "team": ABBREV_ALIASES.get(team, team),
                    "pos": str(r.get("pos") or r.get("position") or "").upper(), "change": _float(r.get("change")) or 0.0})
    return out


def parse_rotowire_injuries(rows: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        rid = r.get("ID") or r.get("playerID") or r.get("id")
        name = r.get("player") or " ".join(x for x in (r.get("firstname"), r.get("lastname")) if x)
        team = str(r.get("team") or "").upper()
        out.append({"rotowire_id": int(rid) if str(rid).isdigit() else None, "name": clean_note(name) or "", "team": ABBREV_ALIASES.get(team, team),
                    "pos": str(r.get("position") or r.get("pos") or "").upper(), "injury": clean_note(r.get("injury")), "status": clean_note(r.get("status"))})
    return out


def fetch_rotowire_moves(week: int) -> dict[str, Any]:
    import json

    out: dict[str, Any] = {"week": week}
    for kind, key in (("added", "added"), ("dropped", "dropped")):
        out[key] = parse_rotowire_moves(json.loads(_get_text(RW_MOVES_URL.format(kind=kind, week=week), referer=RW_REFERER)))
    if not out["added"] and not out["dropped"]:
        raise RuntimeError("Rotowire returned no add/drop rows")
    return out


def fetch_rotowire_injuries() -> dict[str, Any]:
    import json

    rows = parse_rotowire_injuries(json.loads(_get_text(RW_INJURY_URL, referer=RW_REFERER)))
    if not rows:
        raise RuntimeError("Rotowire returned no injury rows")
    return {"rows": rows}


def load_or_fetch_rotowire_moves(cfg: Settings, week: int, refresh: bool = False) -> dict[str, Any]:
    return _load_or_fetch(cfg.data_path / f"rotowire_moves_{cfg.season}_{week}.json", RW_MOVES_TTL, refresh, lambda: fetch_rotowire_moves(week))


def load_or_fetch_rotowire_injuries(cfg: Settings, refresh: bool = False) -> dict[str, Any]:
    return _load_or_fetch(cfg.data_path / "rotowire_injuries.json", RW_INJURY_TTL, refresh, fetch_rotowire_injuries)


def _rw_find(row: dict[str, Any], rw_to_espn: dict[int, int], by_id: dict[int, WaiverPlayer], by_pos: dict[Position, list[WaiverPlayer]], dst: dict[str, WaiverPlayer]) -> WaiverPlayer | None:
    rid = row.get("rotowire_id")
    if rid is not None and rid in rw_to_espn:
        hit = by_id.get(rw_to_espn[rid])
        if hit is not None:
            return hit
    pos = row.get("pos") or ""
    if pos in ("DST", "D/ST", "DEF", "D"):
        return dst.get(row.get("team", ""))
    cands = by_pos.get(pos, []) if pos in by_pos else [p for ps in by_pos.values() for p in ps]  # type: ignore[call-overload]
    hit = match_player_by_name(row.get("name", ""), cands, None)  # type: ignore[arg-type]
    return by_id.get(hit.player_id) if hit else None


def apply_rotowire(players: list[WaiverPlayer], moves: dict[str, Any] | None, injuries: list[dict[str, Any]] | None, rw_to_espn: dict[int, int]) -> tuple[int, int, int]:
    """Returns (adds matched, drops matched, injuries matched)."""
    by_pos, dst, by_id = _index(players)
    a = d = i = 0
    for row in (moves or {}).get("added", []):
        wp = _rw_find(row, rw_to_espn, by_id, by_pos, dst)
        if wp is not None:
            wp.rw_add_pct = row.get("change")
            a += 1
    for row in (moves or {}).get("dropped", []):
        wp = _rw_find(row, rw_to_espn, by_id, by_pos, dst)
        if wp is not None:
            wp.rw_drop_pct = row.get("change")
            d += 1
    for row in injuries or []:
        wp = _rw_find(row, rw_to_espn, by_id, by_pos, dst)
        if wp is not None:
            wp.rw_injury = row.get("injury")
            wp.rw_status = row.get("status")
            i += 1
    return a, d, i


# ---- nflverse snap counts ------------------------------------------------------------------

def _snap_key(name: str, team: str) -> str:
    team = team.upper()
    return f"{normalize_name(name)}|{ABBREV_ALIASES.get(team, team)}"


def parse_snap_csv(text: str) -> dict[str, list[list[float]]]:
    """'normalized name|TEAM' -> [[week, offense_snaps, offense_pct], ...] by week, regular season only."""
    out: dict[str, list[list[float]]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        if row.get("position") not in SNAP_POSITIONS or (row.get("game_type") or "REG") != "REG":
            continue
        try:
            wk, snaps, pct = int(row["week"]), float(row.get("offense_snaps") or 0), float(row.get("offense_pct") or 0)
        except (TypeError, ValueError, KeyError):
            continue
        out.setdefault(_snap_key(row.get("player", ""), row.get("team", "")), []).append([wk, snaps, pct])
    for rows in out.values():
        rows.sort(key=lambda r: r[0])
    return out


def fetch_snaps(season: int) -> dict[str, Any]:
    snaps = parse_snap_csv(_get_text(SNAPS_URL.format(season=season), timeout=60))
    if not snaps:
        raise RuntimeError("nflverse snap counts: no rows")
    return {"season": season, "snaps": snaps}


def load_or_fetch_snaps(cfg: Settings, refresh: bool = False) -> dict[str, Any]:
    return _load_or_fetch(cfg.data_path / f"snaps_{cfg.season}.json", SNAPS_TTL, refresh, lambda: fetch_snaps(cfg.season))


def apply_snaps(players: list[WaiverPlayer], snaps: dict[str, list[list[float]]], week: int) -> int:
    """Fill usage[].snap_pct by week and snap_pct with the latest played week before `week`."""
    n = 0
    for p in players:
        if p.position not in SNAP_POSITIONS:
            continue
        rows = snaps.get(_snap_key(p.name, p.pro_team))
        if not rows:
            continue
        by_week = {int(r[0]): float(r[2]) for r in rows if int(r[0]) < week}
        if not by_week:
            continue
        for u in p.usage:
            if u.week in by_week:
                u.snap_pct = by_week[u.week]
        p.snap_pct = by_week[max(by_week)]
        n += 1
    return n


# ---- misc --------------------------------------------------------------------------------

def apply_bye_weeks(players: list[WaiverPlayer], players_by_id: dict[int, Player]) -> None:
    for p in players:
        pl = players_by_id.get(p.player_id)
        if pl is not None:
            p.bye_week = pl.bye_week


def links(fp_waiver_slug: str | None, week: int) -> list[WaiverLink]:
    return [
        WaiverLink(label="FantasyPros waiver wire", url=FP_BASE.format(slug=fp_waiver_slug or "waiver-wire-overall"), note="expert consensus, free"),
        WaiverLink(label="Rotowire add/drop trends", url=f"https://www.rotowire.com/football/mfl-add-drops.php?week={week}", note="free"),
        WaiverLink(label="Establish The Run waivers", url="https://establishtherun.com/?s=waiver+wire", note="subscription"),
        WaiverLink(label="PFF waiver wire", url="https://www.pff.com/fantasy/waiver-wire", note="subscription"),
    ]
