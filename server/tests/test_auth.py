import pytest
from fastapi.testclient import TestClient

from ffdraft.auth import UserStore, hash_password, make_token, read_token, verify_password
from ffdraft.config import Settings
from ffdraft.context import AppContext
from ffdraft.main import create_app

PW = "hunter2hunter2"


@pytest.fixture
def cfg(tmp_path) -> Settings:
    return Settings(league_id=1, espn_s2="x", swid="{SWID-3}", season=2026, data_dir=tmp_path)


@pytest.fixture
def client(cfg):
    with TestClient(create_app(AppContext(cfg))) as c:
        yield c


# ---- primitives ----------------------------------------------------------
def test_password_hash_roundtrip():
    encoded = hash_password(PW)
    assert encoded.startswith("scrypt$") and PW not in encoded
    assert verify_password(PW, encoded)
    assert not verify_password("wrong-password", encoded)
    # a fresh salt each time
    assert hash_password(PW) != encoded


def test_verify_rejects_garbage_hash():
    assert not verify_password(PW, "not-a-hash")
    assert not verify_password(PW, "md5$1$2$3$4$5")


def test_token_roundtrip_and_tamper():
    secret = b"s" * 32
    token = make_token("abc123", secret, days=30)
    assert read_token(token, secret) == "abc123"
    assert read_token(token, b"other-secret") is None
    payload, _, sig = token.partition(".")
    assert read_token(f"{payload}x.{sig}", secret) is None
    assert read_token("nonsense", secret) is None


def test_expired_token_rejected():
    secret = b"s" * 32
    assert read_token(make_token("abc123", secret, days=-1), secret) is None


def test_store_rejects_duplicates_and_weak_passwords(tmp_path):
    store = UserStore(tmp_path / "users.json")
    store.create("arjun", PW, is_admin=True)
    with pytest.raises(ValueError, match="already taken"):
        store.create("ARJUN", PW)
    with pytest.raises(ValueError, match="at least 4"):
        store.create("friend", "ff2")
    with pytest.raises(ValueError, match="3-32 characters"):
        store.create("no spaces allowed", PW)
    # persisted and reloadable
    assert [u.username for u in UserStore(tmp_path / "users.json").users] == ["arjun"]


def test_cannot_delete_last_admin(tmp_path):
    store = UserStore(tmp_path / "users.json")
    admin = store.create("arjun", PW, is_admin=True)
    store.create("friend", PW)
    with pytest.raises(ValueError, match="only admin"):
        store.delete(admin)


def test_store_sees_writes_from_another_process(tmp_path):
    """make user writes a separate UserStore; the API process must pick that up without restart."""
    path = tmp_path / "users.json"
    api = UserStore(path)
    cli = UserStore(path)
    assert api.is_empty

    created = cli.create("friend", PW)
    seen = api.by_username("friend")
    assert seen is not None and seen.id == created.id
    assert {u.username for u in api.users} == {"friend"}

    cli.set_password(cli.by_username("friend"), "reset-password")
    assert verify_password("reset-password", api.by_username("friend").password_hash)
    assert not verify_password(PW, api.by_username("friend").password_hash)

    cli.delete(cli.by_username("friend"))
    assert api.by_username("friend") is None
    assert api.is_empty


# ---- routes --------------------------------------------------------------
def test_running_api_picks_up_cli_account_changes(tmp_path):
    """make user add/passwd/rm must work against a live API without restarting it."""
    cfg = Settings(league_id=1, season=2026, data_dir=tmp_path)
    with TestClient(create_app(AppContext(cfg))) as c:
        assert c.get("/api/auth/status").json()["users_exist"] is False
        cli = UserStore(cfg.users_path)
        cli.create("arjun", PW, is_admin=True)
        assert c.get("/api/auth/status").json()["users_exist"] is True
        assert c.post("/api/auth/login", json={"username": "arjun", "password": PW}).status_code == 200

        cli.set_password(cli.by_username("arjun"), "reset-password")
        c.post("/api/auth/logout")
        assert c.post("/api/auth/login", json={"username": "arjun", "password": PW}).status_code == 401
        assert c.post("/api/auth/login", json={"username": "arjun", "password": "reset-password"}).status_code == 200

        cli.create("friend", PW)
        assert {u["username"] for u in c.get("/api/auth/users").json()} == {"arjun", "friend"}
        cli.delete(cli.by_username("friend"))
        assert [u["username"] for u in c.get("/api/auth/users").json()] == ["arjun"]


def test_league_routes_require_sign_in(client):
    for path in ("/api/settings", "/api/setup", "/api/players", "/api/draft/state"):
        assert client.get(path).status_code == 401, path
    assert client.post("/api/sync").status_code == 401


def test_status_and_first_registration(client):
    assert client.get("/api/auth/status").json() == {"users_exist": False, "allow_registration": False}
    r = client.post("/api/auth/register", json={"username": "Arjun", "password": PW})
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "arjun" and body["is_admin"] is True and "password_hash" not in body
    assert client.get("/api/auth/status").json()["users_exist"] is True
    assert client.get("/api/settings").status_code == 200


def test_second_registration_closed_by_default(client):
    client.post("/api/auth/register", json={"username": "arjun", "password": PW})
    r = client.post("/api/auth/register", json={"username": "friend", "password": PW})
    assert r.status_code == 403 and "admin" in r.json()["detail"]


def test_open_registration_when_enabled(tmp_path):
    cfg = Settings(league_id=1, season=2026, data_dir=tmp_path, allow_registration=True)
    with TestClient(create_app(AppContext(cfg))) as c:
        assert c.post("/api/auth/register", json={"username": "arjun", "password": PW}).status_code == 200
        r = c.post("/api/auth/register", json={"username": "friend", "password": PW})
        assert r.status_code == 200 and r.json()["is_admin"] is False


def test_login_logout_cycle(client):
    client.post("/api/auth/register", json={"username": "arjun", "password": PW})
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401

    bad = client.post("/api/auth/login", json={"username": "arjun", "password": "not-the-password"})
    assert bad.status_code == 401 and bad.json()["detail"] == "Incorrect username or password."
    assert client.get("/api/auth/me").status_code == 401

    assert client.post("/api/auth/login", json={"username": "ARJUN", "password": PW}).status_code == 200
    assert client.get("/api/auth/me").json()["username"] == "arjun"


def test_unknown_user_and_real_user_give_the_same_error(client):
    client.post("/api/auth/register", json={"username": "arjun", "password": PW})
    a = client.post("/api/auth/login", json={"username": "arjun", "password": "wrong-password"})
    b = client.post("/api/auth/login", json={"username": "ghost", "password": "wrong-password"})
    assert a.json() == b.json()


def test_login_throttled_after_repeated_failures(client):
    client.post("/api/auth/register", json={"username": "arjun", "password": PW})
    for _ in range(5):
        assert client.post("/api/auth/login", json={"username": "arjun", "password": "wrong-password"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": "arjun", "password": PW})
    assert r.status_code == 429 and "Try again" in r.json()["detail"]


def test_session_cookie_is_httponly(client):
    r = client.post("/api/auth/register", json={"username": "arjun", "password": PW})
    header = r.headers["set-cookie"].lower()
    assert "httponly" in header and "samesite=lax" in header


def test_change_password(client):
    client.post("/api/auth/register", json={"username": "arjun", "password": PW})
    wrong = client.post("/api/auth/password", json={"current_password": "nope-nope-nope", "new_password": "brand-new-pass"})
    assert wrong.status_code == 401
    assert client.post("/api/auth/password", json={"current_password": PW, "new_password": "brand-new-pass"}).status_code == 204
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"username": "arjun", "password": PW}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "arjun", "password": "brand-new-pass"}).status_code == 200


def test_admin_manages_users(client):
    client.post("/api/auth/register", json={"username": "arjun", "password": PW})
    r = client.post("/api/auth/users", json={"username": "friend", "password": PW})
    assert r.status_code == 200
    friend_id = r.json()["id"]
    assert {u["username"] for u in client.get("/api/auth/users").json()} == {"arjun", "friend"}

    # a member may not manage users, nor delete themselves
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "friend", "password": PW})
    assert client.get("/api/auth/users").status_code == 403
    assert client.post("/api/auth/users", json={"username": "third", "password": PW}).status_code == 403
    assert client.get("/api/settings").status_code in (200, 404)  # signed in: auth is not the blocker

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "arjun", "password": PW})
    assert client.delete(f"/api/auth/users/{friend_id}").status_code == 204
    assert [u["username"] for u in client.get("/api/auth/users").json()] == ["arjun"]


def test_forged_cookie_rejected(client):
    client.post("/api/auth/register", json={"username": "arjun", "password": PW})
    user_id = client.get("/api/auth/me").json()["id"]
    client.post("/api/auth/logout")
    client.cookies.set("ffdraft_session", make_token(user_id, b"attacker-secret", days=30))
    assert client.get("/api/auth/me").status_code == 401


# ---- deployment surface --------------------------------------------------
def test_bootstrap_admin_created_on_first_boot(tmp_path):
    """On a public URL the admin must exist before anyone can reach the sign-in page."""
    cfg = Settings(league_id=1, season=2026, data_dir=tmp_path, bootstrap_username="bootstrapped", bootstrap_password="bootstrap-pw")
    with TestClient(create_app(AppContext(cfg))) as c:
        assert c.get("/api/auth/status").json()["users_exist"] is True
        # registration is therefore closed to strangers
        assert c.post("/api/auth/register", json={"username": "stranger", "password": "sneaky1"}).status_code == 403
        r = c.post("/api/auth/login", json={"username": "bootstrapped", "password": "bootstrap-pw"})
        assert r.status_code == 200 and r.json()["is_admin"] is True


def test_bootstrap_does_not_touch_existing_accounts(tmp_path):
    cfg = Settings(league_id=1, season=2026, data_dir=tmp_path, bootstrap_username="bootstrapped", bootstrap_password="bootstrap-pw")
    with TestClient(create_app(AppContext(cfg))) as c:
        assert c.post("/api/auth/login", json={"username": "bootstrapped", "password": "bootstrap-pw"}).status_code == 200
        c.post("/api/auth/password", json={"current_password": "bootstrap-pw", "new_password": "changed1"})
    # second boot with the same env must not recreate or reset the account
    with TestClient(create_app(AppContext(cfg))) as c:
        assert c.post("/api/auth/login", json={"username": "bootstrapped", "password": "bootstrap-pw"}).status_code == 401
        assert c.post("/api/auth/login", json={"username": "bootstrapped", "password": "changed1"}).status_code == 200
        assert len(UserStore(cfg.users_path).users) == 1


def test_healthz_needs_no_session(client):
    assert client.get("/healthz").json() == {"ok": True}
