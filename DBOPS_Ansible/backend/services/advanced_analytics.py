"""
Advanced analytics: improved forecasting, alert velocity, stability scores,
MTTR, noise ratio, correlated failures, fleet-level comparisons.
"""

import datetime
import logging
import numpy as np
import pandas as pd
from collections import defaultdict

logger = logging.getLogger(__name__)


# ─── Improved Forecasting with Polynomial Regression + Confidence ────────────

def forecast_with_confidence(dates, values, target_pct=95.0, forecast_days=90):
    """
    Polynomial regression (degree 2) with confidence interval.
    Falls back to linear if quadratic fit is worse.
    Returns dict with forecast curve, confidence bounds, and days_left.
    """
    if len(dates) < 3:
        curr = values[-1] if len(values) > 0 else 0
        return {
            "current": float(curr),
            "days_left": 999,
            "trend": "stable",
            "slope_per_day": 0.0,
            "forecast_dates": [],
            "forecast_values": [],
            "upper_bound": [],
            "lower_bound": [],
            "r_squared": 0.0,
        }

    # Convert dates to ordinals (day numbers)
    ordinals = np.array([d.toordinal() for d in dates], dtype=float)
    vals = np.array(values, dtype=float)

    # Remove NaN
    mask = ~np.isnan(vals)
    ordinals = ordinals[mask]
    vals = vals[mask]

    if len(ordinals) < 3:
        return {
            "current": float(vals[-1]) if len(vals) > 0 else 0,
            "days_left": 999,
            "trend": "stable",
            "slope_per_day": 0.0,
            "forecast_dates": [],
            "forecast_values": [],
            "upper_bound": [],
            "lower_bound": [],
            "r_squared": 0.0,
        }

    x_norm = ordinals - ordinals[0]  # normalize for numerical stability
    current = float(vals[-1])

    # Try quadratic fit
    try:
        coeffs_quad = np.polyfit(x_norm, vals, 2)
        pred_quad = np.polyval(coeffs_quad, x_norm)
        ss_res_quad = np.sum((vals - pred_quad) ** 2)
        ss_tot = np.sum((vals - np.mean(vals)) ** 2)
        r2_quad = 1 - (ss_res_quad / max(ss_tot, 1e-10))
    except Exception:
        r2_quad = -1
        coeffs_quad = None

    # Linear fit
    coeffs_lin = np.polyfit(x_norm, vals, 1)
    pred_lin = np.polyval(coeffs_lin, x_norm)
    ss_res_lin = np.sum((vals - pred_lin) ** 2)
    ss_tot = np.sum((vals - np.mean(vals)) ** 2)
    r2_lin = 1 - (ss_res_lin / max(ss_tot, 1e-10))

    # Pick better model (prefer quadratic only if meaningfully better)
    if coeffs_quad is not None and r2_quad > r2_lin + 0.05:
        coeffs = coeffs_quad
        degree = 2
        r_squared = r2_quad
        residuals = vals - pred_quad
    else:
        coeffs = coeffs_lin
        degree = 1
        r_squared = r2_lin
        residuals = vals - pred_lin

    # Residual std for confidence interval
    residual_std = float(np.std(residuals)) if len(residuals) > 1 else 0

    # Slope (linear component) per day
    if degree == 2:
        # Instantaneous slope at the end point
        slope = float(2 * coeffs[0] * x_norm[-1] + coeffs[1])
    else:
        slope = float(coeffs[0])

    # Determine trend
    if slope > 0.3:
        trend = "rising_fast"
    elif slope > 0.05:
        trend = "rising"
    elif slope < -0.3:
        trend = "falling_fast"
    elif slope < -0.05:
        trend = "falling"
    else:
        trend = "stable"

    # Forecast curve
    last_x = x_norm[-1]
    last_date = dates[-1] if hasattr(dates[-1], 'toordinal') else datetime.datetime.now()
    forecast_x = np.arange(last_x + 1, last_x + forecast_days + 1)
    forecast_vals = np.polyval(coeffs, forecast_x)
    forecast_vals = np.clip(forecast_vals, 0, 100)  # clamp to valid range

    # Confidence bounds (±1.96σ for 95% CI, expanding over time)
    expansion = np.sqrt(np.arange(1, forecast_days + 1) / len(x_norm))
    upper = np.clip(forecast_vals + 1.96 * residual_std * expansion, 0, 100)
    lower = np.clip(forecast_vals - 1.96 * residual_std * expansion, 0, 100)

    # Forecast dates
    forecast_dates = [
        (last_date + datetime.timedelta(days=int(i + 1))).strftime("%Y-%m-%d")
        for i in range(forecast_days)
    ]

    # Days until target
    days_left = 999
    if current >= target_pct:
        days_left = 0
    elif slope > 0.001:
        # Find first day forecast exceeds target
        exceeds = np.where(forecast_vals >= target_pct)[0]
        if len(exceeds) > 0:
            days_left = int(exceeds[0]) + 1
        else:
            days_left = 999

    return {
        "current": round(current, 2),
        "days_left": days_left,
        "trend": trend,
        "slope_per_day": round(slope, 4),
        "forecast_dates": forecast_dates,
        "forecast_values": [round(float(v), 2) for v in forecast_vals],
        "upper_bound": [round(float(v), 2) for v in upper],
        "lower_bound": [round(float(v), 2) for v in lower],
        "r_squared": round(float(max(r_squared, 0)), 4),
        "model_degree": degree,
    }


# ─── Alert Velocity ──────────────────────────────────────────────────────────

def compute_alert_velocity(events_df):
    """
    For each server, compute alert acceleration:
    - alerts in last 3 days vs previous 3 days
    - velocity = rate of change
    Returns sorted list of servers with accelerating alerts.
    """
    if events_df.empty:
        return []

    edf = events_df.copy()
    if "Date" not in edf.columns:
        edf["Date"] = pd.to_datetime(edf["date"], errors="coerce")
    edf = edf.dropna(subset=["Date"])
    if edf.empty:
        return []

    now = datetime.datetime.now()
    recent = edf[edf["Date"] >= (now - datetime.timedelta(days=3))]
    prior = edf[(edf["Date"] >= (now - datetime.timedelta(days=6))) &
                (edf["Date"] < (now - datetime.timedelta(days=3)))]

    recent_counts = recent.groupby("server_name").size().reset_index(name="recent_3d")
    prior_counts = prior.groupby("server_name").size().reset_index(name="prior_3d")

    merged = pd.merge(recent_counts, prior_counts, on="server_name", how="outer").fillna(0)
    merged["velocity"] = merged["recent_3d"] - merged["prior_3d"]
    merged["acceleration_pct"] = np.where(
        merged["prior_3d"] > 0,
        ((merged["recent_3d"] - merged["prior_3d"]) / merged["prior_3d"] * 100).round(1),
        np.where(merged["recent_3d"] > 0, 100.0, 0.0)
    )

    # Only include accelerating servers
    accelerating = merged[merged["velocity"] > 0].sort_values("velocity", ascending=False)

    return accelerating.head(15).to_dict(orient="records")


# ─── Stability Score ─────────────────────────────────────────────────────────

def compute_stability_scores(cap_df):
    """
    Compute load stability per server based on coefficient of variation.
    Lower CV = more stable. Returns list sorted by stability (most unstable first).
    Uses CPU utilization only for consistency.
    """
    if cap_df is None or cap_df.empty:
        return []

    df = cap_df.copy()
    df["Utilization"] = pd.to_numeric(df.get("Utilization", 0), errors="coerce")

    # Filter to CPU metric only for consistent stability analysis
    if "Metric" in df.columns:
        cpu_df = df[df["Metric"].str.upper() == "CPU"]
        if not cpu_df.empty:
            df = cpu_df

    stats = df.groupby("Server Name")["Utilization"].agg(["mean", "std", "min", "max", "count"])
    stats = stats[stats["count"] >= 3].copy()  # need enough data points
    stats["std"] = stats["std"].fillna(0)
    stats["cv"] = np.where(stats["mean"] > 0, (stats["std"] / stats["mean"] * 100).round(1), 0)

    # Stability score: 100 = perfectly stable, 0 = wildly unstable
    stats["stability_score"] = np.clip(100 - stats["cv"], 0, 100).round(0).astype(int)

    # Classify
    def classify(row):
        if row["stability_score"] >= 80:
            return "Stable"
        elif row["stability_score"] >= 50:
            return "Moderate"
        else:
            return "Volatile"

    stats["classification"] = stats.apply(classify, axis=1)
    stats = stats.reset_index()

    result = []
    for _, row in stats.iterrows():
        result.append({
            "server_name": str(row["Server Name"]),
            "stability_score": int(row["stability_score"]),
            "classification": row["classification"],
            "avg_load": round(float(row["mean"]), 1),
            "std_load": round(float(row["std"]), 1),
            "min_load": round(float(row["min"]), 1),
            "max_load": round(float(row["max"]), 1),
            "cv_pct": float(row["cv"]),
            "data_points": int(row["count"]),
        })

    # Sort: most unstable first
    result.sort(key=lambda x: x["stability_score"])
    return result


# ─── MTTR (Mean Time to Recovery) ────────────────────────────────────────────

def compute_mttr(problems_df, events_df=None):
    """
    Estimate MTTR per server by matching problem open/close events.
    problems_df is kept for backward-compat but only events_df is used.
    If called with a single arg (bundle path), it acts as events_df.
    """
    # Support both compute_mttr(events) and compute_mttr(events, events)
    if events_df is None:
        events_df = problems_df
    if events_df.empty:
        return {"fleet_avg_hours": 0, "servers": []}

    edf = events_df.copy()
    if "Date" not in edf.columns:
        edf["Date"] = pd.to_datetime(edf["date"], errors="coerce")
    edf = edf.dropna(subset=["Date"])
    if edf.empty:
        return {"fleet_avg_hours": 0, "servers": []}

    # Group events per server, compute span between first and last event per problem
    grouped = edf.groupby(["server_name", "problem_name"])["Date"].agg(["min", "max", "count"])
    grouped["duration_hours"] = (grouped["max"] - grouped["min"]).dt.total_seconds() / 3600
    grouped = grouped[grouped["count"] >= 2].reset_index()  # need at least 2 events

    if grouped.empty:
        return {"fleet_avg_hours": 0, "servers": []}

    # Per-server avg MTTR
    server_mttr = grouped.groupby("server_name")["duration_hours"].agg(["mean", "median", "count"])
    server_mttr = server_mttr.reset_index()
    server_mttr.columns = ["server_name", "avg_hours", "median_hours", "incident_count"]

    fleet_avg = round(float(server_mttr["avg_hours"].mean()), 1)

    servers = []
    for _, row in server_mttr.sort_values("avg_hours", ascending=False).head(20).iterrows():
        avg_h = float(row["avg_hours"])
        servers.append({
            "server_name": str(row["server_name"]),
            "avg_hours": round(avg_h, 1),
            "median_hours": round(float(row["median_hours"]), 1),
            "incident_count": int(row["incident_count"]),
            "classification": "Slow" if avg_h > 48 else "Moderate" if avg_h > 12 else "Fast",
        })

    return {
        "fleet_avg_hours": fleet_avg,
        "servers": servers,
    }


# ─── Noise Ratio ─────────────────────────────────────────────────────────────

def compute_noise_ratio(events_df):
    """
    Calculate the ratio of low-severity (Information/Warning) alerts vs
    actionable (Average/High/Disaster) alerts per server.
    High noise ratio = too many non-actionable alerts, needs tuning.
    """
    if events_df.empty:
        return {"fleet_noise_pct": 0, "servers": []}

    edf = events_df.copy()
    noise_severities = {"Information", "Info", "Warning", "Not classified", "Not Classified"}
    actionable_severities = {"Average", "High", "Disaster"}

    edf["is_noise"] = edf["severity"].isin(noise_severities)
    edf["is_actionable"] = edf["severity"].isin(actionable_severities)

    # Fleet-wide
    total = len(edf)
    noise_total = edf["is_noise"].sum()
    fleet_noise_pct = round((noise_total / max(total, 1)) * 100, 1)

    # Per-server
    per_server = edf.groupby("server_name").agg(
        total_alerts=("severity", "count"),
        noise_alerts=("is_noise", "sum"),
        actionable_alerts=("is_actionable", "sum"),
    ).reset_index()

    per_server["noise_pct"] = (per_server["noise_alerts"] / per_server["total_alerts"] * 100).round(1)
    per_server = per_server.sort_values("noise_pct", ascending=False)

    servers = []
    for _, row in per_server.head(20).iterrows():
        servers.append({
            "server_name": str(row["server_name"]),
            "total_alerts": int(row["total_alerts"]),
            "noise_alerts": int(row["noise_alerts"]),
            "actionable_alerts": int(row["actionable_alerts"]),
            "noise_pct": float(row["noise_pct"]),
            "recommendation": "Tune thresholds" if row["noise_pct"] > 70 else
                             "Review triggers" if row["noise_pct"] > 40 else "OK",
        })

    return {
        "fleet_noise_pct": fleet_noise_pct,
        "total_alerts": int(total),
        "noise_alerts": int(noise_total),
        "actionable_alerts": int(total - noise_total),
        "servers": servers,
    }


# ─── Correlated Failures ─────────────────────────────────────────────────────

def detect_correlated_failures(events_df, window_minutes=30):
    """
    Find servers that tend to alert within the same time window.
    Suggests shared infrastructure (network, storage, etc.)

    Optimised: uses vectorised pandas groupby + counter-based pair counting
    instead of the original O(n²×m) nested loop with per-pair DataFrame scans.
    """
    if events_df.empty:
        return []

    edf = events_df.copy()
    if "Date" not in edf.columns:
        edf["Date"] = pd.to_datetime(edf["date"], errors="coerce")
    edf = edf.dropna(subset=["Date"])
    if edf.empty:
        return []

    # Bucket events into time windows
    edf["window"] = edf["Date"].dt.floor(f"{window_minutes}min")

    # For each window, collect the set of server names
    window_servers = edf.groupby("window")["server_name"].apply(set).reset_index()
    window_servers = window_servers[window_servers["server_name"].apply(len) >= 2]

    if window_servers.empty:
        return []

    # Cap to prevent combinatorial explosion: skip windows with too many servers
    # (50+ servers in one window is an event storm, not a useful correlation)
    window_servers = window_servers[window_servers["server_name"].apply(len) <= 50]
    if window_servers.empty:
        return []

    # Pre-build a problem lookup by (window, server) — one pass, no per-pair scanning
    problem_lookup = (
        edf.groupby(["window", "server_name"])["problem_name"]
        .apply(lambda x: set(x.unique()[:3]))
        .to_dict()
    )

    # Count co-occurrences using sorted tuples as keys — pure Python, no DataFrame scans
    pair_counts = defaultdict(int)
    pair_problems = defaultdict(set)

    for _, row in window_servers.iterrows():
        servers = sorted(row["server_name"])
        window_key = row["window"]
        for i in range(len(servers)):
            for j in range(i + 1, len(servers)):
                pair = (servers[i], servers[j])
                pair_counts[pair] += 1
                # Look up pre-computed problems — O(1) dict lookup, not O(n) DataFrame scan
                probs_a = problem_lookup.get((window_key, servers[i]), set())
                probs_b = problem_lookup.get((window_key, servers[j]), set())
                pair_problems[pair].update(probs_a | probs_b)

    if not pair_counts:
        return []

    # Sort by frequency and return top correlated pairs
    result = []
    for pair, count in sorted(pair_counts.items(), key=lambda x: -x[1])[:15]:
        if count >= 2:
            result.append({
                "server_a": pair[0],
                "server_b": pair[1],
                "co_occurrence_count": count,
                "shared_problems": list(pair_problems[pair])[:5],
                "likely_cause": "Shared infrastructure" if count >= 5 else "Possible correlation",
            })

    return result


# ─── Fleet Environment Comparison ────────────────────────────────────────────

def compute_environment_comparison(servers_df):
    """
    Compare Production vs Non-Production fleet health.
    """
    if servers_df.empty:
        return []

    df = servers_df.copy()
    result = []

    for env in df["Environment"].unique():
        env_df = df[df["Environment"] == env]
        n = len(env_df)
        if n == 0:
            continue

        avg_load = float(env_df["Current_Load"].mean())
        avg_alerts = float(env_df["Total_Alerts"].mean())
        urgent = int((env_df["Priority"] == "URGENT").sum())
        high = int((env_df["Priority"] == "HIGH").sum())
        healthy = int((env_df["Risk_Category"] == "Healthy").sum())
        healthy_pct = round(healthy / n * 100, 1)

        avg_days = env_df["Days_Left"].replace(999, np.nan).mean()
        avg_days = round(float(avg_days), 0) if not pd.isna(avg_days) else 999

        result.append({
            "environment": str(env),
            "server_count": n,
            "avg_load": round(avg_load, 1),
            "avg_alerts": round(avg_alerts, 1),
            "urgent_count": urgent,
            "high_count": high,
            "healthy_count": healthy,
            "healthy_pct": healthy_pct,
            "avg_runway_days": int(avg_days),
            "risk_score": round(100 - healthy_pct + (urgent * 10) + (high * 5), 1),
        })

    result.sort(key=lambda x: -x["risk_score"])
    return result


# ─── Utilization Distribution ─────────────────────────────────────────────────

def compute_utilization_distribution(servers_df):
    """
    Bucket servers into utilization ranges for histogram display.
    """
    if servers_df.empty:
        return {"buckets": [], "stats": {}}

    loads = servers_df["Current_Load"].dropna().values

    buckets = [
        {"range": "0-10%", "min": 0, "max": 10},
        {"range": "10-20%", "min": 10, "max": 20},
        {"range": "20-40%", "min": 20, "max": 40},
        {"range": "40-60%", "min": 40, "max": 60},
        {"range": "60-80%", "min": 60, "max": 80},
        {"range": "80-90%", "min": 80, "max": 90},
        {"range": "90-100%", "min": 90, "max": 100},
    ]

    for b in buckets:
        count = int(np.sum((loads >= b["min"]) & (loads < b["max"])))
        b["count"] = count
        b["servers"] = [
            str(name) for name, load in
            zip(servers_df["Server Name"].values, loads)
            if b["min"] <= load < b["max"]
        ][:5]  # sample server names
        del b["min"], b["max"]

    stats = {
        "mean": round(float(np.mean(loads)), 1) if len(loads) > 0 else 0,
        "median": round(float(np.median(loads)), 1) if len(loads) > 0 else 0,
        "p90": round(float(np.percentile(loads, 90)), 1) if len(loads) > 0 else 0,
        "p95": round(float(np.percentile(loads, 95)), 1) if len(loads) > 0 else 0,
        "std": round(float(np.std(loads)), 1) if len(loads) > 0 else 0,
    }

    return {"buckets": buckets, "stats": stats}


# ─── Alert Timing Heatmap ────────────────────────────────────────────────────

def compute_alert_heatmap(events_df):
    """
    Count alerts by day-of-week × hour-of-day.

    Useful for: identifying when problems peak so ops teams can schedule
    maintenance windows, staff on-call rotations, and tune Zabbix time periods.

    Returns a flat list of {day, day_index, hour, count} cells — frontend
    renders this as a heatmap.  Only cells with at least one event are returned
    (sparse matrix — frontend fills missing cells with 0).
    """
    if events_df is None or events_df.empty:
        return {"matrix": [], "max_count": 0, "total_events": 0, "peak": None}

    edf = events_df.copy()
    if "Date" not in edf.columns:
        edf["Date"] = pd.to_datetime(edf["date"], errors="coerce")
    edf = edf.dropna(subset=["Date"])
    if edf.empty:
        return {"matrix": [], "max_count": 0, "total_events": 0, "peak": None}

    edf["day_of_week"] = edf["Date"].dt.dayofweek   # 0 = Monday
    edf["hour"] = edf["Date"].dt.hour

    counts = (
        edf.groupby(["day_of_week", "hour"])
        .size()
        .reset_index(name="count")
    )

    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    matrix = [
        {
            "day": day_names[int(row["day_of_week"])],
            "day_index": int(row["day_of_week"]),
            "hour": int(row["hour"]),
            "count": int(row["count"]),
        }
        for row in counts.to_dict("records")
    ]

    max_count = int(counts["count"].max()) if not counts.empty else 0

    # Find the single busiest cell for the summary callout
    peak = None
    if not counts.empty:
        idx = counts["count"].idxmax()
        peak_row = counts.loc[idx]
        peak = {
            "day": day_names[int(peak_row["day_of_week"])],
            "hour": int(peak_row["hour"]),
            "count": int(peak_row["count"]),
        }

    return {
        "matrix": matrix,
        "max_count": max_count,
        "total_events": int(len(edf)),
        "peak": peak,
    }


# ─── Top Alerting Servers ─────────────────────────────────────────────────────

def compute_top_alerters(events_df, n: int = 15):
    """
    Top N servers ranked by total alert count, with per-severity breakdown.

    Useful for: immediately identifying the noisiest servers so the team can
    decide whether to investigate root cause or tune alert thresholds.

    Returns a list sorted descending by total alerts.
    """
    if events_df is None or events_df.empty:
        return []

    # Total per server
    totals = (
        events_df.groupby("server_name")
        .size()
        .reset_index(name="total")
        .sort_values("total", ascending=False)
        .head(n)
    )

    # Per-severity breakdown for the top-N servers only
    top_names = set(totals["server_name"].tolist())
    top_events = events_df[events_df["server_name"].isin(top_names)]
    breakdown = (
        top_events.groupby(["server_name", "severity"])
        .size()
        .reset_index(name="count")
    )

    result = []
    for _, row in totals.iterrows():
        sname = row["server_name"]
        sev_rows = breakdown[breakdown["server_name"] == sname]
        by_severity = {
            str(r["severity"]): int(r["count"])
            for _, r in sev_rows.iterrows()
        }
        result.append({
            "server_name": str(sname),
            "total": int(row["total"]),
            "by_severity": by_severity,
        })

    return result


def compute_alert_categories(events_df) -> dict:
    """
    Classify every problem_name in events_df into a category by keyword matching.
    Returns a dict: { category: count } plus a 'total' key.

    Categories:
      CPU       — cpu, processor, utilization (non-memory), load average
      Memory    — memory, ram, swap, available memory, heap
      Disk      — disk, filesystem, space, vfs, volume, partition
      Database  — mssql, pgsql, postgres, mysql, oracle, database, db size, tempdb
      Service   — service, process, agent, daemon, port, connection, listener
      Network   — network, interface, ping, packet, bandwidth, latency
      Other     — everything else
    """
    if events_df is None or events_df.empty or "problem_name" not in events_df.columns:
        return {"total": 0, "categories": {}}

    RULES = [
        ("Database",  ["mssql", "pgsql", "postgres", "mysql", "oracle",
                       "database", "db size", "tempdb", "replication", "transaction log"]),
        ("Disk",      ["disk", "filesystem", "vfs", "free space", "volume",
                       "partition", "storage", "mount"]),
        ("Memory",    ["memory", "ram", "swap", "heap", "available mem",
                       "out of memory", "virtual mem"]),
        ("CPU",       ["cpu", "processor", "load average", "high load",
                       "run queue", "iowait"]),
        ("Service",   ["service", "process", "agent", "daemon", "port",
                       "connection", "listener", "running", "not running"]),
        ("Network",   ["network", "interface", "ping", "packet", "bandwidth",
                       "latency", "link down", "throughput"]),
    ]

    counts = {cat: 0 for cat, _ in RULES}
    counts["Other"] = 0

    for name in events_df["problem_name"].dropna().str.lower():
        matched = False
        for cat, keywords in RULES:
            if any(kw in name for kw in keywords):
                counts[cat] += 1
                matched = True
                break
        if not matched:
            counts["Other"] += 1

    # Remove zero-count categories to keep the donut clean
    categories = {k: v for k, v in counts.items() if v > 0}
    return {
        "total": int(sum(categories.values())),
        "categories": categories,
    }
