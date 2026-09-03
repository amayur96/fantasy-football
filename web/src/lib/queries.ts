import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiGet, apiPost, errorMessage, isNotSynced } from "./api";
import type {
  AssignBody,
  BoardView,
  CellBody,
  CheatSheetResponse,
  DraftView,
  ExternalSummary,
  KeeperOption,
  KeepersBody,
  OverrideBody,
  PickBody,
  PlayerDetail,
  RankedPlayer,
  RecommendationsResponse,
  SettingsResponse,
  SetupResponse,
  SheetColumnsBody,
  SheetStatus,
  SheetSyncReport,
  SlotBody,
  StrategyGuide,
  SyncReport,
  WeekView,
} from "./types";

export const keys = {
  settings: ["settings"] as const,
  players: (params: PlayersParams = {}) => ["players", params] as const,
  player: (playerId: number | null) => ["player", playerId] as const,
  keeperOptions: ["keeperOptions"] as const,
  cheatsheet: ["cheatsheet"] as const,
  setup: ["setup"] as const,
  draftState: ["draftState"] as const,
  recommendations: ["recommendations"] as const,
  board: ["board"] as const,
  sheetStatus: ["sheetStatus"] as const,
  week: (week?: number) => ["week", week ?? "current"] as const,
  strategy: ["strategy"] as const,
};

/** Don't hammer the server when it just says "sync first". */
function retryUnlessNotSynced(failureCount: number, err: Error) {
  if (isNotSynced(err)) return false;
  return failureCount < 1;
}

export function useSettings() {
  return useQuery({
    queryKey: keys.settings,
    queryFn: () => apiGet<SettingsResponse>("/settings"),
    refetchInterval: 30_000,
  });
}

export interface PlayersParams {
  pos?: string;
  q?: string;
  available?: boolean;
  limit?: number;
}

export function playersPath(params: PlayersParams): string {
  const sp = new URLSearchParams();
  if (params.pos) sp.set("pos", params.pos);
  if (params.q) sp.set("q", params.q);
  if (params.available) sp.set("available", "true");
  if (params.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return `/players${qs ? `?${qs}` : ""}`;
}

export function usePlayers(params: PlayersParams = {}, enabled = true) {
  return useQuery({
    queryKey: keys.players(params),
    queryFn: () => apiGet<RankedPlayer[]>(playersPath(params)),
    enabled,
    retry: retryUnlessNotSynced,
  });
}

/** Everything behind the player card. The first fetch can take a few seconds: the server
 *  goes to ESPN for his season history before it can answer. */
export function usePlayerDetail(playerId: number | null) {
  return useQuery({
    queryKey: keys.player(playerId),
    queryFn: () => apiGet<PlayerDetail>(`/player/${playerId}`),
    enabled: playerId !== null,
    staleTime: 5 * 60_000,
    retry: retryUnlessNotSynced,
  });
}

export function useKeeperOptions() {
  return useQuery({
    queryKey: keys.keeperOptions,
    queryFn: () => apiGet<KeeperOption[]>("/keeper-options"),
    retry: retryUnlessNotSynced,
    staleTime: 0,
    refetchOnMount: "always",
  });
}

export function useCheatSheet() {
  return useQuery({
    queryKey: keys.cheatsheet,
    queryFn: () => apiGet<CheatSheetResponse>("/cheatsheet"),
    retry: retryUnlessNotSynced,
  });
}

export function useSetup() {
  return useQuery({
    queryKey: keys.setup,
    queryFn: () => apiGet<SetupResponse>("/setup"),
    retry: retryUnlessNotSynced,
  });
}

export function useDraftState() {
  return useQuery({
    queryKey: keys.draftState,
    queryFn: () => apiGet<DraftView>("/draft/state"),
    retry: retryUnlessNotSynced,
  });
}

export function useRecommendations(enabled = true) {
  return useQuery({
    queryKey: keys.recommendations,
    queryFn: () => apiGet<RecommendationsResponse>("/draft/recommendations"),
    enabled,
    retry: retryUnlessNotSynced,
  });
}

export function weekPath(week: number | undefined, refresh = false): string {
  const sp = new URLSearchParams();
  if (week !== undefined) sp.set("week", String(week));
  if (refresh) sp.set("refresh", "true");
  const qs = sp.toString();
  return `/week${qs ? `?${qs}` : ""}`;
}

/** Current week's lineup + recommendations; `week` omitted means whatever ESPN says is current. */
export function useWeek(week?: number) {
  return useQuery({
    queryKey: keys.week(week),
    queryFn: () => apiGet<WeekView>(weekPath(week)),
    retry: retryUnlessNotSynced,
    staleTime: 60_000,
  });
}

export function useStrategy() {
  return useQuery({
    queryKey: keys.strategy,
    queryFn: () => apiGet<StrategyGuide>("/strategy"),
    retry: retryUnlessNotSynced,
    staleTime: 10 * 60_000,
  });
}

// ---- Mutations ----

/** Re-pulls the week from ESPN/FantasyPros and replaces the cached WeekView in place. */
export function useRefreshWeek(week?: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiGet<WeekView>(weekPath(week, true)),
    onSuccess: (view) => {
      qc.setQueryData(keys.week(week), view);
      // The refreshed payload is also the answer for its own numbered week.
      if (week === undefined) qc.setQueryData(keys.week(view.week), view);
    },
    onError: (err) => toast.error("Refresh failed", { description: errorMessage(err) }),
  });
}

export function useSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (refresh: boolean) => apiPost<SyncReport>(`/sync?refresh=${refresh ? "true" : "false"}`),
    onSuccess: (report) => {
      toast.success(`Synced ${report.settings.league_name}`, {
        description: `${report.players} players, drafts ${report.draft_years.join(", ") || "none"}`,
      });
      void qc.invalidateQueries();
    },
    onError: (err) => toast.error("Sync failed", { description: errorMessage(err) }),
  });
}

export function useRefreshExternal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<ExternalSummary>("/external/refresh"),
    onSuccess: (ext) => {
      void qc.invalidateQueries({ queryKey: keys.settings });
      void qc.invalidateQueries({ queryKey: keys.keeperOptions });
      void qc.invalidateQueries({ queryKey: keys.cheatsheet });
      void qc.invalidateQueries({ queryKey: ["players"] });
      void qc.invalidateQueries({ queryKey: keys.recommendations });
      void qc.invalidateQueries({ queryKey: keys.board });
      const matched = (ext.matched.fantasypros ?? 0) + (ext.matched.borischen ?? 0);
      toast.success("Expert rankings refreshed", {
        description: `FantasyPros (${ext.fp_experts} experts, updated ${ext.fp_updated || "n/a"}) + Boris Chen tiers · ${matched} players matched`,
      });
    },
    onError: (err) => toast.error("Refreshing expert rankings failed", { description: errorMessage(err) }),
  });
}

/** Shared onSuccess for endpoints returning a fresh SetupResponse. */
function useSetupMutation<TVars>(fn: (vars: TVars) => Promise<SetupResponse>, label: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (data) => {
      qc.setQueryData(keys.setup, data);
      void qc.invalidateQueries({ queryKey: keys.draftState });
      void qc.invalidateQueries({ queryKey: keys.board });
      void qc.invalidateQueries({ queryKey: keys.recommendations });
      void qc.invalidateQueries({ queryKey: keys.keeperOptions });
      void qc.invalidateQueries({ queryKey: keys.cheatsheet });
      void qc.invalidateQueries({ queryKey: ["players"] });
      void qc.invalidateQueries({ queryKey: keys.settings });
      toast.success(label);
    },
    onError: (err) => toast.error(`${label} failed`, { description: errorMessage(err) }),
  });
}

export function useSaveKeepers() {
  return useSetupMutation((body: KeepersBody) => apiPost<SetupResponse>("/setup/keepers", body), "Keepers saved");
}

export function useSaveSlot() {
  return useSetupMutation((body: SlotBody) => apiPost<SetupResponse>("/setup/slot", body), "Draft slot saved");
}

export function useKeeperCostOverride() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: OverrideBody) => apiPost<KeeperOption[]>("/setup/keeper-cost-override", body),
    onSuccess: (data) => {
      qc.setQueryData(keys.keeperOptions, data);
      void qc.invalidateQueries({ queryKey: keys.setup });
    },
    onError: (err) => toast.error("Override failed", { description: errorMessage(err) }),
  });
}

/** Shared onSuccess for endpoints returning a fresh DraftView. */
function useDraftMutation<TVars>(fn: (vars: TVars) => Promise<DraftView>, opts?: { silent?: boolean }) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (view) => {
      qc.setQueryData(keys.draftState, view);
      void qc.invalidateQueries({ queryKey: keys.recommendations });
      void qc.invalidateQueries({ queryKey: ["players"] });
      void qc.invalidateQueries({ queryKey: keys.cheatsheet });
      void qc.invalidateQueries({ queryKey: keys.board });
    },
    onError: (err) => {
      if (!opts?.silent) toast.error(errorMessage(err));
    },
  });
}

/** Legacy sequential pick recorder. Kept for callers outside the live-draft page. */
export function useDraftPick() {
  return useDraftMutation((body: PickBody) => apiPost<DraftView>("/draft/pick", body));
}

/** Draft a player into any pick (or clear one with `player_id: null`), in any order. */
export function useDraftAssign() {
  return useDraftMutation((body: AssignBody) => apiPost<DraftView>("/draft/assign", body));
}

export function useDraftSkip() {
  return useDraftMutation(() => apiPost<DraftView>("/draft/skip"));
}

export function useDraftUndo() {
  return useDraftMutation(() => apiPost<DraftView>("/draft/undo"));
}


// ---- Board + Google Sheet ----

export function useBoard() {
  return useQuery({
    queryKey: keys.board,
    queryFn: () => apiGet<BoardView>("/board"),
    retry: retryUnlessNotSynced,
  });
}

/** Everything derived from the draft board that a cell edit or sheet pull can change. */
function invalidateBoardDerived(qc: ReturnType<typeof useQueryClient>) {
  void qc.invalidateQueries({ queryKey: keys.draftState });
  void qc.invalidateQueries({ queryKey: keys.recommendations });
  void qc.invalidateQueries({ queryKey: ["players"] });
  void qc.invalidateQueries({ queryKey: keys.cheatsheet });
}

export function useSetCell() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CellBody) => apiPost<BoardView>("/board/cell", body),
    onSuccess: (view) => {
      qc.setQueryData(keys.board, view);
      invalidateBoardDerived(qc);
    },
    onError: (err) => toast.error("Could not update cell", { description: errorMessage(err) }),
  });
}

export function useSheetStatus() {
  return useQuery({
    queryKey: keys.sheetStatus,
    queryFn: () => apiGet<SheetStatus>("/sheet/status"),
  });
}

export function useSheetSync(opts?: { silent?: boolean }) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<SheetSyncReport>("/sheet/sync"),
    onSuccess: (report) => {
      void qc.invalidateQueries({ queryKey: keys.board });
      void qc.invalidateQueries({ queryKey: keys.sheetStatus });
      invalidateBoardDerived(qc);
      if (!opts?.silent) {
        toast.success("Pulled from sheet", {
          description: `${report.applied} applied, ${report.cleared} cleared, ${report.owner_changes} owner change${report.owner_changes === 1 ? "" : "s"}`,
        });
      }
    },
    onError: (err) => {
      if (!opts?.silent) toast.error("Sheet pull failed", { description: errorMessage(err) });
    },
  });
}

export function useSaveSheetColumns() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SheetColumnsBody) => apiPost<SheetStatus>("/setup/sheet-columns", body),
    onSuccess: (status) => {
      qc.setQueryData(keys.sheetStatus, status);
      void qc.invalidateQueries({ queryKey: keys.setup });
      void qc.invalidateQueries({ queryKey: keys.board });
      toast.success("Column mapping saved");
    },
    onError: (err) => toast.error("Saving column mapping failed", { description: errorMessage(err) }),
  });
}
