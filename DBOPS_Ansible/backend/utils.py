"""
Shared utilities — safe type conversion, server DataFrame loading, deduplication.

Previously duplicated across servers.py, analytics_routes.py, and incidents.py.
Single definition here; all routers import from this module.
"""

import json
import math
import logging

import pandas as pd
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ── Single source of truth: SQLite column → DataFrame column name ─────────────
COLUMN_RENAME = {
    "name": "Server Name",
    "resource_type": "Resource_Type",
    "current_load": "Current_Load",
    "days_left": "Days_Left",
    "total_alerts": "Total_Alerts",
    "priority": "Priority",
    "risk_category": "Risk_Category",
    "action": "Action",
    "cpu_count": "CPU_Count",
    "ram_gb": "RAM_GB",
    "max_disk_util": "Max_Disk_Util",
    "min_free_gb": "Min_Free_GB",
    "max_db_growth": "Max_DB_Growth",
    "environment": "Environment",
    "criticality": "PAASDB_CRTICALITY",
    "diagnostic": "Diagnostic",
}

_NUMERIC_DEFAULTS = {
    "Current_Load": 0.0,
    "Days_Left": 999,
    "Total_Alerts": 0,
    "CPU_Count": 0,
    "RAM_GB": 0.0,
    "Max_Disk_Util": 0.0,
    "Min_Free_GB": 999.0,
    "Max_DB_Growth": 0.0,
}

_PRIORITY_ORDER = {"URGENT": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "NONE": 4}


# ── Safe type converters ──────────────────────────────────────────────────────

def safe_float(val, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        f = float(val)
        return default if math.isnan(f) or math.isinf(f) else f
    except (ValueError, TypeError):
        return default


def safe_int(val, default: int = 0) -> int:
    if val is None:
        return default
    try:
        f = float(val)
        return default if math.isnan(f) or math.isinf(f) else int(f)
    except (ValueError, TypeError):
        return default


def deep_sanitize(obj):
    if isinstance(obj, dict):
        return {k: deep_sanitize(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [deep_sanitize(v) for v in obj]
    elif isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return 0.0
    return obj


def apply_filters_df(
    df: pd.DataFrame,
    search=None, priority=None, environment=None,
    app_code=None, criticality=None, tag_key=None, tag_value=None,
) -> pd.DataFrame:
    if df.empty:
        return df
    if search:
        df = df[df["Server Name"].astype(str).str.contains(search, case=False, regex=False)]
    if priority:
        df = df[df["Priority"] == priority]
    if environment:
        df = df[df["Environment"] == environment]
    if app_code:
        app_code_upper = app_code.upper()
        df = df[df["Tags"].apply(
            lambda x: any(t.upper() == f"PAASDB_APPCODE:{app_code_upper}" for t in x)
        )]
    if criticality:
        crit_upper = criticality.upper()
        df = df[df["Tags"].apply(
            lambda x: any(t.upper() == f"PAASDB_CRTICALITY:{crit_upper}" for t in x)
        )]
    if tag_key and tag_value:
        key_upper = tag_key.upper()
        val_upper = tag_value.upper()
        df = df[df["Tags"].apply(
            lambda x: any(t.upper() == f"{key_upper}:{val_upper}" for t in x)
        )]
    return df


def get_filtered_server_names(
    session, fetch_id: int,
    search=None, priority=None, environment=None,
    app_code=None, criticality=None,
) -> list:
    """
    Load the server list, apply filters, and return deduplicated server names.
    Returns None if no filters are active (caller should skip the WHERE IN clause).
    """
    has_filter = any([search, priority, environment, app_code, criticality])
    if not has_filter:
        return None

    df = load_servers_df(session, fetch_id)
    if df.empty:
        return []
    df = apply_filters_df(df, search, priority, environment, app_code, criticality)
    df = dedup_servers_df(df)
    return df["Server Name"].tolist()


def scoped_query(session, sql: str, fetch_id: int, server_names=None, extra_params=None):
    """
    Execute a SQL query scoped to a filtered server subset.
    If server_names is None (no filters active), returns all rows for the fetch_id.
    """
    params = {"fetch_id": fetch_id}
    if server_names is not None:
        if not server_names:
            return []
        sql += " AND server_name = ANY(:names)"
        params["names"] = server_names
    if extra_params:
        params.update(extra_params)
    return session.execute(text(sql), params).mappings().fetchall()


# ── DataFrame helpers ─────────────────────────────────────────────────────────

def load_servers_df(session, fetch_id: int) -> pd.DataFrame:
    """Load server rows into a properly typed DataFrame."""
    rows = session.execute(
        text("SELECT * FROM servers WHERE fetch_id = :fid"),
        {"fid": fetch_id},
    ).mappings().fetchall()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([dict(r) for r in rows])

    df["Tags"] = df["tags"].apply(lambda x: json.loads(x) if x else [])

    rename_map = {k: v for k, v in COLUMN_RENAME.items() if k in df.columns}
    df = df.rename(columns=rename_map)

    df = df.fillna(_NUMERIC_DEFAULTS)

    for col, default in [
        ("Priority", "NONE"),
        ("Risk_Category", "Healthy"),
        ("Action", "Monitor"),
        ("Environment", "Unknown"),
        ("PAASDB_CRTICALITY", "Unknown"),
        ("Resource_Type", ""),
        ("Server Name", ""),
        ("Diagnostic", ""),
    ]:
        if col in df.columns:
            df[col] = df[col].fillna(default)
        else:
            df[col] = default

    return df


def dedup_servers_df(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse multiple resource_type rows into one row per server."""
    if df.empty:
        return df

    agg_spec = {}
    for col, agg_fn in [
        ("Resource_Type", "first"),
        ("Current_Load", "max"),
        ("Days_Left", "min"),
        ("Total_Alerts", "max"),
        ("Risk_Category", "first"),
        ("Action", "first"),
        ("CPU_Count", "max"),
        ("RAM_GB", "max"),
        ("Max_Disk_Util", "max"),
        ("Min_Free_GB", "min"),
        ("Max_DB_Growth", "max"),
        ("Environment", "first"),
        ("PAASDB_CRTICALITY", "first"),
        ("Tags", "first"),
        ("Diagnostic", "first"),
    ]:
        if col in df.columns:
            agg_spec[col] = agg_fn

    agg = df.groupby("Server Name", as_index=False).agg(agg_spec)

    priorities = (
        df.groupby("Server Name")["Priority"]
        .apply(lambda x: min(x, key=lambda p: _PRIORITY_ORDER.get(p, 5)))
        .reset_index()
    )
    agg = agg.drop(columns=["Priority"], errors="ignore").merge(
        priorities, on="Server Name"
    )

    return agg
