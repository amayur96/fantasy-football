"""Sign-in routes under /api/auth, plus the dependency that guards every other route."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .auth import COOKIE_NAME, AuthService, PublicUser, User, public

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


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class AuthStatus(BaseModel):
    users_exist: bool
    allow_registration: bool


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
    return AuthStatus(users_exist=not svc.users.is_empty, allow_registration=svc.cfg.allow_registration)


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
def register(body: Credentials, response: Response, svc: AuthService = Depends(auth)) -> PublicUser:
    """Open only for the very first account (which becomes admin), or when ALLOW_REGISTRATION=true."""
    first = svc.users.is_empty
    if not first and not svc.cfg.allow_registration:
        raise HTTPException(status_code=403, detail="Registration is closed. Ask an admin to create your account.")
    user = svc.users.create(body.username, body.password, is_admin=first)
    _set_cookie(response, svc, user)
    return public(user)


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me", response_model=PublicUser)
def me(user: User = Depends(current_user)) -> PublicUser:
    return public(user)


@router.post("/password", status_code=204)
def change_password(body: PasswordChange, user: User = Depends(current_user), svc: AuthService = Depends(auth)) -> None:
    if svc.authenticate(user.username, body.current_password) is None:
        raise HTTPException(status_code=401, detail="Current password is incorrect.")
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
