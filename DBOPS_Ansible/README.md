# DB Infrastructure OPS — Redesigned

Modular FastAPI + React replacement for the original Streamlit dashboard.  
All business logic (risk scoring, forecasting, anomaly detection) is preserved verbatim.

## Quick Start

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8090
```

Once running, visit **http://localhost:8090/docs** for the interactive API docs (Swagger UI).

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Visit **http://localhost:5173** to use the dashboard.

## Architecture

```
Browser (localhost:5173)      FastAPI (localhost:8090)       SQLite
  React + Plotly.js      →     /api/servers                  servers
  Component-level state  →     /api/forecasts                events
  Filters, drill-down    →     /api/triage                   disks
                         →     /api/fetch (triggers Zabbix)  databases
```

## What Changed vs Original

| Aspect | Before (Streamlit) | After (FastAPI + React) |
|--------|-------------------|------------------------|
| Interaction | Full page rerun | Component re-render |
| Triage status | Lost on tab close | Persisted in SQLite |
| Data storage | Pickle file (v57) | SQLite with schema |
| Code structure | 1 file, 1200 lines | ~30 files, clear layers |
| Styling | HTML injection | Tailwind CSS |

## What Didn't Change

All business logic is extracted verbatim:
- `classify_drive()` / `calculate_disk_risk()` → `services/disk_classifier.py`
- `process_data()` / `evaluate_risk()` / `get_business_priority()` → `services/analytics.py`
- `build_anomaly_explanation()` / `build_profile_explanation()` → `services/anomaly.py`
- All Zabbix API calls → `services/zabbix_client.py`
- All thresholds → `config.py` (centralized, configurable)

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/fetch | Trigger Zabbix data refresh |
| GET | /api/fetch/status | Latest fetch run status |
| GET | /api/fetch/history | Recent fetch run history |
| GET | /api/servers | Server list with filters |
| GET | /api/servers/filters | Available filter values for dropdowns |
| GET | /api/health | Fleet health KPIs |
| GET | /api/needs-attention | Monitoring blind spots |
| GET | /api/profiles | Workload profiles (KMeans) |
| GET | /api/right-sizing | Scale up/down recommendations |
| GET | /api/rising-problems | Week-over-week trends |
| GET | /api/severity-trend | Severity by day |
| GET | /api/recurring-issues | Repeated server+problem pairs |
| GET | /api/risk-matrix | Risk by environment × priority |
| GET | /api/forecasts/runway | Shortest-runway servers |
| GET | /api/forecasts/{name} | Per-server projection |
| PATCH | /api/triage/{name} | Update triage status |
| GET | /api/triage | All triage statuses |
| GET | /api/drilldown/{name} | Server drill-down data |
| GET | /api/disks | Disk usage |
| GET | /api/databases | Database growth |
| GET | /api/databases/disk-correlation | DB growth vs disk free scatter |

## Project Structure

```
db-infra-ops/
├── backend/
│   ├── main.py                  # FastAPI app entry point
│   ├── config.py                # Centralized settings & thresholds
│   ├── database.py              # SQLite schema & connection
│   ├── models/schemas.py        # Pydantic request/response models
│   ├── routers/
│   │   ├── fetch.py             # POST /api/fetch
│   │   ├── servers.py           # GET /api/servers, /health, /profiles, etc.
│   │   ├── forecasts.py         # GET /api/forecasts/*
│   │   ├── incidents.py         # PATCH /api/triage, GET /api/drilldown
│   │   ├── disks.py             # GET /api/disks
│   │   └── databases.py         # GET /api/databases
│   └── services/
│       ├── zabbix_client.py     # All Zabbix API logic
│       ├── analytics.py         # process_data, risk scoring
│       ├── anomaly.py           # IsolationForest, KMeans
│       ├── disk_classifier.py   # Drive classification
│       └── persistence.py       # SQLite write operations
└── frontend/
    └── src/
        ├── App.jsx              # Main layout with tabs
        ├── api/client.js        # Axios API wrapper
        ├── hooks/useData.js     # React Query hooks
        ├── components/          # Reusable UI components
        │   ├── HealthBar.jsx
        │   ├── Filters.jsx
        │   ├── ScatterQuadrant.jsx
        │   ├── ServerTable.jsx
        │   ├── DrillDown.jsx
        │   └── FetchForm.jsx
        └── pages/               # Tab pages
            ├── Overview.jsx
            ├── Capacity.jsx
            └── Triage.jsx
```
