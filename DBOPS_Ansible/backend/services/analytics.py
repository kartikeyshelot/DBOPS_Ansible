"""
Analytics engine: data correlation, risk scoring, forecasting.
Extracted from process_data() and supporting functions in the original app.
All business logic is preserved verbatim.
"""

import datetime
import logging
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression

from config import settings

logger = logging.getLogger(__name__)


def get_tag_value(tags: list, key: str) -> str:
    for t in tags:
        if t.startswith(f"{key}:"):
            return t.split(":", 1)[1]
    return "Unknown"


def get_business_priority(env: str, crit: str) -> str:
    """Assign business priority. Unknown environment = Production."""
    e, c = str(env).upper(), str(crit).upper()
    # Production (explicit or Unknown — unknown means production)
    if ("PRODUCTION" in e and "NON" not in e) or "UNKNOWN" in e or e == "":
        if "CRITICAL" in c or "HIGH" in c:
            return "URGENT"
        return "HIGH" if "STANDARD" in c else "LOW"
    # Non-production (explicitly tagged)
    if any(x in e for x in ["NON-PRODUCTION", "NON PRODUCTION", "DEV", "UAT"]):
        if "CRITICAL" in c or "HIGH" in c:
            return "MEDIUM"
        return "LOW"
    return "LOW"


def process_data(cap_df, zab_df, host_tags, disk_df, db_df, hw_df):
    """
    Merge and correlate all data sources into a unified server-level summary.
    Returns (daily_cap_df, summary_df) — identical to the original.
    """
    cap_df = cap_df.copy() if not cap_df.empty else cap_df
    zab_df = zab_df.copy() if not zab_df.empty else zab_df
    disk_df = disk_df.copy() if not disk_df.empty else disk_df
    db_df = db_df.copy() if not db_df.empty else db_df
    hw_df = hw_df.copy() if not hw_df.empty else hw_df

    # --- FORECASTING ENGINE ---
    if not cap_df.empty:
        cap_df["Match_Key"] = cap_df["Server Name"].astype(str).str.strip().str.lower()
        cap_df["Resource_Type"] = cap_df["Metric"].apply(
            lambda x: "CPU" if "cpu" in str(x).lower()
            else ("Memory" if "mem" in str(x).lower() else "Other")
        )
        cap_df["Date_Ordinal"] = cap_df["Date"].map(datetime.datetime.toordinal)

        def forecast_group(group):
            if len(group) < 2:
                return pd.Series({
                    "Current_Load": float(group["Utilization"].iloc[-1]),
                    "Days_Left": 999,
                })
            reg = LinearRegression()
            reg.fit(group["Date_Ordinal"].values.reshape(-1, 1), group["Utilization"].values)
            slope = reg.coef_[0]
            curr = float(group["Utilization"].iloc[-1])
            if curr > settings.forecast_target_pct:
                days = 0
            elif slope > 0.01:
                days = (settings.forecast_target_pct - curr) / slope
            else:
                days = 999
            return pd.Series({
                "Current_Load": curr,
                "Days_Left": int(days) if days < 999 else 999,
            })

        cap_stats = (
            cap_df.groupby(
                ["Server Name", "Match_Key", "Resource_Type"], group_keys=False
            )
            .apply(forecast_group)
            .reset_index()
        )
        # Ensure correct dtypes — pandas apply() can silently upcast to object
        cap_stats["Current_Load"] = pd.to_numeric(cap_stats["Current_Load"], errors="coerce").fillna(0.0)
        cap_stats["Days_Left"] = pd.to_numeric(cap_stats["Days_Left"], errors="coerce").fillna(999).astype(int)
    else:
        if not hw_df.empty:
            cap_stats = hw_df[["Server Name"]].copy()
            cap_stats["Match_Key"] = cap_stats["Server Name"].astype(str).str.strip().str.lower()
            cap_stats["Resource_Type"] = "CPU"
            cap_stats["Current_Load"] = 0.0
            cap_stats["Days_Left"] = 999
        else:
            return None, None

    # Alerts correlation
    if not zab_df.empty:
        zab_df["Match_Key"] = zab_df["Server Name"].astype(str).str.strip().str.lower()
        zab_stats = zab_df.groupby("Match_Key").agg(
            Total_Alerts=("Problem Name", "count")
        ).reset_index()
        merged = pd.merge(cap_stats, zab_stats, on="Match_Key", how="left")
    else:
        merged = cap_stats.copy()
        merged["Total_Alerts"] = 0
    merged["Total_Alerts"] = merged["Total_Alerts"].fillna(0)

    # Tags
    merged["Tags"] = merged["Server Name"].map(host_tags)
    merged["Tags"] = merged["Tags"].apply(lambda x: x if isinstance(x, list) else [])
    merged["Environment"] = merged["Tags"].apply(lambda x: get_tag_value(x, "Environment"))
    # Unknown environment = Production (non-prod servers are explicitly tagged)
    merged["Environment"] = merged["Environment"].replace("Unknown", "Production")
    merged["PAASDB_CRTICALITY"] = merged["Tags"].apply(
        lambda x: get_tag_value(x, "PAASDB_CRTICALITY")
    )

    # Hardware correlation
    if not hw_df.empty:
        hw_df["Match_Key"] = hw_df["Server Name"].astype(str).str.strip().str.lower()
        hw_clean = hw_df[["Match_Key", "CPU_Count", "RAM_GB", "Zab_CPU_Util"]].drop_duplicates()
        merged = pd.merge(merged, hw_clean, on="Match_Key", how="left")
        merged["Current_Load"] = np.where(
            merged["Zab_CPU_Util"] > 0, merged["Zab_CPU_Util"], merged["Current_Load"]
        )
    else:
        merged["CPU_Count"] = 0
        merged["RAM_GB"] = 0

    merged["CPU_Count"] = merged["CPU_Count"].fillna(0).astype(int)
    merged["RAM_GB"] = merged["RAM_GB"].fillna(0).astype(float)

    # Disk correlation
    critical_disk_map = {}
    if not disk_df.empty:
        disk_df["Match_Key"] = disk_df["Server Name"].astype(str).str.strip().str.lower()
        low_space = disk_df[
            (disk_df["Free (GB)"] < 2) & (disk_df["Utilization %"] > 50)
        ].copy()
        if not low_space.empty:
            low_space["Desc"] = low_space.apply(
                lambda x: f"{x['Drive']} ({x['Free (GB)']}GB free)", axis=1
            )
            for mk, desc in low_space.groupby("Match_Key")["Desc"].apply(
                lambda x: ", ".join(x)
            ).to_dict().items():
                critical_disk_map[mk] = f"Low Space: {desc}"

        full_drives = disk_df[disk_df["Utilization %"] > 95].copy()
        if not full_drives.empty:
            full_drives["Desc"] = full_drives.apply(
                lambda x: f"{x['Drive']} ({x['Utilization %']}%)", axis=1
            )
            for mk, desc in full_drives.groupby("Match_Key")["Desc"].apply(
                lambda x: ", ".join(x)
            ).to_dict().items():
                if mk in critical_disk_map:
                    critical_disk_map[mk] += f" & Full: {desc}"
                else:
                    critical_disk_map[mk] = f"Full: {desc}"

        min_free = disk_df.groupby("Match_Key")["Free (GB)"].min().reset_index().rename(
            columns={"Free (GB)": "Min_Free_GB"}
        )
        merged = pd.merge(merged, min_free, on="Match_Key", how="left")
        max_util = disk_df.groupby("Match_Key")["Utilization %"].max().reset_index().rename(
            columns={"Utilization %": "Max_Disk_Util"}
        )
        merged = pd.merge(merged, max_util, on="Match_Key", how="left")
    else:
        merged["Max_Disk_Util"] = 0
        merged["Min_Free_GB"] = 999

    merged["Max_Disk_Util"] = merged["Max_Disk_Util"].fillna(0)
    merged["Min_Free_GB"] = merged["Min_Free_GB"].fillna(999)

    # DB growth correlation
    if not db_df.empty:
        db_df["Match_Key"] = db_df["Server Name"].astype(str).str.strip().str.lower()
        db_df["Growth_GB"] = db_df["Raw Growth"] / (1024 ** 3)
        max_growth = db_df.groupby("Match_Key")["Growth_GB"].max().reset_index().rename(
            columns={"Growth_GB": "Max_DB_Growth"}
        )
        merged = pd.merge(merged, max_growth, on="Match_Key", how="left")
    else:
        merged["Max_DB_Growth"] = 0
    merged["Max_DB_Growth"] = merged["Max_DB_Growth"].fillna(0)

    # Risk evaluation (identical to original evaluate_risk)
    def evaluate_risk(row):
        mk = row["Match_Key"]
        risks, actions = [], []

        if mk in critical_disk_map:
            risks.append(critical_disk_map[mk])
            actions.append("Expand/Clean Disk")
        if row["Days_Left"] < settings.cpu_runway_critical_days:
            risks.append(f"CPU/Mem Exhaustion ({row['CPU_Count']} vCPU)")
            actions.append("Vertical Scale Up" if row["CPU_Count"] <= 2 else "Optimize Workload")
        if row["Max_DB_Growth"] > settings.db_growth_warning_gb:
            risks.append(f"Rapid DB Growth ({row['Max_DB_Growth']:.1f}GB/day)")
            actions.append("Check DB Logs")
        if row["Total_Alerts"] > settings.alert_storm_threshold:
            risks.append(f"High Alerts ({int(row['Total_Alerts'])})")
            actions.append("Tune Monitor")
        if (row["Current_Load"] < settings.underutil_load_pct
                and row["Total_Alerts"] == 0
                and not risks):
            if row["CPU_Count"] >= 2 or row["RAM_GB"] >= 4:
                risks.append(f"Underutilized (Load {row['Current_Load']:.1f}%)")
                actions.append("Scale Down")

        if not risks:
            return pd.Series(
                ["Healthy", "NONE", "Monitor"],
                index=["Risk_Category", "Priority", "Action"]
            )

        return pd.Series([
            " | ".join(risks),
            get_business_priority(row["Environment"], row["PAASDB_CRTICALITY"]),
            " + ".join(actions)
        ], index=["Risk_Category", "Priority", "Action"])

    merged[["Risk_Category", "Priority", "Action"]] = merged.apply(evaluate_risk, axis=1)
    return cap_df, merged
