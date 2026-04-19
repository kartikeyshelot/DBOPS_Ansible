"""
POST /api/fetch  — Trigger a Zabbix data refresh (non-blocking).
GET  /api/fetch/status  — Poll the latest fetch run status.
GET  /api/fetch/history — Recent fetch run history.
"""

import datetime
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlalchemy import text

from models.schemas import FetchRequest, FetchStatusResponse
from services.zabbix_client import ZabbixClient, ZabbixAPIError
from services.analytics import process_data
from services.anomaly import detect_anomalies
from services.persistence import (
    create_fetch_run, complete_fetch_run, fail_fetch_run,
    save_servers, save_events, save_disks, save_databases, save_capacity_trends,
)
from database import get_db, is_fetch_running, cleanup_old_runs, heartbeat_fetch_run

logger = logging.getLogger(__name__)
router = APIRouter()


def _safe_fail(fetch_id: int, error_msg: str):
    """Mark a fetch as failed. If even this DB write fails, log critically."""
    try:
        with get_db() as session:
            fail_fetch_run(session, fetch_id, error_msg)
    except Exception as inner_e:
        logger.critical(
            "Fetch %d: cannot write failure status to DB: %s (original error: %s)",
            fetch_id, inner_e, error_msg,
        )


def _run_fetch(fetch_id: int, req: FetchRequest):
    """Fetch work — runs in a daemon thread."""

    def on_progress(pct: int, msg: str):
        """Write progress to DB + heartbeat to prevent stale detection."""
        try:
            with get_db() as session:
                heartbeat_fetch_run(session, fetch_id, f"{pct}%: {msg}")
        except Exception:
            pass  # best-effort — don't crash the fetch over a progress write

    try:
        on_progress(5, "Connecting to Zabbix...")
        client = ZabbixClient(req.zabbix_url, req.zabbix_token)
        data = client.fetch_all(req.zabbix_group, req.days_back,
                                progress_callback=on_progress)

        on_progress(88, "Processing and correlating data...")
        cap_df, summary_df = process_data(
            data["cap_df"], data["problems_df"], data["host_tags"],
            data["disk_df"], data["db_df"], data["hw_df"],
        )

        if summary_df is None or summary_df.empty:
            _safe_fail(fetch_id, "No processable data returned from Zabbix")
            return

        on_progress(92, "Running anomaly detection...")
        summary_df = detect_anomalies(summary_df)

        on_progress(95, "Saving to database...")
        with get_db() as session:
            save_servers(session, fetch_id, summary_df)
            save_events(session, fetch_id, data["events_df"])
            save_disks(session, fetch_id, data["disk_df"])
            save_databases(session, fetch_id, data["db_df"])
            save_capacity_trends(session, fetch_id, data["cap_df"])
            complete_fetch_run(session, fetch_id, len(summary_df))

        on_progress(100, "Complete")

        with get_db() as session:
            cleanup_old_runs(session)

        logger.info("Fetch %d completed: %d servers", fetch_id, len(summary_df))

    except ZabbixAPIError as e:
        logger.error("Fetch %d Zabbix error: %s", fetch_id, e)
        _safe_fail(fetch_id, f"Zabbix API error: {e}")
    except Exception as e:
        logger.exception("Fetch %d failed unexpectedly", fetch_id)
        _safe_fail(fetch_id, str(e))


@router.post("/fetch", response_model=FetchStatusResponse, status_code=202)
def trigger_fetch(req: FetchRequest, background_tasks: BackgroundTasks):
    with get_db() as session:
        if is_fetch_running(session):
            raise HTTPException(
                status_code=409,
                detail="A fetch is already in progress. Poll /api/fetch/status for updates.",
            )
        fetch_id = create_fetch_run(session, req.zabbix_url, req.zabbix_group, req.days_back)

    background_tasks.add_task(_run_fetch, fetch_id, req)

    return FetchStatusResponse(
        fetch_id=fetch_id,
        status="running",
        started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        server_count=0,
    )


@router.get("/fetch/status")
def get_fetch_status():
    with get_db() as session:
        row = session.execute(
            text("SELECT * FROM fetch_runs ORDER BY id DESC LIMIT 1")
        ).mappings().fetchone()
        if not row:
            return {"status": "no_data", "message": "No fetch has been run yet"}
        return dict(row)


@router.get("/fetch/history")
def get_fetch_history(limit: int = 10):
    limit = min(limit, 100)
    with get_db() as session:
        rows = session.execute(
            text("SELECT * FROM fetch_runs ORDER BY id DESC LIMIT :lim"),
            {"lim": limit},
        ).mappings().fetchall()
        return [dict(r) for r in rows]
