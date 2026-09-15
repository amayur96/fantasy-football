"""Username/password auth: user records, password hashing, and signed session cookies.

Users live in ``data/users.json``; passwords are stored as scrypt hashes (stdlib, no
extra dependency). Sessions are stateless signed tokens carried in an HttpOnly cookie.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid
from typing import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel

from . import mail
from .config import Settings
from .store import load_model, write_json

COOKIE_NAME = "ffdraft_session"
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
MIN_PASSWORD_LEN = 4

# scrypt cost: ~100ms/hash on a laptop, which is plenty for a league-sized app.
_N, _R, _P, _DKLEN, _SALT_BYTES = 2**14, 8, 1, 32, 16


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# ---- passwords -----------------------------------------------------------
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt, want = encoded.split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(password.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), dklen=len(_unb64(want)))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk, _unb64(want))


def validate_username(username: str) -> str:
    name = username.strip().lower()
    if not USERNAME_RE.match(name):
        raise ValueError("Username must be 3-32 characters: letters, numbers, dot, dash or underscore.")
    return name


def validate_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LEN} characters.")
    return password


# ---- users ---------------------------------------------------------------
class User(BaseModel):
    id: str
    username: str
    password_hash: str
    is_admin: bool = False
    created_at: datetime
    team_id: int | None = None  # which league team this person manages; set by the invite that created them
    email: str = ""  # where their invite went; for the members table, never for sign-in


class PublicUser(BaseModel):
    id: str
    username: str
    is_admin: bool
    created_at: datetime
    team_id: int | None = None
    email: str = ""


def public(user: User) -> PublicUser:
    return PublicUser(id=user.id, username=user.username, is_admin=user.is_admin, created_at=user.created_at, team_id=user.team_id, email=user.email)


class UserStore:
    """The user list, backed by a JSON file that is re-read on demand."""

    def __init__(self, path: Path):
        self.path = path
        self._users: list[User] = []

    def _reload(self) -> list[User]:
        self._users = load_model(self.path, list[User]) or []
        return self._users

    @property
    def users(self) -> list[User]:
        return self._reload()

    def save(self) -> None:
        write_json(self.path, self._users)

    @property
    def is_empty(self) -> bool:
        return not self._reload()

    def by_username(self, username: str) -> User | None:
        want = username.strip().lower()
        return next((u for u in self._reload() if u.username == want), None)

    def by_id(self, user_id: str) -> User | None:
        return next((u for u in self._reload() if u.id == user_id), None)

    def create(self, username: str, password: str, is_admin: bool = False, team_id: int | None = None, email: str = "") -> User:
        name = validate_username(username)
        validate_password(password)
        users = self._reload()
        if any(u.username == name for u in users):
            raise ValueError(f"Username {name!r} is already taken.")
        user = User(
            id=uuid.uuid4().hex,
            username=name,
            password_hash=hash_password(password),
            is_admin=is_admin,
            created_at=datetime.now(timezone.utc),
            team_id=team_id,
            email=email.strip().lower(),
        )
        users.append(user)
        self.save()
        return user

    def set_password(self, user: User, password: str) -> None:
        validate_password(password)
        new_hash = hash_password(password)
        target = next((u for u in self._reload() if u.id == user.id), None)
        if target is None:
            raise ValueError(f"No account named {user.username!r}.")
        target.password_hash = new_hash
        user.password_hash = new_hash
        self.save()

    def set_team(self, user: User, team_id: int | None) -> None:
        target = next((u for u in self._reload() if u.id == user.id), None)
        if target is None:
            raise ValueError(f"No account named {user.username!r}.")
        target.team_id = team_id
        user.team_id = team_id
        self.save()

    def by_team(self, team_id: int) -> User | None:
        return next((u for u in self._reload() if u.team_id == team_id), None)

    def delete(self, user: User) -> None:
        users = self._reload()
        if user.is_admin and sum(1 for u in users if u.is_admin) == 1:
            raise ValueError("Cannot delete the only admin.")
        self._users = [u for u in users if u.id != user.id]
        self.save()


# ---- team invites --------------------------------------------------------
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_email(email: str) -> str:
    e = email.strip().lower()
    if not EMAIL_RE.match(e):
        raise ValueError("That does not look like an email address.")
    return e


class Invite(BaseModel):
    """A one-time link, emailed to one person, that creates an account already bound to a team.

    `token` is the secret and only ever leaves the server inside the email. Admin screens address
    invites by `id`, so nobody can rebuild the link from the API."""
    id: str
    token: str
    team_id: int
    email: str
    created_by: str  # user id
    created_at: datetime
    expires_at: datetime
    used_by: str | None = None  # user id, once redeemed
    used_at: datetime | None = None
    revoked: bool = False
    # An admin's dry run for their own team: same email, same page; submitting it creates nothing.
    test: bool = False
    # What happened when we tried to email it, so the admin can see "sent" or the provider's reason.
    sent_at: datetime | None = None
    send_error: str = ""
    message_id: str = ""  # provider's id, for looking it up in their dashboard

    @property
    def status(self) -> str:
        if self.revoked:
            return "revoked"
        if self.used_by:
            return "used"
        if self.expires_at < datetime.now(timezone.utc):
            return "expired"
        return "pending"


class InviteStore:
    def __init__(self, path: Path):
        self.path = path
        self._items: list[Invite] = []

    def _reload(self) -> list[Invite]:
        self._items = load_model(self.path, list[Invite]) or []
        return self._items

    @property
    def items(self) -> list[Invite]:
        return self._reload()

    def save(self) -> None:
        write_json(self.path, self._items)

    def by_token(self, token: str) -> Invite | None:
        return next((i for i in self._reload() if secrets.compare_digest(i.token, token)), None)

    def by_id(self, invite_id: str) -> Invite | None:
        return next((i for i in self._reload() if i.id == invite_id), None)

    def create(self, team_id: int, created_by: str, email: str, days: int = 14, test: bool = False) -> Invite:
        """One live invite per team: creating a new one revokes any still pending."""
        email = validate_email(email)
        items = self._reload()
        for i in items:
            if i.team_id == team_id and i.status == "pending" and i.test == test:
                i.revoked = True
        now = datetime.now(timezone.utc)
        inv = Invite(id=uuid.uuid4().hex[:12], token=secrets.token_urlsafe(32), team_id=team_id, email=email, created_by=created_by, created_at=now, expires_at=now + timedelta(days=days), test=test)
        items.append(inv)
        self.save()
        return inv

    def consume(self, invite: Invite, user_id: str) -> None:
        target = next((i for i in self._reload() if i.token == invite.token), None)
        if target is None:
            raise ValueError("Invite vanished")
        target.used_by, target.used_at = user_id, datetime.now(timezone.utc)
        self.save()

    def record_send(self, invite: Invite, error: str = "", message_id: str = "") -> None:
        target = next((i for i in self._reload() if i.id == invite.id), None)
        if target is None:
            return
        target.send_error = error
        if not error:
            target.sent_at, target.message_id = datetime.now(timezone.utc), message_id
        invite.send_error, invite.sent_at, invite.message_id = target.send_error, target.sent_at, target.message_id
        self.save()

    def revoke(self, invite_id: str) -> bool:
        target = next((i for i in self._reload() if i.id == invite_id), None)
        if target is None:
            return False
        target.revoked = True
        self.save()
        return True


# ---- session tokens ------------------------------------------------------
def load_or_create_secret(cfg: Settings) -> bytes:
    """AUTH_SECRET from the environment, else a generated key persisted under data/."""
    if cfg.auth_secret:
        return cfg.auth_secret.encode()
    path = cfg.auth_secret_path
    if path.exists():
        return path.read_bytes().strip()
    secret = secrets.token_hex(32).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(secret)
    os.chmod(path, 0o600)
    return secret


def make_token(user_id: str, secret: bytes, days: int) -> str:
    payload = _b64(json.dumps({"uid": user_id, "exp": int(time.time()) + days * 86400}).encode())
    sig = _b64(hmac.new(secret, payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def read_token(token: str, secret: bytes) -> str | None:
    """Return the user id for a valid, unexpired token, else None."""
    payload, _, sig = token.partition(".")
    if not payload or not sig:
        return None
    want = _b64(hmac.new(secret, payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, want):
        return None
    try:
        data = json.loads(_unb64(payload))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or int(data.get("exp", 0)) < time.time():
        return None
    uid = data.get("uid")
    return uid if isinstance(uid, str) else None


# ---- brute-force throttle -----------------------------------------------
class LoginThrottle:
    """In-memory lockout after repeated failures for the same username."""

    def __init__(self, max_failures: int = 5, lockout_seconds: int = 60):
        self.max_failures = max_failures
        self.lockout_seconds = lockout_seconds
        self._fails: dict[str, tuple[int, float]] = {}

    def retry_after(self, key: str) -> int:
        count, last = self._fails.get(key, (0, 0.0))
        if count < self.max_failures:
            return 0
        remaining = self.lockout_seconds - (time.time() - last)
        if remaining <= 0:
            self._fails.pop(key, None)
            return 0
        return int(remaining) + 1

    def record_failure(self, key: str) -> None:
        count, _ = self._fails.get(key, (0, 0.0))
        self._fails[key] = (count + 1, time.time())

    def reset(self, key: str) -> None:
        self._fails.pop(key, None)


class AuthService:
    """Everything the API needs to log a user in and recognise them again."""

    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self.users = UserStore(cfg.users_path)
        self.invites = InviteStore(cfg.invites_path)
        self.secret = load_or_create_secret(cfg)
        self.throttle = LoginThrottle()
        # Swapped for a recorder in tests; production goes through SMTP.
        self.send_mail: Callable[[Settings, str, str, str], None] = mail.send

    def bind_owner(self, settings: object) -> str | None:
        """The admin who supplied the ESPN cookie manages the cookie's team. Done once, on startup,
        for an admin with no team while nobody else holds that team. Returns the username bound."""
        owner_team = getattr(settings, "my_team_id", None)
        if not owner_team or self.users.by_team(owner_team) is not None:
            return None
        admin = next((u for u in self.users.users if u.is_admin and u.team_id is None), None)
        if admin is None:
            return None
        self.users.set_team(admin, owner_team)
        return admin.username

    def bootstrap(self) -> str | None:
        """Create the configured admin if there are no accounts yet. Returns the name, or None."""
        if not self.users.is_empty or not (self.cfg.bootstrap_username and self.cfg.bootstrap_password):
            return None
        return self.users.create(self.cfg.bootstrap_username, self.cfg.bootstrap_password, is_admin=True).username

    def authenticate(self, username: str, password: str) -> User | None:
        user = self.users.by_username(username)
        if user is None:
            # Hash anyway so a missing user costs the same as a wrong password.
            hash_password(password)
            return None
        return user if verify_password(password, user.password_hash) else None

    def issue_token(self, user: User) -> str:
        return make_token(user.id, self.secret, self.cfg.session_days)

    def user_from_token(self, token: str | None) -> User | None:
        if not token:
            return None
        uid = read_token(token, self.secret)
        return self.users.by_id(uid) if uid else None
