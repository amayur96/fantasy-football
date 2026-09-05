import pytest
from fastapi.testclient import TestClient

from ffdraft.config import Settings
from ffdraft.context import AppContext
from ffdraft.main import create_app
from ffdraft.store import write_json


@pytest.fixture
def client(tmp_path, settings, players, drafts, roster):
    write_json(tmp_path / "settings.json", settings)
    write_json(tmp_path / "players_2026.json", players)
    write_json(tmp_path / "roster_2025.json", roster)
    for year, picks in drafts.items():
        write_json(tmp_path / f"draft_{year}.json", picks)
    seed = {
        "keepers": [{"owner_name": f"Owner{i}", "player_name": f"RB Player {i}", "round": 5 + i} for i in range(1, 11) if i != 3],
        "pick_trades": [{"season": 2026, "round": r, "original_owner_name": f"Owner{a}", "owner_name": f"Owner{b}"} for r, a, b in
                        [(8, 1, 8), (2, 2, 1), (3, 2, 6), (5, 2, 1), (9, 5, 2), (9, 6, 9), (5, 7, 5), (2, 9, 6), (5, 9, 8), (6, 9, 7), (2, 10, 5), (7, 10, 7)]],
    }
    write_json(tmp_path / "seed" / "league_2026.json", seed)
    cfg = Settings(league_id=1, espn_s2="x", swid="{SWID-3}", season=2026, data_dir=tmp_path)
    app = create_app(AppContext(cfg))
    with TestClient(app) as c:
        # First registration creates the admin account and sets the session cookie.
        assert c.post("/api/auth/register", json={"username": "tester", "password": "hunter2hunter2"}).status_code == 200
        yield c


def test_settings_and_seed(client):
    r = client.get("/api/settings")
    assert r.status_code == 200 and r.json()["ready"] is True
    s = client.get("/api/setup").json()
    # seed keepers resolved to teams by owner last name and players by name
    assert len(s["setup"]["other_keepers"]) == 9
    assert all(k["team_id"] and k["player_id"] for k in s["setup"]["other_keepers"])
    assert len(s["setup"]["pick_trades"]) == 12 and all(t["owner_team_id"] for t in s["setup"]["pick_trades"])


def test_keeper_options_sorted(client):
    r = client.get("/api/keeper-options")
    assert r.status_code == 200
    pts = [o["surplus_points"] for o in r.json() if o["surplus_points"] is not None]
    assert pts == sorted(pts, reverse=True)
    r = client.post("/api/setup/keeper-cost-override", json={"player_id": 101, "cost_round": 10})
    assert any(o["cost_round"] == 10 and o["cost_source"] == "override" for o in r.json())


def test_pick_undo_roundtrip(client):
    state = client.get("/api/draft/state").json()
    first = state["on_the_clock"]
    pid = client.get("/api/players?available=true&limit=1").json()[0]["player_id"]
    mine = first["owner_team_id"] == state["state"]["my_team_id"]
    r = client.post("/api/draft/pick", json={"player_id": pid, "mine": mine})
    assert r.status_code == 200 and pid in r.json()["taken_ids"]
    r = client.post("/api/draft/pick", json={"player_id": pid, "mine": mine})
    assert r.status_code == 409
    r = client.post("/api/draft/undo")
    assert pid not in r.json()["taken_ids"]
    recs = client.get("/api/draft/recommendations").json()
    assert recs["top"] and "reason" in recs["top"][0]


def test_cheatsheet_shape(client):
    cs = client.get("/api/cheatsheet").json()
    assert set(cs["by_pos"]) == {"QB", "RB", "WR", "TE", "K", "D/ST"}
    assert cs["by_pos"]["RB"][0][0]["tier"] == 1


def test_player_detail_card(client, monkeypatch):
    from ffdraft.espn.client import EspnClient
    from ffdraft.models import SeasonPoints

    monkeypatch.setattr(EspnClient, "fetch_points_history", lambda self, ids, years, refresh=False: {
        ids[0]: [SeasonPoints(season=2025, points=240.0, avg=15.0, games=16),
                 SeasonPoints(season=2024, points=90.0, avg=9.0, games=10)]
    })
    top = client.get("/api/players?limit=1").json()[0]
    r = client.get(f"/api/player/{top['player_id']}")
    assert r.status_code == 200
    d = r.json()
    assert d["player"]["player_id"] == top["player_id"]
    assert [h["season"] for h in d["history"]] == [2025, 2024]
    labels = [m["label"] for m in d["metrics"]]
    assert "Projected points" in labels and "Points over replacement" in labels and "Tier" in labels
    assert any("2025 240 pts in 16 games" in n for n in d["notes"])
    assert any("Missed time in 2024" in n for n in d["notes"])
    assert client.get("/api/player/999999").status_code == 404


# ---- sheet conflicts -----------------------------------------------------
def _seed_conflict(client):
    """Type a pick by hand, then hand the board a sheet that disagrees with it."""
    from ffdraft.board import apply_grid
    from ffdraft.sheets import parse_rows

    c = client.app.state.ctx
    board, s = c.board, c.settings
    mine = next(p for p in c.players if p.name == "WR Player 20")
    target = next(p for p in board.picks if p.original_team_id == 1 and p.round == 1)
    board.assign(target.overall, mine.player_id)

    headers = [f"Owner{i}" for i in range(1, 11)]
    rows = [["", *headers]] + [[f"Round {r}"] + [""] * 10 for r in range(1, 19)]
    rows[1][1] = "WR Player 30"  # sheet disagrees with what you typed
    report = apply_grid(board, parse_rows(rows, None), {i: i + 1 for i in range(10)}, s, c.setup, c.players, c.sheet_conflicts.dismissed)
    c.sheet_conflicts.pending = report.conflicts
    c.save_conflicts()
    return target, mine


def test_conflicts_surface_on_the_board(client):
    target, mine = _seed_conflict(client)
    conflicts = client.get("/api/sheet/conflicts").json()
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c["kind"] == "replace" and c["board_player_name"] == "WR Player 20" and c["sheet_player_name"] == "WR Player 30"
    # and the board view carries them so the UI can flag the cell
    assert [x["key"] for x in client.get("/api/board").json()["conflicts"]] == [c["key"]]
    # nothing was overwritten while it waits
    cell = next(x for x in client.get("/api/board").json()["cells"] if x["overall"] == target.overall)
    assert cell["player_id"] == mine.player_id


def test_resolving_in_favour_of_the_sheet_updates_the_board(client):
    target, mine = _seed_conflict(client)
    key = client.get("/api/sheet/conflicts").json()[0]["key"]
    r = client.post("/api/sheet/conflicts/resolve", json={"key": key, "choice": "sheet"})
    assert r.status_code == 200
    cell = next(x for x in r.json()["cells"] if x["overall"] == target.overall)
    assert cell["player_name"] == "WR Player 30" and cell["source"] == "sheet"
    assert r.json()["conflicts"] == [] and client.get("/api/sheet/conflicts").json() == []


def test_resolving_in_favour_of_the_board_keeps_your_pick(client):
    target, mine = _seed_conflict(client)
    key = client.get("/api/sheet/conflicts").json()[0]["key"]
    r = client.post("/api/sheet/conflicts/resolve", json={"key": key, "choice": "board"})
    assert r.status_code == 200
    cell = next(x for x in r.json()["cells"] if x["overall"] == target.overall)
    assert cell["player_id"] == mine.player_id
    assert client.get("/api/sheet/conflicts").json() == []
    # the decision is remembered, so the next sync does not ask again
    assert client.app.state.ctx.sheet_conflicts.dismissed[key] == "WR Player 30"


def test_resolve_rejects_unknown_key_and_bad_choice(client):
    _seed_conflict(client)
    key = client.get("/api/sheet/conflicts").json()[0]["key"]
    assert client.post("/api/sheet/conflicts/resolve", json={"key": "99:1", "choice": "sheet"}).status_code == 404
    assert client.post("/api/sheet/conflicts/resolve", json={"key": key, "choice": "whatever"}).status_code == 422


def test_conflicts_survive_a_restart(client, tmp_path):
    """Mid-draft the process can restart; pending decisions must not vanish."""
    _seed_conflict(client)
    key = client.get("/api/sheet/conflicts").json()[0]["key"]
    c = client.app.state.ctx
    c.load()  # re-read everything from disk, as a fresh boot would
    assert [x.key for x in c.sheet_conflicts.pending] == [key]


def test_player_search_returns_drafted_players_too(client):
    """The Live Draft search labels hits available/drafted, so /players must not hide taken ones."""
    view = client.get("/api/draft/state").json()
    target = next(p for p in view["state"]["picks"] if p["player_id"] is None)
    pool = client.get("/api/players?q=WR Player 2&limit=50").json()
    pick_me = next(p for p in pool if p["name"] == "WR Player 2")

    client.post("/api/draft/assign", json={"overall": target["overall"], "player_id": pick_me["player_id"]})

    again = client.get("/api/players?q=WR Player 2&limit=50").json()
    assert any(p["player_id"] == pick_me["player_id"] for p in again), "drafted player vanished from search"
    # and the draft view says where he went, which is what the row renders
    view2 = client.get("/api/draft/state").json()
    assert pick_me["player_id"] in view2["taken_ids"]
    placed = next(p for p in view2["state"]["picks"] if p["player_id"] == pick_me["player_id"])
    assert placed["round"] >= 1 and placed["owner_team_id"] in view2["team_names"].keys() | {int(k) for k in view2["team_names"]}

    # ...while ?available=true is still the filtered view used elsewhere
    avail = client.get("/api/players?q=WR Player 2&available=true&limit=50").json()
    assert not any(p["player_id"] == pick_me["player_id"] for p in avail)


# ---- setup writes are all-or-nothing -------------------------------------
def _record_a_pick(client):
    """Put one player on the board by hand. The top of the pool may already be a keeper,
    so pick the best player nobody holds and an overall that is actually empty."""
    view = client.get("/api/draft/state").json()
    taken = set(view["taken_ids"])
    player = next(p for p in client.get("/api/players?limit=200").json() if p["player_id"] not in taken)
    overall = next(p["overall"] for p in view["state"]["picks"] if p["player_id"] is None and not p["unknown"])
    r = client.post("/api/draft/assign", json={"overall": overall, "player_id": player["player_id"]})
    assert r.status_code == 200, r.json()
    assert r.json()["can_undo"] is True  # a recorded pick is what the 409 guard protects
    return overall


def test_refused_order_change_leaves_setup_and_board_agreeing(client):
    """A 409 must change nothing. Persisting the order but not rebuilding left the card
    showing one order while the board ran another."""
    first = [10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
    assert client.post("/api/setup/slot", json={"my_slot": None, "slot_order": first, "order_confirmed": True}).status_code == 200
    _record_a_pick(client)

    r = client.post("/api/setup/slot", json={"my_slot": None, "slot_order": list(range(1, 11)), "order_confirmed": True})
    assert r.status_code == 409

    setup = client.get("/api/setup").json()
    state = client.get("/api/draft/state").json()
    assert setup["setup"]["slot_order"] == first          # not half-written
    assert state["state"]["slot_order"] == first          # and the board still matches it
    assert setup["slot_order"] == state["state"]["slot_order"]
    assert state["can_undo"] is True  # the pick it protected survives


def test_force_rebuilds_the_board_and_applies_the_order(client):
    overall = _record_a_pick(client)
    wanted = list(range(1, 11))
    r = client.post("/api/setup/slot?force=true", json={"my_slot": None, "slot_order": wanted, "order_confirmed": True})
    assert r.status_code == 200

    setup = client.get("/api/setup").json()
    state = client.get("/api/draft/state").json()
    assert setup["setup"]["slot_order"] == wanted
    assert state["state"]["slot_order"] == wanted
    assert state["can_undo"] is False  # rebuilding clears the board
    assert next(p for p in state["state"]["picks"] if p["overall"] == overall)["player_id"] is None


def test_order_change_still_works_on_a_clean_board(client):
    wanted = [5, 4, 3, 2, 1, 10, 9, 8, 7, 6]
    r = client.post("/api/setup/slot", json={"my_slot": None, "slot_order": wanted, "order_confirmed": True})
    assert r.status_code == 200 and r.json()["slot_order"] == wanted
    assert client.get("/api/draft/state").json()["state"]["slot_order"] == wanted


def test_refused_keeper_change_is_also_rolled_back(client):
    """The same save-then-rebuild bug applied to keepers and pick trades."""
    before = client.get("/api/setup").json()["setup"]["other_keepers"]
    _record_a_pick(client)
    r = client.post("/api/setup/keepers", json={"other_keepers": [], "my_keeper": None})
    assert r.status_code == 409
    assert client.get("/api/setup").json()["setup"]["other_keepers"] == before
