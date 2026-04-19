"""
GET /api/servers          — Server summary with filtering.
GET /api/servers/filters  — Available filter values for dropdowns.
GET /api/health           — Fleet health KPIs.
GET /api/needs-attention  — Servers with monitoring gaps or compound risk.
GET /api/profiles         — Workload profiles.
GET /api/right-sizing     — Right-sizing recommendations.
GET /api/rising-problems  — Week-over-week problem trends.
GET /api/severity-trend   — Severity counts by day.
GET /api/recurring-issues — Same server+problem 2+ times.
GET /api/risk-matrix      — Risk by environment x priority.
"""

import datetime
import logging
from typing import Optional

import pandas as pd
from fastapi import APIRouter
from sqlalchemy import text

from database import get_db, get_latest_fetch_id
from utils import safe_float, safe_int, deep_sanitize, load_servers_df, dedup_servers_df, apply_filters_df, get_filtered_server_names, scoped_query
from services.anomaly import compute_workload_profiles, compute_right_sizing

logger = logging.getLogger(__name__)
router = APIRouter()


def _apply_filters(df, search=None, priority=None, environment=None,
                   app_code=None, criticality=None, tag_key=None, tag_value=None):
    return apply_filters_df(df, search, priority, environment, app_code, criticality, tag_key, tag_value)


def _serialize_servers(df: pd.DataFrame) -> list[dict]:
    result = []
    for rec in df.to_dict(orient="records"):
        tags = rec.get("Tags")
        result.append({
            "name": str(rec.get("Server Name", "") or ""),
            "resource_type": str(rec.get("Resource_Type", "") or ""),
            "current_load": safe_float(rec.get("Current_Load", 0)),
            "days_left": safe_int(rec.get("Days_Left", 999), 999),
            "total_alerts": safe_int(rec.get("Total_Alerts", 0)),
            "priority": str(rec.get("Priority", "NONE") or "NONE"),
            "risk_category": str(rec.get("Risk_Category", "Healthy") or "Healthy"),
            "action": str(rec.get("Action", "Monitor") or "Monitor"),
            "cpu_count": safe_int(rec.get("CPU_Count", 0)),
            "ram_gb": safe_float(rec.get("RAM_GB", 0)),
            "max_disk_util": safe_float(rec.get("Max_Disk_Util", 0)),
            "min_free_gb": safe_float(rec.get("Min_Free_GB", 999), 999.0),
            "max_db_growth": safe_float(rec.get("Max_DB_Growth", 0)),
            "environment": str(rec.get("Environment", "Unknown") or "Unknown"),
            "criticality": str(rec.get("PAASDB_CRTICALITY", "Unknown") or "Unknown"),
            "tags": tags if isinstance(tags, list) else [],
            "diagnostic": str(rec.get("Diagnostic", "") or ""),
        })
    return result


@router.get("/servers")
def get_servers(
    search: Optional[str] = None, priority: Optional[str] = None,
    environment: Optional[str] = None, app_code: Optional[str] = None,
    criticality: Optional[str] = None, tag_key: Optional[str] = None,
    tag_value: Optional[str] = None,
):
    with get_db() as session:
        fetch_id = get_latest_fetch_id(session)
        if not fetch_id:
            return []
        df = load_servers_df(session, fetch_id)
        if df.empty:
            return []
        df = _apply_filters(df, search, priority, environment, app_code, criticality, tag_key, tag_value)
        df = dedup_servers_df(df)

        triage_rows = session.execute(
            text("SELECT server_name, status FROM triage_status")
        ).mappings().fetchall()
        triage_map = {r["server_name"]: r["status"] for r in triage_rows}

    result = _serialize_servers(df)
    for r in result:
        r["triage_status"] = triage_map.get(r["name"], "Open")
    return result


@router.get("/servers/filters")
def get_filter_options():
    with get_db() as session:
        fetch_id = get_latest_fetch_id(session)
        if not fetch_id:
            return {"app_codes": [], "criticalities": [], "environments": [], "tag_keys": []}
        df = load_servers_df(session, fetch_id)
        if df.empty:
            return {"app_codes": [], "criticalities": [], "environments": [], "tag_keys": []}

    all_tags = [tag for tags in df["Tags"] for tag in tags]
    app_codes = sorted({t.split(":")[1] for t in all_tags if t.upper().startswith("PAASDB_APPCODE:")})
    crits = sorted({t.split(":")[1] for t in all_tags if t.upper().startswith("PAASDB_CRTICALITY:")})
    envs = sorted(df["Environment"].unique().tolist())
    tag_keys = sorted({t.split(":")[0] for t in all_tags if ":" in t})
    return {"app_codes": app_codes, "criticalities": crits, "environments": envs, "tag_keys": tag_keys}


@router.get("/health")
def get_fleet_health(
    search: Optional[str] = None, priority: Optional[str] = None,
    environment: Optional[str] = None, app_code: Optional[str] = None,
):
    with get_db() as session:
        fetch_id = get_latest_fetch_id(session)
        if not fetch_id:
            return {
                "health_score": 100, "total_servers": 0,
                "urgent_count": 0, "high_count": 0, "disks_at_risk": 0,
                "avg_load": 0, "events_7d": 0, "wow_delta": "N/A", "last_fetch": None,
                "total_vcpus": 0, "total_ram_gb": 0, "total_disk_tb": 0,
            }

        df = load_servers_df(session, fetch_id)
        df = _apply_filters(df, search, priority, environment, app_code)
        df = dedup_servers_df(df)

        n_urgent = int((df["Priority"] == "URGENT").sum())
        n_high = int((df["Priority"] == "HIGH").sum())

        filtered_names = df["Server Name"].tolist() if not df.empty else []
        has_filter = any([search, priority, environment, app_code])

        if has_filter and not filtered_names:
            disk_rows = []
            hw_totals = {"total_vcpus": 0, "total_ram_gb": 0}
            disk_totals = {"total_disk_tb": 0}
            events_7d = 0
            events_prev_7d = 0
        elif has_filter and filtered_names:
            disk_rows = session.execute(
                text("SELECT utilization_pct FROM disks WHERE fetch_id = :fid AND server_name = ANY(:names)"),
                {"fid": fetch_id, "names": filtered_names},
            ).mappings().fetchall()

            hw_totals = session.execute(
                text(
                    "SELECT SUM(cpu_count) as total_vcpus, SUM(ram_gb) as total_ram_gb "
                    "FROM servers WHERE fetch_id = :fid AND resource_type = 'CPU' AND name = ANY(:names)"
                ),
                {"fid": fetch_id, "names": filtered_names},
            ).mappings().fetchone()

            disk_totals = session.execute(
                text("SELECT SUM(total_gb) as total_disk_tb FROM disks WHERE fetch_id = :fid AND server_name = ANY(:names)"),
                {"fid": fetch_id, "names": filtered_names},
            ).mappings().fetchone()

            d7_iso  = (datetime.datetime.now() - datetime.timedelta(days=7)).isoformat()
            d14_iso = (datetime.datetime.now() - datetime.timedelta(days=14)).isoformat()
            row_7d = session.execute(
                text("SELECT COUNT(*) as cnt FROM events WHERE fetch_id = :fid AND date >= :d7 AND server_name = ANY(:names)"),
                {"fid": fetch_id, "d7": d7_iso, "names": filtered_names},
            ).mappings().fetchone()
            row_prev = session.execute(
                text("SELECT COUNT(*) as cnt FROM events WHERE fetch_id = :fid AND date >= :d14 AND date < :d7 AND server_name = ANY(:names)"),
                {"fid": fetch_id, "d14": d14_iso, "d7": d7_iso, "names": filtered_names},
            ).mappings().fetchone()
            events_7d      = int(row_7d["cnt"])  if row_7d  else 0
            events_prev_7d = int(row_prev["cnt"]) if row_prev else 0
        else:
            disk_rows = session.execute(
                text("SELECT utilization_pct FROM disks WHERE fetch_id = :fid"),
                {"fid": fetch_id},
            ).mappings().fetchall()

            hw_totals = session.execute(
                text(
                    "SELECT SUM(cpu_count) as total_vcpus, SUM(ram_gb) as total_ram_gb "
                    "FROM servers WHERE fetch_id = :fid AND resource_type = 'CPU'"
                ),
                {"fid": fetch_id},
            ).mappings().fetchone()

            disk_totals = session.execute(
                text("SELECT SUM(total_gb) as total_disk_tb FROM disks WHERE fetch_id = :fid"),
                {"fid": fetch_id},
            ).mappings().fetchone()

            d7_iso  = (datetime.datetime.now() - datetime.timedelta(days=7)).isoformat()
            d14_iso = (datetime.datetime.now() - datetime.timedelta(days=14)).isoformat()
            row_7d = session.execute(
                text("SELECT COUNT(*) as cnt FROM events WHERE fetch_id = :fid AND date >= :d7"),
                {"fid": fetch_id, "d7": d7_iso},
            ).mappings().fetchone()
            row_prev = session.execute(
                text("SELECT COUNT(*) as cnt FROM events WHERE fetch_id = :fid AND date >= :d14 AND date < :d7"),
                {"fid": fetch_id, "d14": d14_iso, "d7": d7_iso},
            ).mappings().fetchone()
            events_7d      = int(row_7d["cnt"])  if row_7d  else 0
            events_prev_7d = int(row_prev["cnt"]) if row_prev else 0

        disk_at_risk = sum(1 for r in disk_rows if (r["utilization_pct"] or 0) >= 90)
        total_vcpus = int(hw_totals["total_vcpus"] or 0)
        total_ram_gb = round(safe_float(hw_totals["total_ram_gb"]), 1)
        total_disk_tb = round(safe_float(disk_totals["total_disk_tb"]) / 1024, 1)

        fetch_info = session.execute(
            text("SELECT completed_at FROM fetch_runs WHERE id = :fid"),
            {"fid": fetch_id},
        ).mappings().fetchone()

    health_score = max(0, min(100, 100 - (n_urgent * 15) - (n_high * 5) - (disk_at_risk * 2)))

    wow_delta = "N/A"
    if events_prev_7d > 0:
        wow_delta = f"{((events_7d - events_prev_7d) / events_prev_7d) * 100:+.1f}%"
    elif events_7d > 0:
        wow_delta = "New"

    avg_load = 0.0
    if len(df) > 0:
        avg_load = round(safe_float(df["Current_Load"].mean()), 1)

    return {
        "health_score": health_score, "total_servers": len(df),
        "urgent_count": n_urgent, "high_count": n_high, "disks_at_risk": disk_at_risk,
        "avg_load": avg_load, "events_7d": events_7d, "wow_delta": wow_delta,
        "last_fetch": fetch_info["completed_at"] if fetch_info else None,
        "total_vcpus": total_vcpus, "total_ram_gb": total_ram_gb, "total_disk_tb": total_disk_tb,
    }


@router.get("/needs-attention")
def get_needs_attention(
    search: Optional[str] = None, priority: Optional[str] = None,
    environment: Optional[str] = None, app_code: Optional[str] = None,
):
    with get_db() as session:
        fetch_id = get_latest_fetch_id(session)
        if not fetch_id:
            return []
        df = load_servers_df(session, fetch_id)
        if df.empty:
            return []
        df = _apply_filters(df, search, priority, environment, app_code)
        df = dedup_servers_df(df)

        triage_rows = session.execute(
            text("SELECT server_name, status FROM triage_status")
        ).mappings().fetchall()
        triage_map = {r["server_name"]: r["status"] for r in triage_rows}

    silent = df[(df["Current_Load"] > 75) & (df["Total_Alerts"] <= 1)].copy()
    silent["Flag"] = "Silent Failure"
    compound = df[
        ((df["Current_Load"] > 70) | (df["Days_Left"] < 60)) &
        ((df["Max_Disk_Util"] > 85) | (df["Max_DB_Growth"] > 2))
    ].copy()
    compound["Flag"] = "Compound Risk"

    attention = pd.concat([silent, compound], ignore_index=True).drop_duplicates(
        subset="Server Name", keep="first"
    )
    if attention.empty:
        return []

    attention = attention.sort_values("Current_Load", ascending=False)
    result = []
    for rec in attention.to_dict(orient="records"):
        flag = str(rec.get("Flag", ""))
        diag = str(rec.get("Diagnostic", "") or "")
        if not diag:
            load = float(rec.get("Current_Load", 0) or 0)
            alerts = int(rec.get("Total_Alerts", 0) or 0)
            disk_util = float(rec.get("Max_Disk_Util", 0) or 0)
            db_growth = float(rec.get("Max_DB_Growth", 0) or 0)
            days = int(rec.get("Days_Left", 999) or 999)
            parts = []
            if flag == "Silent Failure":
                parts.append(f"Load {load:.0f}% with only {alerts} alert(s) — potential monitoring gap")
            elif flag == "Compound Risk":
                if load > 70: parts.append(f"CPU at {load:.0f}%")
                if days < 60: parts.append(f"runway {days}d")
                if disk_util > 85: parts.append(f"disk {disk_util:.0f}% full")
                if db_growth > 2: parts.append(f"DB growing {db_growth:.1f} GB/day")
            diag = ("Compound risk: " + ", ".join(parts)) if parts else flag

        result.append({
            "name": str(rec.get("Server Name", "") or ""),
            "current_load": safe_float(rec.get("Current_Load", 0)),
            "total_alerts": safe_int(rec.get("Total_Alerts", 0)),
            "cpu_count": safe_int(rec.get("CPU_Count", 0)),
            "priority": str(rec.get("Priority", "NONE") or "NONE"),
            "flag": flag, "diagnostic": diag,
            "triage_status": triage_map.get(str(rec.get("Server Name", "")), "Open"),
        })
    return result


@router.get("/profiles")
def get_workload_profiles(
    search: Optional[str] = None, priority: Optional[str] = None,
    environment: Optional[str] = None, app_code: Optional[str] = None,
):
    with get_db() as session:
        fetch_id = get_latest_fetch_id(session)
        if not fetch_id:
            return {"profiles": [], "counts": {}, "reclaimable_vcpus": 0}
        df = load_servers_df(session, fetch_id)
        df = _apply_filters(df, search, priority, environment, app_code)

    if len(df) < 3:
        return {"profiles": [], "counts": {}, "reclaimable_vcpus": 0}

    prof_df = compute_workload_profiles(df)
    counts = prof_df["Profile_Type"].value_counts().to_dict()
    zombies = prof_df[prof_df["Profile_Type"] == "Zombie (High Res, Low Load)"]
    reclaimable = int(zombies["CPU_Count"].sum() - len(zombies) * 2) if not zombies.empty else 0

    profiles = []
    for rec in prof_df.to_dict(orient="records"):
        profiles.append({
            "server_name": str(rec["Server Name"]),
            "vcpu": safe_int(rec.get("VCPU", 0)),
            "ram_gb": safe_float(rec.get("RAM", 0)),
            "resource_load": safe_float(rec.get("Resource_Load", 0)),
            "profile_type": str(rec.get("Profile_Type", "Balanced")),
            "profile_reason": str(rec.get("Profile_Reason", "")),
        })
    return {"profiles": profiles, "counts": counts, "reclaimable_vcpus": max(0, reclaimable)}


@router.get("/right-sizing")
def get_right_sizing(
    search: Optional[str] = None, priority: Optional[str] = None,
    environment: Optional[str] = None, app_code: Optional[str] = None,
):
    with get_db() as session:
        fetch_id = get_latest_fetch_id(session)
        if not fetch_id:
            return {"scale_up": [], "scale_down": []}
        df = load_servers_df(session, fetch_id)
        df = _apply_filters(df, search, priority, environment, app_code)
        if len(df) < 3:
            return {"scale_up": [], "scale_down": []}
        has_filter = any([search, priority, environment, app_code])
        names = dedup_servers_df(df)["Server Name"].tolist() if has_filter else None
        disk_rows = scoped_query(session, "SELECT * FROM disks WHERE fetch_id = :fetch_id", fetch_id, names)
        disk_df = pd.DataFrame([dict(r) for r in disk_rows]) if disk_rows else pd.DataFrame()

    result = compute_right_sizing(df, disk_df)
    return deep_sanitize(result)


@router.get("/rising-problems")
def get_rising_problems(
    search: Optional[str] = None, priority: Optional[str] = None,
    environment: Optional[str] = None, app_code: Optional[str] = None,
):
    with get_db() as session:
        fetch_id = get_latest_fetch_id(session)
        if not fetch_id:
            return []
        names = get_filtered_server_names(session, fetch_id, search, priority, environment, app_code)
        event_rows = scoped_query(session,
            "SELECT date, server_name, problem_name FROM events WHERE fetch_id = :fetch_id",
            fetch_id, names)
    if not event_rows:
        return []

    edf = pd.DataFrame([dict(r) for r in event_rows])
    edf["Date"] = pd.to_datetime(edf["date"], errors="coerce")
    edf = edf.dropna(subset=["Date"])
    if edf.empty:
        return []

    now = datetime.datetime.now()
    curr = edf[edf["Date"] >= (now - datetime.timedelta(days=7))]
    prev = edf[
        (edf["Date"] >= (now - datetime.timedelta(days=14))) &
        (edf["Date"] < (now - datetime.timedelta(days=7)))
    ]
    if curr.empty:
        return []

    curr_counts = curr.groupby(["server_name", "problem_name"]).size().reset_index(name="current_7d")
    prev_counts = prev.groupby(["server_name", "problem_name"]).size().reset_index(name="prev_7d")
    combined = pd.merge(curr_counts, prev_counts, on=["server_name", "problem_name"], how="left")
    combined["prev_7d"] = combined["prev_7d"].fillna(0).astype(int)
    combined["diff"] = combined["current_7d"] - combined["prev_7d"]
    combined["pct_change"] = (
        (combined["diff"] / combined["prev_7d"].replace(0, 1)) * 100
    ).round(1)
    combined = combined.sort_values("diff", ascending=False).head(10)

    return [
        {
            "server_name": str(r["server_name"]),
            "problem_name": str(r["problem_name"]),
            "current_7d": int(r["current_7d"]),
            "prev_7d": int(r["prev_7d"]),
            "diff": int(r["diff"]),
            "pct_change": safe_float(r["pct_change"]),
        }
        for r in combined.to_dict(orient="records")
    ]


@router.get("/severity-trend")
def get_severity_trend(
    search: Optional[str] = None, priority: Optional[str] = None,
    environment: Optional[str] = None, app_code: Optional[str] = None,
):
    with get_db() as session:
        fetch_id = get_latest_fetch_id(session)
        if not fetch_id:
            return []
        names = get_filtered_server_names(session, fetch_id, search, priority, environment, app_code)
        event_rows = scoped_query(session,
            "SELECT date, severity FROM events WHERE fetch_id = :fetch_id",
            fetch_id, names)
    if not event_rows:
        return []

    edf = pd.DataFrame([dict(r) for r in event_rows])
    edf["Date"] = pd.to_datetime(edf["date"], errors="coerce")
    edf = edf.dropna(subset=["Date"])
    if edf.empty:
        return []
    edf["Day"] = edf["Date"].dt.date.astype(str)
    grouped = edf.groupby(["Day", "severity"]).size().reset_index(name="count")
    return grouped.to_dict(orient="records")


@router.get("/recurring-issues")
def get_recurring_issues(
    search: Optional[str] = None, priority: Optional[str] = None,
    environment: Optional[str] = None, app_code: Optional[str] = None,
):
    with get_db() as session:
        fetch_id = get_latest_fetch_id(session)
        if not fetch_id:
            return []
        names = get_filtered_server_names(session, fetch_id, search, priority, environment, app_code)
        event_rows = scoped_query(session,
            "SELECT server_name, problem_name FROM events WHERE fetch_id = :fetch_id",
            fetch_id, names)
    if not event_rows:
        return []

    edf = pd.DataFrame([dict(r) for r in event_rows])
    repeat = edf.groupby(["server_name", "problem_name"]).size().reset_index(name="count")
    repeat = repeat[repeat["count"] >= 2].sort_values("count", ascending=False).head(10)
    return repeat.to_dict(orient="records")


@router.get("/risk-matrix")
def get_risk_matrix(
    search: Optional[str] = None, priority: Optional[str] = None,
    environment: Optional[str] = None, app_code: Optional[str] = None,
):
    with get_db() as session:
        fetch_id = get_latest_fetch_id(session)
        if not fetch_id:
            return []
        df = load_servers_df(session, fetch_id)
    if df.empty:
        return []
    df = _apply_filters(df, search, priority, environment, app_code)
    df = dedup_servers_df(df)
    risk = df[df["Priority"] != "NONE"].groupby(
        ["Environment", "Priority"]
    ).size().reset_index(name="count")
    return risk.to_dict(orient="records")
