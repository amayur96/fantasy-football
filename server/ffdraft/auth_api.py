"""Sign-in routes under /api/auth, plus the dependency that guards every other route."""
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import mail
from .auth import COOKIE_NAME, AuthService, Invite, PublicUser, User, public

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def auth(request: Request) -> AuthService:
    return request.app.state.auth


def current_user(request: Request) -> User:
    """Guard for protected routes: 401 unless the session cookie names a real user."""
    svc: AuthService = request.app.state.auth
    user = svc.user_from_token(request.cookies.get(COOKIE_NAME))
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    return user


def current_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admins only.")
    return user


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class NewUser(Credentials):
    is_admin: bool = False


class TeamChoice(BaseModel):
    team_id: int | None = None


class InviteRequest(BaseModel):
    team_id: int
    email: str = Field(min_length=3, max_length=254)


class InviteView(BaseModel):
    """What admins see. Deliberately no token and no link: the link exists only in the email."""
    id: str
    team_id: int
    team_name: str
    email: str
    status: str  # pending / used / expired / revoked
    created_at: datetime
    expires_at: datetime
    used_by: str | None = None  # username
    test: bool = False
    sent_at: datetime | None = None
    send_error: str = ""  # the provider's reason when the email did not go out
    message_id: str = ""


class TestInviteRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class InviteInfo(BaseModel):
    """What the join page shows before any account exists."""
    valid: bool
    reason: str = ""
    team_name: str = ""
    league_name: str = ""
    test: bool = False


class JoinRequest(Credentials):
    token: str = Field(min_length=16, max_length=128)


class JoinResult(BaseModel):
    user: PublicUser | None = None  # the new account, signed in — absent for a test run
    test: bool = False
    message: str = ""


class MailInfo(BaseModel):
    configured: bool
    provider: str = ""  # resend / smtp / ""
    sender: str = ""
    reply_to: str = ""
    sandbox: bool = False  # Resend's onboarding sender: delivers only to the account owner's address
    link_base: str = ""  # what invite links start with; "" when it cannot be determined (APP_URL missing)


class LeagueTeam(BaseModel):
    team_id: int
    name: str
    owners: list[str] = Field(default_factory=list)
    claimed_by: str | None = None  # username, when someone already manages this team here


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class AuthStatus(BaseModel):
    users_exist: bool
    allow_registration: bool
    mail_configured: bool = False  # invites can be emailed rather than copied


def _set_cookie(response: Response, svc: AuthService, user: User) -> None:
    response.set_cookie(
        COOKIE_NAME,
        svc.issue_token(user),
        max_age=svc.cfg.session_days * 86400,
        httponly=True,
        samesite="lax",
        secure=svc.cfg.cookie_secure,
        path="/",
    )


@router.get("/status", response_model=AuthStatus)
def status(svc: AuthService = Depends(auth)) -> AuthStatus:
    """Unauthenticated: tells the sign-in page whether to offer account creation."""
    return AuthStatus(users_exist=not svc.users.is_empty, allow_registration=svc.cfg.allow_registration, mail_configured=svc.cfg.mail_configured)


@router.post("/login", response_model=PublicUser)
def login(body: Credentials, response: Response, svc: AuthService = Depends(auth)) -> PublicUser:
    key = body.username.strip().lower()
    wait = svc.throttle.retry_after(key)
    if wait:
        raise HTTPException(status_code=429, detail=f"Too many attempts. Try again in {wait}s.")
    user = svc.authenticate(body.username, body.password)
    if user is None:
        svc.throttle.record_failure(key)
        raise HTTPException(status_code=401, detail="Incorrect username or password.")
    svc.throttle.reset(key)
    _set_cookie(response, svc, user)
    return public(user)


@router.post("/register", response_model=PublicUser)
def register(body: Credentials, request: Request, response: Response, svc: AuthService = Depends(auth)) -> PublicUser:
    """Open only for the very first account (which becomes admin), or when ALLOW_REGISTRATION=true.
    Everyone else arrives through a team invite (POST /auth/join)."""
    first = svc.users.is_empty
    if not first and not svc.cfg.allow_registration:
        raise HTTPException(status_code=403, detail="Registration is closed. Ask the tool's admin for an invite link.")
    # The first admin is whoever set the ESPN cookie up, so they own the cookie's team.
    settings = getattr(request.app.state.ctx, "settings", None)
    team = getattr(settings, "my_team_id", None) if first else None
    user = svc.users.create(body.username, body.password, is_admin=first, team_id=team)
    _set_cookie(response, svc, user)
    return public(user)


@router.post("/logout", status_code=204)
def logout(response: Response, svc: AuthService = Depends(auth)) -> None:
    response.delete_cookie(COOKIE_NAME, secure=svc.cfg.cookie_secure, path="/")


@router.get("/me", response_model=PublicUser)
def me(user: User = Depends(current_user)) -> PublicUser:
    return public(user)


@router.post("/password", status_code=204)
def change_password(body: PasswordChange, user: User = Depends(current_user), svc: AuthService = Depends(auth)) -> None:
    # 400, not 401: the session is still valid. The SPA treats every 401 as signed-out.
    if svc.authenticate(user.username, body.current_password) is None:
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    svc.users.set_password(user, body.new_password)


@router.get("/users", response_model=list[PublicUser])
def list_users(_: User = Depends(current_admin), svc: AuthService = Depends(auth)) -> list[PublicUser]:
    return [public(u) for u in svc.users.users]


@router.post("/users", response_model=PublicUser)
def add_user(body: NewUser, _: User = Depends(current_admin), svc: AuthService = Depends(auth)) -> PublicUser:
    return public(svc.users.create(body.username, body.password, is_admin=body.is_admin))


@router.delete("/users/{user_id}", status_code=204)
def remove_user(user_id: str, me: User = Depends(current_admin), svc: AuthService = Depends(auth)) -> None:
    target = svc.users.by_id(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="No such user.")
    if target.id == me.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")
    svc.users.delete(target)


# ---- teams and invites ---------------------------------------------------


def _league(request: Request):
    return request.app.state.ctx.settings


def _league_teams(request: Request) -> list:
    st = _league(request)
    return list(st.teams) if st is not None else []


@router.get("/teams", response_model=list[LeagueTeam])
def teams(request: Request, _: User = Depends(current_admin), svc: AuthService = Depends(auth)) -> list[LeagueTeam]:
    """The league's teams and who manages each one here. Admin-only: it is the invite screen's data."""
    claimed = {u.team_id: u.username for u in svc.users.users if u.team_id is not None}
    return [LeagueTeam(team_id=t.team_id, name=t.name, owners=list(t.owner_names), claimed_by=claimed.get(t.team_id)) for t in _league_teams(request)]


def _assign_team(request: Request, svc: AuthService, target: User, team_id: int | None) -> None:
    if team_id is not None:
        if team_id not in {t.team_id for t in _league_teams(request)}:
            raise HTTPException(status_code=404, detail="No such team in this league. Sync the league first if the list is empty.")
        holder = svc.users.by_team(team_id)
        if holder is not None and holder.id != target.id:
            svc.users.set_team(holder, None)  # an admin moving a team hands it over
    svc.users.set_team(target, team_id)


@router.post("/users/{user_id}/team", response_model=PublicUser)
def set_user_team(user_id: str, body: TeamChoice, request: Request, _: User = Depends(current_admin), svc: AuthService = Depends(auth)) -> PublicUser:
    """Admins can correct who manages what; members themselves never choose."""
    target = svc.users.by_id(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="No such user.")
    _assign_team(request, svc, target, body.team_id)
    return public(target)


def _base_url(request: Request, svc: AuthService) -> str:
    """Where invite links point. APP_URL when set; otherwise this host, which is only right when the
    API also serves the web build (the single-service deploy). On Render the site and API are split,
    so a link built from the API's host lands on a JSON 404 — refuse rather than email that."""
    if svc.cfg.app_url:
        return svc.cfg.app_url.rstrip("/")
    from .main import WEB_DIST

    if not (WEB_DIST / "index.html").exists():
        raise HTTPException(status_code=400, detail="APP_URL is not set, so invite links would point at the API instead of the site. Set APP_URL to the site's address (e.g. https://your-site.onrender.com) and try again.")
    return str(request.base_url).rstrip("/")


def _invite_view(inv: Invite, request: Request, svc: AuthService) -> InviteView:
    names = {t.team_id: t.name for t in _league_teams(request)}
    used = svc.users.by_id(inv.used_by).username if inv.used_by and svc.users.by_id(inv.used_by) else None
    return InviteView(
        id=inv.id, team_id=inv.team_id, team_name=names.get(inv.team_id, f"Team {inv.team_id}"), email=inv.email, status=inv.status,
        created_at=inv.created_at, expires_at=inv.expires_at, used_by=used, test=inv.test,
        sent_at=inv.sent_at, send_error=inv.send_error, message_id=inv.message_id,
    )


def _email_invite(inv: Invite, request: Request, svc: AuthService) -> None:
    """The only place the link is ever assembled."""
    if not svc.cfg.mail_configured:
        raise HTTPException(status_code=400, detail="Email is not set up on the server yet (MAIL_FROM plus RESEND_API_KEY). Invites are sent by email only.")
    names = {t.team_id: t.name for t in _league_teams(request)}
    league = getattr(_league(request), "league_name", None) or "your league"
    link = f"{_base_url(request, svc)}/join?token={inv.token}"
    subject, text = mail.invite_text(league, names.get(inv.team_id, f"Team {inv.team_id}"), link, svc.cfg.invite_days)
    try:
        message_id = svc.send_mail(svc.cfg, inv.email, subject, text) or ""
    except Exception as exc:  # noqa: BLE001
        log.warning("invite email to %s failed: %s", inv.email, exc)
        svc.invites.record_send(inv, error=str(exc))
        raise HTTPException(status_code=502, detail=f"The email did not go out: {exc}") from exc
    svc.invites.record_send(inv, message_id=str(message_id))


@router.get("/mail", response_model=MailInfo)
def mail_info(request: Request, _: User = Depends(current_admin), svc: AuthService = Depends(auth)) -> MailInfo:
    """How invite emails go out, so the admin can see it and send themselves one first."""
    cfg = svc.cfg
    provider = "resend" if cfg.resend_api_key else "smtp" if cfg.smtp_host else ""
    try:
        base = _base_url(request, svc)
    except HTTPException:
        base = ""
    return MailInfo(configured=cfg.mail_configured, provider=provider, sender=cfg.sender, reply_to=cfg.mail_reply_to, sandbox="resend.dev" in cfg.sender.lower(), link_base=base)


@router.get("/invites", response_model=list[InviteView])
def list_invites(request: Request, _: User = Depends(current_admin), svc: AuthService = Depends(auth)) -> list[InviteView]:
    return [_invite_view(i, request, svc) for i in sorted(svc.invites.items, key=lambda i: i.created_at, reverse=True)]


@router.post("/invites", response_model=InviteView)
def create_invite(body: InviteRequest, request: Request, me: User = Depends(current_admin), svc: AuthService = Depends(auth)) -> InviteView:
    """Email one person a one-time link that creates an account tied to this team."""
    names = {t.team_id: t.name for t in _league_teams(request)}
    if body.team_id not in names:
        raise HTTPException(status_code=404, detail="No such team in this league.")
    holder = svc.users.by_team(body.team_id)
    if holder is not None:
        raise HTTPException(status_code=409, detail=f"{names[body.team_id]} is already managed by {holder.username}. Reassign or remove that account first.")
    if not svc.cfg.mail_configured:
        raise HTTPException(status_code=400, detail="Email is not set up on the server yet (MAIL_FROM plus RESEND_API_KEY). Invites are sent by email only.")
    _base_url(request, svc)  # a link we cannot build correctly must not leave an invite behind
    try:
        inv = svc.invites.create(body.team_id, created_by=me.id, email=body.email, days=svc.cfg.invite_days)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _email_invite(inv, request, svc)
    return _invite_view(inv, request, svc)


@router.post("/invites/test", response_model=InviteView)
def test_invite(body: TestInviteRequest, request: Request, me: User = Depends(current_admin), svc: AuthService = Depends(auth)) -> InviteView:
    """A dry run for the admin's own team: the exact email and page a league-mate gets. Submitting the
    form at the end creates nothing and changes nothing."""
    team = me.team_id if me.team_id is not None else getattr(_league(request), "my_team_id", None)
    if team is None:
        raise HTTPException(status_code=400, detail="Your account has no team yet, so there is nothing to test with.")
    if not svc.cfg.mail_configured:
        raise HTTPException(status_code=400, detail="Email is not set up on the server yet (MAIL_FROM plus RESEND_API_KEY). Invites are sent by email only.")
    _base_url(request, svc)
    try:
        inv = svc.invites.create(team, created_by=me.id, email=body.email, days=svc.cfg.invite_days, test=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _email_invite(inv, request, svc)
    return _invite_view(inv, request, svc)


@router.post("/invites/{invite_id}/resend", response_model=InviteView)
def resend_invite(invite_id: str, request: Request, _: User = Depends(current_admin), svc: AuthService = Depends(auth)) -> InviteView:
    """Same link, same address — for when the first one went to spam."""
    inv = svc.invites.by_id(invite_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="No such invite.")
    if inv.status != "pending":
        raise HTTPException(status_code=409, detail=f"That invite is {inv.status}; create a new one instead.")
    _email_invite(inv, request, svc)
    return _invite_view(inv, request, svc)


@router.delete("/invites/{invite_id}", status_code=204)
def revoke_invite(invite_id: str, _: User = Depends(current_admin), svc: AuthService = Depends(auth)) -> None:
    if not svc.invites.revoke(invite_id):
        raise HTTPException(status_code=404, detail="No such invite.")


@router.get("/invite/{token}", response_model=InviteInfo)
def invite_info(token: str, request: Request, svc: AuthService = Depends(auth)) -> InviteInfo:
    """Unauthenticated: the join page asks what this link is for before showing the form."""
    inv = svc.invites.by_token(token)
    if inv is None:
        return InviteInfo(valid=False, reason="This invite link is not recognised. Ask the tool's admin for a fresh one.")
    if inv.status != "pending":
        why = {"used": "This invite has already been used.", "expired": "This invite has expired.", "revoked": "This invite was cancelled."}[inv.status]
        return InviteInfo(valid=False, reason=f"{why} Ask the tool's admin for a fresh one.")
    names = {t.team_id: t.name for t in _league_teams(request)}
    st = _league(request)
    return InviteInfo(valid=True, team_name=names.get(inv.team_id, f"Team {inv.team_id}"), league_name=getattr(st, "league_name", "") or "", test=inv.test)


@router.post("/join", response_model=JoinResult)
def join(body: JoinRequest, request: Request, response: Response, svc: AuthService = Depends(auth)) -> JoinResult:
    """Redeem a team invite: the account is created bound to the invite's team, and the link is spent.
    A test invite goes through every step but the last: nothing is created and nobody is signed in."""
    inv = svc.invites.by_token(body.token)
    if inv is None or inv.status != "pending":
        raise HTTPException(status_code=403, detail=invite_info(body.token, request, svc).reason)
    names = {t.team_id: t.name for t in _league_teams(request)}
    if inv.test:
        # Validate exactly what a real join would, so the dry run catches the same mistakes.
        from .auth import validate_password, validate_username

        try:
            name = validate_username(body.username)
            validate_password(body.password)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if svc.users.by_username(name) is not None:
            raise HTTPException(status_code=400, detail=f"Username {name!r} is already taken.")
        svc.invites.consume(inv, inv.created_by)
        holder = svc.users.by_team(inv.team_id)
        who = f" {holder.username}" if holder else ""
        return JoinResult(test=True, message=f"That was a test. A league-mate would now have an account named {name!r} tied to {names.get(inv.team_id, 'their team')}. Nothing was created —{who} still manages it.")
    holder = svc.users.by_team(inv.team_id)
    if holder is not None:
        raise HTTPException(status_code=409, detail="That team is already managed by another account. Ask the tool's admin to sort it out.")
    user = svc.users.create(body.username, body.password, is_admin=False, team_id=inv.team_id, email=inv.email)
    svc.invites.consume(inv, user.id)
    _set_cookie(response, svc, user)
    return JoinResult(user=public(user))
