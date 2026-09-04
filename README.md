# Fantasy Football Tool


## Setup

```bash
brew install uv            # once
uv python install 3.12     # once
make setup                 # uv sync + npm install
make sync-refresh          # pull league settings, players, your 2025 roster, and 2019-2025 draft history
make dev                   # API on :8000, UI on http://localhost:5173
```

Open http://localhost:5173 and create the first account — it becomes the admin.

## Accounts

Every `/api` route needs a signed-in user. Accounts live in `data/users.json` (git-ignored) with scrypt-hashed
passwords; the session is an HttpOnly cookie signed with `AUTH_SECRET` (generated into `data/auth_secret` if
unset). The first person to hit the sign-in page creates the admin account; after that, admins add members from
**Account → League members**, or from the terminal:

```bash
make user CMD="list"                 # who has an account
make user CMD="add friend"           # prompts for a password
make user CMD="passwd friend"        # reset a forgotten password
make user CMD="rm friend"            # revoke access
```

Optional `.env` settings: `ALLOW_REGISTRATION=true` lets anyone sign themselves up, `SESSION_DAYS` (default 30)
sets how long a login lasts, and `COOKIE_SECURE=true` is required if you ever serve this over HTTPS.

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
| `make user CMD="..."` | Manage sign-in accounts (`list`, `add <name>`, `passwd <name>`, `rm <name>`) |
| `make reset-draft` | Wipe the draft board (`data/draft_state.json`) |

## Deploying to Render

`render.yaml` is a blueprint: in Render, **New → Blueprint**, point it at this repo, and fill in the
values it prompts for. It creates two services, because Render's Python runtime has no Node and so
cannot build the UI:

| Service | What it is | Plan |
|---|---|---|
| `ff-draft-web` | Static site: `npm ci && npm run build`, publishes `web/dist` | free |
| `ff-draft-api` | Python service: `pip install -r requirements.txt`, runs uvicorn | `0.5c-512mb` + 1 GB disk |

The static site proxies `/api/*` through to the API with a rewrite rule, so the browser only ever
talks to one origin and the HttpOnly session cookie stays first-party — no CORS, no `SameSite=None`.
If Render appends a suffix to the API's URL (it does when the name is taken), fix the `destination`
in `render.yaml` to match.

Environment variables to set in the dashboard; the rest come from `render.yaml`:

| Variable | Why |
|---|---|
| `BOOTSTRAP_USERNAME` / `BOOTSTRAP_PASSWORD` | Creates the admin on first boot, so no stranger can claim it. Clear both once you have signed in. |
| `LEAGUE_ID`, `ESPN_S2`, `SWID` | ESPN league access, same values as your local `.env` |
| `GOOGLE_SHEET_ID`, `GOOGLE_SHEET_TAB` | Draft board sync; the sheet must be link-viewable |

Python is pinned to 3.12 by `.python-version` — Render's default is 3.14, which `uv.lock` does not
target. `requirements.txt` is generated from that lockfile, so regenerate it whenever deps change:

```bash
make requirements
```

### Storage and cost

The API runs on a paid instance with a 1 GB disk mounted at `/var/ffdraft`, with `DATA_DIR` pointed
at it. Accounts, draft state, setup overrides and the ESPN caches all survive deploys and restarts,
and a paid instance never sleeps — so no cold starts, and a live draft is safe to run on it.

Roughly **$7.25/month**: about $7 for the `0.5c-512mb` instance (0.5 CPU / 512 MB — the app peaks
around 55 MB with the whole league loaded) plus $0.25 for the 1 GB disk. The static site is free.
Local data is ~4 MB, so 1 GB is far more than needed; it is the smallest disk Render sells.

The workspace stays on **Hobby, $0/mo** — Render bills compute on top of every workspace tier, so a
paid instance does not require a paid workspace. Hobby covers up to 25 services and 5 GB of
bandwidth a month, well beyond a ten-person league.

Two things to know about disks: Render runs a single instance for any service that has one, so
deploys restart the service instead of rolling (a few seconds of downtime), and a disk's `sizeGB`
can be increased later but never reduced.

After the first deploy the disk is empty — sign in, then run a sync from the dashboard to pull the
league from ESPN. Two files never travel with the repo because they are git-ignored league data:
`data/seed/league_2026.json` (other teams' keepers and pick trades) and, if you use OAuth for sheet
cell colours, `google_credentials.json`. Copy them onto the disk from Render's Shell tab, or re-enter
those keepers from the Setup screen.

## Data sources

| Source | Used for | Config |
|---|---|---|
| ESPN (private league API) | Settings, scoring, rosters, projections, ADP, weekly lineup, free agents | `LEAGUE_ID`, `ESPN_S2`, `SWID` in `.env` |
| League Google Sheet ("Drafts") | Draft history + keeper flags (source of truth), live draft board, other teams' keepers and pick trades | `GOOGLE_SHEET_ID` (+ optional `GOOGLE_SHEET_TAB`) in `.env`; sheet must be link-viewable, or add `google_credentials.json` for OAuth with cell colors |
| FantasyPros consensus | Draft value blend (superflex list for this 2-QB league), weekly start/sit grades and projections | none; public pages, cached 1 day / 6 hours |
| Boris Chen tiers | Tiers on the Live Draft aid and Draft Board, tier-cliff logic in draft and lineup recommendations | none; public text files, cached 1 day |

Everything is cached under `data/` (git-ignored), so draft day works offline once synced.
