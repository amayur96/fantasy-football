"""Single mutable app state: cached league data, rankings, setup overrides, and the draft board."""
from __future__ import annotations

import logging
from pathlib import Path

from .config import Settings, get_settings
from .draft import ConflictError, DraftBoard
from .espn.client import EspnClient
from .espn.parse import match_player_by_name
from .models import (
    DraftHistoryPick,
    KeeperEntry,
    LeagueSettings,
    PickTrade,
    Player,
    RosterEntry,
    SetupOverrides,
    SheetColumn,
    SheetConflict,
    SheetConflictState,
    SheetGrid,
    SheetStatus,
    SheetSyncReport,
    SyncReport,
)
from . import external, sheets
from .models import ExternalData
from .store import load_model, read_json, write_json
from .value import Rankings, build_rankings, pick_curve

log = logging.getLogger(__name__)


class AppContext:
    def __init__(self, cfg: Settings | None = None):
        self.cfg = cfg or get_settings()
        self.client = EspnClient(self.cfg)
        self.settings: LeagueSettings | None = None
        self.players: list[Player] = []
        self.rankings: Rankings | None = None
        self.drafts: dict[int, list[DraftHistoryPick]] = {}
        self.roster_prev: list[RosterEntry] = []
        self.setup: SetupOverrides = SetupOverrides()
        self.board: DraftBoard | None = None
        self.setup_warnings: list[str] = []
        self.last_sheet: SheetSyncReport | None = None
        self.sheet_conflicts: SheetConflictState = SheetConflictState()
        self.last_grid: SheetGrid | None = None
        self.history_source: dict[int, str] = {}
        self.roster_source: str = "espn"
        self.external: ExternalData | None = None
        self.points_history: dict[int, list] = {}

    # ---- paths ------------------------------------------------------------
    @property
    def setup_path(self) -> Path:
        return self.cfg.data_path / "setup.json"

    @property
    def draft_path(self) -> Path:
        return self.cfg.data_path / "draft_state.json"

    @property
    def conflicts_path(self) -> Path:
        """Sheet disagreements awaiting a decision; survives restarts mid-draft."""
        return self.cfg.data_path / "sheet_conflicts.json"

    @property
    def seed_path(self) -> Path:
        """Git-ignored per-league seed (other teams' keepers + pick trades)."""
        return self.cfg.data_path / "seed" / f"league_{self.cfg.season}.json"

    # ---- loading ----------------------------------------------------------
    def load(self) -> None:
        """Read everything from data/ (no network)."""
        self.settings = self.client.load_cached_settings()
        self.players = self.client.load_cached_players()
        self.drafts = self.client.load_cached_drafts()
        self.history_source = {y: "espn" for y in self.drafts}
        for path in sorted(self.cfg.data_path.glob("sheet_draft_*.json")):
            try:
                year = int(path.stem.split("_")[-1])
            except ValueError:
                continue
            picks = load_model(path, list[DraftHistoryPick])
            if picks:
                self.drafts[year] = picks
                self.history_source[year] = "sheet"
        self.roster_prev = self.client.load_cached_roster(self.cfg.season - 1)
        self.roster_source = "espn"
        sheet_roster = load_model(self.cfg.data_path / f"sheet_roster_{self.cfg.season - 1}.json", list[RosterEntry])
        if sheet_roster:
            self.roster_prev, self.roster_source = sheet_roster, "sheet"
        self.setup = load_model(self.setup_path, SetupOverrides) or SetupOverrides()
        self.sheet_conflicts = load_model(self.conflicts_path, SheetConflictState) or SheetConflictState()
        self.external = external.load_cached(self.cfg)
        external.apply_to_players(self.players, self.external)
        from .models import SeasonPoints

        self.points_history = load_model(self.cfg.data_path / f"points_{self.cfg.season}.json", dict[int, list[SeasonPoints]]) or {}
        self.recompute()

    def sync(self, refresh: bool) -> SyncReport:
        report = self.client.sync_all(refresh=refresh)
        self.load()
        if self.cfg.google_sheet_id and self.settings is not None:
            report.errors += self.sync_sheet_history(refresh)
            self.load()
        if self.roster_prev:
            years = [self.cfg.season - k for k in (1, 2, 3)]
            try:
                self.points_history = self.client.fetch_points_history([r.player_id for r in self.roster_prev], years, refresh=refresh)
            except Exception as exc:  # noqa: BLE001
                report.errors.append(f"points history: {exc}")
        if self.settings is not None and self.players:
            data = external.load_or_fetch(self.cfg, self.settings, self.players, refresh=refresh)
            if data is None:
                report.errors.append("Expert rankings unavailable (FantasyPros / Boris Chen)")
            else:
                report.errors += data.errors
            self.load()
        return report

    def refresh_external(self) -> ExternalData:
        s = self.require_ready()
        data = external.fetch_all(self.cfg, s, self.players)
        self.load()
        return data

    def external_summary(self) -> dict[str, object] | None:
        d = self.external
        if d is None:
            return None
        return {
            "scoring": d.scoring, "superflex": d.superflex, "fp_experts": d.fp_experts, "fp_updated": d.fp_updated,
            "fp_page": d.fp_page, "fetched_at": d.fetched_at, "errors": d.errors, "matched": d.matched,
            "unmatched": {k: v[:25] for k, v in d.unmatched.items()}, "stale": external.is_stale(d),
        }

    def sync_sheet_history(self, refresh: bool) -> list[str]:
        """Rebuild draft_{year} from the sheet's history tabs (cached as sheet_draft_{year}.json)."""
        from .history import history_from_grid, resolve_history_columns, roster_from_grid

        assert self.settings is not None
        errors: list[str] = []
        for year in range(self.cfg.season - 1, self.cfg.first_history_year - 1, -1):
            path = self.cfg.data_path / f"sheet_draft_{year}.json"
            if path.exists() and not refresh:
                continue
            try:
                grid = sheets.fetch_grid(self.cfg, str(year))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"sheet {year}: {exc}")
                continue
            espn = self.client.load_cached_drafts().get(year, [])
            my_ids = {p.player_id for p in espn if p.team_id == self.settings.my_team_id}
            mapping = resolve_history_columns(grid, self.settings.my_team_id, my_ids, self.players, self.setup.sheet_columns, self.team_by_owner_name)
            picks = history_from_grid(grid, year, mapping, self.players)
            if not picks:
                errors.append(f"sheet {year}: no picks parsed")
                continue
            write_json(path, picks)
            if year == self.cfg.season - 1:
                my_col = next((c for c, t in mapping.items() if t == self.settings.my_team_id), None)
                if my_col is None:
                    errors.append(f"sheet {year}: could not tell which column is yours; keeper options fall back to the ESPN roster")
                else:
                    write_json(self.cfg.data_path / f"sheet_roster_{year}.json", roster_from_grid(grid, year, my_col, self.settings.my_team_id, self.players))
        return errors

    def recompute(self) -> None:
        if self.settings and self.players:
            self.rankings = build_rankings(self.players, self.settings)
            if not self.setup_path.exists():
                self.seed_setup()
            self.board = DraftBoard.load_or_build(self.settings, self.setup, self.draft_path)
        else:
            self.rankings = None
            self.board = None

    @property
    def ready(self) -> bool:
        return self.settings is not None and self.rankings is not None

    def require_ready(self) -> LeagueSettings:
        if self.settings is None or self.rankings is None:
            raise LookupError("League data not synced yet. Run a sync from the Setup page (or `make sync`).")
        return self.settings

    def curve(self) -> list[float]:
        s = self.require_ready()
        assert self.rankings is not None
        return pick_curve(self.rankings, s.rounds * s.team_count)

    # ---- setup persistence ---------------------------------------------
    def save_setup(self) -> None:
        write_json(self.setup_path, self.setup)

    def team_by_owner_name(self, owner_last: str) -> int:
        assert self.settings is not None
        want = owner_last.strip().lower()
        for t in self.settings.teams:
            hay = " ".join(t.owner_names + [t.name, t.abbrev]).lower()
            if want and want in hay:
                return t.team_id
        return 0

    def resolve_keeper(self, k: KeeperEntry) -> KeeperEntry:
        """Fill team_id / player_id from names where missing."""
        if not k.team_id and k.owner_name:
            k.team_id = self.team_by_owner_name(k.owner_name)
        if not k.player_id and k.player_name:
            hit = match_player_by_name(k.player_name, self.players)
            if hit:
                k.player_id, k.player_name = hit.player_id, hit.name
        return k

    def resolve_trade(self, t: PickTrade) -> PickTrade:
        if not t.original_team_id and t.original_owner_name:
            t.original_team_id = self.team_by_owner_name(t.original_owner_name)
        if not t.owner_team_id and t.owner_name:
            t.owner_team_id = self.team_by_owner_name(t.owner_name)
        return t

    def seed_setup(self) -> None:
        raw = read_json(self.seed_path) or {}
        if self.settings is None:
            return
        keepers = [self.resolve_keeper(KeeperEntry(**k)) for k in raw.get("keepers", [])]
        trades = [self.resolve_trade(PickTrade(**t)) for t in raw.get("pick_trades", [])]
        self.setup.other_keepers = [k for k in keepers if k.team_id != self.settings.my_team_id]
        self.setup.pick_trades = trades
        self.setup_warnings = [
            f"Unresolved keeper: {k.owner_name} / {k.player_name}" for k in keepers if not k.team_id or not k.player_id
        ] + [
            f"Unresolved pick trade: R{t.round} {t.original_owner_name} -> {t.owner_name}" for t in trades if not t.original_team_id or not t.owner_team_id
        ]
        self.save_setup()

    def rebuild_board(self, force: bool = False) -> None:
        if self.settings is None:
            return
        if self.board is not None and self.board.user_picks_made() and not force:
            raise ConflictError("Draft picks have been recorded; reset the draft board before changing setup.")
        if self.draft_path.exists():
            self.draft_path.unlink()
        self.board = DraftBoard.load_or_build(self.settings, self.setup, self.draft_path)

    # ---- Google Sheet ----------------------------------------------------
    @property
    def players_by_id(self) -> dict[int, Player]:
        return {p.player_id: p for p in self.players}

    def sheet_status(self) -> SheetStatus:
        cfg = self.cfg
        cols: list[SheetColumn] = []
        if self.last_grid is not None:
            from .board import resolve_columns

            mapping = resolve_columns(self.last_grid, self.settings, self.setup, self.team_by_owner_name) if self.settings else {}
            cols = [SheetColumn(header=h, team_id=mapping.get(i, 0), color=self.last_grid.header_colors[i]) for i, h in enumerate(self.last_grid.headers) if h]
        else:
            cols = [SheetColumn(header=h, team_id=t) for h, t in self.setup.sheet_columns.items()]
        return SheetStatus(
            configured=bool(cfg.google_sheet_id), sheet_id=cfg.google_sheet_id, tab=cfg.sheet_tab, auth=sheets.auth_mode(cfg),  # type: ignore[arg-type]
            credentials_file_present=cfg.google_credentials_file.exists(), token_present=cfg.google_token_path.exists(),
            poll_seconds=cfg.sheet_poll_seconds, last=self.last_sheet, columns=cols,
        )

    def sheet_sync(self) -> SheetSyncReport:
        from .board import apply_grid, resolve_columns

        s = self.require_ready()
        assert self.board is not None
        grid = sheets.fetch_grid(self.cfg)
        self.last_grid = grid
        mapping = resolve_columns(grid, s, self.setup, self.team_by_owner_name)
        # remember the resolved mapping in sheet order so the board can mirror the sheet's columns
        self.setup.sheet_columns = {h: mapping.get(i, self.setup.sheet_columns.get(h, 0)) for i, h in enumerate(grid.headers) if h}
        report = apply_grid(self.board, grid, mapping, s, self.setup, self.players, self.sheet_conflicts.dismissed)
        # Each sync re-detects from scratch: a conflict the user resolved simply stops appearing.
        self.sheet_conflicts.pending = report.conflicts
        self.save_conflicts()
        self.save_setup()
        self.last_sheet = report
        return report

    def save_conflicts(self) -> None:
        write_json(self.conflicts_path, self.sheet_conflicts)

    def resolve_sheet_conflict(self, key: str, choice: str) -> SheetConflict:
        """choice "sheet" applies the spreadsheet's player; "board" keeps what you typed."""
        from .board import apply_conflict

        hit = next((c for c in self.sheet_conflicts.pending if c.key == key), None)
        if hit is None:
            raise LookupError(f"No pending sheet conflict for {key}")
        if choice not in ("sheet", "board"):
            raise ValueError('choice must be "sheet" or "board"')
        assert self.board is not None
        if choice == "sheet":
            apply_conflict(self.board, hit)
            self.sheet_conflicts.dismissed.pop(key, None)
        else:
            # Remember the rejection so the next sync does not ask again about this same value.
            self.sheet_conflicts.dismissed[key] = hit.sheet_text
        self.sheet_conflicts.pending = [c for c in self.sheet_conflicts.pending if c.key != key]
        self.save_conflicts()
        return hit

    def set_sheet_columns(self, columns: dict[str, int]) -> None:
        self.setup.sheet_columns = {h: int(t) for h, t in columns.items()}
        self.save_setup()

    # ---- weekly lineup ----------------------------------------------------
    def week_view(self, week: int | None = None, refresh: bool = False) -> "WeekView":
        from datetime import datetime, timezone

        from . import weekly
        from .external import fetch_borischen, is_superflex, scoring_format
        from .lineup import LineupWeights, slot_rows, start_sit_moves, waiver_moves, weekly_score
        from .models import WeekPlayer, WeekView

        s = self.require_ready()
        errors: list[str] = []
        try:
            data = weekly.load_or_fetch_espn_week(self.cfg, s.my_team_id, week, refresh)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"ESPN weekly data: {exc}") from exc
        roster = [WeekPlayer(**r) for r in data["roster"]]
        fas = [WeekPlayer(**f) for f in data["free_agents"]]
        wk = int(data["week"])
        label = f"NFL Week {wk}" + (" (preseason)" if int(data.get("current_week") or 0) == 0 else "")
        sources = {"espn": data["fetched_at"]}
        if roster:
            try:
                fp = weekly.load_or_fetch_fp_weekly(self.cfg, s, is_superflex(s), refresh)
                weekly.apply_fp_weekly(roster + fas, fp)
                errors += fp.get("errors", [])
                sources["fantasypros"] = f"week {fp.get('week')} · {fp.get('experts')} experts · updated {fp.get('updated')}"
            except Exception as exc:  # noqa: BLE001
                errors.append(f"FantasyPros weekly: {exc}")
            if self.external is not None:
                for p in roster + fas:
                    er = self.external.ranks.get(p.player_id)
                    if er and er.bc_tier:
                        p.bc_tier = er.bc_tier
                sources["borischen"] = f"tiers fetched {self.external.fetched_at:%b %d %H:%M}"
        w = LineupWeights()
        for p in roster + fas:
            p.score = weekly_score(p, w)
        moves, optimal, cur_total, opt_total = start_sit_moves(roster, s, w) if roster else ([], {}, 0.0, 0.0)
        waivers = waiver_moves(roster, fas, s, w) if roster else []
        rows = slot_rows(roster, s, optimal)
        return WeekView(
            season=int(data["season"]), week=wk, week_label=label, fetched_at=datetime.fromisoformat(data["fetched_at"]) if isinstance(data["fetched_at"], str) else datetime.now(timezone.utc),
            roster_empty=not roster, opponent_name=data.get("opponent_name"), rows=rows,
            starters=[r.player for r in rows if r.player and r.slot not in ("BE", "IR")], bench=[r.player for r in rows if r.player and r.slot in ("BE", "IR")],
            optimal_slots=optimal, current_total=cur_total, optimal_total=opt_total, moves=moves, waivers=waivers, sources=sources, errors=errors,
        )
