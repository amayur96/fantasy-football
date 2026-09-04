"""The single-service deploy serves the built UI from the API process."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ffdraft.config import Settings
from ffdraft.context import AppContext
from ffdraft.main import create_app, mount_web


@pytest.fixture
def dist(tmp_path):
    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("<!doctype html><title>shell</title>")
    (d / "assets" / "app.js").write_text("console.log(1)")
    (d / "favicon.svg").write_text("<svg/>")
    return d


@pytest.fixture
def web_client(tmp_path, dist):
    app = create_app(AppContext(Settings(league_id=1, season=2026, data_dir=tmp_path / "data")), web_dist=dist)
    with TestClient(app) as c:
        yield c


def test_serves_real_files(web_client):
    assert web_client.get("/assets/app.js").text == "console.log(1)"
    assert web_client.get("/favicon.svg").text == "<svg/>"


def test_client_routes_fall_back_to_the_shell(web_client):
    for path in ("/", "/board", "/login", "/account", "/draft"):
        r = web_client.get(path)
        assert r.status_code == 200 and "shell" in r.text, path


def test_unknown_api_paths_still_404_as_json(web_client):
    r = web_client.get("/api/does-not-exist")
    assert r.status_code == 404 and r.json() == {"detail": "Not found"}
    assert "shell" not in r.text


def test_protected_api_routes_are_not_shadowed_by_the_shell(web_client):
    assert web_client.get("/api/settings").status_code == 401


def test_traversal_cannot_escape_dist(web_client):
    for path in ("/../pyproject.toml", "/..%2fpyproject.toml", "/../../etc/passwd"):
        r = web_client.get(path)
        assert r.status_code == 200 and "shell" in r.text, path  # falls back, never leaks


def test_mount_is_a_no_op_without_a_build(tmp_path):
    app = FastAPI()
    mount_web(app, tmp_path / "missing")
    assert not [r for r in app.routes if getattr(r, "name", "") == "spa"]
