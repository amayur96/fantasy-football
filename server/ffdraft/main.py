"""uvicorn ffdraft.main:app --app-dir server"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .auth import AuthService
from .auth_api import current_user
from .auth_api import router as auth_router
from .config import ROOT
from .context import AppContext

log = logging.getLogger(__name__)
WEB_DIST = ROOT / "web" / "dist"


def mount_web(app: FastAPI, dist: Path = WEB_DIST) -> None:
    """Serve the built React app from the API process (production single-service deploys).

    Skipped when web/dist is absent, which is the case in dev — Vite serves the UI there.
    """
    index = dist / "index.html"
    if not index.exists():
        return
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    root = dist.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        # Registered last, so it only sees paths no API route claimed. Unknown /api paths
        # must still 404 as JSON rather than quietly returning the HTML shell.
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (root / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(index)  # client-side route: let React Router handle it


def create_app(ctx: AppContext | None = None, web_dist: Path = WEB_DIST) -> FastAPI:
    # uvicorn configures only its own loggers, so without this our startup messages
    # (the bootstrap admin, a failed initial load) never reach the deploy log.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.ctx = ctx or AppContext()
        app.state.auth = AuthService(app.state.ctx.cfg)
        created = app.state.auth.bootstrap()
        if created:
            log.info("Created bootstrap admin account %r", created)
        try:
            app.state.ctx.load()
        except Exception as exc:  # noqa: BLE001
            log.warning("Initial load failed: %s", exc)
        yield

    app = FastAPI(title="ffdraft", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_router)
    # Every league route requires a signed-in user.
    app.include_router(router, dependencies=[Depends(current_user)])

    @app.exception_handler(LookupError)
    async def _lookup(_: Request, exc: LookupError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def _value(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, bool]:
        return {"ok": True}

    mount_web(app, web_dist)
    return app


app = create_app()
