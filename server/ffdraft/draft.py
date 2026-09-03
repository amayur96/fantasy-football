"""Snake draft board with pick trades, keepers, manual pick tracking, undo, and persistence."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .models import DraftPick, DraftState, KeeperEntry, LeagueSettings, PickTrade, Position, SetupOverrides
from .store import load_model, write_json
from .value import FLEX_MAP


class ConflictError(Exception):
    pass


def snake_order(slot_order: list[int], rounds: int) -> list[DraftPick]:
    picks: list[DraftPick] = []
    T = len(slot_order)
    overall = 0
    for r in range(1, rounds + 1):
        order = slot_order if r % 2 == 1 else list(reversed(slot_order))
        for i, team_id in enumerate(order, start=1):
            overall += 1
            picks.append(DraftPick(overall=overall, round=r, pick_in_round=i, original_team_id=team_id, owner_team_id=team_id))
    return picks


def apply_pick_trades(picks: list[DraftPick], trades: list[PickTrade], season: int) -> list[str]:
    warnings: list[str] = []
    for t in trades:
        if t.season != season:
            continue
        hit = next((p for p in picks if p.round == t.round and p.original_team_id == t.original_team_id), None)
        if hit is None:
            warnings.append(f"Pick trade R{t.round} from team {t.original_team_id}: no such pick")
            continue
        hit.owner_team_id = t.owner_team_id
    return warnings


def apply_keepers(picks: list[DraftPick], keepers: list[KeeperEntry], rounds: int, team_names: dict[int, str]) -> list[str]:
    warnings: list[str] = []
    for k in keepers:
        if not k.team_id or not k.player_id:
            warnings.append(f"Keeper '{k.player_name or '?'}' for {k.owner_name or 'unknown team'} is unresolved; not placed on the board")
            continue
        name = team_names.get(k.team_id, f"team {k.team_id}")
        placed = False
        for r in range(k.round, rounds + 1):
            slot = next((p for p in picks if p.round == r and p.owner_team_id == k.team_id and p.player_id is None), None)
            if slot is not None:
                slot.player_id, slot.is_keeper = k.player_id, True
                if r != k.round:
                    warnings.append(f"{name} has no open R{k.round} pick for keeper {k.player_name}; used their R{r} pick instead")
                placed = True
                break
        if not placed:
            warnings.append(f"{name} has no pick at or after R{k.round} for keeper {k.player_name}; not placed")
    return warnings


def resolve_slot_order(settings: LeagueSettings, setup: SetupOverrides) -> tuple[list[int], bool]:
    """(slot_order, provisional). Priority: manual full order > ESPN order > my_slot with placeholders."""
    ids = [t.team_id for t in settings.teams]
    if setup.slot_order and sorted(setup.slot_order) == sorted(ids):
        return list(setup.slot_order), False
    if settings.draft_order and sorted(settings.draft_order) == sorted(ids):
        return list(settings.draft_order), not setup.order_confirmed
    others = [i for i in ids if i != settings.my_team_id]
    slot = setup.my_slot or 1
    slot = max(1, min(len(ids), slot))
    order = others[: slot - 1] + [settings.my_team_id] + others[slot - 1 :]
    return order, True


def build_state(settings: LeagueSettings, setup: SetupOverrides) -> DraftState:
    order, provisional = resolve_slot_order(settings, setup)
    picks = snake_order(order, settings.rounds)
    names = {t.team_id: t.name for t in settings.teams}
    warnings = apply_pick_trades(picks, setup.pick_trades, settings.season)
    keepers = list(setup.other_keepers)
    if setup.my_keeper:
        keepers.append(setup.my_keeper)
    warnings += apply_keepers(picks, keepers, settings.rounds, names)
    return DraftState(
        season=settings.season, my_team_id=settings.my_team_id, slot_order=order, provisional_order=provisional,
        picks=picks, history=[], warnings=warnings, updated_at=datetime.now(timezone.utc),
    )


class DraftBoard:
    def __init__(self, state: DraftState, path: Path):
        self.state = state
        self.path = path

    @classmethod
    def load_or_build(cls, settings: LeagueSettings, setup: SetupOverrides, path: Path) -> "DraftBoard":
        try:
            existing = load_model(path, DraftState)
        except Exception:  # a cache written by an older shape: start fresh
            existing = None
        if existing is not None and existing.season == settings.season and len(existing.picks) == settings.rounds * settings.team_count:
            return cls(existing, path)
        board = cls(build_state(settings, setup), path)
        board.save()
        return board

    # ---- queries ----------------------------------------------------------
    @property
    def picks(self) -> list[DraftPick]:
        return self.state.picks

    def next_open(self) -> DraftPick | None:
        return next((p for p in self.picks if p.player_id is None and not p.unknown), None)

    def taken_ids(self) -> set[int]:
        return {p.player_id for p in self.picks if p.player_id is not None}

    def my_picks(self) -> list[DraftPick]:
        return [p for p in self.picks if p.owner_team_id == self.state.my_team_id]

    def my_next_pick(self) -> DraftPick | None:
        return next((p for p in self.my_picks() if p.player_id is None and not p.unknown), None)

    def picks_until_my_turn(self) -> int | None:
        nxt = self.my_next_pick()
        if nxt is None:
            return None
        return sum(1 for p in self.picks if p.overall < nxt.overall and p.player_id is None and not p.unknown)

    def my_roster_ids(self) -> list[int]:
        return [p.player_id for p in self.my_picks() if p.player_id is not None]

    def user_picks_made(self) -> bool:
        return bool(self.state.history)

    def recent(self, n: int = 10) -> list[DraftPick]:
        done = [p for p in self.picks if p.player_id is not None or p.unknown]
        done.sort(key=lambda p: p.overall)
        return done[-n:]

    # ---- mutations --------------------------------------------------------
    def _push(self, pick: DraftPick) -> None:
        """Remember a pick exactly as it was, so undo can put it back."""
        self.state.history.append(pick.model_copy(deep=True))

    def pick_at(self, overall: int) -> DraftPick:
        if overall < 1 or overall > len(self.picks):
            raise LookupError(f"There is no pick #{overall} in this draft")
        return self.picks[overall - 1]

    def assign(self, overall: int, player_id: int | None) -> DraftPick:
        """Put a player in (or clear) any pick, in any order. The heart of live drafting."""
        pick = self.pick_at(overall)
        if player_id is not None:
            dup = next((q for q in self.picks if q.player_id == player_id and q.overall != overall), None)
            if dup is not None:
                raise ConflictError(f"That player is already at pick #{dup.overall} (round {dup.round})")
        self._push(pick)
        pick.taken_at = datetime.now(timezone.utc) if player_id is not None else None
        pick.player_id = player_id
        pick.unknown = False
        pick.raw_name = None
        pick.source = "manual" if player_id is not None else None
        if player_id is None:
            pick.is_keeper = False
        self.save()
        return pick

    def record_pick(self, player_id: int, mine: bool = False, force: bool = False) -> DraftPick:
        if player_id in self.taken_ids():
            raise ConflictError("That player is already off the board")
        slot = self.next_open()
        if slot is None:
            raise ConflictError("The draft is complete")
        if mine and slot.owner_team_id != self.state.my_team_id and not force:
            raise ConflictError(f"Not your pick: pick {slot.overall} (R{slot.round}) belongs to another team. Shift-click to force.")
        if not mine and slot.owner_team_id == self.state.my_team_id and not force:
            raise ConflictError(f"Pick {slot.overall} is yours - use 'Mine' (or force) to record it.")
        self._push(slot)
        slot.player_id = player_id
        slot.taken_at = datetime.now(timezone.utc)
        slot.source = "manual"
        self.save()
        return slot

    def skip_pick(self) -> DraftPick:
        slot = self.next_open()
        if slot is None:
            raise ConflictError("The draft is complete")
        self._push(slot)
        slot.unknown = True
        slot.taken_at = datetime.now(timezone.utc)
        self.save()
        return slot

    def undo(self) -> DraftPick | None:
        """Restore the last changed pick to exactly what it was."""
        if not self.state.history:
            return None
        snap = self.state.history.pop()
        self.picks[snap.overall - 1] = snap
        self.save()
        return snap

    def save(self) -> None:
        self.state.updated_at = datetime.now(timezone.utc)
        write_json(self.path, self.state)


def open_slots(roster_positions: list[Position], roster_slots: dict[str, int]) -> dict[str, int]:
    """Greedy fill: dedicated slots, then flex slots, then bench. Returns remaining count per slot key."""
    remaining = {k: v for k, v in roster_slots.items() if k != "IR" and v > 0}
    unplaced: list[Position] = []
    for pos in roster_positions:
        if remaining.get(pos, 0) > 0:
            remaining[pos] -= 1
        else:
            unplaced.append(pos)
    still: list[Position] = []
    for pos in unplaced:
        placed = False
        for slot, eligible in FLEX_MAP.items():
            if remaining.get(slot, 0) > 0 and pos in eligible:
                remaining[slot] -= 1
                placed = True
                break
        if not placed:
            still.append(pos)
    for _ in still:
        if remaining.get("BE", 0) > 0:
            remaining["BE"] -= 1
    return remaining
