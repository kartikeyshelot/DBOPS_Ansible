"""
PostgreSQL database layer via SQLAlchemy.
Replaces the original SQLite-based persistence.

Public API (unchanged signatures for all callers):
    init_db()                         — create tables on startup
    get_db()                          — context manager yielding a Session
    get_latest_fetch_id(session)      — most recent completed fetch run ID
    is_fetch_running(session)         — True if a fetch is in progress
    cleanup_old_runs(session, keep)   — prune old fetch data
    get_fetch_info(session, fetch_id) — single fetch run record
"""

import logging
from typing import Optional
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from config import settings

logger = logging.getLogger(__name__)

# ── Engine & session factory ──────────────────────────────────────────────────

engine = create_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_pool_max_overflow,
    pool_pre_ping=True,
    pool_recycle=settings.db_pool_recycle,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

# ── Schema — PostgreSQL DDL ───────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS fetch_runs (
    id SERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    last_heartbeat_at TIMESTAMPTZ,
    server_count INTEGER DEFAULT 0,
    zabbix_url TEXT,
    zabbix_group TEXT,
    days_back INTEGER,
    status TEXT DEFAULT 'running',
    progress TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS servers (
    id SERIAL PRIMARY KEY,
    fetch_id INTEGER NOT NULL REFERENCES fetch_runs(id),
    name TEXT NOT NULL,
    resource_type TEXT,
    current_load DOUBLE PRECISION DEFAULT 0,
    days_left INTEGER DEFAULT 999,
    total_alerts INTEGER DEFAULT 0,
    priority TEXT DEFAULT 'NONE',
    risk_category TEXT DEFAULT 'Healthy',
    action TEXT DEFAULT 'Monitor',
    cpu_count INTEGER DEFAULT 0,
    ram_gb DOUBLE PRECISION DEFAULT 0,
    max_disk_util DOUBLE PRECISION DEFAULT 0,
    min_free_gb DOUBLE PRECISION DEFAULT 999,
    max_db_growth DOUBLE PRECISION DEFAULT 0,
    environment TEXT DEFAULT 'Unknown',
    criticality TEXT DEFAULT 'Unknown',
    tags TEXT DEFAULT '[]',
    diagnostic TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS triage_status (
    server_name TEXT PRIMARY KEY,
    status TEXT DEFAULT 'Open',
    notes TEXT DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    fetch_id INTEGER NOT NULL REFERENCES fetch_runs(id),
    date TEXT NOT NULL,
    server_name TEXT NOT NULL,
    problem_name TEXT,
    severity TEXT
);

CREATE TABLE IF NOT EXISTS disks (
    id SERIAL PRIMARY KEY,
    fetch_id INTEGER NOT NULL REFERENCES fetch_runs(id),
    server_name TEXT NOT NULL,
    drive TEXT,
    type TEXT,
    total_gb DOUBLE PRECISION DEFAULT 0,
    used_gb DOUBLE PRECISION DEFAULT 0,
    free_gb DOUBLE PRECISION DEFAULT 0,
    utilization_pct DOUBLE PRECISION DEFAULT 0,
    risk_category TEXT,
    action_required TEXT
);

CREATE TABLE IF NOT EXISTS databases (
    id SERIAL PRIMARY KEY,
    fetch_id INTEGER NOT NULL REFERENCES fetch_runs(id),
    server_name TEXT NOT NULL,
    db_name TEXT,
    db_type TEXT,
    raw_size DOUBLE PRECISION DEFAULT 0,
    raw_growth DOUBLE PRECISION DEFAULT 0,
    suggestion TEXT DEFAULT 'Stable',
    trend TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS capacity_trends (
    id SERIAL PRIMARY KEY,
    fetch_id INTEGER NOT NULL REFERENCES fetch_runs(id),
    date TEXT NOT NULL,
    server_name TEXT NOT NULL,
    metric TEXT,
    utilization DOUBLE PRECISION DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_servers_fetch ON servers(fetch_id);
CREATE INDEX IF NOT EXISTS idx_servers_name ON servers(name);
CREATE INDEX IF NOT EXISTS idx_servers_priority ON servers(priority);
CREATE INDEX IF NOT EXISTS idx_events_fetch ON events(fetch_id);
CREATE INDEX IF NOT EXISTS idx_events_server ON events(server_name);
CREATE INDEX IF NOT EXISTS idx_events_fetch_server ON events(fetch_id, server_name);
CREATE INDEX IF NOT EXISTS idx_disks_fetch ON disks(fetch_id);
CREATE INDEX IF NOT EXISTS idx_disks_fetch_server ON disks(fetch_id, server_name);
CREATE INDEX IF NOT EXISTS idx_databases_fetch ON databases(fetch_id);
CREATE INDEX IF NOT EXISTS idx_databases_fetch_server ON databases(fetch_id, server_name);
CREATE INDEX IF NOT EXISTS idx_capacity_fetch ON capacity_trends(fetch_id);
CREATE INDEX IF NOT EXISTS idx_capacity_fetch_server ON capacity_trends(fetch_id, server_name);
"""

# How many completed fetch runs to keep (older ones are deleted to prevent DB bloat)
KEEP_RUNS = 3


@contextmanager
def get_db():
    """Yield a SQLAlchemy Session. Auto-commits on clean exit, rolls back on error."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    """Create tables and indexes. Safe to call repeatedly (IF NOT EXISTS)."""
    with engine.connect() as conn:
        for statement in SCHEMA_SQL.strip().split(";"):
            stmt = statement.strip()
            if stmt:
                conn.execute(text(stmt))
        conn.commit()
    logger.info("Database initialised at %s", settings.database_url.split("@")[-1])


def get_latest_fetch_id(session: Session) -> Optional[int]:
    """Return the most recent *completed* fetch run ID, or None."""
    row = session.execute(
        text("SELECT id FROM fetch_runs WHERE status = 'completed' ORDER BY id DESC LIMIT 1")
    ).mappings().fetchone()
    return row["id"] if row else None


def get_fetch_info(session: Session, fetch_id: int) -> Optional[dict]:
    row = session.execute(
        text("SELECT * FROM fetch_runs WHERE id = :fid"),
        {"fid": fetch_id},
    ).mappings().fetchone()
    return dict(row) if row else None


def is_fetch_running(session: Session) -> bool:
    """
    True if a fetch is currently in progress.
    Auto-expires runs stuck in 'running' beyond fetch_stale_timeout_seconds.
    Compares against last_heartbeat_at (or started_at if no heartbeat yet).
    Uses SELECT ... FOR UPDATE to prevent cross-worker race conditions.
    """
    row = session.execute(
        text(
            "SELECT id, started_at, last_heartbeat_at FROM fetch_runs "
            "WHERE status = 'running' ORDER BY id DESC LIMIT 1 "
            "FOR UPDATE"
        )
    ).mappings().fetchone()
    if row is None:
        return False

    try:
        import datetime
        # Use the most recent heartbeat; fall back to started_at if none yet
        last_seen = row["last_heartbeat_at"] or row["started_at"]
        if isinstance(last_seen, str):
            last_seen = datetime.datetime.fromisoformat(last_seen)
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=datetime.timezone.utc)
        now = datetime.datetime.now(datetime.timezone.utc)
        if (now - last_seen).total_seconds() > settings.fetch_stale_timeout_seconds:
            session.execute(
                text(
                    "UPDATE fetch_runs SET status = :status, completed_at = :now "
                    "WHERE id = :fid"
                ),
                {
                    "status": f"failed: timed out (no heartbeat for {settings.fetch_stale_timeout_seconds // 60}m)",
                    "now": now.isoformat(),
                    "fid": row["id"],
                },
            )
            logger.warning(
                "Fetch run %d was stuck in 'running' since %s (last heartbeat: %s) — auto-marked as failed",
                row["id"], row["started_at"], row["last_heartbeat_at"],
            )
            return False
    except (ValueError, TypeError):
        pass

    return True


def heartbeat_fetch_run(session: Session, fetch_id: int, progress: str = ""):
    """
    Touch last_heartbeat_at to prevent stale detection from expiring
    a still-running fetch.  Optionally stores a progress message that the
    frontend can display (e.g. '40%: Loading capacity trends').
    started_at is never modified — it always reflects the true start time.
    """
    import datetime
    session.execute(
        text(
            "UPDATE fetch_runs SET last_heartbeat_at = :now, progress = :prog WHERE id = :fid"
        ),
        {
            "now": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "prog": progress[:500] if progress else "",
            "fid": fetch_id,
        },
    )


def cleanup_old_runs(session: Session, keep: int = KEEP_RUNS):
    """
    Delete data from fetch runs older than the last `keep` completed runs.
    Prevents unbounded database growth on deployments that fetch daily.
    """
    rows = session.execute(
        text("SELECT id FROM fetch_runs WHERE status = 'completed' ORDER BY id DESC")
    ).mappings().fetchall()

    if len(rows) <= keep:
        return

    ids_to_delete = [r["id"] for r in rows[keep:]]

    for table in ("servers", "events", "disks", "databases", "capacity_trends"):
        session.execute(
            text(f"DELETE FROM {table} WHERE fetch_id = ANY(:ids)"),
            {"ids": ids_to_delete},
        )
    session.execute(
        text("DELETE FROM fetch_runs WHERE id = ANY(:ids)"),
        {"ids": ids_to_delete},
    )
    logger.info(
        "Cleaned up %d old fetch run(s): ids %s", len(ids_to_delete), ids_to_delete
    )


def dispose_engine():
    """Clean shutdown — close all pooled connections."""
    engine.dispose()
    logger.info("Database engine disposed.")
