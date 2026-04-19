import React, { useState, useRef, useEffect } from 'react'
import { useFilterOptions, useFetchStatus, useFleetHealth } from './hooks/useData'
import FetchForm from './components/FetchForm'
import ErrorBoundary from './components/ErrorBoundary'
import Overview from './pages/Overview'
import Analytics from './pages/Analytics'
import Capacity from './pages/Capacity'
import Triage from './pages/Triage'

// Tab definitions — label shown in tab, kick shown above it
const TABS = [
  { key: 'overview',   kick: 'Fleet health',  label: 'Overview'              },
  { key: 'analytics',  kick: 'ML insights',   label: 'Advanced Analytics'    },
  { key: 'capacity',   kick: 'Projections',   label: 'Capacity & Forecasting'},
  { key: 'triage',     kick: 'Active events', label: 'Incidents & Triage'    },
]

// Priority chips — always visible for quick one-click filtering
const PRIORITY_CHIPS = [
  { label: 'Urgent', value: 'URGENT', style: 'amber' },
  { label: 'High',   value: 'HIGH',   style: 'dark'  },
  { label: 'Medium', value: 'MEDIUM', style: 'dark'  },
  { label: 'Low',    value: 'LOW',    style: 'dark'  },
]

export default function App() {
  const [activeTab, setActiveTab] = useState('overview')
  const [filters,   setFilters  ] = useState({})
  const [showFetch, setShowFetch] = useState(false)
  const [showAdvFilter, setShowAdvFilter] = useState(false)
  const advFilterRef = useRef(null)

  const { data: filterOptions } = useFilterOptions()
  const { data: fetchStatus   } = useFetchStatus()
  const { data: health        } = useFleetHealth(filters)

  const hasData  = fetchStatus?.status === 'completed'
  const isRunning = fetchStatus?.status === 'running'

  // Close advanced filter panel on outside click
  useEffect(() => {
    if (!showAdvFilter) return
    const handler = (e) => {
      if (advFilterRef.current && !advFilterRef.current.contains(e.target)) {
        setShowAdvFilter(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showAdvFilter])

  // ── Filter helpers ──────────────────────────────────────────────────────
  const setFilter = (key, value) =>
    setFilters(prev => ({ ...prev, [key]: value || undefined }))

  const clearAllFilters = () => setFilters({})

  const togglePriority = (value) =>
    setFilters(prev => ({ ...prev, priority: prev.priority === value ? undefined : value }))

  const toggleEnv = (value) =>
    setFilters(prev => ({ ...prev, environment: prev.environment === value ? undefined : value }))

  const hasAnyFilter = Object.values(filters).some(Boolean)

  // ── Chip active state ───────────────────────────────────────────────────
  const chipClass = (active, style = 'dark') => {
    if (!active) return 'chip'
    return style === 'amber' ? 'chip amber-active' : 'chip active'
  }

  // Environments from API — limit to first 4 for chip row space
  const envChips = (filterOptions?.environments || []).slice(0, 4)

  return (
    <div className="shell-wrap">
      <div className="shell">

        {/* ══ HEADER ══════════════════════════════════════════════════════ */}
        <div className="shell-hdr">

          {/* Chips row — sits directly at the top, no brand bar above it */}
          <div className="chips-row">
            <span className="chip-lbl">Viewing</span>

            {/* All chip */}
            <span
              className={chipClass(!hasAnyFilter)}
              onClick={clearAllFilters}
            >
              All
            </span>

            {/* Priority chips */}
            {PRIORITY_CHIPS.map(p => (
              <span
                key={p.value}
                className={chipClass(filters.priority === p.value, p.style)}
                onClick={() => togglePriority(p.value)}
              >
                {p.label}
                {health && p.value === 'URGENT' && health.urgent_count > 0 && (
                  <span style={{
                    background: 'rgba(255,255,255,0.25)', borderRadius: 10,
                    padding: '0 5px', marginLeft: 4, fontSize: 8,
                  }}>
                    {health.urgent_count}
                  </span>
                )}
              </span>
            ))}

            {/* Environment chips — dynamic from API */}
            {envChips.map(env => (
              <span
                key={env}
                className={chipClass(filters.environment === env)}
                onClick={() => toggleEnv(env)}
              >
                {env}
              </span>
            ))}

            {/* Advanced filter toggle */}
            <div style={{ position: 'relative' }} ref={advFilterRef}>
              <div
                className="chip-add"
                title="More filters"
                onClick={() => setShowAdvFilter(v => !v)}
              >
                {showAdvFilter ? '×' : '+'}
              </div>

              {/* Advanced filter dropdown */}
              {showAdvFilter && (
                <div className="chip-filter-panel">
                  {/* Search */}
                  <div style={{ gridColumn: 'span 2' }}>
                    <span className="chip-filter-panel-label">Search server</span>
                    <input
                      className="input"
                      type="text"
                      placeholder="server name…"
                      value={filters.search || ''}
                      onChange={e => setFilter('search', e.target.value)}
                      style={{ fontSize: 12 }}
                    />
                  </div>

                  {/* Criticality */}
                  {filterOptions?.criticalities?.length > 0 && (
                    <div>
                      <span className="chip-filter-panel-label">Criticality</span>
                      <select
                        className="select"
                        value={filters.criticality || ''}
                        onChange={e => setFilter('criticality', e.target.value)}
                        style={{ width: '100%', fontSize: 11 }}
                      >
                        <option value="">Any</option>
                        {filterOptions.criticalities.map(v => (
                          <option key={v} value={v}>{v}</option>
                        ))}
                      </select>
                    </div>
                  )}

                  {/* App Code */}
                  {filterOptions?.app_codes?.length > 0 && (
                    <div>
                      <span className="chip-filter-panel-label">App Code</span>
                      <select
                        className="select"
                        value={filters.app_code || ''}
                        onChange={e => setFilter('app_code', e.target.value)}
                        style={{ width: '100%', fontSize: 11 }}
                      >
                        <option value="">Any</option>
                        {filterOptions.app_codes.map(v => (
                          <option key={v} value={v}>{v}</option>
                        ))}
                      </select>
                    </div>
                  )}

                  {/* All environments (if more than 4) */}
                  {(filterOptions?.environments || []).length > 4 && (
                    <div>
                      <span className="chip-filter-panel-label">Environment</span>
                      <select
                        className="select"
                        value={filters.environment || ''}
                        onChange={e => setFilter('environment', e.target.value)}
                        style={{ width: '100%', fontSize: 11 }}
                      >
                        <option value="">Any</option>
                        {filterOptions.environments.map(v => (
                          <option key={v} value={v}>{v}</option>
                        ))}
                      </select>
                    </div>
                  )}

                  {/* Clear button */}
                  {hasAnyFilter && (
                    <div style={{ gridColumn: 'span 2', paddingTop: 4 }}>
                      <button
                        className="btn-secondary"
                        onClick={() => { clearAllFilters(); setShowAdvFilter(false) }}
                        style={{ width: '100%', fontSize: 11 }}
                      >
                        ✕ Clear all filters
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Tab row */}
          <div className="tab-row">
            {TABS.map(tab => (
              <div
                key={tab.key}
                className={`shell-tab ${activeTab === tab.key ? 'active' : ''}`}
                onClick={() => setActiveTab(tab.key)}
              >
                <span className="tkick">{tab.kick}</span>
                <span className="tlbl">{tab.label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* ══ BODY ════════════════════════════════════════════════════════ */}
        <div className="shell-body">
          {hasData ? (
            <>
              {activeTab === 'overview'  && <ErrorBoundary key="ov" fallbackTitle="Overview failed"><Overview  filters={filters} /></ErrorBoundary>}
              {activeTab === 'analytics' && <ErrorBoundary key="an" fallbackTitle="Analytics failed"><Analytics filters={filters} /></ErrorBoundary>}
              {activeTab === 'capacity'  && <ErrorBoundary key="ca" fallbackTitle="Capacity failed"><Capacity  filters={filters} /></ErrorBoundary>}
              {activeTab === 'triage'    && <ErrorBoundary key="tr" fallbackTitle="Triage failed"><Triage    filters={filters} /></ErrorBoundary>}
            </>
          ) : (
            <div className="empty-state">
              <div className="empty-icon">◆</div>
              <div className="empty-title">Welcome to DB Infra OPS</div>
              <p className="empty-sub">
                Connect your Zabbix API to start monitoring infrastructure health,
                capacity forecasts, and incident triage.
              </p>
              <button className="btn-primary" onClick={() => setShowFetch(true)}>
                ⚡ Configure Data Source
              </button>
            </div>
          )}
        </div>

      </div>{/* /shell */}

      {/* ══ FETCH MODAL ═════════════════════════════════════════════════ */}
      {showFetch && (
        <div className="fetch-modal-overlay" onClick={e => { if (e.target === e.currentTarget) setShowFetch(false) }}>
          <div className="fetch-modal">
            <FetchForm onClose={() => setShowFetch(false)} />
          </div>
        </div>
      )}

    </div>
  )
}
