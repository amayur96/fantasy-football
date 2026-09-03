// Hand-written mirrors of server/ffdraft/models.py (snake_case, same field names).

export type Position = "QB" | "RB" | "WR" | "TE" | "K" | "D/ST";
export const POSITIONS: readonly Position[] = ["QB", "RB", "WR", "TE", "K", "D/ST"];

export interface TeamInfo {
  team_id: number;
  name: string;
  abbrev: string;
  owner_ids: string[];
  owner_names: string[];
}

export interface ScoringRule {
  stat_id: number;
  abbr: string;
  label: string;
  points: number;
}

export interface LeagueSettings {
  league_id: number;
  league_name: string;
  season: number;
  team_count: number;
  rounds: number;
  roster_slots: Record<string, number>;
  scoring: ScoringRule[];
  teams: TeamInfo[];
  my_team_id: number;
  my_team_name: string;
  keeper_count: number;
  draft_order: number[] | null;
  synced_at: string;
}

export interface Player {
  player_id: number;
  name: string;
  position: Position;
  pro_team: string;
  eligible_slots: string[];
  injury_status: string | null;
  bye_week: number | null;
  proj_points: number;
  adp: number | null;
  percent_owned: number;
  espn_rank: number | null;
  on_team_id: number | null;
  // Expert consensus (FantasyPros) and Boris Chen tiers, merged from data/external_{season}.json.
  fp_rank: number | null;
  fp_pos_rank: string | null; // e.g. "RB14"
  fp_tier: number | null;
  fp_rank_ave: number | null;
  fp_rank_std: number | null;
  fp_best: number | null;
  fp_worst: number | null;
  fp_bye: number | null;
  bc_tier: number | null;
}

export interface RankedPlayer extends Player {
  vorp: number;
  adp_vorp: number;
  value: number;
  pos_rank: number;
  overall_rank: number;
  tier: number;
  adp_round: number | null;
  value_round: number;
  fp_vorp: number;
  // fp_rank − ESPN projection rank; positive = ESPN more optimistic than the experts.
  consensus_gap: number | null;
}

export interface DraftHistoryPick {
  season: number;
  team_id: number;
  player_id: number;
  player_name: string;
  round_num: number;
  round_pick: number;
  keeper_status: boolean;
}

export interface RosterEntry {
  season: number;
  team_id: number;
  player_id: number;
  name: string;
  position: Position;
  pro_team: string;
}

export interface KeeperHistoryEntry {
  season: number;
  round: number;
  was_keeper: boolean;
  team_id: number;
}

export type CostSource = "drafted" | "kept" | "undrafted" | "override";

/** Actual fantasy points under this league's scoring for one past season. */
export interface SeasonPoints {
  season: number;
  points: number;
  avg: number;
  games: number;
}

export interface KeeperOption {
  roster_entry: RosterEntry;
  player: RankedPlayer | null;
  cost_round: number;
  cost_source: CostSource;
  years_kept: number;
  history: KeeperHistoryEntry[];
  cost_pick_overall: number | null;
  adp_round: number | null;
  value_round: number | null;
  surplus_rounds: number | null;
  surplus_points: number | null;
  warnings: string[];
  reason: string;
  // Most recent season first, up to 3 seasons; may be empty.
  history_points: SeasonPoints[];
  slot_known: boolean;
  surplus_by_slot: Record<string, number> | null;
}

export interface KeeperEntry {
  team_id: number;
  player_id: number;
  player_name: string;
  round: number;
  tentative: boolean;
  owner_name: string;
}

export interface PickTrade {
  season: number;
  round: number;
  original_team_id: number;
  owner_team_id: number;
  note: string;
  original_owner_name: string;
  owner_name: string;
}

export interface SetupOverrides {
  my_slot: number | null;
  slot_order: number[] | null;
  order_confirmed: boolean;
  other_keepers: KeeperEntry[];
  my_keeper: KeeperEntry | null;
  pick_trades: PickTrade[];
  // JSON object keys are always strings on the wire.
  keeper_cost_overrides: Record<string, number>;
  // Google Sheet column header -> team_id.
  sheet_columns: Record<string, number>;
}

export interface DraftPick {
  overall: number;
  round: number;
  pick_in_round: number;
  original_team_id: number;
  owner_team_id: number;
  player_id: number | null;
  is_keeper: boolean;
  unknown: boolean;
  taken_at: string | null;
  raw_name?: string | null;
  source?: string | null;
}

export interface DraftState {
  season: number;
  my_team_id: number;
  slot_order: number[];
  provisional_order: boolean;
  picks: DraftPick[];
  history: number[];
  warnings: string[];
  updated_at: string;
}

export interface DraftView {
  state: DraftState;
  on_the_clock: DraftPick | null;
  my_next_pick: DraftPick | null;
  picks_until_my_turn: number | null;
  my_roster: RankedPlayer[];
  open_slots: Record<string, number>;
  taken_ids: number[];
  recent: DraftPick[];
  team_names: Record<string, string>;
  player_names: Record<string, string>;
  can_undo: boolean;
  /** Human label for what undo would restore, e.g. "pick #40 (R4) — Jahmyr Gibbs". */
  undo_label: string | null;
}

export interface Recommendation {
  player: RankedPlayer;
  score: number;
  /** Full prose rationale; the short form lives in `fit` + `why`. */
  reason: string;
  components: Record<string, number>;
  /** What this pick does for the roster, e.g. "Fills your open RB2 slot". */
  fit: string;
  /** Where each source has him, e.g. "ESPN ADP #19 · FantasyPros #1 (QB1) · Boris Chen tier 1". */
  sources: string;
  /** Bullet-sized reasons, most important first. */
  why: string[];
  strategy_team: string;
  strategy_market: string;
}

export interface SyncReport {
  settings: LeagueSettings;
  players: number;
  roster_prev: number;
  draft_years: number[];
  from_cache: string[];
  errors: string[];
}

export type ExternalScoring = "HALF" | "PPR" | "STD";

/** Summary of the cached FantasyPros + Boris Chen download (context.external_summary). */
export interface ExternalSummary {
  scoring: ExternalScoring;
  superflex: boolean;
  fp_experts: number;
  fp_updated: string;
  fp_page: string;
  fetched_at: string;
  errors: string[];
  matched: { fantasypros: number; borischen: number };
  unmatched: { fantasypros: string[]; borischen: string[] };
  stale: boolean;
}

// ---- Route payloads (api.py) ----

export interface SettingsResponse {
  settings: LeagueSettings | null;
  ready: boolean;
  has_credentials: boolean;
  season: number;
  cache_files: Record<string, number>; // mtime, epoch seconds
  setup_warnings: string[];
  players: number;
  draft_years: number[];
  roster_prev: number;
  external: ExternalSummary | null;
}

export interface CheatSheetResponse {
  by_pos: Partial<Record<Position, RankedPlayer[][]>>;
  overall: RankedPlayer[];
  baselines: Record<string, number>;
  starter_counts: Record<string, number>;
  taken_ids: number[];
}

export interface SetupResponse {
  espn_order_present: boolean;
  setup: SetupOverrides;
  slot_order: number[];
  provisional: boolean;
  warnings: string[];
  teams: TeamInfo[];
  my_team_id: number;
}

export interface KeepersBody {
  other_keepers: KeeperEntry[];
  my_keeper: KeeperEntry | null;
}

export interface SlotBody {
  order_confirmed?: boolean | null;
  my_slot: number | null;
  slot_order: number[] | null;
}

export interface OverrideBody {
  player_id: number;
  cost_round: number | null;
}

export interface PickBody {
  player_id: number;
  mine: boolean;
  force: boolean;
}

/** Put a player in any pick by its overall number, or clear it with a null player. */
export interface AssignBody {
  overall: number;
  player_id: number | null;
}

export interface RecommendationsResponse {
  top: Recommendation[];
  by_position: Partial<Record<Position, Recommendation>>;
  /** Roster slots still open, including BE/IR. */
  open_slots: Record<string, number>;
  /** One entry per unfilled *starting* slot, so duplicates mean "two of these": ["QB","QB","RB/WR/TE"]. */
  unfilled_starters: string[];
  roster_counts: Partial<Record<Position, number>>;
  /** Positions below the bench-depth target. */
  thin_positions: string[];
  roster_size: number;
}

// ---- Color-coded board + Google Sheet ----

export interface BoardColumn {
  team_id: number;
  name: string;
  owner: string;
  color: string; // hex
  header: string; // sheet header text, may be ""
  is_me: boolean;
}

export type CellSource = "manual" | "sheet" | "keeper";

export interface BoardCell {
  overall: number;
  round: number;
  original_team_id: number;
  owner_team_id: number;
  player_id: number | null;
  player_name: string | null;
  position: string | null;
  raw_name: string | null;
  is_keeper: boolean;
  unknown: boolean;
  source: CellSource | null;
  on_clock: boolean;
}

export interface BoardView {
  season: number;
  my_team_id: number;
  rounds: number;
  columns: BoardColumn[];
  cells: BoardCell[];
  on_the_clock: DraftPick | null;
  picks_until_my_turn: number | null;
  warnings: string[];
}

export interface CellBody {
  original_team_id: number;
  round: number;
  player_id?: number;
  owner_team_id?: number;
  clear?: boolean;
}

export interface SheetUnmatched {
  round: number;
  header: string;
  text: string;
  reason: string;
}

export interface SheetSyncReport {
  source: string;
  fetched_at: string;
  applied: number;
  cleared: number;
  owner_changes: number;
  unmatched: SheetUnmatched[];
  unmapped_columns: string[];
  error: string | null;
}

export interface SheetColumn {
  header: string;
  team_id: number;
  color: string | null;
}

export type SheetAuth = "oauth" | "csv" | "none";

export interface SheetStatus {
  configured: boolean;
  sheet_id: string;
  tab: string;
  auth: SheetAuth;
  credentials_file_present: boolean;
  token_present: boolean;
  poll_seconds: number;
  last: SheetSyncReport | null;
  columns: SheetColumn[];
}

export interface SheetColumnsBody {
  columns: Record<string, number>; // header -> team_id
}

// ---- In-season weekly lineup (GET /week) ----

export interface WeekPlayer {
  player_id: number;
  name: string;
  position: Position;
  pro_team: string;
  slot: string; // current ESPN lineup slot
  eligible_slots: string[];
  injury_status: string | null;
  on_bye: boolean;
  opponent: string | null;
  opp_rank_vs_pos: number | null; // 1 = toughest defense vs this position
  espn_proj: number | null;
  season_proj: number | null;
  fp_rank: number | null; // FantasyPros weekly cross-position rank
  fp_pos_rank: string | null;
  fp_grade: string | null;
  fp_proj: number | null;
  fp_best: number | null;
  fp_worst: number | null;
  bc_tier: number | null;
  score: number; // blended weekly score used for lineup decisions
  points: number | null; // actual points this week
  last_points: number | null;
  season_points: number | null;
  season_avg: number | null;
  percent_owned: number | null;
  percent_started: number | null;
  on_my_team: boolean;
}

export interface SlotRow {
  slot: string; // ESPN slot key: QB, RB, WR, WR/TE, TE, RB/WR/TE, D/ST, K, BE, IR
  label: string; // display label: FLEX for RB/WR/TE
  key: string; // unique slot key like RB2
  player: WeekPlayer | null;
  recommended_player_id: number | null;
}

export type MoveKind = "start" | "waiver";

export interface LineupMove {
  kind: MoveKind;
  slot: string;
  player_in: WeekPlayer;
  player_out: WeekPlayer | null;
  delta: number;
  headline: string;
  quant: string;
  qual: string;
}

export interface WeekView {
  season: number;
  week: number;
  week_label: string;
  fetched_at: string;
  roster_empty: boolean;
  opponent_name: string | null;
  rows: SlotRow[];
  starters: WeekPlayer[];
  bench: WeekPlayer[];
  optimal_slots: Record<string, number>; // slot key like "RB2" -> player_id
  current_total: number;
  optimal_total: number;
  moves: LineupMove[];
  waivers: LineupMove[];
  sources: Record<string, string>; // espn (ISO timestamp), fantasypros, borischen
  errors: string[];
}

// ---- Player detail card (GET /player/{id}) ----

export interface DetailMetric {
  label: string;
  value: string;
  /** What the number means and why a drafter cares; shown as a tooltip. */
  hint: string;
  tone: "good" | "bad" | "neutral";
}

export interface InjuryNote {
  date: string;
  headline: string;
  body_part: string | null;
  source: string;
}

export interface MissedTime {
  season: number;
  games: number;
  missed: number;
}

export type InjuryLevel = "none" | "watch" | "concern";

export interface InjuryReport {
  status: string | null;
  body_part: string | null;
  concern: string;
  level: InjuryLevel;
  notes: InjuryNote[];
  missed: MissedTime[];
  error: string | null;
}

export interface PlayerDetail {
  player: RankedPlayer;
  /** Newest season first; may be empty. */
  history: SeasonPoints[];
  metrics: DetailMetric[];
  notes: string[];
  /** Overall pick number, when he is already off the board. */
  taken_at: number | null;
  taken_by: string | null;
  history_error: string | null;
  injury: InjuryReport | null;
}

export interface StrategyPosition {
  position: Position;
  starters_league_wide: number;
  replacement_points: number;
  top_vorp: number;
  last_starter_vorp: number;
  above_replacement: number;
  cliff_after: number | null;
  cliff_size: number | null;
  note: string;
}

export interface StrategySection {
  title: string;
  body: string;
  bullets: string[];
}

export interface StrategyGuide {
  league_summary: string;
  headline: string;
  positions: StrategyPosition[];
  sections: StrategySection[];
  round_plan: string[];
  metrics: DetailMetric[];
}
