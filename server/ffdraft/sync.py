"""CLI: uv run python -m ffdraft.sync [--refresh]"""
from __future__ import annotations

import argparse
import logging

from .config import get_settings
from .espn.client import EspnClient


def main() -> None:
    ap = argparse.ArgumentParser(description="Pull league settings, players, roster and draft history from ESPN")
    ap.add_argument("--refresh", action="store_true", help="ignore cached JSON and hit ESPN")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = get_settings()
    report = EspnClient(cfg).sync_all(refresh=args.refresh)
    s = report.settings
    print(f"League: {s.league_name} ({s.team_count} teams, {s.rounds} rounds) - my team: {s.my_team_name} (id {s.my_team_id})")
    print(f"Roster slots: {s.roster_slots}")
    print(f"Draft order: {s.draft_order or 'not set yet'}")
    print(f"Players: {report.players}  | {cfg.season - 1} roster: {report.roster_prev} | draft years: {report.draft_years}")
    if report.from_cache:
        print(f"From cache: {', '.join(report.from_cache)}")
    for e in report.errors:
        print(f"WARNING {e}")


if __name__ == "__main__":
    main()
