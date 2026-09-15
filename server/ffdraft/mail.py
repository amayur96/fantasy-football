"""Outbound email for team invites: Resend when a key is set, SMTP otherwise.

Callers check `cfg.mail_configured` first; sending is never a silent no-op.
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any

from .config import Settings

RESEND_URL = "https://api.resend.com/emails"


def send(cfg: Settings, to: str, subject: str, body: str) -> str:
    """Returns the provider's message id ('' for SMTP). Raises with the provider's own reason on failure."""
    if not cfg.mail_configured:
        raise RuntimeError("Email is not configured (MAIL_FROM plus RESEND_API_KEY or SMTP_HOST)")
    if cfg.resend_api_key:
        return _send_resend(cfg, to, subject, body)
    _send_smtp(cfg, to, subject, body)
    return ""


def _send_resend(cfg: Settings, to: str, subject: str, body: str) -> str:
    import requests

    payload: dict[str, Any] = {"from": cfg.sender, "to": [to], "subject": subject, "text": body}
    if cfg.mail_reply_to:
        payload["reply_to"] = cfg.mail_reply_to
    r = requests.post(RESEND_URL, json=payload, headers={"Authorization": f"Bearer {cfg.resend_api_key}"}, timeout=20)
    if r.status_code >= 300:
        # Resend's errors are useful ("domain is not verified") — surface them verbatim.
        try:
            detail = r.json().get("message") or r.text
        except ValueError:
            detail = r.text
        raise RuntimeError(f"Resend {r.status_code}: {detail}")
    try:
        return str(r.json().get("id") or "")
    except ValueError:
        return ""


def _send_smtp(cfg: Settings, to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = cfg.sender
    msg["To"] = to
    msg["Subject"] = subject
    if cfg.mail_reply_to:
        msg["Reply-To"] = cfg.mail_reply_to
    msg.set_content(body)
    with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=20) as smtp:
        if cfg.smtp_starttls:
            smtp.starttls()
        if cfg.smtp_user:
            smtp.login(cfg.smtp_user, cfg.smtp_password)
        smtp.send_message(msg)


def invite_text(league: str, team: str, link: str, days: int) -> tuple[str, str]:
    """The subject names only the league; the body says which team the login is for."""
    subject = f"Your {league} fantasy football tool login"
    body = (
        f"You have been invited to {league}'s fantasy football tool as the manager of {team}.\n\n"
        f"This link creates your login for {team} \u2014 just pick a username and password:\n\n{link}\n\n"
        f"It works once and expires in {days} days. If {team} is not your team, or you were not expecting this, ignore it.\n\n"
        f"Please don't reply to this email \u2014 it isn't monitored. Questions go to the tool's admin."
    )
    return subject, body
