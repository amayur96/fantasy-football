"""Pydantic models shared by the ESPN client, engines, API, and JSON cache."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Position = Literal["QB", "RB", "WR", "TE", "K", "D/ST"]
POSITIONS: tuple[Position, ...] = ("QB", "RB", "WR", "TE", "K", "D/ST")


class TeamInfo(BaseModel):
    team_id: int
    name: str
    abbrev: str
    owner_ids: list[str] = Field(default_factory=list)
    owner_names: list[str] = Field(default_factory=list)


class ScoringRule(BaseModel):
    stat_id: int
    abbr: str
    label: str
    points: float


class LeagueSettings(BaseModel):
    league_id: int
    league_name: str
    season: int
    team_count: int
    rounds: int
    roster_slots: dict[str, int]
    scoring: list[ScoringRule]
    teams: list[TeamInfo]
    my_team_id: int
    my_team_name: str
    keeper_count: int = 1
    draft_order: list[int] | None = None
    synced_at: datetime


class Player(BaseModel):
    player_id: int
    name: str
    position: Position
    pro_team: str
    eligible_slots: list[str] = Field(default_factory=list)
    injury_status: str | None = None
    bye_week: int | None = None
    proj_points: float = 0.0
    adp: float | None = None
    percent_owned: float = 0.0
    espn_rank: int | None = None
    on_team_id: int | None = None
    # expert consensus (FantasyPros) and Boris Chen tiers, merged in from data/external_{season}.json
    fp_rank: int | None = None
    fp_pos_rank: str | None = None
    fp_tier: int | None = None
    fp_rank_ave: float | None = None
    fp_rank_std: float | None = None
    fp_best: int | None = None
    fp_worst: int | None = None
    fp_bye: int | None = None
    bc_tier: int | None = None


class RankedPlayer(Player):
    vorp: float = 0.0
    adp_vorp: float = 0.0
    fp_vorp: float = 0.0
    value: float = 0.0
    consensus_gap: float | None = None  # ESPN projection rank - FP rank; positive = ESPN more optimistic
    pos_rank: int = 0
    overall_rank: int = 0
    tier: int = 1
    adp_round: int | None = None
    value_round: int = 0


class DraftHistoryPick(BaseModel):
    season: int
    team_id: int
    player_id: int
    player_name: str = ""
    round_num: int
    round_pick: int
    keeper_status: bool = False


class RosterEntry(BaseModel):
    season: int
    team_id: int
    player_id: int
    name: str
    position: Position
    pro_team: str = ""


class KeeperHistoryEntry(BaseModel):
    season: int
    round: int
    was_keeper: bool
    team_id: int


CostSource = Literal["drafted", "kept", "undrafted", "override"]


class SeasonPoints(BaseModel):
    season: int
    points: float = 0.0
    avg: float = 0.0
    games: int = 0


class KeeperOption(BaseModel):
    roster_entry: RosterEntry
    player: RankedPlayer | None = None
    cost_round: int
    cost_source: CostSource
    years_kept: int = 0
    history: list[KeeperHistoryEntry] = Field(default_factory=list)
    cost_pick_overall: int | None = None
    adp_round: int | None = None
    value_round: int | None = None
    surplus_rounds: float | None = None
    surplus_points: float | None = None
    warnings: list[str] = Field(default_factory=list)
    reason: str = ""
    history_points: list[SeasonPoints] = Field(default_factory=list)
    slot_known: bool = True
    surplus_by_slot: dict[int, float] | None = None  # slot -> surplus points, when the draft order is unknown
    expected_value: float | None = None  # value of the best player you'd expect at the cost pick
    expected_examples: list[str] = Field(default_factory=list)  # names of players typically available there


class KeeperEntry(BaseModel):
    team_id: int = 0
    player_id: int = 0
    player_name: str = ""
    round: int
    tentative: bool = False
    owner_name: str = ""


class PickTrade(BaseModel):
    season: int
    round: int
    original_team_id: int = 0
    owner_team_id: int = 0
    note: str = ""
    original_owner_name: str = ""
    owner_name: str = ""


class SetupOverrides(BaseModel):
    my_slot: int | None = None
    slot_order: list[int] | None = None
    order_confirmed: bool = False  # ESPN's pickOrder is only trusted once the league confirms it
    other_keepers: list[KeeperEntry] = Field(default_factory=list)
    my_keeper: KeeperEntry | None = None
    pick_trades: list[PickTrade] = Field(default_factory=list)
    keeper_cost_overrides: dict[int, int] = Field(default_factory=dict)
    sheet_columns: dict[str, int] = Field(default_factory=dict)  # sheet header text -> team_id
    team_colors: dict[int, str] = Field(default_factory=dict)  # team_id -> hex


class DraftPick(BaseModel):
    overall: int
    round: int
    pick_in_round: int
    original_team_id: int
    owner_team_id: int
    player_id: int | None = None
    is_keeper: bool = False
    unknown: bool = False
    taken_at: datetime | None = None
    raw_name: str | None = None
    source: Literal["manual", "sheet", "keeper"] | None = None


class DraftState(BaseModel):
    season: int
    my_team_id: int
    slot_order: list[int]
    provisional_order: bool = False
    picks: list[DraftPick]
    history: list[DraftPick] = Field(default_factory=list)  # undo stack: each pick as it was before a change
    history_batch_sizes: list[int] = Field(default_factory=list)  # snapshots belonging to each undoable action
    warnings: list[str] = Field(default_factory=list)
    updated_at: datetime


class DraftView(BaseModel):
    state: DraftState
    on_the_clock: DraftPick | None
    my_next_pick: DraftPick | None
    picks_until_my_turn: int | None
    my_roster: list[RankedPlayer]
    open_slots: dict[str, int]
    taken_ids: list[int]
    recent: list[DraftPick]
    team_names: dict[int, str]
    player_names: dict[int, str]
    can_undo: bool = False
    undo_label: str | None = None


class Recommendation(BaseModel):
    player: RankedPlayer
    score: float
    reason: str
    components: dict[str, float] = Field(default_factory=dict)
    fit: str = ""  # what this pick does for the roster, e.g. "Fills your open RB2 slot"
    sources: str = ""  # where each data source has him
    why: list[str] = Field(default_factory=list)  # bullet-sized reasons, most important first
    strategy_team: str = ""  # why this fits the roster I have already built
    strategy_market: str = ""  # why it fits what my competitors are doing


class SyncReport(BaseModel):
    settings: LeagueSettings
    players: int
    roster_prev: int
    draft_years: list[int]
    from_cache: list[str]
    errors: list[str] = Field(default_factory=list)


# ---- Google Sheet draft board -------------------------------------------------


class SheetCell(BaseModel):
    round: int
    col: int  # 0-based team column index (column A = labels is excluded)
    text: str
    color: str | None = None  # hex background, None when unknown (CSV) or white


class SheetGrid(BaseModel):
    headers: list[str]
    header_colors: list[str | None]
    cells: list[SheetCell]
    extras: list[SheetCell] = Field(default_factory=list)  # unlabeled rows under the last round: in-season pickups
    keepers: list[str] = Field(default_factory=list)
    source: Literal["oauth", "csv"]
    fetched_at: datetime


class SheetUnmatched(BaseModel):
    round: int
    header: str
    text: str
    reason: str


class SheetConflict(BaseModel):
    """A sheet change held back because it would overwrite something a human typed.

    Only raised when the sheet disagrees with a *manual* entry; sheet-to-sheet edits
    still apply on their own, so a normal draft stays quiet.
    """

    key: str  # f"{original_team_id}:{round}" - stable across board rebuilds
    kind: Literal["replace", "move"]
    overall: int
    round: int
    original_team_id: int
    team_name: str = ""
    header: str = ""  # the sheet column this came from
    board_player_id: int | None = None
    board_player_name: str | None = None
    sheet_text: str
    sheet_player_id: int
    sheet_player_name: str
    from_overall: int | None = None  # "move": where the sheet's player sits right now
    from_round: int | None = None
    detected_at: datetime


class SheetConflictState(BaseModel):
    """Persisted so a conflict survives a restart and is not re-raised once decided."""

    pending: list[SheetConflict] = Field(default_factory=list)
    dismissed: dict[str, str] = Field(default_factory=dict)  # key -> sheet text the user rejected


class SheetSyncReport(BaseModel):
    source: str
    fetched_at: datetime
    applied: int = 0
    cleared: int = 0
    owner_changes: int = 0
    unmatched: list[SheetUnmatched] = Field(default_factory=list)
    moved: list[str] = Field(default_factory=list)  # players the sheet relocated from a manual entry
    conflicts: list[SheetConflict] = Field(default_factory=list)  # held back, awaiting your decision
    unmapped_columns: list[str] = Field(default_factory=list)
    error: str | None = None


class SheetColumn(BaseModel):
    header: str
    team_id: int
    color: str | None = None


class SheetStatus(BaseModel):
    configured: bool
    sheet_id: str
    tab: str
    auth: Literal["oauth", "csv", "none"]
    credentials_file_present: bool
    token_present: bool
    poll_seconds: int
    last: SheetSyncReport | None = None
    columns: list[SheetColumn] = Field(default_factory=list)


class BoardColumn(BaseModel):
    team_id: int
    name: str
    owner: str = ""  # the person's name behind the team, from ESPN
    color: str
    header: str = ""
    is_me: bool = False


class BoardCell(BaseModel):
    overall: int
    round: int
    original_team_id: int
    owner_team_id: int
    player_id: int | None = None
    player_name: str | None = None
    position: str | None = None
    raw_name: str | None = None
    is_keeper: bool = False
    unknown: bool = False
    source: str | None = None
    on_clock: bool = False


class BoardView(BaseModel):
    season: int
    my_team_id: int
    rounds: int
    columns: list[BoardColumn]
    cells: list[BoardCell]
    on_the_clock: DraftPick | None = None
    picks_until_my_turn: int | None = None
    warnings: list[str] = Field(default_factory=list)
    conflicts: list[SheetConflict] = Field(default_factory=list)


# ---- external expert rankings ----------------------------------------------


class ExternalRank(BaseModel):
    fp_rank: int | None = None
    fp_pos_rank: str | None = None
    fp_tier: int | None = None
    fp_rank_ave: float | None = None
    fp_rank_std: float | None = None
    fp_best: int | None = None
    fp_worst: int | None = None
    fp_bye: int | None = None
    bc_tier: int | None = None


class ExternalData(BaseModel):
    season: int
    scoring: str
    superflex: bool
    fp_experts: int = 0
    fp_updated: str = ""
    fp_page: str = ""
    fetched_at: datetime
    ranks: dict[int, ExternalRank] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    unmatched: dict[str, list[str]] = Field(default_factory=dict)
    matched: dict[str, int] = Field(default_factory=dict)


# ---- weekly lineup ----------------------------------------------------------------


class WeekPlayer(BaseModel):
    player_id: int
    name: str
    position: Position
    pro_team: str = ""
    slot: str = "BE"  # current ESPN lineup slot
    eligible_slots: list[str] = Field(default_factory=list)
    injury_status: str | None = None
    on_bye: bool = False
    opponent: str | None = None
    opp_rank_vs_pos: int | None = None  # 1 = toughest defense vs this position
    espn_proj: float | None = None
    season_proj: float | None = None
    fp_rank: int | None = None  # FantasyPros weekly cross-position rank (superflex/flex list)
    fp_pos_rank: str | None = None
    fp_grade: str | None = None
    fp_proj: float | None = None
    fp_best: int | None = None
    fp_worst: int | None = None
    bc_tier: int | None = None
    score: float = 0.0  # blended weekly score used for lineup decisions
    points: float | None = None  # actual points this week (once games are played)
    last_points: float | None = None  # actual points the previous week
    season_points: float | None = None  # actual points so far this season
    season_avg: float | None = None
    percent_owned: float | None = None
    percent_started: float | None = None
    on_my_team: bool = True


class SlotRow(BaseModel):
    slot: str  # ESPN slot key: QB, RB, WR, WR/TE, TE, RB/WR/TE, D/ST, K, BE, IR
    label: str  # display label: FLEX for RB/WR/TE
    key: str  # unique slot key like RB2
    player: WeekPlayer | None = None
    recommended_player_id: int | None = None  # who the optimiser would put here


class LineupMove(BaseModel):
    kind: Literal["start", "waiver"]
    slot: str
    player_in: WeekPlayer
    player_out: WeekPlayer | None = None
    delta: float = 0.0
    headline: str
    quant: str
    qual: str


class WeekView(BaseModel):
    season: int
    week: int
    week_label: str
    fetched_at: datetime
    roster_empty: bool = False
    opponent_name: str | None = None
    rows: list[SlotRow] = Field(default_factory=list)  # every slot in ESPN order, empties included
    starters: list[WeekPlayer] = Field(default_factory=list)
    bench: list[WeekPlayer] = Field(default_factory=list)
    optimal_slots: dict[str, int] = Field(default_factory=dict)  # slot key like "RB2" -> player_id
    current_total: float = 0.0
    optimal_total: float = 0.0
    moves: list[LineupMove] = Field(default_factory=list)
    waivers: list[LineupMove] = Field(default_factory=list)
    sources: dict[str, str] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


# ---- player detail card ------------------------------------------------------------


class DetailMetric(BaseModel):
    label: str
    value: str
    hint: str = ""  # what it means / why a drafter cares
    tone: Literal["good", "bad", "neutral"] = "neutral"


class InjuryNote(BaseModel):
    date: str = ""
    headline: str = ""
    body_part: str | None = None
    source: str = ""


class MissedTime(BaseModel):
    season: int
    games: int
    missed: int


class InjuryReport(BaseModel):
    status: str | None = None  # ESPN's current designation
    body_part: str | None = None  # most recent one mentioned in the news
    concern: str = ""  # plain-English read
    level: Literal["none", "watch", "concern"] = "none"
    notes: list[InjuryNote] = Field(default_factory=list)
    missed: list[MissedTime] = Field(default_factory=list)
    error: str | None = None


class PlayerDetail(BaseModel):
    player: RankedPlayer
    history: list[SeasonPoints] = Field(default_factory=list)
    metrics: list[DetailMetric] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    taken_at: int | None = None  # overall pick, when already drafted
    taken_by: str | None = None
    history_error: str | None = None
    injury: InjuryReport | None = None


# ---- draft strategy guide ----------------------------------------------------------


class StrategyPosition(BaseModel):
    position: Position
    starters_league_wide: int
    replacement_points: float
    top_vorp: float
    last_starter_vorp: float
    above_replacement: int
    cliff_after: int | None = None  # pos rank where the biggest value drop happens
    cliff_size: float | None = None
    note: str = ""


class RosterTarget(BaseModel):
    """How many of one position to come away with, and how that splits."""

    position: str
    starters: int  # spots you must fill every week, including this position's share of the flex
    bench: int
    total: int
    note: str = ""


class StrategySection(BaseModel):
    title: str
    body: str
    bullets: list[str] = Field(default_factory=list)


class StrategyGuide(BaseModel):
    league_summary: str
    headline: str
    positions: list[StrategyPosition] = Field(default_factory=list)
    sections: list[StrategySection] = Field(default_factory=list)
    roster_targets: list[RosterTarget] = Field(default_factory=list)
    roster_note: str = ""
    round_plan: list[str] = Field(default_factory=list)
    metrics: list[DetailMetric] = Field(default_factory=list)
