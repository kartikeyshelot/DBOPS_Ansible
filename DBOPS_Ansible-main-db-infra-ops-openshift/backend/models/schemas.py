"""
Pydantic models for API request/response validation.
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


# --- Enums ---

class Priority(str, Enum):
    URGENT = "URGENT"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


class TriageStatusEnum(str, Enum):
    OPEN = "Open"
    IN_PROGRESS = "In Progress"
    FIXED = "Fixed"
    WONT_FIX = "Won't Fix"


class Severity(str, Enum):
    DISASTER = "Disaster"
    HIGH = "High"
    AVERAGE = "Average"
    WARNING = "Warning"
    INFO = "Info"


# --- Request Models ---

class FetchRequest(BaseModel):
    zabbix_url: str = Field(..., description="Zabbix API endpoint URL")
    zabbix_token: str = Field(..., description="Zabbix API auth token")
    zabbix_group: str = Field(default="PAASDB", description="Host group name")
    days_back: int = Field(default=30, ge=7, le=90, description="Days of history to fetch")


class TriageUpdateRequest(BaseModel):
    status: TriageStatusEnum
    notes: Optional[str] = None


class ServerFilterParams(BaseModel):
    search: Optional[str] = None
    priority: Optional[Priority] = None
    environment: Optional[str] = None
    app_code: Optional[str] = None
    criticality: Optional[str] = None
    tag_key: Optional[str] = None
    tag_value: Optional[str] = None


# --- Response Models ---

class ServerSummary(BaseModel):
    name: str
    resource_type: str = ""
    current_load: float = 0
    days_left: int = 999
    total_alerts: int = 0
    priority: str = "NONE"
    risk_category: str = "Healthy"
    action: str = "Monitor"
    cpu_count: int = 0
    ram_gb: float = 0
    max_disk_util: float = 0
    min_free_gb: float = 999
    max_db_growth: float = 0
    environment: str = "Unknown"
    criticality: str = "Unknown"
    tags: list[str] = []
    triage_status: str = "Open"
    diagnostic: str = ""


class EventRecord(BaseModel):
    date: str
    server_name: str
    problem_name: str
    severity: str


class DiskRecord(BaseModel):
    server_name: str
    drive: str
    type: str
    total_gb: float
    used_gb: float
    free_gb: float
    utilization_pct: float
    risk_category: str
    action_required: str


class DatabaseRecord(BaseModel):
    server_name: str
    db_name: str
    db_type: str
    raw_size: float
    raw_growth: float
    suggestion: str
    trend: list[float] = []
    smart_size: str = ""
    growth_mb_day: str = ""


class ForecastResult(BaseModel):
    server_name: str
    min_free_gb: float
    max_db_growth: float
    max_disk_util: float
    estimated_runway_days: float
    current_load: float
    days_left: int
    priority: str
    projection: list[dict] = []


class FleetHealth(BaseModel):
    health_score: int
    total_servers: int
    urgent_count: int
    high_count: int
    disks_at_risk: int
    avg_load: float
    events_7d: int
    wow_delta: str
    last_fetch: Optional[str] = None


class FetchStatusResponse(BaseModel):
    fetch_id: int
    status: str
    started_at: str
    completed_at: Optional[str] = None
    server_count: int = 0


class WorkloadProfile(BaseModel):
    server_name: str
    vcpu: int
    ram_gb: float
    resource_load: float
    profile_type: str
    profile_reason: str


class RisingStat(BaseModel):
    problem_name: str
    current_7d: int
    prev_7d: int
    diff: int
    pct_change: float


class SeverityTrendPoint(BaseModel):
    day: str
    severity: str
    count: int


class RecurringIssue(BaseModel):
    server_name: str
    problem_name: str
    count: int


class RiskMatrixEntry(BaseModel):
    environment: str
    priority: str
    count: int


class NeedsAttentionServer(BaseModel):
    server_name: str
    current_load: float
    total_alerts: int
    cpu_count: int
    priority: str
    flag: str


class RightSizingRecommendation(BaseModel):
    server_name: str
    current_vcpu: int
    current_load: float
    recommended_vcpu: int
    delta: int
    action: str
