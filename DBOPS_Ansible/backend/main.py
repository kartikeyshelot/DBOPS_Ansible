"""
DB Infrastructure OPS — FastAPI Backend
Entry point: gunicorn main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8090
"""

import json
import math
import datetime as _dt
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from config import settings
from database import init_db, dispose_engine
from routers import fetch, servers, forecasts, incidents, disks, databases, analytics_routes, export


class NaNSafeEncoder(json.JSONEncoder):
    """JSON encoder that converts NaN/Inf to null, handles numpy types and datetimes."""
    def default(self, obj):
        if isinstance(obj, _dt.datetime):
            return obj.isoformat()
        if isinstance(obj, _dt.date):
            return obj.isoformat()
        if isinstance(obj, _dt.time):
            return obj.isoformat()
        try:
            import numpy as np
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                v = float(obj)
                return None if math.isnan(v) or math.isinf(v) else v
            if isinstance(obj, np.ndarray):
                return obj.tolist()
        except ImportError:
            pass
        return super().default(obj)

    def encode(self, o):
        return super().encode(self._sanitize(o))

    def _sanitize(self, obj):
        if isinstance(obj, _dt.datetime):
            return obj.isoformat()
        if isinstance(obj, _dt.date):
            return obj.isoformat()
        if isinstance(obj, float):
            if math.isnan(obj) or math.isinf(obj):
                return None
        elif isinstance(obj, dict):
            return {k: self._sanitize(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._sanitize(v) for v in obj]
        return obj


class NaNSafeJSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(
            content,
            cls=NaNSafeEncoder,
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    init_db()

    if STATIC_DIR.exists():
        logger.info("Frontend: serving pre-built UI from %s", STATIC_DIR)
    else:
        logger.warning(
            "Frontend: static/ directory not found. "
            "API still works at /api/* and /docs, but no UI will be served."
        )

    logger.info("DB Infrastructure OPS backend ready.")
    logger.info("Open http://localhost:8090 in your browser.")
    yield
    logger.info("Shutting down — disposing database engine...")
    dispose_engine()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="DB Infrastructure OPS",
    description="Database infrastructure monitoring and capacity planning API",
    version="1.0.0",
    lifespan=lifespan,
    default_response_class=NaNSafeJSONResponse,
)

# ── CORS — configurable origins from settings ────────────────────────────────
cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API routes ────────────────────────────────────────────────────────────────
app.include_router(fetch.router, prefix="/api", tags=["Fetch"])
app.include_router(servers.router, prefix="/api", tags=["Servers"])
app.include_router(forecasts.router, prefix="/api", tags=["Forecasts"])
app.include_router(incidents.router, prefix="/api", tags=["Incidents"])
app.include_router(disks.router, prefix="/api", tags=["Disks"])
app.include_router(databases.router, prefix="/api", tags=["Databases"])
app.include_router(analytics_routes.router, prefix="/api", tags=["Advanced Analytics"])
app.include_router(export.router, prefix="/api", tags=["Export"])


@app.get("/api/ping")
def ping():
    return {"status": "ok"}


# ── Serve pre-built frontend ─────────────────────────────────────────────────
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        file_path = STATIC_DIR / full_path
        if full_path and file_path.resolve().is_relative_to(STATIC_DIR.resolve()) and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(STATIC_DIR / "index.html")
else:
    @app.get("/")
    def root():
        return {
            "app": "DB Infrastructure OPS",
            "docs": "/docs",
            "note": "No frontend found. Place pre-built files in backend/static/ or use /docs for the API.",
            "status": "running"
        }
