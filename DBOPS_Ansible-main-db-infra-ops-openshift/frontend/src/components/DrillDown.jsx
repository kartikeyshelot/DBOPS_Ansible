import React, { useState, useEffect, useCallback } from 'react'
import Plot from 'react-plotly.js'
import { useDrilldown, useUpdateTriage, useAdvancedForecast, useTriage } from '../hooks/useData'

const STATUS_OPTIONS = ['Open', 'In Progress', 'Fixed', 'Won\'t Fix']
const STATUS_BADGE = {
  'Open': 'badge badge-open',
  'In Progress': 'badge badge-in-progress',
  'Fixed': 'badge badge-fixed',
  "Won't Fix": 'badge badge-none',
}

export default function DrillDown({ serverName, triageStatus, onClose }) {
  const { data, isLoading } = useDrilldown(serverName)
  const { data: advForecast } = useAdvancedForecast(serverName)
  const { data: allTriage } = useTriage()
  const mutation = useUpdateTriage()
  const [status, setStatus] = useState(triageStatus || 'Open')
  const [notes, setNotes] = useState('')
  const [notesSaved, setNotesSaved] = useState(false)
  const notesSavedTimerRef = React.useRef(null)

  // Clean up the toast timer on unmount
  useEffect(() => () => {
    if (notesSavedTimerRef.current) clearTimeout(notesSavedTimerRef.current)
  }, [])

  useEffect(() => { setStatus(triageStatus || 'Open') }, [serverName, triageStatus])

  // Load saved notes when triage data arrives
  useEffect(() => {
    if (allTriage?.[serverName]?.notes !== undefined) {
      setNotes(allTriage[serverName].notes || '')
    }
  }, [allTriage, serverName])

  const handleStatusChange = (e) => {
    const newStatus = e.target.value
    setStatus(newStatus)
    mutation.mutate({ serverName, status: newStatus, notes })
  }

  const handleNotesSave = useCallback(() => {
    mutation.mutate(
      { serverName, status, notes },
      {
        onSuccess: () => {
          setNotesSaved(true)
          if (notesSavedTimerRef.current) clearTimeout(notesSavedTimerRef.current)
          notesSavedTimerRef.current = setTimeout(() => setNotesSaved(false), 2000)
        },
      }
    )
  }, [serverName, status, notes, mutation])

  const info = data?.server_info || {}
  const events = data?.recent_events || []
  const forecast = data?.forecast

  return (
    <>
      <div className="slide-overlay" onClick={onClose} />
      <div className="slide-panel">
        {/* Header */}
        <div style={{
          padding: '20px 24px', borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          position: 'sticky', top: 0, background: 'var(--bg-card)', zIndex: 1,
        }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, fontFamily: 'Outfit' }}>{serverName}</h2>
            <div style={{ display: 'flex', gap: 8, marginTop: 6, alignItems: 'center' }}>
              {info.priority && <span className={`badge badge-${info.priority?.toLowerCase()}`}>{info.priority}</span>}
              {info.environment && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{info.environment}</span>}
            </div>
          </div>
          <button onClick={onClose} style={{
            background: 'var(--bg-canvas)', border: 'none', borderRadius: 8,
            width: 36, height: 36, cursor: 'pointer', fontSize: 16,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: 'var(--text-muted)',
          }}>✕</button>
        </div>

        {isLoading ? (
          <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-muted)' }}>Loading...</div>
        ) : (
          <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* Triage Status */}
            <div className="card card-padded">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                <div>
                  <div className="kpi-label">Triage Status</div>
                  <span className={STATUS_BADGE[status] || 'badge badge-none'} style={{ marginTop: 6 }}>{status}</span>
                </div>
                <select className="select" value={status} onChange={handleStatusChange} style={{ width: 160 }}>
                  {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                  <div className="kpi-label">Notes</div>
                  {notesSaved && (
                    <span style={{ fontSize: 11, color: 'var(--success)', fontWeight: 600 }}>✓ Saved</span>
                  )}
                </div>
                <textarea
                  value={notes}
                  onChange={e => setNotes(e.target.value)}
                  onBlur={handleNotesSave}
                  placeholder="What's being done? Who's handling it? Any context for the team..."
                  rows={3}
                  style={{
                    width: '100%', boxSizing: 'border-box',
                    background: 'var(--bg-canvas)', border: '1px solid var(--border)',
                    borderRadius: 8, padding: '8px 12px',
                    fontSize: 13, color: 'var(--text-primary)',
                    fontFamily: 'Plus Jakarta Sans, sans-serif',
                    resize: 'vertical', lineHeight: 1.5, outline: 'none',
                  }}
                  onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleNotesSave() }}
                />
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                  Auto-saves on focus-out · Ctrl+Enter to save now
                </div>
              </div>
            </div>

            {/* Key Metrics */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
              {[
                { label: 'Load', value: `${(info.current_load || 0).toFixed(1)}%`,
                  color: (info.current_load || 0) > 80 ? 'var(--critical)' : (info.current_load || 0) > 60 ? 'var(--warning)' : 'var(--success)' },
                { label: 'Alerts', value: info.total_alerts || 0,
                  color: (info.total_alerts || 0) > 5 ? 'var(--critical)' : 'var(--text-primary)' },
                { label: 'Days Left', value: info.days_left || '999',
                  color: (info.days_left || 999) < 30 ? 'var(--critical)' : (info.days_left || 999) < 90 ? 'var(--warning)' : 'var(--success)' },
              ].map(m => (
                <div key={m.label} className="kpi-card" style={{ padding: '14px 16px' }}>
                  <div className="kpi-label">{m.label}</div>
                  <div style={{ fontFamily: 'Outfit', fontSize: 22, fontWeight: 700, color: m.color }}>{m.value}</div>
                </div>
              ))}
            </div>

            {/* Hardware */}
            <div className="card card-padded">
              <div className="kpi-label" style={{ marginBottom: 12 }}>Hardware</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, fontSize: 13 }}>
                {[
                  { label: 'vCPUs', value: info.cpu_count || 0 },
                  { label: 'RAM', value: `${(info.ram_gb || 0).toFixed(1)} GB` },
                  { label: 'Max Disk Util', value: `${(info.max_disk_util || 0).toFixed(1)}%` },
                  { label: 'Min Free GB', value: `${(info.min_free_gb || 0).toFixed(1)} GB` },
                ].map(m => (
                  <div key={m.label} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--border-light)' }}>
                    <span style={{ color: 'var(--text-muted)' }}>{m.label}</span>
                    <span style={{ fontWeight: 600 }}>{m.value}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Risk & Action */}
            {info.risk_category && info.risk_category !== 'Healthy' && (
              <div style={{ padding: '14px 18px', borderRadius: 'var(--radius-sm)', background: 'var(--warning-bg)', border: '1px solid rgba(245,158,11,0.15)' }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: '#b45309', marginBottom: 4 }}>⚠ Risk Identified</div>
                <div style={{ fontSize: 13, color: '#92400e' }}>{info.risk_category}</div>
                {info.action && <div style={{ fontSize: 12, color: '#a16207', marginTop: 4 }}>Action: {info.action}</div>}
              </div>
            )}

            {/* Advanced Forecast Chart */}
            {advForecast && advForecast.actual_dates && advForecast.actual_dates.length > 0 && (
              <div className="card" style={{ overflow: 'hidden' }}>
                <div style={{ padding: '16px 20px 0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div className="kpi-label">Capacity Forecast</div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                      Trend: <span style={{
                        fontWeight: 600,
                        color: advForecast.trend === 'rising_fast' ? 'var(--critical)'
                          : advForecast.trend === 'rising' ? 'var(--warning)'
                          : advForecast.trend === 'falling_fast' || advForecast.trend === 'falling' ? 'var(--success)'
                          : 'var(--text-muted)',
                      }}>
                        {advForecast.trend === 'rising_fast' ? '↑↑ Rising Fast'
                          : advForecast.trend === 'rising' ? '↑ Rising'
                          : advForecast.trend === 'falling_fast' ? '↓↓ Falling Fast'
                          : advForecast.trend === 'falling' ? '↓ Falling'
                          : '→ Stable'}
                      </span>
                      {advForecast.r_squared > 0 && (
                        <span style={{ marginLeft: 8, color: 'var(--text-muted)' }}>
                          R² = {advForecast.r_squared} ({advForecast.model_degree === 2 ? 'quadratic' : 'linear'})
                        </span>
                      )}
                    </div>
                  </div>
                  {advForecast.days_left < 999 && (
                    <span style={{
                      fontFamily: 'Outfit', fontSize: 16, fontWeight: 700,
                      color: advForecast.days_left < 30 ? 'var(--critical)' : advForecast.days_left < 90 ? 'var(--warning)' : 'var(--success)',
                    }}>
                      {advForecast.days_left}d left
                    </span>
                  )}
                </div>
                <Plot
                  data={[
                    // Actual data
                    { x: advForecast.actual_dates, y: advForecast.actual_values, type: 'scatter', mode: 'lines+markers',
                      name: 'Actual', line: { color: '#3b82f6', width: 2 }, marker: { size: 3 } },
                    // Confidence band (upper)
                    ...(advForecast.upper_bound?.length > 0 ? [{
                      x: advForecast.forecast_dates, y: advForecast.upper_bound,
                      type: 'scatter', mode: 'lines', name: '95% CI',
                      line: { width: 0 }, showlegend: false,
                    }] : []),
                    // Confidence band (lower, with fill)
                    ...(advForecast.lower_bound?.length > 0 ? [{
                      x: advForecast.forecast_dates, y: advForecast.lower_bound,
                      type: 'scatter', mode: 'lines', name: '95% CI',
                      line: { width: 0 }, fill: 'tonexty', fillcolor: 'rgba(245,158,11,0.1)',
                    }] : []),
                    // Forecast line
                    ...(advForecast.forecast_dates?.length > 0 ? [{
                      x: advForecast.forecast_dates, y: advForecast.forecast_values,
                      type: 'scatter', mode: 'lines', name: 'Forecast',
                      line: { color: '#f59e0b', width: 2, dash: 'dash' },
                    }] : []),
                    // 95% threshold line
                    { x: [...(advForecast.actual_dates || []), ...(advForecast.forecast_dates || [])],
                      y: Array((advForecast.actual_dates?.length || 0) + (advForecast.forecast_dates?.length || 0)).fill(95),
                      type: 'scatter', mode: 'lines', name: '95% Threshold',
                      line: { color: '#ef4444', width: 1, dash: 'dot' },
                    },
                  ]}
                  layout={{
                    height: 220, margin: { t: 8, b: 36, l: 44, r: 16 },
                    paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
                    font: { family: 'Plus Jakarta Sans', size: 10, color: '#94a3b8' },
                    xaxis: { gridcolor: '#f1f5f9' },
                    yaxis: { gridcolor: '#f1f5f9', title: { text: '%', font: { size: 10 } }, range: [0, 105] },
                    legend: { orientation: 'h', y: 1.15, font: { size: 10 } },
                    showlegend: true,
                  }}
                  config={{ displayModeBar: false, responsive: true }}
                  style={{ width: '100%' }}
                />
              </div>
            )}
            {/* Fallback to simple forecast if advanced not available */}
            {(!advForecast || !advForecast.actual_dates) && forecast?.dates && forecast.dates.length > 0 && (
              <div className="card" style={{ overflow: 'hidden' }}>
                <div style={{ padding: '16px 20px 0' }}>
                  <div className="kpi-label">Capacity Forecast</div>
                </div>
                <Plot
                  data={[
                    { x: forecast.dates, y: forecast.values, type: 'scatter', mode: 'lines', name: 'Actual',
                      line: { color: '#3b82f6', width: 2 } },
                    ...(forecast.forecast_dates ? [{
                      x: forecast.forecast_dates, y: forecast.forecast_values, type: 'scatter', mode: 'lines', name: 'Forecast',
                      line: { color: '#f59e0b', width: 2, dash: 'dash' },
                    }] : []),
                  ]}
                  layout={{
                    height: 200, margin: { t: 8, b: 36, l: 44, r: 16 },
                    paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
                    font: { family: 'Plus Jakarta Sans', size: 10, color: '#94a3b8' },
                    xaxis: { gridcolor: '#f1f5f9' },
                    yaxis: { gridcolor: '#f1f5f9', title: { text: '%', font: { size: 10 } } },
                    legend: { orientation: 'h', y: 1.12, font: { size: 10 } },
                    showlegend: true,
                  }}
                  config={{ displayModeBar: false, responsive: true }}
                  style={{ width: '100%' }}
                />
              </div>
            )}

            {/* Recent Events */}
            {events.length > 0 && (
              <div className="card" style={{ overflow: 'hidden' }}>
                <div style={{ padding: '16px 20px 12px' }}>
                  <div className="kpi-label">Recent Events ({events.length})</div>
                </div>
                <div style={{ maxHeight: 280, overflowY: 'auto' }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Problem</th>
                        <th>Severity</th>
                      </tr>
                    </thead>
                    <tbody>
                      {events.slice(0, 30).map((ev, i) => (
                        <tr key={i}>
                          <td style={{ whiteSpace: 'nowrap', fontSize: 12 }}>{new Date(ev.date).toLocaleDateString()}</td>
                          <td style={{ fontSize: 12 }}>{ev.problem_name}</td>
                          <td>
                            <span className={`badge ${ev.severity === 'Disaster' || ev.severity === 'High' ? 'badge-urgent' : ev.severity === 'Average' ? 'badge-medium' : 'badge-low'}`}>
                              {ev.severity}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Diagnostic */}
            {info.diagnostic && (
              <div className="card card-padded">
                <div className="kpi-label" style={{ marginBottom: 8 }}>AI Diagnostic</div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>{info.diagnostic}</div>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  )
}
