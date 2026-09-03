"""Injury picture for a player: ESPN's current tag, recent beat-writer notes, and games missed."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import Settings
from .models import InjuryNote, InjuryReport, MissedTime, Player, SeasonPoints
from .store import read_json, write_json

log = logging.getLogger(__name__)
NEWS_TTL = timedelta(hours=12)
FULL_SEASON = 17

BODY_PARTS = (
    "knee acl mcl hamstring ankle groin shoulder concussion calf quad quadriceps foot toe back hip wrist elbow "
    "ribs achilles hand finger thumb neck oblique pectoral thigh heel shin forearm collarbone abdomen illness"
).split()
INJURY_WORDS = ["injury", "injured", "surgery", "strain", "sprain", "tear", "torn", "fracture", "soreness",
                "sidelined", "questionable", "doubtful", "designated to return", "did not practice", "limited participant"]
# Word boundaries matter: "football" must not read as a foot injury.
BODY_RE = re.compile(r"\b(" + "|".join(BODY_PARTS) + r")\b", re.I)
WORD_RE = re.compile(r"\b(" + "|".join(w.replace(" ", r"\s+") for w in INJURY_WORDS) + r")\b", re.I)
# "Chase (knee) was present but..." -> knee
PAREN = re.compile(r"\(([a-zA-Z/ ]{3,24})\)")
ACTIVE = {"", "ACTIVE", "NORMAL", "NONE"}


def _is_injury_item(headline: str, story: str) -> bool:
    """Only a parenthetical body part in the headline, or explicit injury language, counts.

    ESPN's feed mixes beat-writer injury notes with general fantasy articles; the latter
    routinely say "football", which must not read as a foot injury.
    """
    if _paren_part(headline):
        return True
    text = f"{headline} {story}"
    return bool(WORD_RE.search(text)) and bool(BODY_RE.search(text))


def _paren_part(headline: str) -> str | None:
    m = PAREN.search(headline)
    if not m:
        return None
    part = m.group(1).strip().lower()
    return part if BODY_RE.search(part) else None


def _body_part(headline: str) -> str | None:
    hit = _paren_part(headline)
    if hit:
        return hit
    m = BODY_RE.search(headline)
    return m.group(1).lower() if m else None


def parse_news(raw: dict[str, Any], limit: int = 4) -> tuple[list[InjuryNote], str | None]:
    feed = ((raw or {}).get("news") or {}).get("feed") or []
    notes: list[InjuryNote] = []
    for item in feed:
        headline = str(item.get("headline") or "").strip()
        story = re.sub(r"<[^>]+>", " ", str(item.get("story") or ""))
        if not headline or not _is_injury_item(headline, story[:400]):
            continue
        notes.append(InjuryNote(
            date=str(item.get("published") or "")[:10],
            headline=headline[:220],
            body_part=_body_part(headline) or _body_part(story[:200]),
            source=str(item.get("type") or ""),
        ))
        if len(notes) >= limit:
            break
    part = next((n.body_part for n in notes if n.body_part), None)
    return notes, part


def missed_time(history: list[SeasonPoints]) -> list[MissedTime]:
    return [
        MissedTime(season=h.season, games=h.games, missed=max(0, FULL_SEASON - h.games))
        for h in history
        if h.games and h.games < FULL_SEASON
    ]


def fetch_news(cfg: Settings, client: Any, player_id: int) -> dict[str, Any]:
    """ESPN's player news feed, cached for half a day."""
    path = cfg.data_path / f"news_{cfg.season}.json"
    cache = read_json(path) or {}
    hit = cache.get(str(player_id))
    if hit and datetime.now(timezone.utc) - datetime.fromisoformat(hit["fetched_at"]) < NEWS_TTL:
        return hit["raw"]
    league = client._league(cfg.season)
    raw = league.espn_request.get_player_news(player_id)
    cache[str(player_id)] = {"fetched_at": datetime.now(timezone.utc).isoformat(), "raw": raw}
    write_json(path, cache)
    return raw


def build_report(player: Player, history: list[SeasonPoints], raw_news: dict[str, Any] | None, error: str | None = None) -> InjuryReport:
    status = (player.injury_status or "").upper()
    status_out = None if status in ACTIVE else status.replace("_", " ").title()
    notes, part = parse_news(raw_news or {})
    missed = missed_time(history)
    total_missed = sum(m.missed for m in missed)

    level = "none"
    bits: list[str] = []
    if status in ("OUT", "INJURY_RESERVE", "IR", "SUSPENSION", "DOUBTFUL"):
        level = "concern"
        bits.append(f"ESPN lists him {status_out} right now")
    elif status == "QUESTIONABLE":
        level = "watch"
        bits.append("ESPN lists him Questionable right now")
    if part:
        bits.append(f"recent reports mention a {part}")
        if level == "none":
            level = "watch"
    if missed:
        seasons = ", ".join(f"{m.season} ({m.missed} missed)" for m in missed)
        bits.append(f"he has missed games before: {seasons}")
        if total_missed >= 6 and level != "concern":
            level = "concern"
        elif level == "none":
            level = "watch"
    if not bits:
        concern = "No injury designation and no missed games in the seasons on record."
    else:
        concern = bits[0][0].upper() + bits[0][1:] + ("; " + "; ".join(bits[1:]) if len(bits) > 1 else "") + "."
        if level == "concern":
            concern += " Treat the projection as a ceiling and plan for a backup."
        elif level == "watch":
            concern += " Worth checking his status before the draft, but not disqualifying."
    return InjuryReport(status=status_out, body_part=part, concern=concern, level=level, notes=notes, missed=missed, error=error)
