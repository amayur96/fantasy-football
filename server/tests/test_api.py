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
