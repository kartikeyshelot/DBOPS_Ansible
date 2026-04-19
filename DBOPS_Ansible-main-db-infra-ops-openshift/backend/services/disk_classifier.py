"""
Drive classification and risk assessment.
Extracted verbatim from the original Streamlit app.
"""

from typing import Tuple
from config import settings


def classify_drive(drive_name: str) -> str:
    d = drive_name.upper()
    if d.startswith("C:") or d.startswith("D:"):
        return "System"
    if drive_name in ["/", "/boot", "/tmp", "/var", "/opt", "/local", "/local/home"]:
        return "System"
    return "Database"


def calculate_disk_risk(drive_type: str, used_gb: float, total_gb: float) -> Tuple[str, str]:
    if total_gb == 0:
        return "UNKNOWN", "Check Agent"

    util_pct = (used_gb / total_gb) * 100
    free_gb = total_gb - used_gb

    if drive_type == "System":
        if util_pct > settings.system_drive_critical_pct:
            return "CRITICAL: OS Drive Full", "Clean Logs/Temp Urgent"
        if free_gb < settings.system_drive_low_free_gb and util_pct > 50:
            return f"CRITICAL: Low Free Space ({free_gb:.1f}GB)", "Expand Partition"
        if util_pct > settings.system_drive_warning_pct:
            return "WARNING: System > 90%", "Plan Cleanup"
    else:
        if util_pct > settings.db_drive_critical_pct:
            return "CRITICAL: DB Drive Full", "Expand Storage Immediately"
        if util_pct > settings.db_drive_warning_pct:
            return "WARNING: DB Space > 90%", "Monitor Growth"

    return "HEALTHY", "Monitor"
