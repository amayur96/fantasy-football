"""Environment configuration loaded from .env / process env."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    league_id: int = 0
    espn_s2: str = ""
    swid: str = ""
    season: int = 2026
    data_dir: Path = ROOT / "data"
    first_history_year: int = 2019

    # Google Sheet draft board (optional)
    google_sheet_id: str = ""
    google_sheet_tab: str = ""  # defaults to str(season)
    google_credentials_file: Path = ROOT / "google_credentials.json"
    sheet_poll_seconds: int = 15

    # Sign-in
    auth_secret: str = ""  # generated into data/auth_secret when blank
    session_days: int = 30
    allow_registration: bool = False  # when False, only admins can add users after the first
    cookie_secure: bool = False  # set True when serving over HTTPS
    # Creates this admin on startup when no accounts exist yet. On a public URL this closes the
    # window where the first stranger to load the site could claim the admin account.
    bootstrap_username: str = ""
    bootstrap_password: str = ""

    @property
    def data_path(self) -> Path:
        p = self.data_dir if self.data_dir.is_absolute() else ROOT / self.data_dir
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def has_credentials(self) -> bool:
        return bool(self.league_id and self.espn_s2 and self.swid)

    @property
    def sheet_tab(self) -> str:
        return self.google_sheet_tab or str(self.season)

    @property
    def google_token_path(self) -> Path:
        return self.data_path / "google_token.json"

    @property
    def users_path(self) -> Path:
        return self.data_path / "users.json"

    @property
    def auth_secret_path(self) -> Path:
        return self.data_path / "auth_secret"


def get_settings() -> Settings:
    return Settings()
