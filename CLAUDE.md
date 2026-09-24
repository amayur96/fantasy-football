# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A keeper + draft assistant for one private 10-team, 2-QB ESPN fantasy league. FastAPI backend
(`server/ffdraft`) + React/Vite frontend (`web`). No database — everything is JSON files under `data/`.

## Commands

```bash
make setup          # uv sync + npm install (needs: brew install uv; uv python install 3.12)
make dev            # API on :8000 and Vite on :5173 together (-j2)
make server         # uvicorn ffdraft.main:app --reload --port 8000 --app-dir server
make web            # vite dev server (proxies /api -> :8000)
make sync           # pull from ESPN, cache-first
make sync-refresh   # force a full refresh from ESPN + sheet history + expert rankings
make test           # pytest -q (server/tests, never hits the network)
make reset-draft    # rm data/draft_state.json
make user CMD="add alice"   # list | add <name> | passwd <name> | rm <name>
make requirements   # regenerate requirements.txt from uv.lock — run after changing pyproject.toml
```

Single test: `uv run pytest server/tests/test_keeper.py -q` or `uv run pytest -k keeper_chain -q`.
`pythonpath`/`testpaths` are set in `pyproject.toml`, so no `PYTHONPATH` is needed for pytest (but the
`python -m ffdraft.*` CLIs do need `PYTHONPATH=server`, as the Makefile shows).

Frontend: `npm --prefix web run lint` (oxlint) and `npm --prefix web run build` (`tsc -b && vite build`).
There are no frontend tests; typecheck via the build.

Python is pinned to 3.12 by `.python-version` — `uv.lock` does not target 3.13+.

## Architecture

**`AppContext` (`context.py`) is the whole application state.** One instance lives on
`app.state.ctx`, created in the `lifespan` of `create_app()`. It holds league settings, the player
pool, rankings, draft history, setup overrides, the live `DraftBoard`, and external rankings. Every
route reaches it through the `ctx(request)` helper in `api.py`. It is mutable and not thread-safe —
this is a single-instance app by design (Render runs one instance because the service has a disk).

The data flow is layered and one-directional:

```
ESPN / Google Sheet / FantasyPros / Boris Chen / Sleeper / Rotowire / nflverse
        ↓  (espn/client.py, weekly.py, sheets.py, external.py, sleeper.py, waiver_sources.py — all write JSON into data/)
   ctx.load()      reads only from disk, never the network
        ↓
   ctx.recompute() → build_rankings() (value.py) + DraftBoard.load_or_build() (draft.py)
        ↓
   pure engines: keeper.py, recommend.py, grade.py, lineup.py, recap.py, waivers.py, strategy.py, detail.py, injury.py
        ↓
   api.py routes → Pydantic models (models.py) → JSON
```

Key consequences to respect when changing things:

- **`ctx.load()` must stay offline.** Anything that fetches goes in `ctx.sync()` / `refresh_external()`
  / `sheet_sync()`. Draft day is expected to work with the network down.
- **`store.cached(path, refresh, loader, model)`** is the caching primitive: returns the disk copy
  unless `refresh`, and falls back to a stale cache if the loader raises. Writes are atomic
  (tmp file + `os.replace`).
- **`models.py` is the single schema** for the ESPN client, the engines, the API responses, *and* the
  on-disk JSON cache. Renaming a field there invalidates cached files under `data/` and breaks the
  frontend types.
- **`web/src/lib/types.ts` is a hand-written mirror of `models.py`** (snake_case, identical field
  names). There is no codegen — change both sides together.

### Draft board

`draft.py` builds the board from scratch every time setup changes: `snake_order()` →
`apply_pick_trades()` → `apply_keepers()`. Keepers consume their team's pick in the cost round; if
that pick was traded away, the next owned pick is used and a warning is recorded on
`state.warnings`. `resolve_slot_order()` picks the draft order by priority: manual full order >
ESPN's order > `my_slot` with placeholder teams (`provisional=True`).

`_apply_setup()` in `api.py` mutates setup, rebuilds the board, and *only then* saves — rebuilding
raises `ConflictError` (→ HTTP 409) once real picks exist, and nothing is persisted on that path.
`force=true` discards the recorded picks. Preserve this ordering; saving first left setup.json and
the live board disagreeing.

Pick recording is order-independent (`assign(overall, player_id)`), so falling behind during a live
draft is recoverable.

### Google Sheet sync

The league's Google Sheet is the **source of truth for draft history and keeper flags** — ESPN's
rounds and keeper flags are entered after the fact and are unreliable. `sheets.py` reads it two ways:
OAuth desktop flow when `google_credentials.json` exists (gives cell background colors), otherwise
the public CSV/gviz export (no colors, sheet must be link-viewable). One tab per season;
`history.py` rebuilds `data/sheet_draft_{year}.json` from the "Round N" rows, and those override the
ESPN-derived history in `ctx.load()`.

During a live draft `board.apply_grid()` pulls the sheet into the board. When the sheet disagrees
with something typed by hand it does **not** overwrite — it records a `SheetConflict` for the user to
resolve ("sheet" applies it, "board" remembers the rejection in `dismissed` so the next sync stops
asking). Conflicts are re-detected from scratch on every sync and persisted to
`data/sheet_conflicts.json` so they survive a mid-draft restart.

### Rankings

`value.py` computes value-over-replacement against baselines derived from the league's own roster
slots (including flex via `FLEX_MAP`), blends in ADP, and tiers by gaps. `external.py` layers
FantasyPros consensus (superflex list, since this is a 2-QB league) and Boris Chen tiers on top,
cached for a day. Everything downstream — recommendations, keeper surplus, draft grades, the
strategy guide — reads `Rankings`, so league settings genuinely change the advice.

### Dashboard (weekly lineup)

`lineup.py` computes two different things and they must not be confused. `optimal_lineup()` is the
raw optimum; `start_sit_moves()` returns the **recommended** lineup — the current one with only the
moves that survived filtering applied. `WeekView.optimal_slots` carries the latter, because the UI
tints a row by diffing it against what ESPN has. Feed it the raw optimum and rows light up with no
move to explain them: a pure slot permutation (same starters, rearranged, identical points) and a
swap below `swap_threshold` both look like changes but produce no move. Whatever is highlighted and
whatever is listed under "Recommended moves" have to come from the same place.

`recap.py` is the post-mortem for a finished week, built from `weekly.load_or_fetch_box_score()`
(both lineups with actual vs projected, cached forever once `complete`) plus `sleeper.py` — Sleeper's
public, keyless API for add/drop trends and practice reports, matched to ESPN players by `espn_id`.
`hindsight()` reuses `start_sit_moves()` with actual points as the score and a zero threshold, so
"the lineup you could have played" obeys the same slot-eligibility rules as the recommendations.
`AppContext.week_recap()` recaps exactly the week asked for and returns `available=False` with a
reason while that week is still being played — it never substitutes the previous week, so the recap
always sits with its own week in the dashboard's week selector.

### Waiver wire

`AppContext.waiver_view()` is the in-season "who to add, who to drop" page. It reads the same
`week_{season}_t{team}_*.json` as the dashboard, so the free-agent pool is built once in
`weekly._fetch_free_agents()`: one `kona_player_info` pull per position plus a "risers" pull sorted
by 7-day roster change, keeping ESPN's raw entry so `percent_change` and `waiver_status` survive
(espn_api's `Player` discards them). The two `filterStats*` keys in `_fa_filter()` matter: without
them ESPN returns only season totals and the current week, and `WeekPlayer.usage` (targets, carries,
attempts for the last three played weeks) stays empty for every free agent. Kickers are dropped at
the source; the league has no K slot.

`waiver_sources.py` follows the `weekly.py` split: `load_or_fetch_*` fetch with their own TTL and
stale fallback (FantasyPros waiver panel 6h and rest-of-season 12h, Rotowire add/drop 6h and
injuries 3h, nflverse snap counts 24h), and `apply_*` are pure joins onto `WaiverPlayer`s. Joins are
by id where a source carries one (Sleeper `espn_id`, Rotowire `playerID` via Sleeper `rotowire_id`)
and by name within position otherwise; Sleeper's `espn_id` is missing for roughly half its records
(rookies especially), which is why `sleeper_index()` exists. FantasyPros has no superflex
rest-of-season list (`ros-superflex` redirects), so QB ranks come from a 1-QB list and the engine
takes the kinder of overall and position rank for quarterbacks in a 2-QB league. Establish The Run
and PFF are paywalled and appear only as links. `sleeper.PLAYERS_VERSION` must be bumped whenever
`sleeper.KEEP` grows, or a day-old cache silently lacks the new field.

`waivers.py` never fetches. It takes the set of sources that actually loaded: a missing source is an
*absent* component (the weights renormalise), not a zero, so a FantasyPros outage does not drag
everyone down. Free agents and bench players are scored with the same `add_score()` on one 0-100
scale, which is what makes "add X, drop Y" mean something; the FantasyPros waiver panel is absent
rather than zero for rostered players for the same reason. Rest-of-season value uses the *overall*
consensus rank scaled to how many players the league rosters, because position ranks made a TE
ranked 157th overall look better than a WR ranked 117th. Defenses only ever swap for the defense
you start (`stream_candidates`), never for a skill player. A "claim" is a clear margin over a bench
player or a strong score on its own; expect mostly "watch" in a 10-team league, that is the honest
answer.

### Auth

Every `/api` route is behind `Depends(current_user)`, wired once in `create_app()`. Accounts live in
`data/users.json` with scrypt hashes; sessions are stateless signed tokens in an HttpOnly cookie
(`AUTH_SECRET`, generated into `data/auth_secret` when unset). The first person to register becomes
admin, unless `BOOTSTRAP_USERNAME`/`BOOTSTRAP_PASSWORD` claimed it at startup. Everyone else arrives
through a **team invite**: an admin names a team and an email (`POST /auth/invites`, stored in
`data/invites.json`), `mail.py` emails a one-time link (Resend when `RESEND_API_KEY` is set, SMTP otherwise), and `POST /auth/join` creates the account
with that `team_id` and spends the link. The link is assembled only inside `_email_invite()` and is
never returned by the API — admin screens address invites by `id`, not `token` — so keep it that way.
Tests swap `AuthService.send_mail` for a recorder and read the token out of the "email". Members never choose a team; `ALLOW_REGISTRATION`
still exists but produces team-less accounts an admin must link.

**One ESPN cookie serves the whole league.** `settings.my_team_id` is the *cookie owner's* team (found
by SWID) and is only a default. Each user carries a `team_id`; `AppContext.team_for(user)` resolves it
and every per-team route (`/week`, `/recap`, `/draft/*`, `/board`, `/keeper-options`, `/setup`) passes
it into the engines rather than reading `settings.my_team_id`. Per-team caches are keyed by team
(`week_{season}_t{team}_*.json`, `box_{season}_t{team}_*.json`, `roster_{year}_t{team}.json`). The
owner's keeper lives in `setup.my_keeper`; everyone else's in `setup.other_keepers` — go through
`keeper_for()` / `set_keeper_for()` rather than touching either directly. On startup `bind_owner()`
gives the first team-less admin the cookie owner's team. A non-admin with no team sees a "no team
linked" screen (`RequireTeam`); on the API side any team-less user falls back to the owner's team so
nothing 500s.

### Serving

In dev, Vite serves the UI and proxies `/api`. In a single-service deploy, `mount_web()` serves
`web/dist` from the API process — its catch-all is registered last, returns JSON 404s for unknown
`/api/*` paths, and otherwise falls through to `index.html` for React Router. On Render the two are
split (static site + API) with a rewrite so the session cookie stays first-party.

### Frontend

React 19 + React Router, TanStack Query, shadcn/ui on Tailwind 4.

`App.tsx` holds the whole route table. The top-level nav is deliberately only **Dashboard** (the
season-long weekly lineup), **Waiver Wire** (`/waivers`, the in-season add/drop page) and a
**Draft Tools** dropdown; the draft-day tools are routes under
`/draft` (Live Draft), `/draft/board` and `/draft/keepers`, reached from that menu (`DRAFT_TOOLS` in
`AppShell.tsx`) rather than from a second row of tabs. The pre-move paths `/board` and `/keeper`
redirect, so old bookmarks keep working. `LiveDraft` sizes its panes against the viewport by
subtracting the header and main's padding — adjust that calc if the header chrome changes height.

Theme is class-based (`.dark` on `<html>`, `@custom-variant dark` in `index.css`). `lib/theme.ts`
owns the state and an inline boot script in `index.html` applies the stored choice before React
mounts; the `ffdraft-theme` localStorage key is shared between the two, so change both together.

All server access goes through `lib/api.ts` (which dispatches `ffdraft:unauthorized` on a 401 so
`AuthProvider` can bounce to `/login`) and `lib/queries.ts` (query keys, mutations, toasts). Add new
endpoints there rather than calling `fetch` from components. `@/` aliases `web/src`.

## Privacy

The repo is public; `data/`, `.env`, `data/seed/*`, `*.pdf` and `google_credentials.json` are
git-ignored because they contain real league members' names and ESPN credentials. Do not commit
fixtures, examples, or test data derived from real league files — `server/tests/conftest.py` builds a
synthetic league ("Owner1".."Owner10") for exactly this reason.
