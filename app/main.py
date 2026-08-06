"""FastAPI entrypoint for FitPath (multi-user)."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .auth import router as auth_router
from .db import SessionLocal, init_db
from .routes import (
    admin,
    ai,
    apple_health,
    exercises,
    insights,
    logs,
    nutrition,
    performance,
    profile,
    programs,
    recommendations,
    workouts,
)
from .seed_exercises import seed_exercises
from .security import CSRFMiddleware

BASE_DIR = Path(__file__).resolve().parent.parent
# Single-origin production serving: the compiled Vite SPA in ``frontend/dist``
# (built with `npm run build`). Served by the SPA routes at the bottom of this
# module. This replaces the old hand-written ``static/`` vanilla app.
FRONTEND_DIR = (BASE_DIR / "frontend" / "dist").resolve()
FRONTEND_ASSETS = FRONTEND_DIR / "assets"
FRONTEND_INDEX = FRONTEND_DIR / "index.html"
FRONTEND_SW = FRONTEND_DIR / "sw.js"

NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}

# Vite dev server origins (frontend track). allow_credentials requires explicit
# origins (no "*") so the session/CSRF cookies flow cross-origin in dev.
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with SessionLocal() as session:
        seed_exercises(session)
    yield


app = FastAPI(title="FitPath", version="1.0.0", lifespan=lifespan)

# Middleware: the last one added is the outermost. Add CSRF first (inner) and
# CORS last (outer) so CORS headers are attached even to a 403 from the CSRF
# check.
app.add_middleware(CSRFMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(profile.router)
app.include_router(logs.router)
app.include_router(insights.router)
app.include_router(exercises.router)
app.include_router(workouts.router)
app.include_router(performance.router)
app.include_router(programs.router)
app.include_router(nutrition.router)
app.include_router(recommendations.router)
app.include_router(admin.router)
app.include_router(ai.router)
app.include_router(apple_health.router)


@app.get("/api/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}


# --- Single-origin SPA serving (React build from ``frontend/dist``) ---------
# Hashed JS/CSS bundles are served under ``/assets``; every other non-API,
# non-file path falls back to ``index.html`` so client-side routes (e.g.
# ``/login``, ``/insights``) resolve on a hard refresh. Registered LAST so the
# ``/api/*`` routers and ``/api/health`` always win.
if FRONTEND_ASSETS.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_ASSETS), name="assets")


@app.get("/sw.js", include_in_schema=False)
def retired_service_worker() -> FileResponse:
    """Retire the offline worker shipped by the old vanilla/PWA frontend."""
    if FRONTEND_SW.is_file():
        return FileResponse(
            FRONTEND_SW,
            media_type="application/javascript",
            headers={
                **NO_CACHE_HEADERS,
                "Service-Worker-Allowed": "/",
            },
        )
    raise HTTPException(
        status_code=404,
        detail="frontend build missing — run `npm run build` in frontend/",
    )


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str) -> FileResponse:
    # Never let the SPA fallback shadow the API surface: an unknown ``/api/*``
    # path must stay a JSON 404, not the HTML shell.
    if full_path == "api" or full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="not found")

    # Serve real build files (favicon.svg, icons.svg, ...) when present, guarding
    # against path traversal outside the build directory.
    if full_path:
        candidate = (FRONTEND_DIR / full_path).resolve()
        if candidate.is_file() and FRONTEND_DIR in candidate.parents:
            return FileResponse(candidate)

    # SPA entrypoint (client-side routing handles the rest).
    if FRONTEND_INDEX.is_file():
        return FileResponse(FRONTEND_INDEX, headers=NO_CACHE_HEADERS)
    raise HTTPException(
        status_code=404,
        detail="frontend build missing — run `npm run build` in frontend/",
    )
