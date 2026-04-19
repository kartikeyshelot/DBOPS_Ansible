import React, { useState } from 'react'
import Plot from 'react-plotly.js'
import {
  useServers, useFleetHealth, useNeedsAttention,
  useSeverityTrend, useRiskMatrix,
} from '../hooks/useData'
import ScatterQuadrant from '../components/ScatterQuadrant'
import ServerTable from '../components/ServerTable'
import DrillDown from '../components/DrillDown'

function ChartSkeleton({ height = 200 }) {
  return (
    <div className="card" style={{ height, position: 'relative', overflow: 'hidden' }}>
      <div style={{
        position: 'absolute', inset: 0,
        background: 'linear-gradient(90deg, var(--bg-canvas) 25%, var(--bg-card) 50%, var(--bg-canvas) 75%)',
        backgroundSize: '200% 100%', animation: 'shimmer 1.5s infinite',
      }} />
      <style>{`@keyframes shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }`}</style>
    </div>
  )
}

function buildExportUrl(endpoint, filters = {}) {
  const url = new URL(`/api/export/${endpoint}`, window.location.origin)
  Object.entries(filters).forEach(([k, v]) => { if (v) url.searchParams.set(k, v) })
  return url.toString()
}

function ExportButton({ href, label = 'Export CSV' }) {
  return (
    <a href={href} download
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        padding: '5px 12px', borderRadius: 6, fontSize: 12, fontWeight: 500,
        background: 'var(--bg-canvas)', border: '1px solid var(--border)',
        color: 'var(--text-secondary)', textDecoration: 'none', cursor: 'pointer',
      }}>
      ⬇ {label}
    </a>
  )
}

export default function Overview({ filters }) {
  const { data: servers, isLoading: serversLoading } = useServers(filters)
  const { data: health } = useFleetHealth(filters)
  const { data: needsAttention } = useNeedsAttention(filters)
  const { data: severityTrend } = useSeverityTrend(filters)
  const { data: riskMatrix } = useRiskMatrix(filters)

  const [drillServer, setDrillServer] = useState(null)
  const openDrill = (name, triageStatus) => setDrillServer({ name, triageStatus })
  const closeDrill = () => setDrillServer(null)

  const totalServers = servers?.length || 0
  const urgentCount  = servers?.filter(s => s.priority === 'URGENT').length || 0
  const highCount    = servers?.filter(s => s.priority === 'HIGH').length || 0
  const healthyCount = servers?.filter(s => s.risk_category === 'Healthy').length || 0

  return (
    <div>
      {/* KPI Cards Row */}
      <div className="stagger-in" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 12 }}>
        <div className="kpi-card">
          <div className="kpi-label">Total Servers</div>
          <div className="kpi-value">{totalServers}</div>
          <div className="kpi-sub">Monitored infrastructure</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Urgent</div>
          <div className={`kpi-value ${urgentCount > 0 ? 'critical' : ''}`}>{urgentCount}</div>
          <div className="kpi-sub">
            {urgentCount > 0 ? 'Requires immediate action' : 'All clear'}
          </div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">High Priority</div>
          <div className={`kpi-value ${highCount > 0 ? 'warning' : ''}`}>{highCount}</div>
          <div className="kpi-sub">Needs attention soon</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Healthy</div>
          <div className="kpi-value success">{healthyCount}</div>
          <div className="kpi-sub">
            {totalServers > 0 ? `${Math.round(healthyCount / totalServers * 100)}% of fleet` : '—'}
          </div>
        </div>
      </div>

      {/* Hardware Inventory Row */}
      {health && (health.total_vcpus > 0 || health.total_ram_gb > 0) && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginBottom: 18 }}>
          <div className="hw-card">
            <div className="kpi-label">Provisioned vCPUs</div>
            <div className="hw-num" style={{ color: '#6355C7' }}>
              {(health.total_vcpus || 0).toLocaleString()}
            </div>
            <div className="kpi-sub">Fleet avg load {health.avg_load}%</div>
            <div className="hw-bar">
              <div className="hw-fill" style={{ width: `${Math.min(health.avg_load || 0, 100)}%`, background: '#6355C7' }} />
            </div>
          </div>
          <div className="hw-card">
            <div className="kpi-label">Total RAM</div>
            <div className="hw-num" style={{ color: '#1D5799' }}>
              {health.total_ram_gb >= 1024
                ? `${(health.total_ram_gb / 1024).toFixed(1)} TB`
                : `${health.total_ram_gb} GB`}
            </div>
            <div className="kpi-sub">Across {totalServers} servers</div>
            <div className="hw-bar">
              <div className="hw-fill" style={{ background: '#1D5799', width: '60%' }} />
            </div>
          </div>
          <div className="hw-card">
            <div className="kpi-label">Total Disk</div>
            <div className="hw-num" style={{ color: health.disks_at_risk > 0 ? 'var(--critical)' : '#3B6D11' }}>
              {health.total_disk_tb >= 1
                ? `${health.total_disk_tb} TB`
                : `${(health.total_disk_tb * 1024).toFixed(0)} GB`}
            </div>
            <div className="kpi-sub" style={{ color: health.disks_at_risk > 0 ? 'var(--critical)' : 'var(--ink-muted)' }}>
              {health.disks_at_risk > 0 ? `⚠ ${health.disks_at_risk} drives at risk` : 'All drives healthy'}
            </div>
            <div className="hw-bar">
              <div className="hw-fill" style={{ background: health.disks_at_risk > 0 ? 'var(--critical)' : '#3B6D11', width: '58%' }} />
            </div>
          </div>
        </div>
      )}

      {/* Charts Row — scatter + needs attention */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 24 }}>
        {serversLoading
          ? <ChartSkeleton height={320} />
          : <ScatterQuadrant servers={servers} onServerClick={(s) => openDrill(s.name, s.triage_status)} />
        }

        {needsAttention && needsAttention.length > 0 && (
          <div className="card" style={{ overflow: 'hidden' }}>
            <div style={{ padding: '16px 20px 12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h4 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>⚠ Needs Attention</h4>
                <p style={{ margin: '2px 0 0', fontSize: 12, color: 'var(--text-muted)' }}>
                  Monitoring blind spots &amp; compound risks — servers where metrics suggest a problem but alerts may not be firing
                </p>
              </div>
              <span className="badge badge-urgent">{needsAttention.length}</span>
            </div>
            <div style={{ maxHeight: 280, overflowY: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr><th>Server</th><th>Load</th><th>Alerts</th><th>Flag</th><th>Reason</th></tr>
                </thead>
                <tbody>
                  {needsAttention.map((s, i) => (
                    <tr key={i} onClick={() => openDrill(s.name, s.triage_status)} style={{ cursor: 'pointer' }}>
                      <td style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: 12 }}>{s.name}</td>
                      <td style={{ fontSize: 12 }}>{(s.current_load || 0).toFixed(1)}%</td>
                      <td style={{ fontSize: 12 }}>{s.total_alerts}</td>
                      <td>
                        <span className={`badge ${s.flag === 'Silent Failure' ? 'badge-urgent' : 'badge-medium'}`} style={{ fontSize: 10 }}>
                          {s.flag}
                        </span>
                      </td>
                      <td style={{ fontSize: 11, color: 'var(--text-muted)', maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {s.diagnostic || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Severity Trend */}
      {severityTrend && severityTrend.length > 0 && (() => {
        const SEV_ORDER  = ['Disaster', 'High', 'Average', 'Warning', 'Info', 'Not classified']
        const SEV_COLORS = {
          Disaster: '#ef4444', High: '#f97316', Average: '#eab308',
          Warning: '#7c66dc', Info: '#94a3b8', 'Not classified': '#cbd5e1',
        }
        const days       = [...new Set(severityTrend.map(r => r.Day))].sort()
        const severities = [...new Set(severityTrend.map(r => r.severity))]
          .sort((a, b) => SEV_ORDER.indexOf(a) - SEV_ORDER.indexOf(b))

        const traces = severities.map(sev => {
          const bySev  = severityTrend.filter(r => r.severity === sev)
          const lookup = Object.fromEntries(bySev.map(r => [r.Day, r.count]))
          return {
            name: sev, type: 'scatter', mode: 'lines+markers',
            x: days, y: days.map(d => lookup[d] || 0),
            line: { color: SEV_COLORS[sev] || '#94a3b8', width: 2 },
            marker: { size: 4 },
            hovertemplate: `<b>${sev}</b><br>%{x}: %{y} alerts<extra></extra>`,
          }
        })

        return (
          <div style={{ marginBottom: 24 }}>
            <div style={{ marginBottom: 12 }}>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>📅 Alert Severity Over Time</h3>
              <p style={{ margin: '2px 0 0', fontSize: 12, color: 'var(--text-muted)' }}>
                Daily count per severity — rising lines need investigation; falling lines confirm improvements
              </p>
            </div>
            <div className="card" style={{ overflow: 'hidden' }}>
              <Plot
                data={traces}
                layout={{
                  height: 260, margin: { t: 12, b: 48, l: 44, r: 16 },
                  paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
                  font: { family: 'Plus Jakarta Sans', size: 11, color: '#8A7A68' },
                  xaxis: { gridcolor: 'rgba(28,20,16,0.06)', tickangle: -35 },
                  yaxis: { gridcolor: 'rgba(28,20,16,0.06)', title: { text: 'Alerts', font: { size: 11 } } },
                  legend: { orientation: 'h', y: -0.22, x: 0 },
                  hovermode: 'x unified',
                }}
                config={{ displayModeBar: false, responsive: true }}
                style={{ width: '100%' }}
              />
            </div>
          </div>
        )
      })()}

      {/* Risk Matrix */}
      {riskMatrix && riskMatrix.length > 0 && (() => {
        const PRIORITY_COLORS = { URGENT: '#ef4444', HIGH: '#f97316', MEDIUM: '#3b82f6', LOW: '#10b981' }
        const PRIORITY_ORDER  = ['URGENT', 'HIGH', 'MEDIUM', 'LOW']
        const envs       = [...new Set(riskMatrix.map(r => r.Environment))].sort()
        const priorities = [...new Set(riskMatrix.map(r => r.Priority))]
          .sort((a, b) => PRIORITY_ORDER.indexOf(a) - PRIORITY_ORDER.indexOf(b))

        const traces = priorities.map(p => {
          const lookup = Object.fromEntries(
            riskMatrix.filter(r => r.Priority === p).map(r => [r.Environment, r.count])
          )
          return {
            name: p, type: 'bar',
            x: envs, y: envs.map(e => lookup[e] || 0),
            marker: { color: PRIORITY_COLORS[p] || '#94a3b8' },
            hovertemplate: `<b>${p}</b><br>%{x}: %{y} servers<extra></extra>`,
          }
        })

        return (
          <div style={{ marginBottom: 24 }}>
            <div style={{ marginBottom: 12 }}>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>🗂 Risk by Environment</h3>
              <p style={{ margin: '2px 0 0', fontSize: 12, color: 'var(--text-muted)' }}>
                Production URGENT/HIGH bars should be the first thing actioned every morning
              </p>
            </div>
            <div className="card" style={{ overflow: 'hidden' }}>
              <Plot
                data={traces}
                layout={{
                  barmode: 'group', height: 220,
                  margin: { t: 12, b: 48, l: 44, r: 16 },
                  paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
                  font: { family: 'Plus Jakarta Sans', size: 11, color: '#8A7A68' },
                  xaxis: { gridcolor: 'rgba(28,20,16,0.06)' },
                  yaxis: { gridcolor: 'rgba(28,20,16,0.06)', title: { text: 'Servers', font: { size: 11 } } },
                  legend: { orientation: 'h', y: -0.25, x: 0 },
                }}
                config={{ displayModeBar: false, responsive: true }}
                style={{ width: '100%' }}
              />
            </div>
          </div>
        )
      })()}

      {/* Server Table */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <div>
            <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>All Servers</h3>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{totalServers} total</span>
          </div>
          <ExportButton href={buildExportUrl('servers', filters)} label="Export Servers CSV" />
        </div>
        {serversLoading
          ? <ChartSkeleton height={200} />
          : <ServerTable servers={servers} onSelect={(s) => openDrill(s.name, s.triage_status)} />
        }
      </div>

      {drillServer && (
        <DrillDown serverName={drillServer.name} triageStatus={drillServer.triageStatus} onClose={closeDrill} />
      )}
    </div>
  )
}
