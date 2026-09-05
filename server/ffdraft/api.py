"""FastAPI routes under /api."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Body, HTTPException, Query, Request
from pydantic import BaseModel

from . import keeper as keeper_engine
from . import recommend as rec_engine
from .context import AppContext
from .draft import ConflictError, DraftBoard, open_slots
from .board import board_view, set_cell
from . import injury as injury_engine
from .detail import build_detail
from .strategy import build_guide
from .models import BoardView, StrategyGuide, DraftView, KeeperEntry, PickTrade, PlayerDetail, RankedPlayer, Recommendation, SheetConflict, SheetStatus, SheetSyncReport, WeekView

router = APIRouter(prefix="/api")


def ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def _view(c: AppContext) -> DraftView:
    s = c.require_ready()
    assert c.rankings is not None and c.board is not None
    b: DraftBoard = c.board
    my = [c.rankings.by_id[i] for i in b.my_roster_ids() if i in c.rankings.by_id]
    names = {p.player_id: p.name for p in c.players}
    last = b.state.history[-1] if b.state.history else None
    undo_label = None
    if last is not None:
        cur = b.state.picks[last.overall - 1]
        who = names.get(cur.player_id) if cur.player_id else None
        undo_label = f"pick #{last.overall} (R{last.round})" + (f" \u2014 {who}" if who else "")
    return DraftView(
        state=b.state,
        on_the_clock=b.next_open(),
        my_next_pick=b.my_next_pick(),
        picks_until_my_turn=b.picks_until_my_turn(),
        my_roster=my,
        open_slots=open_slots([p.position for p in my], s.roster_slots),
        taken_ids=sorted(b.taken_ids()),
        recent=b.recent(),
        team_names={t.team_id: t.name for t in s.teams},
        player_names={pid: names.get(pid, "?") for pid in b.taken_ids()},
        can_undo=bool(b.state.history),
        undo_label=undo_label,
    )


@router.get("/settings")
def get_settings(request: Request) -> dict[str, Any]:
    c = ctx(request)
    files = {}
    for p in sorted(c.cfg.data_path.glob("*.json")):
        files[p.name] = p.stat().st_mtime
    return {
        "settings": c.settings,
        "ready": c.ready,
        "has_credentials": c.cfg.has_credentials,
        "season": c.cfg.season,
        "cache_files": files,
        "setup_warnings": c.setup_warnings,
        "players": len(c.players),
        "draft_years": sorted(c.drafts.keys()),
        "history_source": c.history_source,
        "roster_source": c.roster_source,
        "external": c.external_summary(),
        "roster_prev": len(c.roster_prev),
    }


@router.post("/sync")
def post_sync(request: Request, refresh: bool = Query(False)) -> Any:
    c = ctx(request)
    try:
        return c.sync(refresh=refresh)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"ESPN sync failed: {exc}") from exc


@router.get("/players", response_model=list[RankedPlayer])
def get_players(request: Request, pos: str | None = None, q: str | None = None, available: bool = False, limit: int = 1200) -> list[RankedPlayer]:
    c = ctx(request)
    c.require_ready()
    assert c.rankings is not None
    out = c.rankings.overall
    if pos:
        out = [p for p in out if p.position == pos]
    if q:
        ql = q.lower()
        out = [p for p in out if ql in p.name.lower()]
    if available and c.board is not None:
        taken = c.board.taken_ids()
        out = [p for p in out if p.player_id not in taken]
    return out[:limit]


@router.get("/keeper-options")
def get_keeper_options(request: Request) -> Any:
    c = ctx(request)
    s = c.require_ready()
    assert c.rankings is not None
    opts = keeper_engine.keeper_options(c.roster_prev, c.rankings, c.drafts, s, c.setup, c.curve())
    for o in opts:
        o.history_points = c.points_history.get(o.roster_entry.player_id, [])
    return opts


@router.get("/cheatsheet")
def get_cheatsheet(request: Request) -> dict[str, Any]:
    c = ctx(request)
    c.require_ready()
    assert c.rankings is not None
    by_pos: dict[str, list[list[RankedPlayer]]] = {}
    for pos, lst in c.rankings.by_pos.items():
        tiers: list[list[RankedPlayer]] = []
        for p in lst:
            if not tiers or tiers[-1][0].tier != p.tier:
                tiers.append([])
            tiers[-1].append(p)
        by_pos[pos] = tiers
    taken = sorted(c.board.taken_ids()) if c.board else []
    return {"by_pos": by_pos, "overall": c.rankings.overall, "baselines": c.rankings.baselines, "starter_counts": c.rankings.starter_counts, "taken_ids": taken}


@router.get("/setup")
def get_setup(request: Request) -> dict[str, Any]:
    c = ctx(request)
    s = c.require_ready()
    from .draft import resolve_slot_order

    order, provisional = resolve_slot_order(s, c.setup)
    espn_order = bool(s.draft_order) and sorted(s.draft_order or []) == sorted(t.team_id for t in s.teams)
    return {"setup": c.setup, "slot_order": order, "provisional": provisional, "espn_order_present": espn_order, "warnings": c.setup_warnings + (c.board.state.warnings if c.board else []), "teams": s.teams, "my_team_id": s.my_team_id}


class KeepersBody(BaseModel):
    other_keepers: list[KeeperEntry]
    my_keeper: KeeperEntry | None = None


@router.post("/setup/keepers")
def post_keepers(request: Request, body: KeepersBody) -> Any:
    c = ctx(request)
    c.require_ready()
    c.setup.other_keepers = [c.resolve_keeper(k) for k in body.other_keepers]
    c.setup.my_keeper = c.resolve_keeper(body.my_keeper) if body.my_keeper else None
    c.save_setup()
    _rebuild(c)
    return get_setup(request)


@router.post("/setup/pick-trades")
def post_pick_trades(request: Request, trades: list[PickTrade] = Body(...)) -> Any:
    c = ctx(request)
    c.require_ready()
    c.setup.pick_trades = [c.resolve_trade(t) for t in trades]
    c.save_setup()
    _rebuild(c)
    return get_setup(request)


class SlotBody(BaseModel):
    my_slot: int | None = None
    slot_order: list[int] | None = None
    order_confirmed: bool | None = None


@router.post("/setup/slot")
def post_slot(request: Request, body: SlotBody) -> Any:
    c = ctx(request)
    c.require_ready()
    c.setup.my_slot = body.my_slot
    c.setup.slot_order = body.slot_order
    if body.order_confirmed is not None:
        c.setup.order_confirmed = body.order_confirmed
    c.save_setup()
    _rebuild(c)
    return get_setup(request)


class OverrideBody(BaseModel):
    player_id: int
    cost_round: int | None = None


@router.post("/setup/keeper-cost-override")
def post_override(request: Request, body: OverrideBody) -> Any:
    c = ctx(request)
    c.require_ready()
    if body.cost_round is None:
        c.setup.keeper_cost_overrides.pop(body.player_id, None)
    else:
        c.setup.keeper_cost_overrides[body.player_id] = body.cost_round
    c.save_setup()
    return get_keeper_options(request)


def _rebuild(c: AppContext) -> None:
    try:
        c.rebuild_board()
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/draft/state", response_model=DraftView)
def get_draft_state(request: Request) -> DraftView:
    return _view(ctx(request))


class StateAction(BaseModel):
    action: str


@router.post("/draft/state", response_model=DraftView)
def post_draft_state(request: Request, body: StateAction) -> DraftView:
    c = ctx(request)
    c.require_ready()
    if body.action == "reset":
        c.rebuild_board(force=True)
    else:
        raise HTTPException(status_code=400, detail="Unknown action")
    return _view(c)


class PickBody(BaseModel):
    player_id: int
    mine: bool = False
    force: bool = False


@router.post("/draft/pick", response_model=DraftView)
def post_pick(request: Request, body: PickBody) -> DraftView:
    c = ctx(request)
    c.require_ready()
    assert c.board is not None and c.rankings is not None
    if body.player_id not in c.rankings.by_id:
        raise HTTPException(status_code=404, detail="Unknown player id")
    try:
        c.board.record_pick(body.player_id, mine=body.mine, force=body.force)
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _view(c)


class AssignBody(BaseModel):
    overall: int
    player_id: int | None = None


@router.post("/draft/assign", response_model=DraftView)
def post_assign(request: Request, body: AssignBody) -> DraftView:
    """Draft a player into any pick, or clear it. Order-independent, so falling behind is recoverable."""
    c = ctx(request)
    c.require_ready()
    assert c.board is not None and c.rankings is not None
    if body.player_id is not None and body.player_id not in c.rankings.by_id:
        raise HTTPException(status_code=404, detail="Unknown player id")
    try:
        c.board.assign(body.overall, body.player_id)
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _view(c)


@router.post("/draft/skip", response_model=DraftView)
def post_skip(request: Request) -> DraftView:
    c = ctx(request)
    c.require_ready()
    assert c.board is not None
    try:
        c.board.skip_pick()
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _view(c)


@router.post("/draft/undo", response_model=DraftView)
def post_undo(request: Request) -> DraftView:
    c = ctx(request)
    c.require_ready()
    assert c.board is not None
    c.board.undo()
    return _view(c)


@router.get("/draft/recommendations")
def get_recommendations(request: Request) -> dict[str, Any]:
    c = ctx(request)
    s = c.require_ready()
    assert c.board is not None and c.rankings is not None
    recs = rec_engine.recommend(c.board, c.rankings, s)
    by_pos: dict[str, Recommendation] = rec_engine.best_by_position(recs)
    return {
        "top": rec_engine.top(recs),
        "by_position": by_pos,
        **rec_engine.roster_needs(c.board, c.rankings, s),
    }


# ---- color-coded board + Google Sheet ---------------------------------------


@router.get("/board", response_model=BoardView)
def get_board(request: Request) -> BoardView:
    c = ctx(request)
    s = c.require_ready()
    assert c.board is not None
    return board_view(c.board, s, c.setup, c.players_by_id, c.sheet_conflicts.pending)


class CellBody(BaseModel):
    original_team_id: int
    round: int
    player_id: int | None = None
    owner_team_id: int | None = None
    clear: bool = False


@router.post("/board/cell", response_model=BoardView)
def post_cell(request: Request, body: CellBody) -> BoardView:
    c = ctx(request)
    s = c.require_ready()
    assert c.board is not None
    try:
        set_cell(c.board, c.setup, s.season, body.original_team_id, body.round, body.player_id, body.owner_team_id, body.clear)
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    c.save_setup()
    return board_view(c.board, s, c.setup, c.players_by_id, c.sheet_conflicts.pending)


@router.get("/sheet/status", response_model=SheetStatus)
def get_sheet_status(request: Request) -> SheetStatus:
    return ctx(request).sheet_status()


@router.post("/sheet/sync", response_model=SheetSyncReport)
def post_sheet_sync(request: Request) -> SheetSyncReport:
    c = ctx(request)
    try:
        return c.sheet_sync()
    except LookupError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Sheet sync failed: {exc}") from exc


@router.get("/sheet/conflicts", response_model=list[SheetConflict])
def get_sheet_conflicts(request: Request) -> list[SheetConflict]:
    """Sheet changes held back because they disagree with something typed by hand."""
    return ctx(request).sheet_conflicts.pending


class ConflictResolveBody(BaseModel):
    key: str
    choice: Literal["sheet", "board"]


@router.post("/sheet/conflicts/resolve", response_model=BoardView)
def post_resolve_conflict(request: Request, body: ConflictResolveBody) -> BoardView:
    c = ctx(request)
    s = c.require_ready()
    assert c.board is not None
    try:
        c.resolve_sheet_conflict(body.key, body.choice)
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return board_view(c.board, s, c.setup, c.players_by_id, c.sheet_conflicts.pending)


class SheetColumnsBody(BaseModel):
    columns: dict[str, int]


@router.post("/setup/sheet-columns", response_model=SheetStatus)
def post_sheet_columns(request: Request, body: SheetColumnsBody) -> SheetStatus:
    c = ctx(request)
    c.set_sheet_columns(body.columns)
    return c.sheet_status()


@router.post("/external/refresh")
def post_external_refresh(request: Request) -> Any:
    c = ctx(request)
    try:
        c.refresh_external()
    except LookupError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Expert rankings refresh failed: {exc}") from exc
    return c.external_summary()


@router.get("/week", response_model=WeekView)
def get_week(request: Request, week: int | None = None, refresh: bool = False) -> WeekView:
    c = ctx(request)
    try:
        return c.week_view(week=week, refresh=refresh)
    except LookupError:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/player/{player_id}", response_model=PlayerDetail)
def get_player_detail(request: Request, player_id: int) -> PlayerDetail:
    """Everything worth knowing before spending a pick on him."""
    c = ctx(request)
    s = c.require_ready()
    assert c.rankings is not None
    player = c.rankings.by_id.get(player_id)
    if player is None:
        raise HTTPException(status_code=404, detail="Unknown player id")
    history = c.points_history.get(player_id) or c.points_history.get(str(player_id)) or []
    err: str | None = None
    if not history:
        try:
            years = [s.season - k for k in (1, 2, 3)]
            fetched = c.client.fetch_points_history([player_id], years)
            history = fetched.get(player_id, [])
            c.points_history[player_id] = history
        except Exception as exc:  # noqa: BLE001
            err = f"Season history unavailable: {exc}"
    taken_at = taken_by = None
    if c.board is not None:
        hit = next((p for p in c.board.picks if p.player_id == player_id), None)
        if hit is not None:
            taken_at = hit.overall
            taken_by = next((t.name for t in s.teams if t.team_id == hit.owner_team_id), None)
    taken = c.board.taken_ids() if c.board else set()
    detail = build_detail(player, history, c.rankings, s, taken, taken_at, taken_by, err)
    raw_news, news_err = None, None
    try:
        raw_news = injury_engine.fetch_news(c.cfg, c.client, player_id)
    except Exception as exc:  # noqa: BLE001
        news_err = f"Injury news unavailable: {exc}"
    detail.injury = injury_engine.build_report(player, history, raw_news, news_err)
    return detail


@router.get("/strategy", response_model=StrategyGuide)
def get_strategy(request: Request) -> StrategyGuide:
    """How to think about this specific league's draft, with its real numbers."""
    c = ctx(request)
    s = c.require_ready()
    assert c.rankings is not None
    return build_guide(c.rankings, s)
