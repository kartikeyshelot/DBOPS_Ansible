"""
Anomaly detection (IsolationForest) and workload profiling (KMeans).
Extracted from the original app with identical logic.
"""

import logging
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from config import settings

logger = logging.getLogger(__name__)


def build_anomaly_explanation(row: dict, fleet_stats: dict) -> str:
    """Builds a human-readable explanation for why a server was flagged. Verbatim from original."""
    reasons = []
    load = row.get("Current_Load", 0) or 0
    alerts = row.get("Total_Alerts", 0) or 0
    db_growth = row.get("Max_DB_Growth", 0) or 0
    disk_util = row.get("Max_Disk_Util", 0) or 0

    if load > 85 and alerts < 2:
        reasons.append("**Monitoring gap:** Load >85% with few alerts — possible blind spot.")
    elif load < 20 and alerts > 8:
        reasons.append("**Alert storm:** >8 alerts on an idle server — tune thresholds.")

    mean_g = fleet_stats.get("DB_Growth_Mean", 0) or 0
    std_g = fleet_stats.get("DB_Growth_Std", 0.001) or 0.001
    if db_growth > mean_g + (2 * std_g) and std_g > 0:
        reasons.append(
            f"**Rapid growth:** DB at {db_growth:.1f} GB/day, 2σ above fleet avg ({mean_g:.1f})."
        )

    if load > 70 and disk_util > 85:
        reasons.append(
            f"**Converging pressure:** CPU ({load:.0f}%) and Disk ({disk_util:.0f}%) both elevated."
        )

    if not reasons:
        reasons.append(
            "**Statistical outlier:** Deviates from normal fleet behavior — investigate manually."
        )

    return " ".join(reasons)


def build_profile_explanation(row: dict) -> str:
    """Explains why a server falls into its workload profile. Verbatim from original."""
    load = row.get("Resource_Load", 0) or 0
    vcpu = row.get("VCPU", 0) or 0
    profile = row.get("Profile_Type", "")

    if profile == "Zombie (High Res, Low Load)":
        return f"Underutilized: {vcpu} vCPUs allocated, only {load:.1f}% used. Consider downsizing."
    elif profile == "Thrasher (High Load)":
        return f"Overloaded: {load:.1f}% exceeds 75% safety threshold. Scale up."
    return f"Healthy: {load:.1f}% load is well-matched to capacity."


def detect_anomalies(servers_df: pd.DataFrame) -> pd.DataFrame:
    """Run IsolationForest on server data and add Diagnostic column."""
    df = servers_df.copy()
    fleet_stats = {
        "DB_Growth_Mean": df["Max_DB_Growth"].mean(),
        "DB_Growth_Std": max(df["Max_DB_Growth"].std(), 0.001)
    }

    n_samples = len(df)
    if n_samples >= 3:
        iso_cols = df[["Current_Load", "Total_Alerts", "Max_DB_Growth"]].fillna(0)
        contamination = min(0.1, max(0.01, 2 / n_samples))
        iso_model = IsolationForest(contamination=contamination, random_state=42)
        df["_anomaly"] = iso_model.fit_predict(iso_cols)
        df["Diagnostic"] = df.apply(
            lambda r: build_anomaly_explanation(r.to_dict(), fleet_stats)
            if r["_anomaly"] == -1 else "",
            axis=1
        )
        df.drop(columns=["_anomaly"], inplace=True)
    else:
        df["Diagnostic"] = ""

    return df


def label_profile(row: dict) -> str:
    """Assign workload profile label. Identical to original."""
    load = row.get("Resource_Load", 0) or 0
    vcpu = row.get("VCPU", 0) or 0
    if load < settings.zombie_load_pct and vcpu > settings.zombie_min_vcpu:
        return "Zombie (High Res, Low Load)"
    elif load > settings.overload_pct:
        return "Thrasher (High Load)"
    return "Balanced"


def compute_workload_profiles(servers_df: pd.DataFrame) -> pd.DataFrame:
    """Run KMeans profiling. Returns DataFrame with profile columns added."""
    df = servers_df.copy()
    df["VCPU"] = df["CPU_Count"].fillna(0).astype(int)
    df["RAM"] = df["RAM_GB"].fillna(0).astype(float)
    df["Resource_Load"] = df["Current_Load"].fillna(0).astype(float)

    features = df[["VCPU", "RAM", "Resource_Load"]].fillna(0)
    n_clusters = min(3, len(df))

    if n_clusters >= 2:
        scaler = StandardScaler()
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        df["Cluster_ID"] = kmeans.fit_predict(scaler.fit_transform(features))
    else:
        df["Cluster_ID"] = 0

    df["Profile_Type"] = df.apply(lambda r: label_profile(r.to_dict()), axis=1)
    df["Profile_Reason"] = df.apply(
        lambda r: build_profile_explanation(r.to_dict()), axis=1
    )

    return df


def compute_right_sizing(servers_df: pd.DataFrame, disk_df: pd.DataFrame = None) -> dict:
    """
    Comprehensive right-sizing across vCPU, RAM, and Disk.
    Each server gets per-resource recommendations + a composite efficiency score.
    """
    df = servers_df.copy()

    # ── Pivot: get CPU load and Memory load per server ──
    # servers_df may have multiple rows per server (one per Resource_Type)
    cpu_rows = df[df["Resource_Type"].str.upper() == "CPU"].copy()
    mem_rows = df[df["Resource_Type"].str.upper() == "MEMORY"].copy()

    # Build a per-server summary with both CPU and Memory
    if not cpu_rows.empty:
        cpu_summary = cpu_rows.groupby("Server Name").agg({
            "Current_Load": "max",
            "CPU_Count": "max",
            "RAM_GB": "max",
            "Days_Left": "min",
            "Total_Alerts": "max",
            "Max_Disk_Util": "max",
            "Min_Free_GB": "min",
            "Max_DB_Growth": "max",
            "Environment": "first",
            "Priority": "first",
        }).reset_index()
        cpu_summary.rename(columns={"Current_Load": "CPU_Load", "Days_Left": "CPU_Days_Left"}, inplace=True)
    else:
        cpu_summary = pd.DataFrame(columns=[
            "Server Name", "CPU_Load", "CPU_Count", "RAM_GB", "CPU_Days_Left",
            "Total_Alerts", "Max_Disk_Util", "Min_Free_GB", "Max_DB_Growth",
            "Environment", "Priority"
        ])

    if not mem_rows.empty:
        mem_summary = mem_rows.groupby("Server Name").agg({
            "Current_Load": "max",
            "Days_Left": "min",
        }).reset_index()
        mem_summary.rename(columns={"Current_Load": "Mem_Load", "Days_Left": "Mem_Days_Left"}, inplace=True)
    else:
        mem_summary = pd.DataFrame(columns=["Server Name", "Mem_Load", "Mem_Days_Left"])

    # Merge CPU + Memory
    combined = pd.merge(cpu_summary, mem_summary, on="Server Name", how="outer")
    # Explicit fillna + cast to avoid pandas FutureWarning on silent downcasting
    for col, default, dtype in [
        ("CPU_Load", 0.0, float), ("Mem_Load", 0.0, float),
        ("CPU_Count", 0, int), ("RAM_GB", 0.0, float),
        ("CPU_Days_Left", 999, int), ("Mem_Days_Left", 999, int),
        ("Max_Disk_Util", 0.0, float), ("Min_Free_GB", 999.0, float),
        ("Max_DB_Growth", 0.0, float), ("Total_Alerts", 0, int),
    ]:
        if col in combined.columns:
            combined[col] = pd.to_numeric(combined[col], errors="coerce").fillna(default).astype(dtype)
        else:
            combined[col] = default
    for col, default in [("Environment", "Production"), ("Priority", "NONE")]:
        if col in combined.columns:
            combined[col] = combined[col].fillna(default).astype(str)
        else:
            combined[col] = default

    # ── Per-server disk aggregation ──
    disk_per_server = {}
    if disk_df is not None and not disk_df.empty:
        ddf = disk_df.copy()
        ddf["Match_Key"] = ddf["server_name"].astype(str).str.strip().str.lower()
        for mk, group in ddf.groupby("server_name"):
            total = group["total_gb"].sum()
            used = group["used_gb"].sum()
            free = group["free_gb"].sum()
            disk_per_server[mk] = {
                "total_gb": round(float(total), 1),
                "used_gb": round(float(used), 1),
                "free_gb": round(float(free), 1),
                "util_pct": round(float(used / max(total, 0.01) * 100), 1),
                "drive_count": len(group),
            }

    # ── Compute recommendations per server ──
    scale_up = []
    scale_down = []

    for _, row in combined.iterrows():
        server_name = str(row["Server Name"])
        cpu_load = float(row["CPU_Load"])
        mem_load = float(row["Mem_Load"])
        vcpu = int(row["CPU_Count"])
        ram_gb = float(row["RAM_GB"])
        disk_util = float(row["Max_Disk_Util"])
        min_free = float(row["Min_Free_GB"])
        db_growth = float(row["Max_DB_Growth"])
        cpu_days = int(row["CPU_Days_Left"])
        mem_days = int(row["Mem_Days_Left"])
        env = str(row["Environment"])
        alerts = int(row["Total_Alerts"])
        priority = str(row["Priority"])

        disk_info = disk_per_server.get(server_name, {})
        disk_total = disk_info.get("total_gb", 0)
        disk_used = disk_info.get("used_gb", 0)
        disk_free = disk_info.get("free_gb", min_free)

        # ── CPU recommendation ──
        cpu_rec = {"status": "adequate", "current": vcpu, "recommended": vcpu, "delta": 0}
        if vcpu > 0:
            if cpu_load > settings.overload_pct:
                target_vcpu = max(1, int(np.ceil((cpu_load * vcpu) / 70)))
                cpu_rec = {
                    "status": "scale_up",
                    "current": vcpu,
                    "recommended": target_vcpu,
                    "delta": target_vcpu - vcpu,
                    "load": round(cpu_load, 1),
                    "days_left": cpu_days,
                }
            elif cpu_load < settings.zombie_load_pct and vcpu > settings.zombie_min_vcpu:
                target_vcpu = max(2, int(np.ceil((cpu_load * vcpu) / 50)))
                cpu_rec = {
                    "status": "scale_down",
                    "current": vcpu,
                    "recommended": target_vcpu,
                    "delta": target_vcpu - vcpu,
                    "load": round(cpu_load, 1),
                    "days_left": cpu_days,
                }
            else:
                cpu_rec["load"] = round(cpu_load, 1)
                cpu_rec["days_left"] = cpu_days

        # ── RAM recommendation ──
        ram_rec = {"status": "adequate", "current_gb": round(ram_gb, 1), "recommended_gb": round(ram_gb, 1), "delta_gb": 0}
        if ram_gb > 0:
            # Estimate actual RAM usage from utilization percentage
            ram_used_gb = (mem_load / 100) * ram_gb if mem_load > 0 else 0

            if mem_load > 80:
                # Scale up: target 60% utilization at current usage
                target_ram = max(4, int(np.ceil(ram_used_gb / 0.60)))
                # Round to nearest sensible increment (4GB steps)
                target_ram = int(np.ceil(target_ram / 4) * 4)
                ram_rec = {
                    "status": "scale_up",
                    "current_gb": round(ram_gb, 1),
                    "recommended_gb": float(target_ram),
                    "delta_gb": round(target_ram - ram_gb, 1),
                    "load": round(mem_load, 1),
                    "used_gb": round(ram_used_gb, 1),
                    "days_left": mem_days,
                }
            elif mem_load > 0 and mem_load < 20 and ram_gb >= 16:
                # Scale down: only if we have real memory data (mem_load > 0)
                target_ram = max(4, int(np.ceil(ram_used_gb / 0.40)))
                target_ram = int(np.ceil(target_ram / 4) * 4)
                if target_ram < ram_gb:
                    ram_rec = {
                        "status": "scale_down",
                        "current_gb": round(ram_gb, 1),
                        "recommended_gb": float(target_ram),
                        "delta_gb": round(target_ram - ram_gb, 1),
                        "load": round(mem_load, 1),
                        "used_gb": round(ram_used_gb, 1),
                        "days_left": mem_days,
                    }
            else:
                ram_rec["load"] = round(mem_load, 1)
                ram_rec["used_gb"] = round(ram_used_gb, 1)
                ram_rec["days_left"] = mem_days

        # ── Disk recommendation ──
        disk_rec = {
            "status": "adequate",
            "current_total_gb": round(disk_total, 1),
            "used_gb": round(disk_used, 1),
            "free_gb": round(disk_free, 1),
            "util_pct": round(disk_util, 1) if disk_total > 0 else 0.0,
            "db_growth_gb_day": round(db_growth, 2),
            "runway_days": 999,
            "recommended_action": "Monitor",
        }
        if disk_total > 0:
            # Disk runway based on DB growth
            if db_growth > 0.01:
                disk_runway_days = int(disk_free / db_growth) if disk_free > 0 else 0
            else:
                disk_runway_days = 999

            if disk_util > 90 or disk_free < 5:
                expand_gb = max(50, int(np.ceil(db_growth * 90)))  # ~90 days headroom
                disk_rec = {
                    "status": "expand",
                    "current_total_gb": round(disk_total, 1),
                    "used_gb": round(disk_used, 1),
                    "free_gb": round(disk_free, 1),
                    "util_pct": round(disk_util, 1),
                    "db_growth_gb_day": round(db_growth, 2),
                    "runway_days": disk_runway_days,
                    "expand_by_gb": expand_gb,
                    "recommended_action": f"Expand by {expand_gb}GB",
                }
            elif disk_util < 20 and disk_total > 200 and db_growth < 0.1:
                shrink_to = max(50, int(disk_used * 2))  # keep 2× headroom
                disk_rec = {
                    "status": "shrink",
                    "current_total_gb": round(disk_total, 1),
                    "used_gb": round(disk_used, 1),
                    "free_gb": round(disk_free, 1),
                    "util_pct": round(disk_util, 1),
                    "db_growth_gb_day": round(db_growth, 2),
                    "runway_days": disk_runway_days,
                    "shrink_to_gb": shrink_to,
                    "reclaimable_gb": round(disk_total - shrink_to, 1),
                    "recommended_action": f"Shrink to {shrink_to}GB (reclaim {round(disk_total - shrink_to)}GB)",
                }
            else:
                disk_rec.update({
                    "used_gb": round(disk_used, 1),
                    "free_gb": round(disk_free, 1),
                    "util_pct": round(disk_util, 1),
                    "db_growth_gb_day": round(db_growth, 2),
                    "runway_days": disk_runway_days,
                })

        # ── Composite Efficiency Score (0-100) ──
        # 100 = perfectly right-sized, 0 = severely mis-sized
        cpu_eff = _efficiency_score(cpu_load, target_low=30, target_high=70) if vcpu > 0 else 50
        ram_eff = _efficiency_score(mem_load, target_low=30, target_high=70) if ram_gb > 0 else 50
        disk_eff = _efficiency_score(disk_util, target_low=20, target_high=80) if disk_total > 0 else 50

        # Weight: CPU 40%, RAM 35%, Disk 25%
        composite = round(cpu_eff * 0.40 + ram_eff * 0.35 + disk_eff * 0.25)

        # ── Confidence based on data availability ──
        data_signals = sum([
            vcpu > 0, ram_gb > 0, cpu_load > 0, mem_load > 0,
            disk_total > 0, cpu_days < 999,
        ])
        confidence = "High" if data_signals >= 5 else "Medium" if data_signals >= 3 else "Low"

        # ── Determine overall direction ──
        needs_up = cpu_rec["status"] == "scale_up" or ram_rec["status"] == "scale_up" or disk_rec["status"] == "expand"
        needs_down = cpu_rec["status"] == "scale_down" or ram_rec["status"] == "scale_down" or disk_rec["status"] == "shrink"

        rec = {
            "server_name": server_name,
            "environment": env,
            "priority": priority,
            "alerts": alerts,
            "cpu": cpu_rec,
            "ram": ram_rec,
            "disk": disk_rec,
            "efficiency_score": composite,
            "confidence": confidence,
        }

        if needs_up:
            scale_up.append(rec)
        elif needs_down:
            scale_down.append(rec)

    # Sort: scale_up by efficiency ascending (worst first), scale_down by efficiency descending (most wasteful first)
    scale_up.sort(key=lambda x: x["efficiency_score"])
    scale_down.sort(key=lambda x: -x["efficiency_score"])

    return {"scale_up": scale_up, "scale_down": scale_down}


def _efficiency_score(utilization: float, target_low: float = 30, target_high: float = 70) -> float:
    """
    Score how well-sized a resource is based on utilization.
    Sweet spot = target_low to target_high → score 100.
    Below target_low → over-provisioned (score decreases).
    Above target_high → under-provisioned (score decreases faster).
    """
    if target_low <= utilization <= target_high:
        return 100.0
    elif utilization < target_low:
        # Over-provisioned: linear decay
        return max(0, 100 - ((target_low - utilization) / target_low * 100))
    else:
        # Under-provisioned: steeper decay (more dangerous)
        overshoot = utilization - target_high
        max_over = 100 - target_high
        return max(0, 100 - (overshoot / max(max_over, 1) * 120))
