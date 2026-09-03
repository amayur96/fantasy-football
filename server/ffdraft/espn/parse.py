"""Turn raw ESPN JSON / espn_api objects into our models."""
from __future__ import annotations

import difflib
import re
from datetime import datetime, timezone
from typing import Any, Iterable

from espn_api.football.constant import POSITION_MAP, PRO_TEAM_MAP

from ..models import (
    DraftHistoryPick,
    LeagueSettings,
    Player,
    Position,
    RosterEntry,
    ScoringRule,
    TeamInfo,
)

POSITION_BY_ID: dict[int, Position] = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "D/ST"}
SLOT_BY_ID: dict[int, str] = {k: v for k, v in POSITION_MAP.items() if isinstance(k, int)}

# Sheet spellings that fuzzy matching can't recover -> ESPN full names.
NAME_ALIASES: dict[str, str] = {
    "rachee rice": "rashee rice",
    "jaxson smith njigba": "jaxon smith njigba",
    "chubba hubbard": "chuba hubbard",
    "pooka nakooa": "puka nacua",
    "skatteboooo": "cam skattebo",
    "kaleb johnson": "kaleb johnson",
    "hollywood brown": "marquise brown",
    "philly d": "eagles d/st",
    "broncos d": "broncos d/st",
}


def normalize_swid(swid: str) -> str:
    return swid.strip().strip("{}").upper()


def normalize_name(name: str) -> str:
    s = name.lower().replace("'", "").replace(".", "")
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    s = re.sub(r"[^a-z0-9/ ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return NAME_ALIASES.get(s, s)


def find_my_team(league: Any, swid: str) -> Any:
    want = normalize_swid(swid)
    for team in league.teams:
        for owner in team.owners:
            if normalize_swid(str(owner.get("id", ""))) == want:
                return team
    raise LookupError("No team in this league is owned by the SWID in .env")


def parse_settings(league: Any, swid: str, season: int, draft_order: list[int] | None) -> LeagueSettings:
    st = league.settings
    slots: dict[str, int] = {k: int(v) for k, v in st.position_slot_counts.items() if int(v) > 0}
    rounds = sum(v for k, v in slots.items() if k != "IR")
    teams = [
        TeamInfo(
            team_id=t.team_id,
            name=t.team_name,
            abbrev=t.team_abbrev,
            owner_ids=[normalize_swid(str(o.get("id", ""))) for o in t.owners],
            owner_names=[
                " ".join(p for p in (o.get("firstName", ""), o.get("lastName", "")) if p).strip() or o.get("displayName", "")
                for o in t.owners
            ],
        )
        for t in league.teams
    ]
    me = find_my_team(league, swid)
    scoring = [
        ScoringRule(stat_id=int(r.get("id", 0)), abbr=str(r.get("abbr", "")), label=str(r.get("label", "")), points=float(r.get("points", 0) or 0))
        for r in st.scoring_format
    ]
    return LeagueSettings(
        league_id=league.league_id,
        league_name=st.name,
        season=season,
        team_count=st.team_count,
        rounds=rounds,
        roster_slots=slots,
        scoring=scoring,
        teams=teams,
        my_team_id=me.team_id,
        my_team_name=me.team_name,
        keeper_count=int(getattr(st, "keeper_count", 1) or 1),
        draft_order=draft_order,
        synced_at=datetime.now(timezone.utc),
    )


def parse_draft_order(raw: dict[str, Any]) -> list[int] | None:
    order = (raw.get("settings") or {}).get("draftSettings", {}).get("pickOrder")
    if isinstance(order, list) and order and all(isinstance(x, int) for x in order):
        return list(order)
    return None


def parse_bye_weeks(raw: dict[str, Any]) -> dict[int, int]:
    out: dict[int, int] = {}
    for t in (raw.get("settings") or {}).get("proTeams", []):
        if t.get("byeWeek"):
            out[int(t["id"])] = int(t["byeWeek"])
    return out


def parse_kona_player(entry: dict[str, Any], season: int, bye_weeks: dict[int, int] | None = None) -> Player | None:
    p = entry.get("player") or entry
    pos = POSITION_BY_ID.get(int(p.get("defaultPositionId", -1)))
    if pos is None:
        return None
    proj = 0.0
    for s in p.get("stats", []) or []:
        if s.get("statSourceId") == 1 and s.get("scoringPeriodId") == 0 and s.get("seasonId") == season:
            proj = float(s.get("appliedTotal") or 0.0)
            break
    own = p.get("ownership") or {}
    pct = float(own.get("percentOwned") or 0.0)
    adp_raw = own.get("averageDraftPosition")
    adp = float(adp_raw) if adp_raw and float(adp_raw) > 0 and pct >= 1.0 else None
    ranks = p.get("draftRanksByRankType") or {}
    espn_rank = None
    for key in ("PPR", "STANDARD"):
        r = ranks.get(key) or {}
        if r.get("rank"):
            espn_rank = int(r["rank"])
            break
    pro_id = int(p.get("proTeamId") or 0)
    return Player(
        player_id=int(p["id"]),
        name=str(p.get("fullName") or ""),
        position=pos,
        pro_team=PRO_TEAM_MAP.get(pro_id, "FA"),
        eligible_slots=[SLOT_BY_ID.get(int(s), str(s)) for s in p.get("eligibleSlots", []) or []],
        injury_status=p.get("injuryStatus"),
        bye_week=(bye_weeks or {}).get(pro_id),
        proj_points=proj,
        adp=adp,
        percent_owned=pct,
        espn_rank=espn_rank,
        on_team_id=entry.get("onTeamId") or None,
    )


def parse_draft(league: Any, season: int) -> list[DraftHistoryPick]:
    out: list[DraftHistoryPick] = []
    for pick in league.draft:
        team_id = getattr(pick.team, "team_id", 0) or 0
        out.append(
            DraftHistoryPick(
                season=season,
                team_id=int(team_id),
                player_id=int(pick.playerId or 0),
                player_name=str(pick.playerName or ""),
                round_num=int(pick.round_num or 0),
                round_pick=int(pick.round_pick or 0),
                keeper_status=bool(pick.keeper_status),
            )
        )
    return out


def _player_position(p: Any) -> Position | None:
    pos = getattr(p, "position", "")
    return pos if pos in POSITION_BY_ID.values() else None


def parse_roster(team: Any, season: int) -> list[RosterEntry]:
    out: list[RosterEntry] = []
    for p in team.roster:
        pos = _player_position(p)
        if pos is None:
            continue
        out.append(
            RosterEntry(
                season=season,
                team_id=int(team.team_id),
                player_id=int(p.playerId),
                name=str(p.name),
                position=pos,
                pro_team=str(getattr(p, "proTeam", "") or ""),
            )
        )
    return out


def match_player_by_name(name: str, pool: Iterable[Player], position: Position | None = None) -> Player | None:
    """Normalized exact match, then fuzzy match (cutoff 0.85) within the position if given."""
    target = normalize_name(name)
    if not target:
        return None
    candidates = [p for p in pool if position is None or p.position == position]
    by_norm: dict[str, Player] = {}
    for p in candidates:
        by_norm.setdefault(normalize_name(p.name), p)
    if target in by_norm:
        return by_norm[target]
    # last-name-only shorthand like "Gibbs" or "Skattebo"
    last_hits = [p for k, p in by_norm.items() if k.split(" ")[-1] == target]
    if len(last_hits) == 1:
        return last_hits[0]
    close = difflib.get_close_matches(target, list(by_norm.keys()), n=1, cutoff=0.85)
    return by_norm[close[0]] if close else None
