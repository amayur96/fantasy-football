"""Read the league's Google Sheet draft board (one tab per season).

Two ways in:
  * OAuth desktop flow (google_credentials.json present): full read incl. cell background colors.
  * Public CSV export (gviz): no credentials, but the sheet must be link-shared and colors are unavailable.
"""
from __future__ import annotations

import csv
import io
import logging
import re
from datetime import datetime, timezone
from typing import Any

from .config import Settings
from .models import SheetCell, SheetGrid

log = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
ROUND_RE = re.compile(r"^\s*round\s*(\d+)\s*$", re.I)
KEEPER_RE = re.compile(r"^\s*keepers?\s*:?\s*$", re.I)


# ---- auth / fetch --------------------------------------------------------------

def auth_mode(cfg: Settings) -> str:
    if not cfg.google_sheet_id:
        return "none"
    return "oauth" if cfg.google_credentials_file.exists() else "csv"


def _oauth_credentials(cfg: Settings) -> Any:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    token = cfg.google_token_path
    if token.exists():
        creds = Credentials.from_authorized_user_file(str(token), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(str(cfg.google_credentials_file), SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True)
    token.write_text(creds.to_json())
    return creds


def _hex(color: dict[str, Any] | None) -> str | None:
    if not color:
        return None
    r, g, b = (int(round(float(color.get(k, 0)) * 255)) for k in ("red", "green", "blue"))
    if (r, g, b) == (255, 255, 255):
        return None
    return f"#{r:02x}{g:02x}{b:02x}"


def fetch_oauth(cfg: Settings, tab: str | None = None) -> tuple[list[list[str]], list[list[str | None]]]:
    from googleapiclient.discovery import build

    tab = tab or cfg.sheet_tab
    service = build("sheets", "v4", credentials=_oauth_credentials(cfg), cache_discovery=False)
    resp = (
        service.spreadsheets()
        .get(spreadsheetId=cfg.google_sheet_id, ranges=[f"'{tab}'"], includeGridData=True,
             fields="sheets.data.rowData.values(formattedValue,effectiveFormat.backgroundColor)")
        .execute()
    )
    rows: list[list[str]] = []
    colors: list[list[str | None]] = []
    for sheet in resp.get("sheets", []):
        for block in sheet.get("data", []):
            for row in block.get("rowData", []):
                texts, cols = [], []
                for v in row.get("values", []) or []:
                    texts.append(str(v.get("formattedValue") or "").strip())
                    cols.append(_hex((v.get("effectiveFormat") or {}).get("backgroundColor")))
                rows.append(texts)
                colors.append(cols)
    return rows, colors


def fetch_csv(cfg: Settings, tab: str | None = None) -> list[list[str]]:
    import requests

    url = f"https://docs.google.com/spreadsheets/d/{cfg.google_sheet_id}/gviz/tq"
    r = requests.get(url, params={"tqx": "out:csv", "sheet": tab or cfg.sheet_tab, "headers": "0"}, timeout=20)
    if r.status_code != 200 or "<html" in r.text[:200].lower():
        raise RuntimeError("Sheet is not readable without credentials (share it 'anyone with the link', or add google_credentials.json)")
    return [[c.strip() for c in row] for row in csv.reader(io.StringIO(r.text))]


def fetch_grid(cfg: Settings, tab: str | None = None) -> SheetGrid:
    mode = auth_mode(cfg)
    if mode == "none":
        raise RuntimeError("GOOGLE_SHEET_ID is not set in .env")
    if mode == "oauth":
        rows, colors = fetch_oauth(cfg, tab)
        return parse_rows(rows, colors, source="oauth")
    return parse_rows(fetch_csv(cfg, tab), None, source="csv")


# ---- parsing -------------------------------------------------------------------

def parse_rows(rows: list[list[str]], colors: list[list[str | None]] | None, source: str = "csv") -> SheetGrid:
    """Layout: column A holds labels ('Round 1'.., 'Keepers'); the header row (team names) is the last
    row above 'Round 1' with at least three non-empty cells."""

    def cell(r: int, c: int) -> str:
        return rows[r][c].strip() if r < len(rows) and c < len(rows[r]) else ""

    def color(r: int, c: int) -> str | None:
        if colors is None or r >= len(colors) or c >= len(colors[r]):
            return None
        return colors[r][c]

    first_round_row = next((i for i, row in enumerate(rows) if row and ROUND_RE.match(row[0] or "") and ROUND_RE.match(row[0]).group(1) == "1"), None)
    if first_round_row is None:
        raise RuntimeError("Could not find a 'Round 1' row on the sheet tab")
    header_row = None
    for i in range(first_round_row - 1, -1, -1):
        if sum(1 for c in rows[i][1:] if c.strip()) >= 3:
            header_row = i
            break
    if header_row is None:
        raise RuntimeError("Could not find the team header row above 'Round 1'")
    width = max(len(r) for r in rows)
    headers, header_colors = [], []
    for c in range(1, width):
        h = cell(header_row, c)
        if not h and c > 1 and not any(cell(rr, c) for rr in range(first_round_row, len(rows))):
            continue
        headers.append(h)
        header_colors.append(color(header_row, c))
    n = len(headers)
    cells: list[SheetCell] = []
    extras: list[SheetCell] = []
    keepers: list[str] = []
    seen_round = False
    for i in range(first_round_row, len(rows)):
        label = cell(i, 0)
        m = ROUND_RE.match(label)
        if m:
            seen_round = True
            rnd = int(m.group(1))
            for c in range(n):
                text = cell(i, c + 1)
                col = color(i, c + 1)
                if text or col:
                    cells.append(SheetCell(round=rnd, col=c, text=text, color=col))
        elif KEEPER_RE.match(label):
            keepers = [cell(i, c + 1) for c in range(n)]
        elif seen_round and not keepers:
            for c in range(n):
                text = cell(i, c + 1)
                if text:
                    extras.append(SheetCell(round=0, col=c, text=text, color=color(i, c + 1)))
    return SheetGrid(headers=headers, header_colors=header_colors, cells=cells, extras=extras, keepers=keepers, source=source, fetched_at=datetime.now(timezone.utc))
