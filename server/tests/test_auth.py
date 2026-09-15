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
    assert client.get("/api/auth/status").json() == {"users_exist": False, "allow_registration": False, "mail_configured": False}
    r = client.post("/api/auth/register", json={"username": "Arjun", "password": PW})
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "arjun" and body["is_admin"] is True and "password_hash" not in body
    assert client.get("/api/auth/status").json()["users_exist"] is True
    assert client.get("/api/settings").status_code == 200


def test_second_registration_closed_by_default(client):
    client.post("/api/auth/register", json={"username": "arjun", "password": PW})
    r = client.post("/api/auth/register", json={"username": "friend", "password": PW})
    assert r.status_code == 403 and "invite link" in r.json()["detail"]


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


def test_secure_session_cookie_is_securely_deleted(tmp_path):
    cfg = Settings(league_id=1, season=2026, data_dir=tmp_path, cookie_secure=True)
    with TestClient(create_app(AppContext(cfg)), base_url="https://testserver") as client:
        registered = client.post("/api/auth/register", json={"username": "arjun", "password": PW})
        assert "secure" in registered.headers["set-cookie"].lower()

        logged_out = client.post("/api/auth/logout")
        header = logged_out.headers["set-cookie"].lower()
        assert "ffdraft_session=" in header
        assert "max-age=0" in header
        assert "secure" in header
        assert client.get("/api/auth/me").status_code == 401


def test_change_password(client):
    client.post("/api/auth/register", json={"username": "arjun", "password": PW})
    wrong = client.post("/api/auth/password", json={"current_password": "nope-nope-nope", "new_password": "brand-new-pass"})
    assert wrong.status_code == 400 and wrong.json()["detail"] == "Current password is incorrect."
    assert client.get("/api/auth/me").status_code == 200  # typo must not kill the session
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



# ---- team invites --------------------------------------------------------
@pytest.fixture
def league_client(tmp_path, settings, players):
    """An app with a synced league (so teams exist), SMTP 'configured', a recorder in place of the
    mail server, and the commissioner signed in as admin."""
    from ffdraft.store import write_json

    write_json(tmp_path / "settings.json", settings)
    write_json(tmp_path / "players_2026.json", players)
    cfg = Settings(league_id=1, espn_s2="x", swid="{SWID-3}", season=2026, data_dir=tmp_path, app_url="https://ff.example.com", resend_api_key="re_test", mail_from="FF <ff@test.co>")
    with TestClient(create_app(AppContext(cfg))) as c:
        c.app.state.outbox = []
        c.app.state.auth.send_mail = lambda cfg, to, subject, body: c.app.state.outbox.append((to, subject, body))
        assert c.post("/api/auth/register", json={"username": "commish", "password": PW}).status_code == 200
        yield c


def _fresh(client):
    """A second, signed-out browser against the same app."""
    return TestClient(client.app)


def _token_from(email_body: str) -> str:
    import re

    return re.search(r"/join\?token=([A-Za-z0-9_-]+)", email_body).group(1)


def test_first_admin_owns_the_cookie_holders_team(league_client):
    me = league_client.get("/api/auth/me").json()
    assert me["is_admin"] is True and me["team_id"] == 3  # conftest: SWID-3 owns team 3


def test_nobody_can_register_or_pick_a_team_without_an_invite(league_client):
    other = _fresh(league_client)
    r = other.post("/api/auth/register", json={"username": "friend", "password": PW})
    assert r.status_code == 403 and "invite" in r.json()["detail"]
    assert other.post("/api/auth/team", json={"team_id": 5}).status_code in (401, 404, 405)


def test_invite_is_emailed_and_the_link_never_appears_in_the_api(league_client):
    r = league_client.post("/api/auth/invites", json={"team_id": 5, "email": " Friend@Example.com "})
    assert r.status_code == 200
    inv = r.json()
    assert inv["status"] == "pending" and inv["team_name"] == "Team Owner5" and inv["email"] == "friend@example.com"
    assert "token" not in inv and "link" not in inv
    to, subject, body = league_client.app.state.outbox[-1]
    assert to == "friend@example.com" and subject == "Your Test League fantasy football tool login"
    assert "Team Owner5" not in subject and "manager of Team Owner5" in body  # team in the body, never the subject
    assert "https://ff.example.com/join?token=" in body and "expires in 14 days" in body
    assert body.rstrip().endswith("Please don't reply to this email \u2014 it isn't monitored. Questions go to the tool's admin.")
    token = _token_from(body)
    assert token not in str(league_client.get("/api/auth/invites").json())

    friend = _fresh(league_client)
    info = friend.get(f"/api/auth/invite/{token}").json()
    assert info == {"valid": True, "reason": "", "team_name": "Team Owner5", "league_name": "Test League", "test": False}
    r = friend.post("/api/auth/join", json={"token": token, "username": "friend", "password": PW})
    assert r.status_code == 200 and r.json()["test"] is False
    made = r.json()["user"]
    assert made["team_id"] == 5 and made["email"] == "friend@example.com" and made["is_admin"] is False
    assert friend.get("/api/setup").json()["my_team_id"] == 5
    assert next(c for c in friend.get("/api/board").json()["columns"] if c["is_me"])["team_id"] == 5

    # the link is spent
    assert friend.get(f"/api/auth/invite/{token}").json()["valid"] is False
    assert _fresh(league_client).post("/api/auth/join", json={"token": token, "username": "impostor", "password": PW}).status_code == 403
    listed = league_client.get("/api/auth/invites").json()
    assert listed[0]["status"] == "used" and listed[0]["used_by"] == "friend"
    assert next(t for t in league_client.get("/api/auth/teams").json() if t["team_id"] == 5)["claimed_by"] == "friend"


def test_invite_needs_a_real_email_and_a_mail_server(league_client):
    r = league_client.post("/api/auth/invites", json={"team_id": 5, "email": "not-an-email"})
    assert r.status_code == 400 and "email address" in r.json()["detail"]
    assert league_client.post("/api/auth/invites", json={"team_id": 5}).status_code == 422
    league_client.app.state.auth.cfg.resend_api_key = ""
    r = league_client.post("/api/auth/invites", json={"team_id": 5, "email": "a@b.co"})
    assert r.status_code == 400 and "not set up" in r.json()["detail"]
    assert league_client.get("/api/auth/invites").json() == []  # nothing created when it cannot be sent


def test_send_failure_is_reported_and_resend_works(league_client):
    def boom(cfg, to, subject, body):
        raise ConnectionError("smtp down")

    league_client.app.state.auth.send_mail = boom
    r = league_client.post("/api/auth/invites", json={"team_id": 6, "email": "six@example.com"})
    assert r.status_code == 502 and "smtp down" in r.json()["detail"]
    inv = league_client.get("/api/auth/invites").json()[0]  # created, so Resend can retry
    assert inv["status"] == "pending" and inv["sent_at"] is None and "smtp down" in inv["send_error"]
    league_client.app.state.auth.send_mail = lambda cfg, to, subject, body: (league_client.app.state.outbox.append((to, subject, body)), "msg_123")[1]
    r = league_client.post(f"/api/auth/invites/{inv['id']}/resend")
    assert r.status_code == 200 and r.json()["send_error"] == "" and r.json()["sent_at"] and r.json()["message_id"] == "msg_123"
    assert league_client.app.state.outbox[-1][0] == "six@example.com"


def test_invites_are_one_per_team_and_can_be_revoked(league_client):
    a = league_client.post("/api/auth/invites", json={"team_id": 6, "email": "a@example.com"}).json()
    b = league_client.post("/api/auth/invites", json={"team_id": 6, "email": "b@example.com"}).json()
    by_id = {i["id"]: i["status"] for i in league_client.get("/api/auth/invites").json()}
    assert by_id[a["id"]] == "revoked" and by_id[b["id"]] == "pending"
    token_a = _token_from(league_client.app.state.outbox[-2][2])
    assert _fresh(league_client).get(f"/api/auth/invite/{token_a}").json()["reason"].startswith("This invite was cancelled")
    assert league_client.delete(f"/api/auth/invites/{b['id']}").status_code == 204
    assert league_client.post(f"/api/auth/invites/{b['id']}/resend").status_code == 409
    assert _fresh(league_client).get("/api/auth/invite/not-a-real-token").json()["valid"] is False


def test_cannot_invite_for_a_team_someone_already_manages(league_client):
    r = league_client.post("/api/auth/invites", json={"team_id": 3, "email": "x@example.com"})
    assert r.status_code == 409 and "commish" in r.json()["detail"]
    assert league_client.post("/api/auth/invites", json={"team_id": 99, "email": "x@example.com"}).status_code == 404


def test_invites_are_admin_only(league_client):
    league_client.post("/api/auth/invites", json={"team_id": 8, "email": "eight@example.com"})
    token = _token_from(league_client.app.state.outbox[-1][2])
    friend = _fresh(league_client)
    friend.post("/api/auth/join", json={"token": token, "username": "friend", "password": PW})
    assert friend.get("/api/auth/invites").status_code == 403
    assert friend.post("/api/auth/invites", json={"team_id": 9, "email": "nine@example.com"}).status_code == 403
    assert friend.get("/api/auth/teams").status_code == 403


def test_admin_can_reassign_a_team(league_client):
    league_client.post("/api/auth/invites", json={"team_id": 5, "email": "five@example.com"})
    token = _token_from(league_client.app.state.outbox[-1][2])
    friend = _fresh(league_client)
    friend.post("/api/auth/join", json={"token": token, "username": "friend", "password": PW})
    fid = friend.get("/api/auth/me").json()["id"]
    r = league_client.post(f"/api/auth/users/{fid}/team", json={"team_id": 7})
    assert r.status_code == 200 and r.json()["team_id"] == 7
    assert friend.get("/api/auth/me").json()["team_id"] == 7
    assert friend.post(f"/api/auth/users/{fid}/team", json={"team_id": 8}).status_code == 403


def test_expired_invite_is_refused(league_client):
    from datetime import datetime, timedelta, timezone

    league_client.post("/api/auth/invites", json={"team_id": 5, "email": "five@example.com"})
    token = _token_from(league_client.app.state.outbox[-1][2])
    store = league_client.app.state.auth.invites
    item = store.by_token(token)
    item.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    store.save()
    friend = _fresh(league_client)
    assert friend.get(f"/api/auth/invite/{token}").json()["reason"].startswith("This invite has expired")
    assert friend.post("/api/auth/join", json={"token": token, "username": "late", "password": PW}).status_code == 403


def test_mail_info_tells_the_admin_how_invites_go_out(league_client):
    info = league_client.get("/api/auth/mail").json()
    assert info == {"configured": True, "provider": "resend", "sender": "FF <ff@test.co>", "reply_to": "", "sandbox": False, "link_base": "https://ff.example.com"}
    league_client.app.state.auth.cfg.mail_from = "Aljux Fantasy <onboarding@resend.dev>"
    assert league_client.get("/api/auth/mail").json()["sandbox"] is True
    friend = _fresh(league_client)
    assert friend.get("/api/auth/mail").status_code == 401


def test_a_real_invite_to_yourself_still_makes_a_real_account(league_client):
    """Not the recommended dry run (see test invites), but it must keep working."""
    r = league_client.post("/api/auth/invites", json={"team_id": 9, "email": "commish@example.com"})
    assert r.status_code == 200
    token = _token_from(league_client.app.state.outbox[-1][2])
    me_again = _fresh(league_client)
    r = me_again.post("/api/auth/join", json={"token": token, "username": "commish-test", "password": PW})
    assert r.status_code == 200 and r.json()["user"]["team_id"] == 9
    # deleting the test account frees the team for a real invite
    uid = r.json()["user"]["id"]
    assert league_client.delete(f"/api/auth/users/{uid}").status_code == 204
    assert league_client.post("/api/auth/invites", json={"team_id": 9, "email": "real@example.com"}).status_code == 200


def test_test_invite_is_the_real_email_for_your_own_team_and_creates_nothing(league_client):
    before = len(league_client.app.state.auth.users.users)
    r = league_client.post("/api/auth/invites/test", json={"email": "commish@example.com"})
    assert r.status_code == 200 and r.json()["test"] is True and r.json()["team_id"] == 3  # commish's own team
    to, subject, body = league_client.app.state.outbox[-1]
    assert to == "commish@example.com" and subject == "Your Test League fantasy football tool login"
    token = _token_from(body)
    # byte-for-byte the real email, for my own team: nothing in it says "test"
    from ffdraft import mail

    assert body == mail.invite_text("Test League", "Team Owner3", f"https://ff.example.com/join?token={token}", 14)[1]
    # the join page looks exactly like the real one, apart from knowing it is a dry run
    info = league_client.get(f"/api/auth/invite/{token}").json()
    assert info["valid"] is True and info["team_name"] == "Team Owner3" and info["test"] is True
    # same validation as the real thing
    assert league_client.post("/api/auth/join", json={"token": token, "username": "commish", "password": PW}).status_code == 400
    r = league_client.post("/api/auth/join", json={"token": token, "username": "dryrun", "password": PW})
    assert r.status_code == 200 and r.json()["test"] is True and r.json()["user"] is None
    assert "Nothing was created" in r.json()["message"] and "commish still manages it" in r.json()["message"]
    assert len(league_client.app.state.auth.users.users) == before
    assert league_client.get("/api/auth/me").json()["username"] == "commish"  # still signed in as myself
    assert league_client.get(f"/api/auth/invite/{token}").json()["valid"] is False  # spent, like a real one
    listed = league_client.get("/api/auth/invites").json()[0]
    assert listed["status"] == "used" and listed["test"] is True and listed["used_by"] == "commish"


def test_test_invite_does_not_disturb_a_real_pending_invite(league_client):
    league_client.post("/api/auth/invites", json={"team_id": 5, "email": "five@example.com"})
    league_client.post("/api/auth/invites/test", json={"email": "commish@example.com"})
    statuses = {(i["team_id"], i["test"]): i["status"] for i in league_client.get("/api/auth/invites").json()}
    assert statuses[(5, False)] == "pending" and statuses[(3, True)] == "pending"


def test_invites_refuse_to_send_links_that_would_hit_the_api(league_client, monkeypatch):
    """Split deploy (site + API) with APP_URL unset: a link built from the API host is a JSON 404."""
    from pathlib import Path

    from ffdraft import main

    league_client.app.state.auth.cfg.app_url = ""
    monkeypatch.setattr(main, "WEB_DIST", Path("/nowhere/dist"))
    r = league_client.post("/api/auth/invites", json={"team_id": 5, "email": "five@example.com"})
    assert r.status_code == 400 and "APP_URL" in r.json()["detail"]
    assert league_client.get("/api/auth/invites").json() == []  # nothing created
    assert league_client.get("/api/auth/mail").json()["link_base"] == ""
    # single-service deploy: the API serves the site, so its own host is right
    dist = Path(league_client.app.state.ctx.cfg.data_path) / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html>")
    monkeypatch.setattr(main, "WEB_DIST", dist)
    assert league_client.get("/api/auth/mail").json()["link_base"] == "http://testserver"
