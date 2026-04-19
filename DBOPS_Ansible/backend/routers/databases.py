"""
GET /api/databases — Database growth data.
GET /api/databases/disk-correlation — DB growth vs disk free scatter data.
"""

import json
import math
import logging
from fastapi import APIRouter
from typing import Optional
from sqlalchemy import text
from database import get_db, get_latest_fetch_id
from utils import safe_float as _sf, get_filtered_server_names, scoped_query
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)
router = APIRouter()


def _fmt_size(b) -> str:
    b = _sf(b, 0)
    if b / (1024 ** 3) < 1:
        return f"{b / (1024 ** 2):.1f} MB"
    return f"{b / (1024 ** 3):.2f} GB"


def _slope(vals: list) -> float:
    n = len(vals)
    if n < 2:
        return 0.0
    x = list(range(n))
    mx = sum(x) / n
    my = sum(vals) / n
    num = sum((x[i] - mx) * (vals[i] - my) for i in range(n))
    den = sum((x[i] - mx) ** 2 for i in range(n))
    return num / den if den != 0 else 0.0


@router.get("/databases")
def get_databases(
    server_name: Optional[str] = None,
    search: Optional[str] = None, priority: Optional[str] = None,
    environment: Optional[str] = None, app_code: Optional[str] = None,
):
    with get_db() as session:
        fetch_id = get_latest_fetch_id(session)
        if not fetch_id:
            return []

        if server_name:
            rows = session.execute(
                text("SELECT * FROM databases WHERE fetch_id = :fid AND server_name = :name"),
                {"fid": fetch_id, "name": server_name},
            ).mappings().fetchall()
        else:
            names = get_filtered_server_names(session, fetch_id, search, priority, environment, app_code)
            rows = scoped_query(session,
                "SELECT * FROM databases WHERE fetch_id = :fetch_id", fetch_id, names)

        result = []
        for r in rows:
            d = dict(r)
            raw_size = _sf(d.get("raw_size"), 0)
            raw_growth = _sf(d.get("raw_growth"), 0)
            d["raw_size"] = raw_size
            d["raw_growth"] = raw_growth
            d["size_display"] = _fmt_size(raw_size)
            d["growth_display"] = f"{raw_growth / (1024 ** 2):.1f} MB/day"
            d["smart_size"] = d["size_display"]
            d["growth_mb_day"] = d["growth_display"]
            d["trend"] = json.loads(d["trend"]) if d.get("trend") else []
            d["trend"] = [0.0 if (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else v
                          for v in d["trend"]]

            trend = d["trend"]
            accel_label = "Stable"
            accel_multiplier = 1.0
            if len(trend) >= 6:
                mid = len(trend) // 2
                first_half = [v for v in trend[:mid] if v > 0]
                second_half = [v for v in trend[mid:] if v > 0]
                if len(first_half) >= 2 and len(second_half) >= 2:
                    s1 = _slope(first_half)
                    s2 = _slope(second_half)
                    if s1 > 0 and s2 > 0:
                        ratio = s2 / s1
                        if ratio >= 2.5:
                            accel_label = "Accelerating"
                            accel_multiplier = round(ratio, 1)
                        elif ratio <= 0.4:
                            accel_label = "Decelerating"
                            accel_multiplier = round(ratio, 1)
                    elif s2 > 0.001 and s1 <= 0:
                        accel_label = "Accelerating"
                        accel_multiplier = 0.0
                    elif s2 <= 0 and s1 > 0.001:
                        accel_label = "Decelerating"
                        accel_multiplier = 0.0

            d["growth_acceleration"] = accel_label
            d["growth_multiplier"] = accel_multiplier
            result.append(d)

        return result


@router.get("/databases/disk-correlation")
def get_db_disk_correlation(
    search: Optional[str] = None, priority: Optional[str] = None,
    environment: Optional[str] = None, app_code: Optional[str] = None,
):
    with get_db() as session:
        fetch_id = get_latest_fetch_id(session)
        if not fetch_id:
            return []

        names = get_filtered_server_names(session, fetch_id, search, priority, environment, app_code)
        db_rows = scoped_query(session,
            "SELECT server_name, raw_growth FROM databases WHERE fetch_id = :fetch_id",
            fetch_id, names)

        params = {"fid": fetch_id}
        disk_sql = "SELECT server_name, free_gb, type FROM disks WHERE fetch_id = :fid AND type = 'Database'"
        if names is not None:
            if not names:
                return []
            disk_sql += " AND server_name = ANY(:names)"
            params["names"] = names
        disk_rows = session.execute(text(disk_sql), params).mappings().fetchall()

        if not db_rows or not disk_rows:
            return []

        db_df = pd.DataFrame([dict(r) for r in db_rows])
        db_df["raw_growth"] = pd.to_numeric(db_df["raw_growth"], errors="coerce").fillna(0)
        db_df["growth_gb_day"] = db_df["raw_growth"] / (1024 ** 3)
        db_agg = db_df.groupby("server_name")["growth_gb_day"].max().reset_index()

        disk_df = pd.DataFrame([dict(r) for r in disk_rows])
        disk_df["free_gb"] = pd.to_numeric(disk_df["free_gb"], errors="coerce").fillna(0)
        disk_agg = disk_df.groupby("server_name")["free_gb"].min().reset_index()

        merged = pd.merge(db_agg, disk_agg, on="server_name", how="inner")
        merged = merged[(merged["growth_gb_day"] > 0.01) & (merged["free_gb"] < 500)]

        if len(merged) < 2:
            return []

        merged["storage_days"] = np.where(
            merged["growth_gb_day"] > 0,
            (merged["free_gb"] / merged["growth_gb_day"]).clip(upper=999),
            999.0
        )
        merged = merged.replace([np.inf, -np.inf], 999.0).fillna(0)

        records = merged.to_dict(orient="records")
        for rec in records:
            for k, v in rec.items():
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    rec[k] = 0.0
        return records
