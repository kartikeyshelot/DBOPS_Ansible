"""
Persistence service: saves fetched and processed data into PostgreSQL.

Key change from original: all save functions use executemany-style bulk inserts
via SQLAlchemy text() with lists of parameter dicts — one round-trip per table.
"""

import json
import math
import datetime
import logging
import pandas as pd

from sqlalchemy import text

logger = logging.getLogger(__name__)


# ── Safe type helpers ─────────────────────────────────────────────────────────

def _sf(val, default: float = 0.0) -> float:
    """Safe float — NaN / None → default."""
    if val is None:
        return default
    try:
        f = float(val)
        return default if math.isnan(f) or math.isinf(f) else f
    except (ValueError, TypeError):
        return default


def _si(val, default: int = 0) -> int:
    """Safe int — NaN / None → default."""
    if val is None:
        return default
    try:
        f = float(val)
        return default if math.isnan(f) or math.isinf(f) else int(f)
    except (ValueError, TypeError):
        return default


def _clean_list(lst) -> list:
    """Sanitise a list of floats — replace NaN / Inf with 0."""
    if not isinstance(lst, list):
        return []
    return [
        0.0 if isinstance(v, float) and (math.isnan(v) or math.isinf(v)) else v
        for v in lst
    ]


# ── Fetch run lifecycle ───────────────────────────────────────────────────────

def create_fetch_run(session, zabbix_url: str, zabbix_group: str, days_back: int) -> int:
    """Insert a new fetch_run row and return its ID."""
    result = session.execute(
        text(
            "INSERT INTO fetch_runs (started_at, zabbix_url, zabbix_group, days_back, status) "
            "VALUES (:started, :url, :grp, :days, 'running') "
            "RETURNING id"
        ),
        {
            "started": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "url": zabbix_url,
            "grp": zabbix_group,
            "days": days_back,
        },
    )
    return result.scalar_one()


def complete_fetch_run(session, fetch_id: int, server_count: int):
    session.execute(
        text(
            "UPDATE fetch_runs SET completed_at = :now, server_count = :cnt, "
            "status = 'completed' WHERE id = :fid"
        ),
        {
            "now": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "cnt": server_count,
            "fid": fetch_id,
        },
    )


def fail_fetch_run(session, fetch_id: int, error: str):
    session.execute(
        text(
            "UPDATE fetch_runs SET completed_at = :now, status = :status WHERE id = :fid"
        ),
        {
            "now": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "status": f"failed: {error[:500]}",
            "fid": fetch_id,
        },
    )


# ── Data savers — bulk inserts via executemany ────────────────────────────────

def save_servers(session, fetch_id: int, summary_df: pd.DataFrame):
    """Save processed server summary to the database."""
    if summary_df is None or summary_df.empty:
        return

    df = summary_df.copy()
    has_diagnostic = "Diagnostic" in df.columns

    df["Server Name"]        = df.get("Server Name",        pd.Series(dtype=str)).fillna("").astype(str)
    df["Resource_Type"]      = df.get("Resource_Type",      pd.Series(dtype=str)).fillna("").astype(str)
    df["Current_Load"]       = pd.to_numeric(df.get("Current_Load",  0), errors="coerce").fillna(0.0)
    df["Days_Left"]          = pd.to_numeric(df.get("Days_Left",    999), errors="coerce").fillna(999).astype(int)
    df["Total_Alerts"]       = pd.to_numeric(df.get("Total_Alerts",   0), errors="coerce").fillna(0).astype(int)
    df["Priority"]           = df.get("Priority",           pd.Series(dtype=str)).fillna("NONE").astype(str)
    df["Risk_Category"]      = df.get("Risk_Category",      pd.Series(dtype=str)).fillna("Healthy").astype(str)
    df["Action"]             = df.get("Action",             pd.Series(dtype=str)).fillna("Monitor").astype(str)
    df["CPU_Count"]          = pd.to_numeric(df.get("CPU_Count",   0), errors="coerce").fillna(0).astype(int)
    df["RAM_GB"]             = pd.to_numeric(df.get("RAM_GB",      0), errors="coerce").fillna(0.0)
    df["Max_Disk_Util"]      = pd.to_numeric(df.get("Max_Disk_Util", 0), errors="coerce").fillna(0.0)
    df["Min_Free_GB"]        = pd.to_numeric(df.get("Min_Free_GB", 999), errors="coerce").fillna(999.0)
    df["Max_DB_Growth"]      = pd.to_numeric(df.get("Max_DB_Growth", 0), errors="coerce").fillna(0.0)
    df["Environment"]        = df.get("Environment",        pd.Series(dtype=str)).fillna("Unknown").astype(str)
    df["PAASDB_CRTICALITY"]  = df.get("PAASDB_CRTICALITY", pd.Series(dtype=str)).fillna("Unknown").astype(str)
    df["Diagnostic"]         = (df["Diagnostic"].fillna("").astype(str)
                                 if has_diagnostic else pd.Series("", index=df.index))
    tags_col = df.get("Tags", pd.Series([[] for _ in range(len(df))], index=df.index))

    params = [
        {
            "fetch_id": fetch_id,
            "name": row["Server Name"],
            "resource_type": row["Resource_Type"],
            "current_load": _sf(row["Current_Load"]),
            "days_left": _si(row["Days_Left"], 999),
            "total_alerts": _si(row["Total_Alerts"]),
            "priority": row["Priority"] or "NONE",
            "risk_category": row["Risk_Category"] or "Healthy",
            "action": row["Action"] or "Monitor",
            "cpu_count": _si(row["CPU_Count"]),
            "ram_gb": _sf(row["RAM_GB"]),
            "max_disk_util": _sf(row["Max_Disk_Util"]),
            "min_free_gb": _sf(row["Min_Free_GB"], 999.0),
            "max_db_growth": _sf(row["Max_DB_Growth"]),
            "environment": row["Environment"] or "Unknown",
            "criticality": row["PAASDB_CRTICALITY"] or "Unknown",
            "tags": json.dumps(tags_col.iloc[i] if isinstance(tags_col.iloc[i], list) else []),
            "diagnostic": row["Diagnostic"],
        }
        for i, (_, row) in enumerate(df.iterrows())
    ]

    session.execute(
        text(
            "INSERT INTO servers "
            "(fetch_id, name, resource_type, current_load, days_left, "
            "total_alerts, priority, risk_category, action, cpu_count, ram_gb, "
            "max_disk_util, min_free_gb, max_db_growth, environment, criticality, "
            "tags, diagnostic) "
            "VALUES (:fetch_id, :name, :resource_type, :current_load, :days_left, "
            ":total_alerts, :priority, :risk_category, :action, :cpu_count, :ram_gb, "
            ":max_disk_util, :min_free_gb, :max_db_growth, :environment, :criticality, "
            ":tags, :diagnostic)"
        ),
        params,
    )


def save_events(session, fetch_id: int, events_df: pd.DataFrame):
    if events_df is None or events_df.empty:
        return

    dates    = events_df.get("Date",         pd.Series(dtype=str)).fillna("").astype(str)
    servers  = events_df.get("Server Name",  pd.Series(dtype=str)).fillna("").astype(str)
    problems = events_df.get("Problem Name", pd.Series(dtype=str)).fillna("").astype(str)
    sevs     = events_df.get("Severity",     pd.Series(dtype=str)).fillna("").astype(str)

    params = [
        {"fetch_id": fetch_id, "date": d, "server_name": s, "problem_name": p, "severity": sv}
        for d, s, p, sv in zip(dates, servers, problems, sevs)
    ]

    session.execute(
        text(
            "INSERT INTO events (fetch_id, date, server_name, problem_name, severity) "
            "VALUES (:fetch_id, :date, :server_name, :problem_name, :severity)"
        ),
        params,
    )


def save_disks(session, fetch_id: int, disk_df: pd.DataFrame):
    if disk_df is None or disk_df.empty:
        return

    servers  = disk_df.get("Server Name",    pd.Series(dtype=str)).fillna("").astype(str)
    drives   = disk_df.get("Drive",          pd.Series(dtype=str)).fillna("").astype(str)
    types    = disk_df.get("Type",           pd.Series(dtype=str)).fillna("").astype(str)
    total    = pd.to_numeric(disk_df.get("Total Size (GB)", 0), errors="coerce").fillna(0.0)
    used     = pd.to_numeric(disk_df.get("Used (GB)",       0), errors="coerce").fillna(0.0)
    free     = pd.to_numeric(disk_df.get("Free (GB)",       0), errors="coerce").fillna(0.0)
    util     = pd.to_numeric(disk_df.get("Utilization %",   0), errors="coerce").fillna(0.0)
    risk     = disk_df.get("Risk Category",   pd.Series(dtype=str)).fillna("").astype(str)
    action   = disk_df.get("Action Required", pd.Series(dtype=str)).fillna("").astype(str)

    params = [
        {
            "fetch_id": fetch_id, "server_name": s, "drive": d, "type": t,
            "total_gb": _sf(tot), "used_gb": _sf(u), "free_gb": _sf(f),
            "utilization_pct": _sf(ut), "risk_category": r, "action_required": a,
        }
        for s, d, t, tot, u, f, ut, r, a in zip(servers, drives, types, total, used, free, util, risk, action)
    ]

    session.execute(
        text(
            "INSERT INTO disks "
            "(fetch_id, server_name, drive, type, total_gb, used_gb, "
            "free_gb, utilization_pct, risk_category, action_required) "
            "VALUES (:fetch_id, :server_name, :drive, :type, :total_gb, :used_gb, "
            ":free_gb, :utilization_pct, :risk_category, :action_required)"
        ),
        params,
    )


def save_databases(session, fetch_id: int, db_df: pd.DataFrame):
    if db_df is None or db_df.empty:
        return

    servers   = db_df.get("Server Name",          pd.Series(dtype=str)).fillna("").astype(str)
    db_names  = db_df.get("Database Name",         pd.Series(dtype=str)).fillna("").astype(str)
    db_types  = db_df.get("Type",                  pd.Series(dtype=str)).fillna("").astype(str)
    raw_size  = pd.to_numeric(db_df.get("Raw Size",   0), errors="coerce").fillna(0.0)
    raw_grow  = pd.to_numeric(db_df.get("Raw Growth", 0), errors="coerce").fillna(0.0)
    suggest   = db_df.get("Utilization Suggestion", pd.Series(dtype=str)).fillna("Stable").astype(str)
    trends    = db_df.get("Trend", pd.Series([[] for _ in range(len(db_df))], index=db_df.index))

    params = [
        {
            "fetch_id": fetch_id, "server_name": s, "db_name": dn, "db_type": dt,
            "raw_size": _sf(rs), "raw_growth": _sf(rg), "suggestion": sg or "Stable",
            "trend": json.dumps(_clean_list(tr) if isinstance(tr, list) else []),
        }
        for s, dn, dt, rs, rg, sg, tr in zip(servers, db_names, db_types, raw_size, raw_grow, suggest, trends)
    ]

    session.execute(
        text(
            "INSERT INTO databases "
            "(fetch_id, server_name, db_name, db_type, raw_size, raw_growth, suggestion, trend) "
            "VALUES (:fetch_id, :server_name, :db_name, :db_type, :raw_size, :raw_growth, "
            ":suggestion, :trend)"
        ),
        params,
    )


def save_capacity_trends(session, fetch_id: int, cap_df: pd.DataFrame):
    if cap_df is None or cap_df.empty:
        return

    dates   = cap_df.get("Date",         pd.Series(dtype=str)).fillna("").astype(str)
    servers = cap_df.get("Server Name",  pd.Series(dtype=str)).fillna("").astype(str)
    metrics = cap_df.get("Metric",       pd.Series(dtype=str)).fillna("").astype(str)
    utils   = pd.to_numeric(cap_df.get("Utilization", 0), errors="coerce").fillna(0.0)

    params = [
        {"fetch_id": fetch_id, "date": d, "server_name": s, "metric": m, "utilization": _sf(u)}
        for d, s, m, u in zip(dates, servers, metrics, utils)
    ]

    session.execute(
        text(
            "INSERT INTO capacity_trends (fetch_id, date, server_name, metric, utilization) "
            "VALUES (:fetch_id, :date, :server_name, :metric, :utilization)"
        ),
        params,
    )
