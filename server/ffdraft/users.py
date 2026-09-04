"""CLI: make user CMD="{list,add,passwd,rm} [username]"

Handy when nobody can sign in yet, or when someone forgets a password.
"""
from __future__ import annotations

import argparse
import getpass
import sys

from .auth import UserStore, validate_password
from .config import get_settings


def _prompt_password(username: str) -> str:
    first = getpass.getpass(f"Password for {username}: ")
    if first != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match.")
    try:
        return validate_password(first)
    except ValueError as exc:
        sys.exit(str(exc))


def main() -> None:
    ap = argparse.ArgumentParser(description="Manage sign-in accounts stored in data/users.json")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="show every account")
    add = sub.add_parser("add", help="create an account")
    add.add_argument("username")
    add.add_argument("--admin", action="store_true", help="may add and remove other users")
    pw = sub.add_parser("passwd", help="set a new password")
    pw.add_argument("username")
    rm = sub.add_parser("rm", help="delete an account")
    rm.add_argument("username")
    args = ap.parse_args()

    cfg = get_settings()
    store = UserStore(cfg.users_path)

    if args.cmd == "list":
        if not store.users:
            print('No accounts yet. Create one with: make user CMD="add <username> --admin"')
            return
        for u in store.users:
            print(f"{u.username:<24} {'admin' if u.is_admin else 'member':<7} created {u.created_at:%Y-%m-%d}")
        return

    if args.cmd == "add":
        password = _prompt_password(args.username)
        try:
            user = store.create(args.username, password, is_admin=args.admin or store.is_empty)
        except ValueError as exc:
            sys.exit(str(exc))
        print(f"Created {user.username} ({'admin' if user.is_admin else 'member'}).")
        return

    user = store.by_username(args.username)
    if user is None:
        sys.exit(f"No account named {args.username!r}.")

    if args.cmd == "passwd":
        store.set_password(user, _prompt_password(user.username))
        print(f"Password updated for {user.username}.")
    else:
        try:
            store.delete(user)
        except ValueError as exc:
            sys.exit(str(exc))
        print(f"Deleted {user.username}.")


if __name__ == "__main__":
    main()
