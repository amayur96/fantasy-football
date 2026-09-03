"""Weekly data: my ESPN roster with this week's projections/opponents, free agents, and expert weekly ranks."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from espn_api.football.constant import PRO_TEAM_MAP

from .config import Settings
from .espn.parse import POSITION_BY_ID, SLOT_BY_ID, match_player_by_name, normalize_swid
from .external import ABBREV_ALIASES, FP_POS, TEAM_ABBREV, UA, fetch_borischen, parse_fantasypros, scoring_format
from .models import LeagueSettings, Position, WeekPlayer
from .store import read_json, write_json

log = logging.getLogger(__name__)
WEEK_TTL = timedelta(minutes=30)
FP_WEEKLY_TTL = timedelta(hours=6)
FP_WEEK_BASE = "https://www.fantasypros.com/nfl/rankings/{slug}.php"


# ---- ESPN --------------------------------------------------------------------------------

def _week_player(p: Any, week: int, pro_sched: dict[int, tuple[int, int]], pos_ratings: dict[str, dict[str, int]], on_my_team: bool) -> WeekPlayer | None:
    pos = p.position if p.position in POSITION_BY_ID.values() else None
    if pos is None:
        return None
    wk = p.stats.get(week, {}) if hasattr(p, "stats") else {}
    pro_id = next((k for k, v in PRO_TEAM_MAP.items() if v == p.proTeam), 0)
    opp, opp_rank, bye = None, None, False
    if pro_id in pro_sched:
        opp_id, _ = pro_sched[pro_id]
        opp = PRO_TEAM_MAP.get(opp_id)
        pos_id = next((k for k, v in POSITION_BY_ID.items() if v == pos), None)
        if pos_id is not None:
            opp_rank = (pos_ratings.get(str(pos_id)) or {}).get(str(opp_id))
    elif pro_id:
        bye = True
    season = p.stats.get(0, {}) if hasattr(p, "stats") else {}
    last = p.stats.get(week - 1, {}) if hasattr(p, "stats") and week > 1 else {}
    inj = getattr(p, "injuryStatus", None)
    inj = inj.upper() if isinstance(inj, str) and inj and inj.upper() != "ACTIVE" else None
    avg = season.get("avg_points")
    return WeekPlayer(
        player_id=int(p.playerId), name=p.name, position=pos, pro_team=p.proTeam or "", slot=getattr(p, "lineupSlot", "BE") or "BE",
        eligible_slots=list(getattr(p, "eligibleSlots", []) or []), injury_status=inj, on_bye=bye,
        opponent=opp, opp_rank_vs_pos=int(opp_rank) if opp_rank else None,
        espn_proj=wk.get("projected_points"), season_proj=float(getattr(p, "projected_total_points", 0) or 0),
        points=wk.get("points") if wk.get("breakdown") else None, last_points=last.get("points") if last.get("breakdown") else None,
        season_points=season.get("points"), season_avg=float(avg) if avg else None,
        percent_owned=float(getattr(p, "percent_owned", 0) or 0), percent_started=float(getattr(p, "percent_started", 0) or 0), on_my_team=on_my_team,
    )


def fetch_espn_week(cfg: Settings, my_team_id: int, week: int | None = None, season: int | None = None, fa_size: int = 120) -> dict[str, Any]:
    from espn_api.football import League

    year = season or cfg.season
    league = League(league_id=cfg.league_id, year=year, espn_s2=cfg.espn_s2, swid=cfg.swid)
    wk = week or (league.current_week if league.current_week and league.current_week > 0 else 1)
    pro_sched = league._get_pro_schedule(wk)
    ratings = league._get_positional_ratings(wk)
    me = next((t for t in league.teams if t.team_id == my_team_id), None)
    if me is None:
        raise LookupError("My team not found in this season")
    roster = [_week_player(p, wk, pro_sched, ratings, True) for p in me.roster]
    fas: list[WeekPlayer] = []
    try:
        for p in league.free_agents(week=wk, size=fa_size):
            wp = _week_player(p, wk, pro_sched, ratings, False)
            if wp:
                fas.append(wp)
    except Exception as exc:  # noqa: BLE001
        log.warning("free agents: %s", exc)
    opp_name = None
    try:
        sched = me.schedule
        if 0 < wk <= len(sched):
            opp_name = getattr(sched[wk - 1], "team_name", None)
    except Exception:  # noqa: BLE001
        pass
    return {
        "week": wk, "current_week": league.current_week, "season": year,
        "roster": [r.model_dump(mode="json") for r in roster if r], "free_agents": [f.model_dump(mode="json") for f in fas],
        "opponent_name": opp_name, "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def load_or_fetch_espn_week(cfg: Settings, my_team_id: int, week: int | None, refresh: bool) -> dict[str, Any]:
    key = week or "current"
    path = cfg.data_path / f"week_{cfg.season}_{key}.json"
    cached = read_json(path)
    if cached and not refresh:
        fetched = datetime.fromisoformat(cached["fetched_at"])
        if datetime.now(timezone.utc) - fetched < WEEK_TTL:
            return cached
    try:
        data = fetch_espn_week(cfg, my_team_id, week)
    except Exception:
        if cached:
            return cached
        raise
    write_json(path, data)
    return data


# ---- FantasyPros weekly --------------------------------------------------------------------------

def fp_weekly_slugs(fmt: str, superflex: bool) -> dict[str, str]:
    prefix = {"HALF": "half-point-ppr-", "PPR": "ppr-", "STD": ""}.get(fmt, "")
    slugs = {"QB": "qb", "RB": f"{prefix}rb", "WR": f"{prefix}wr", "TE": f"{prefix}te", "D/ST": "dst", "K": "k"}
    slugs["ALL"] = f"{prefix}superflex" if superflex else f"{prefix}flex"
    return slugs


def fetch_fp_weekly(fmt: str, superflex: bool) -> dict[str, Any]:
    import requests

    out: dict[str, Any] = {"pages": {}, "week": None, "errors": []}
    for key, slug in fp_weekly_slugs(fmt, superflex).items():
        try:
            r = requests.get(FP_WEEK_BASE.format(slug=slug), headers={"User-Agent": UA, "Accept": "text/html"}, timeout=20)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            d = parse_fantasypros(r.text)
            out["pages"][key] = d.get("players", [])
            out["week"] = out["week"] or d.get("week")
            out["experts"] = d.get("total_experts")
            out["updated"] = d.get("last_updated")
        except Exception as exc:  # noqa: BLE001
            out["errors"].append(f"FantasyPros {slug}: {exc}")
    return out


def load_or_fetch_fp_weekly(cfg: Settings, settings: LeagueSettings, superflex: bool, refresh: bool) -> dict[str, Any]:
    fmt = scoring_format(settings)
    path = cfg.data_path / f"fp_weekly_{cfg.season}.json"
    cached = read_json(path)
    if cached and not refresh:
        fetched = datetime.fromisoformat(cached["fetched_at"])
        if datetime.now(timezone.utc) - fetched < FP_WEEKLY_TTL:
            return cached
    data = fetch_fp_weekly(fmt, superflex)
    data["fetched_at"] = datetime.now(timezone.utc).isoformat()
    if data["pages"]:
        write_json(path, data)
        return data
    return cached or data


def _float(v: Any) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def apply_fp_weekly(players: list[WeekPlayer], fp: dict[str, Any]) -> None:
    """Attach cross-position weekly rank (ALL page) and per-position grade/opponent/projection."""
    pages = fp.get("pages", {})
    by_pos: dict[Position, list[WeekPlayer]] = {}
    for p in players:
        by_pos.setdefault(p.position, []).append(p)
    dst = {p.pro_team.upper(): p for p in players if p.position == "D/ST"}
    pool_by_id = {p.player_id: p for p in players}

    def find(row: dict[str, Any], pos: Position | None) -> WeekPlayer | None:
        if pos == "D/ST":
            team = str(row.get("player_team_id", "")).upper()
            return dst.get(ABBREV_ALIASES.get(team, team)) or dst.get(TEAM_ABBREV.get(str(row.get("player_name", "")).lower(), ""))
        cands = by_pos.get(pos, []) if pos else players
        hit = match_player_by_name(str(row.get("player_name", "")), cands, None)  # type: ignore[arg-type]
        return pool_by_id.get(hit.player_id) if hit else None

    for row in pages.get("ALL", []):
        pos = FP_POS.get(str(row.get("player_position_id", "")).upper())
        wp = find(row, pos)
        if wp is None:
            continue
        wp.fp_rank = int(row.get("rank_ecr") or 0) or None
        wp.fp_best = int(row.get("rank_min") or 0) or None
        wp.fp_worst = int(row.get("rank_max") or 0) or None
    for pos, key in (("QB", "QB"), ("RB", "RB"), ("WR", "WR"), ("TE", "TE"), ("D/ST", "D/ST"), ("K", "K")):
        for row in pages.get(key, []):
            wp = find(row, pos)  # type: ignore[arg-type]
            if wp is None:
                continue
            wp.fp_pos_rank = row.get("pos_rank") or f"{pos}{row.get('rank_ecr')}"
            wp.fp_grade = row.get("start_sit_grade") or None
            wp.fp_proj = _float(row.get("r2p_pts"))
            if wp.fp_rank is None:
                wp.fp_rank = int(row.get("rank_ecr") or 0) or None
            if not wp.opponent and row.get("player_opponent"):
                wp.opponent = str(row.get("player_opponent")).replace("vs.", "").replace("at", "").strip() or None


def apply_bc_tiers(players: list[WeekPlayer], bc: dict[Position, list[tuple[str, int]]] | None) -> None:
    if not bc:
        return
    by_pos: dict[Position, list[WeekPlayer]] = {}
    for p in players:
        by_pos.setdefault(p.position, []).append(p)
    dst = {p.pro_team.upper(): p for p in players if p.position == "D/ST"}
    for pos, rows in bc.items():
        for name, tier in rows:
            if pos == "D/ST":
                wp = dst.get(TEAM_ABBREV.get(name.lower(), ""))
            else:
                hit = match_player_by_name(name, by_pos.get(pos, []), None)  # type: ignore[arg-type]
                wp = next((p for p in by_pos.get(pos, []) if hit and p.player_id == hit.player_id), None)
            if wp is not None and wp.bc_tier is None:
                wp.bc_tier = tier
