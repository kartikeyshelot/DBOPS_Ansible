"""
CSV Export endpoints — one per dashboard tab.
"""

import csv
import io
import logging
import pandas as pd
from typing import Optional
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from database import get_db, get_latest_fetch_id
from utils import (
    load_servers_df, dedup_servers_df, apply_filters_df,
    get_filtered_server_names, scoped_query, safe_float,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _stream_csv(rows: list[dict], filename: str) -> StreamingResponse:
    output = io.StringIO()
    if not rows:
        output.write("no_data\n")
    else:
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _load_events_df(session, fetch_id: int, names=None) -> pd.DataFrame:
    rows = scoped_query(session, "SELECT * FROM events WHERE fetch_id = :fetch_id", fetch_id, names)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([dict(r) for r in rows])
    df["Date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


@router.get("/export/servers")
def export_servers(
    search: Optional[str] = None, priority: Optional[str] = None,
    environment: Optional[str] = None, app_code: Optional[str] = None,
    criticality: Optional[str] = None,
):
    with get_db() as session:
        fetch_id = get_latest_fetch_id(session)
        if not fetch_id:
            return _stream_csv([], "overview_servers.csv")
        df = load_servers_df(session, fetch_id)
        if df.empty:
            return _stream_csv([], "overview_servers.csv")
        df = apply_filters_df(df, search, priority, environment, app_code, criticality)
        df = dedup_servers_df(df)

        triage_rows = session.execute(
            text("SELECT server_name, status, notes FROM triage_status")
        ).mappings().fetchall()
        triage_map = {r["server_name"]: r["status"] for r in triage_rows}
        notes_map  = {r["server_name"]: r["notes"]  for r in triage_rows}

    rows = []
    for rec in df.to_dict(orient="records"):
        name = str(rec.get("Server Name", "") or "")
        rows.append({
            "server_name": name,
            "priority": str(rec.get("Priority", "NONE") or "NONE"),
            "risk_category": str(rec.get("Risk_Category", "Healthy") or "Healthy"),
            "action": str(rec.get("Action", "Monitor") or "Monitor"),
            "current_load_pct": safe_float(rec.get("Current_Load", 0)),
            "days_left": int(safe_float(rec.get("Days_Left", 999), 999)),
            "total_alerts": int(safe_float(rec.get("Total_Alerts", 0))),
            "cpu_vcpus": int(safe_float(rec.get("CPU_Count", 0))),
            "ram_gb": safe_float(rec.get("RAM_GB", 0)),
            "max_disk_util_pct": safe_float(rec.get("Max_Disk_Util", 0)),
            "min_free_gb": safe_float(rec.get("Min_Free_GB", 999), 999.0),
            "max_db_growth_gb": safe_float(rec.get("Max_DB_Growth", 0)),
            "environment": str(rec.get("Environment", "Unknown") or "Unknown"),
            "criticality": str(rec.get("PAASDB_CRTICALITY", "Unknown") or "Unknown"),
            "triage_status": triage_map.get(name, "Open"),
            "triage_notes": notes_map.get(name, "") or "",
            "diagnostic": str(rec.get("Diagnostic", "") or ""),
        })
    return _stream_csv(rows, "overview_servers.csv")


@router.get("/export/databases")
def export_databases(
    search: Optional[str] = None, priority: Optional[str] = None,
    environment: Optional[str] = None, app_code: Optional[str] = None,
):
    with get_db() as session:
        fetch_id = get_latest_fetch_id(session)
        if not fetch_id:
            return _stream_csv([], "capacity_databases.csv")
        names = get_filtered_server_names(session, fetch_id, search, priority, environment, app_code)
        db_rows = scoped_query(session,
            "SELECT server_name, db_name, db_type, raw_size, raw_growth, suggestion "
            "FROM databases WHERE fetch_id = :fetch_id",
            fetch_id, names)

    rows = []
    for r in db_rows:
        d = dict(r)
        raw_size   = safe_float(d.get("raw_size"),   0)
        raw_growth = safe_float(d.get("raw_growth"), 0)
        rows.append({
            "server_name": str(d.get("server_name", "")),
            "db_name": str(d.get("db_name", "")),
            "db_type": str(d.get("db_type", "")),
            "size_gb": round(raw_size / (1024 ** 3), 3),
            "growth_mb_per_day": round(raw_growth / (1024 ** 2), 3),
            "suggestion": str(d.get("suggestion", "Stable")),
        })
    return _stream_csv(rows, "capacity_databases.csv")


@router.get("/export/runway")
def export_runway(
    search: Optional[str] = None, priority: Optional[str] = None,
    environment: Optional[str] = None, app_code: Optional[str] = None,
):
    with get_db() as session:
        fetch_id = get_latest_fetch_id(session)
        if not fetch_id:
            return _stream_csv([], "capacity_runway.csv")
        names = get_filtered_server_names(session, fetch_id, search, priority, environment, app_code)

        params = {"fid": fetch_id}
        sql = (
            "SELECT name, resource_type, current_load, days_left, priority, "
            "max_disk_util, min_free_gb, max_db_growth "
            "FROM servers WHERE fetch_id = :fid"
        )
        if names is not None:
            if not names:
                return _stream_csv([], "capacity_runway.csv")
            sql += " AND name = ANY(:names)"
            params["names"] = names
        sql += " ORDER BY days_left ASC"
        raw = session.execute(text(sql), params).mappings().fetchall()

    rows = []
    for r in raw:
        d = dict(r)
        rows.append({
            "server_name": str(d.get("name", "")),
            "resource_type": str(d.get("resource_type", "")),
            "current_load_pct": safe_float(d.get("current_load", 0)),
            "days_left": int(safe_float(d.get("days_left", 999), 999)),
            "priority": str(d.get("priority", "NONE") or "NONE"),
            "max_disk_util_pct": safe_float(d.get("max_disk_util", 0)),
            "min_free_gb": safe_float(d.get("min_free_gb", 999), 999.0),
            "max_db_growth_gb": safe_float(d.get("max_db_growth", 0)),
        })
    return _stream_csv(rows, "capacity_runway.csv")


@router.get("/export/events")
def export_events(
    search: Optional[str] = None, priority: Optional[str] = None,
    environment: Optional[str] = None, app_code: Optional[str] = None,
):
    with get_db() as session:
        fetch_id = get_latest_fetch_id(session)
        if not fetch_id:
            return _stream_csv([], "analytics_events.csv")
        names = get_filtered_server_names(session, fetch_id, search, priority, environment, app_code)
        event_rows = scoped_query(session,
            "SELECT date, server_name, problem_name, severity FROM events WHERE fetch_id = :fetch_id",
            fetch_id, names)
    return _stream_csv([dict(r) for r in event_rows], "analytics_events.csv")


@router.get("/export/top-alerters")
def export_top_alerters():
    from services.advanced_analytics import compute_top_alerters
    with get_db() as session:
        fetch_id = get_latest_fetch_id(session)
        if not fetch_id:
            return _stream_csv([], "analytics_top_alerters.csv")
        df = _load_events_df(session, fetch_id)
    data = compute_top_alerters(df, n=100)
    all_sevs = sorted({sev for s in data for sev in s.get("by_severity", {})})
    rows = []
    for s in data:
        row = {"server_name": s["server_name"], "total_alerts": s["total"]}
        for sev in all_sevs:
            row[f"sev_{sev.lower().replace(' ', '_')}"] = s.get("by_severity", {}).get(sev, 0)
        rows.append(row)
    return _stream_csv(rows, "analytics_top_alerters.csv")


@router.get("/export/stability")
def export_stability():
    from services.advanced_analytics import compute_stability_scores
    with get_db() as session:
        fetch_id = get_latest_fetch_id(session)
        if not fetch_id:
            return _stream_csv([], "analytics_stability.csv")
        cap_rows = session.execute(
            text("SELECT server_name, metric, date, utilization FROM capacity_trends WHERE fetch_id = :fid"),
            {"fid": fetch_id},
        ).mappings().fetchall()
    if not cap_rows:
        return _stream_csv([], "analytics_stability.csv")
    cap_df = pd.DataFrame([dict(r) for r in cap_rows])
    cap_df = cap_df.rename(columns={
        "server_name": "Server Name", "metric": "Metric",
        "date": "Date", "utilization": "Utilization",
    })
    cap_df["Date"]        = pd.to_datetime(cap_df["Date"], errors="coerce")
    cap_df["Utilization"] = pd.to_numeric(cap_df["Utilization"], errors="coerce")
    data = compute_stability_scores(cap_df)
    return _stream_csv(data, "analytics_stability.csv")
