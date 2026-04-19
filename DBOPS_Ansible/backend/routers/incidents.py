"""
GET/PATCH /api/triage — Triage status management.
GET /api/drilldown/{server_name} — Drill-down data for a specific server.
"""

import datetime
import logging
from fastapi import APIRouter
from sqlalchemy import text
from database import get_db, get_latest_fetch_id
from models.schemas import TriageUpdateRequest

logger = logging.getLogger(__name__)
router = APIRouter()


@router.patch("/triage/{server_name}")
def update_triage_status(server_name: str, req: TriageUpdateRequest):
    """Update triage status (and optional notes) for a server."""
    with get_db() as session:
        existing_notes = ""
        try:
            existing = session.execute(
                text("SELECT notes FROM triage_status WHERE server_name = :name"),
                {"name": server_name},
            ).mappings().fetchone()
            existing_notes = (existing["notes"] if existing else "") or ""
        except Exception:
            pass

        notes_to_save = req.notes if req.notes is not None else existing_notes

        session.execute(
            text(
                "INSERT INTO triage_status (server_name, status, notes, updated_at) "
                "VALUES (:name, :status, :notes, :now) "
                "ON CONFLICT (server_name) DO UPDATE SET "
                "status = EXCLUDED.status, notes = EXCLUDED.notes, updated_at = EXCLUDED.updated_at"
            ),
            {
                "name": server_name,
                "status": req.status.value,
                "notes": notes_to_save,
                "now": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            },
        )
    return {"server_name": server_name, "status": req.status.value, "notes": notes_to_save}


@router.get("/triage")
def get_all_triage_status():
    """Get all triage statuses with timestamps and notes."""
    with get_db() as session:
        rows = session.execute(
            text("SELECT * FROM triage_status")
        ).mappings().fetchall()
        return {
            r["server_name"]: {
                "status": r["status"],
                "notes": r["notes"] if r["notes"] else "",
                "updated_at": r["updated_at"],
            }
            for r in rows
        }


@router.get("/drilldown/{server_name}")
def get_server_drilldown(server_name: str):
    """Combined drill-down data for a server."""
    with get_db() as session:
        fetch_id = get_latest_fetch_id(session)
        if not fetch_id:
            return {"server_info": {}, "recent_events": [], "disks": []}

        server_row = session.execute(
            text("SELECT * FROM servers WHERE fetch_id = :fid AND name = :name LIMIT 1"),
            {"fid": fetch_id, "name": server_name},
        ).mappings().fetchone()

        server_info = {}
        if server_row:
            srv = dict(server_row)
            server_info = {
                "name": srv.get("name", ""),
                "resource_type": srv.get("resource_type", ""),
                "current_load": srv.get("current_load", 0) or 0,
                "days_left": srv.get("days_left", 999) or 999,
                "total_alerts": srv.get("total_alerts", 0) or 0,
                "priority": srv.get("priority", "NONE") or "NONE",
                "risk_category": srv.get("risk_category", "Healthy") or "Healthy",
                "action": srv.get("action", "Monitor") or "Monitor",
                "cpu_count": srv.get("cpu_count", 0) or 0,
                "ram_gb": srv.get("ram_gb", 0) or 0,
                "max_disk_util": srv.get("max_disk_util", 0) or 0,
                "min_free_gb": srv.get("min_free_gb", 999) or 999,
                "max_db_growth": srv.get("max_db_growth", 0) or 0,
                "environment": srv.get("environment", "Unknown") or "Unknown",
                "criticality": srv.get("criticality", "Unknown") or "Unknown",
                "diagnostic": str(srv.get("diagnostic") or ""),
            }

        problem_rows = session.execute(
            text(
                "SELECT date, problem_name, severity FROM events "
                "WHERE fetch_id = :fid AND server_name = :name "
                "ORDER BY date DESC"
            ),
            {"fid": fetch_id, "name": server_name},
        ).mappings().fetchall()

        disk_rows = session.execute(
            text(
                "SELECT drive, type, total_gb, used_gb, free_gb, utilization_pct, "
                "risk_category, action_required "
                "FROM disks WHERE fetch_id = :fid AND server_name = :name"
            ),
            {"fid": fetch_id, "name": server_name},
        ).mappings().fetchall()

        cap_rows = session.execute(
            text(
                "SELECT date, utilization FROM capacity_trends "
                "WHERE fetch_id = :fid AND server_name = :name "
                "ORDER BY date ASC"
            ),
            {"fid": fetch_id, "name": server_name},
        ).mappings().fetchall()

        forecast = None
        if cap_rows and len(cap_rows) >= 2:
            dates = [r["date"] for r in cap_rows]
            values = [float(r["utilization"] or 0) for r in cap_rows]
            forecast = {"dates": dates, "values": values}

        return {
            "server_name": server_name,
            "server_info": server_info,
            "recent_events": [dict(r) for r in problem_rows],
            "forecast": forecast,
            "disks": [dict(r) for r in disk_rows],
        }
