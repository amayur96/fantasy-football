# Fantasy Football Tool


## Setup

```bash
brew install uv            # once
uv python install 3.12     # once
make setup                 # uv sync + npm install
make sync-refresh          # pull league settings, players, your 2025 roster, and 2019-2025 draft history
make dev                   # API on :8000, UI on http://localhost:5173
```

## Keeper rules as encoded (verified against the 2019–2026 draft history)

- First year keeping a player you drafted: same round he was drafted in.
- Each additional consecutive year: 2 rounds earlier than last year's cost. Floor: round 1.
- Undrafted (waiver) pickup: last round the first year, then 2 earlier each year.
- Acquired in-season by trade/waiver: the cost chain follows the player unchanged.
- Acquired in the offseason: league precedent is 2 rounds earlier than normal. Shown as a warning + override,
  not applied automatically.
- A keeper consumes that team's pick in the cost round. If the team traded that pick away, the app assumes the
  next-later owned pick and warns.

## Commands

| Command | What it does |
|---|---|
| `make sync` | Load from cache, fetching from ESPN only what's missing |
| `make sync-refresh` | Force a full refresh from ESPN |
| `make server` / `make web` / `make dev` | Run the API / UI / both |
| `make test` | Backend tests (no network) |
| `make reset-draft` | Wipe the draft board (`data/draft_state.json`) |

## Data sources

| Source | Used for | Config |
|---|---|---|
| ESPN (private league API) | Settings, scoring, rosters, projections, ADP, weekly lineup, free agents | `LEAGUE_ID`, `ESPN_S2`, `SWID` in `.env` |
| League Google Sheet ("Drafts") | Draft history + keeper flags (source of truth), live draft board, other teams' keepers and pick trades | `GOOGLE_SHEET_ID` (+ optional `GOOGLE_SHEET_TAB`) in `.env`; sheet must be link-viewable, or add `google_credentials.json` for OAuth with cell colors |
| FantasyPros consensus | Draft value blend (superflex list for this 2-QB league), weekly start/sit grades and projections | none; public pages, cached 1 day / 6 hours |
| Boris Chen tiers | Tiers on the Live Draft aid and Draft Board, tier-cliff logic in draft and lineup recommendations | none; public text files, cached 1 day |

Everything is cached under `data/` (git-ignored), so draft day works offline once synced.
