import React from 'react'
import Plot from 'react-plotly.js'
import { useServers, useRunwayOverview, useDatabases, useDbDiskCorrelation, useRightSizing } from '../hooks/useData'

const CHART_LAYOUT = {
  paper_bgcolor: 'transparent',
  plot_bgcolor: 'transparent',
  font: { family: 'Plus Jakarta Sans', size: 11, color: '#8A7A68' },
  margin: { t: 12, b: 40, l: 52, r: 16 },
}

const CHART_CONFIG = { displayModeBar: false, responsive: true }

function Section({ title, subtitle, exportHref, children }) {
  return (
    <div style={{ marginBottom: 32 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
        <div>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>{title}</h3>
          {subtitle && <p style={{ margin: '2px 0 0', fontSize: 12, color: 'var(--ink-muted)' }}>{subtitle}</p>}
        </div>
        {exportHref && (
          <a href={exportHref} download style={{
            display: 'inline-flex', alignItems: 'center', gap: 6, flexShrink: 0,
            padding: '5px 12px', borderRadius: 6, fontSize: 12, fontWeight: 500,
            background: 'var(--bg-canvas)', border: '1px solid var(--border)',
            color: 'var(--text-secondary)', textDecoration: 'none',
          }}>⬇ Export CSV</a>
        )}
      </div>
      {children}
    </div>
  )
}

class CapacityErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { hasError: false, error: null } }
  static getDerivedStateFromError(error) { return { hasError: true, error } }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ textAlign: 'center', padding: '80px 0', color: 'var(--text-muted)' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>⚠️</div>
          <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>Something went wrong</div>
          <div style={{ fontSize: 13, marginBottom: 16 }}>Error rendering capacity data. Try refreshing.</div>
          <div style={{ fontSize: 11, fontFamily: 'monospace', background: '#f1f5f9', padding: 12, borderRadius: 8, maxWidth: 400, margin: '0 auto', textAlign: 'left' }}>
            {this.state.error?.message || 'Unknown error'}
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

const sf  = (v, d = 0) => { const n = Number(v); return (isNaN(n) || !isFinite(n)) ? d : n }
const fmt = (v, dp = 1) => sf(v).toFixed(dp)

// Sticky table head for nested-scroll tables
const StickyThead = ({ children }) => (
  <thead style={{ position: 'sticky', top: 0, zIndex: 2, background: 'var(--bg-canvas)' }}>
    {children}
  </thead>
)

function buildExportUrl(endpoint, filters = {}) {
  const url = new URL(`/api/export/${endpoint}`, window.location.origin)
  Object.entries(filters).forEach(([k, v]) => { if (v) url.searchParams.set(k, v) })
  return url.toString()
}

export default function Capacity({ filters }) {
  const { data: servers }   = useServers(filters)
  const { data: runway }    = useRunwayOverview(filters)
  const { data: databases } = useDatabases(filters)
  const { data: diskCorr }  = useDbDiskCorrelation(filters)
  const { data: rightSizing } = useRightSizing(filters)

  return (
    <CapacityErrorBoundary>
    <div>

      {/* ── Capacity Runway ── */}
      {runway && runway.length > 0 && (
        <Section
          title="⏱ Capacity Runway"
          subtitle="Servers closest to resource exhaustion — how long before a resource hits 95% and needs action"
          exportHref={buildExportUrl('runway', filters)}
        >
          {/* Runway explanation callout */}
          <div style={{
            marginBottom: 16, padding: '12px 16px', borderRadius: 8,
            background: 'rgba(59,130,246,0.06)', border: '1px solid rgba(59,130,246,0.18)',
            display: 'flex', gap: 12, alignItems: 'flex-start',
          }}>
            <span style={{ fontSize: 18, flexShrink: 0 }}>📐</span>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
              <strong style={{ color: 'var(--text-primary)', display: 'block', marginBottom: 4 }}>
                How "Runway" is calculated
              </strong>
              <strong>Runway = estimated days until a resource reaches 95% capacity</strong>, based on
              its historical growth trend. The system fits a linear regression to daily CPU/memory
              utilization data collected from Zabbix, then extrapolates forward to find when utilization
              crosses the 95% threshold.{' '}
              <span style={{ color: 'var(--critical)', fontWeight: 500 }}>Red (&lt;30 days)</span>{' '}
              means immediate action is required;{' '}
              <span style={{ color: '#f97316', fontWeight: 500 }}>orange (&lt;90 days)</span>{' '}
              means plan ahead; green means you are comfortable.{' '}
              Servers with flat or declining trends show <em>∞ or 999</em> and are excluded from this list.
            </div>
          </div>

          <div className="stagger-in" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12, marginBottom: 16 }}>
            {runway.slice(0, 8).map((s, i) => (
              <div key={i} className="kpi-card" style={{ padding: '14px 18px' }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>{s.name}</div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                  <span style={{
                    fontFamily: 'Outfit', fontSize: 28, fontWeight: 700,
                    color: s.days_left < 30 ? 'var(--critical)' : s.days_left < 90 ? 'var(--warning)' : 'var(--success)',
                  }}>
                    {s.days_left}
                  </span>
                  <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>days</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
                  <div className="progress-bar" style={{ flex: 1 }}>
                    <div className="progress-fill" style={{
                      width: `${Math.min(s.current_load || 0, 100)}%`,
                      background: (s.current_load || 0) > 80 ? 'var(--critical)' : (s.current_load || 0) > 60 ? 'var(--warning)' : 'var(--success)',
                    }} />
                  </div>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{fmt(s.current_load, 0)}%</span>
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{s.resource_type}</div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* ── Right-Sizing Recommendations ── */}
      {rightSizing && (rightSizing.scale_up?.length > 0 || rightSizing.scale_down?.length > 0) && (
        <Section title="⚖ Right-Sizing Recommendations" subtitle="Comprehensive analysis across vCPU, RAM, and Disk">

          {/* Efficiency legend */}
          <div style={{
            display: 'flex', gap: 20, marginBottom: 16, padding: '10px 16px',
            borderRadius: 8, background: 'var(--bg-canvas)', border: '1px solid var(--border)',
            fontSize: 12, color: 'var(--text-secondary)', flexWrap: 'wrap', alignItems: 'center',
          }}>
            <span style={{ fontWeight: 600, color: 'var(--text-primary)', marginRight: 4 }}>Eff. Score:</span>
            <span>0–100 composite (CPU 40% + RAM 35% + Disk 25%). Sweet spot = 30–70% utilization per resource.</span>
            <span style={{ color: 'var(--success)', fontWeight: 600 }}>≥70 well-sized</span>
            <span style={{ color: 'var(--warning)', fontWeight: 600 }}>30–69 moderate</span>
            <span style={{ color: 'var(--critical)', fontWeight: 600 }}>&lt;30 mis-sized</span>
          </div>

          {/* Scale Up */}
          {rightSizing.scale_up?.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <h4 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: 'var(--critical)' }}>↑ Scale Up</h4>
                  <span className="badge badge-urgent">{rightSizing.scale_up.length}</span>
                </div>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Resource-starved — need more capacity</span>
              </div>
              {/* Nested scroll container — sticky header + capped height */}
              <div className="card" style={{ overflow: 'hidden' }}>
                <div style={{ overflowX: 'auto' }}>
                  <div style={{ maxHeight: 380, overflowY: 'auto' }}>
                    <table className="data-table" style={{ minWidth: 900 }}>
                      <StickyThead>
                        <tr>
                          <th>Server</th><th>Eff.</th><th>Conf.</th>
                          <th style={{ borderLeft: '2px solid #e2e8f0' }}>vCPU</th><th>CPU Load</th><th>Rec.</th>
                          <th style={{ borderLeft: '2px solid #e2e8f0' }}>RAM</th><th>Mem Load</th><th>Rec.</th>
                          <th style={{ borderLeft: '2px solid #e2e8f0' }}>Disk</th><th>Util</th><th>Action</th>
                        </tr>
                      </StickyThead>
                      <tbody>
                        {rightSizing.scale_up.map((s, i) => (
                          <tr key={i}>
                            <td style={{ fontWeight: 600, fontSize: 12, color: 'var(--text-primary)' }}>{s.server_name}</td>
                            <td>
                              <span style={{
                                fontFamily: 'Outfit', fontWeight: 700, fontSize: 14,
                                color: s.efficiency_score < 30 ? 'var(--critical)' : s.efficiency_score < 60 ? 'var(--warning)' : 'var(--success)',
                              }}>{s.efficiency_score}</span>
                            </td>
                            <td><span className={`badge ${s.confidence === 'High' ? 'badge-low' : s.confidence === 'Medium' ? 'badge-medium' : 'badge-none'}`}>{s.confidence}</span></td>
                            {/* CPU */}
                            <td style={{ borderLeft: '2px solid #f1f5f9', fontSize: 12 }}>{s.cpu?.current || '—'}</td>
                            <td>
                              {s.cpu?.load !== undefined ? (
                                <span style={{ fontSize: 12, fontWeight: 600, color: s.cpu.load > 80 ? 'var(--critical)' : s.cpu.load > 60 ? 'var(--warning)' : 'var(--text-secondary)' }}>
                                  {s.cpu.load}%
                                </span>
                              ) : '—'}
                            </td>
                            <td style={{ fontSize: 12 }}>
                              {s.cpu?.status === 'scale_up' ? (
                                <span style={{ fontWeight: 600, color: 'var(--critical)' }}>→ {s.cpu.recommended} <span style={{ fontSize: 10 }}>({s.cpu.delta > 0 ? '+' : ''}{s.cpu.delta})</span></span>
                              ) : <span style={{ color: 'var(--text-muted)' }}>OK</span>}
                            </td>
                            {/* RAM */}
                            <td style={{ borderLeft: '2px solid #f1f5f9', fontSize: 12 }}>{s.ram?.current_gb || '—'} GB</td>
                            <td>
                              {s.ram?.load !== undefined ? (
                                <span style={{ fontSize: 12, fontWeight: 600, color: s.ram.load > 80 ? 'var(--critical)' : s.ram.load > 60 ? 'var(--warning)' : 'var(--text-secondary)' }}>
                                  {s.ram.load}%
                                </span>
                              ) : '—'}
                            </td>
                            <td style={{ fontSize: 12 }}>
                              {s.ram?.status === 'scale_up' ? (
                                <span style={{ fontWeight: 600, color: 'var(--critical)' }}>→ {s.ram.recommended_gb} GB <span style={{ fontSize: 10 }}>({s.ram.delta_gb > 0 ? '+' : ''}{s.ram.delta_gb})</span></span>
                              ) : <span style={{ color: 'var(--text-muted)' }}>OK</span>}
                            </td>
                            {/* Disk */}
                            <td style={{ borderLeft: '2px solid #f1f5f9', fontSize: 12 }}>{s.disk?.current_total_gb || '—'} GB</td>
                            <td>
                              {s.disk?.util_pct !== undefined ? (
                                <span style={{ fontSize: 12, fontWeight: 600, color: s.disk.util_pct > 85 ? 'var(--critical)' : s.disk.util_pct > 70 ? 'var(--warning)' : 'var(--text-secondary)' }}>
                                  {s.disk.util_pct}%
                                </span>
                              ) : '—'}
                            </td>
                            <td style={{ fontSize: 11 }}>
                              {s.disk?.status === 'expand' ? (
                                <span style={{ fontWeight: 600, color: 'var(--critical)' }}>{s.disk.recommended_action}</span>
                              ) : <span style={{ color: 'var(--text-muted)' }}>OK</span>}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Scale Down */}
          {rightSizing.scale_down?.length > 0 && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <h4 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: 'var(--success)' }}>↓ Scale Down</h4>
                  <span className="badge badge-low">{rightSizing.scale_down.length}</span>
                </div>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Over-provisioned — reclaim resources</span>
              </div>
              <div className="card" style={{ overflow: 'hidden' }}>
                <div style={{ overflowX: 'auto' }}>
                  <div style={{ maxHeight: 380, overflowY: 'auto' }}>
                    <table className="data-table" style={{ minWidth: 900 }}>
                      <StickyThead>
                        <tr>
                          <th>Server</th><th>Eff.</th><th>Conf.</th>
                          <th style={{ borderLeft: '2px solid #e2e8f0' }}>vCPU</th><th>CPU Load</th><th>Rec.</th>
                          <th style={{ borderLeft: '2px solid #e2e8f0' }}>RAM</th><th>Mem Load</th><th>Rec.</th>
                          <th style={{ borderLeft: '2px solid #e2e8f0' }}>Disk</th><th>Util</th><th>Action</th>
                        </tr>
                      </StickyThead>
                      <tbody>
                        {rightSizing.scale_down.map((s, i) => (
                          <tr key={i}>
                            <td style={{ fontWeight: 600, fontSize: 12, color: 'var(--text-primary)' }}>{s.server_name}</td>
                            <td>
                              <span style={{
                                fontFamily: 'Outfit', fontWeight: 700, fontSize: 14,
                                color: s.efficiency_score < 30 ? 'var(--critical)' : s.efficiency_score < 60 ? 'var(--warning)' : 'var(--success)',
                              }}>{s.efficiency_score}</span>
                            </td>
                            <td><span className={`badge ${s.confidence === 'High' ? 'badge-low' : s.confidence === 'Medium' ? 'badge-medium' : 'badge-none'}`}>{s.confidence}</span></td>
                            {/* CPU */}
                            <td style={{ borderLeft: '2px solid #f1f5f9', fontSize: 12 }}>{s.cpu?.current || '—'}</td>
                            <td>
                              {s.cpu?.load !== undefined ? (
                                <span style={{ fontSize: 12, fontWeight: 600, color: s.cpu.load < 15 ? 'var(--info)' : 'var(--text-secondary)' }}>
                                  {s.cpu.load}%
                                </span>
                              ) : '—'}
                            </td>
                            <td style={{ fontSize: 12 }}>
                              {s.cpu?.status === 'scale_down' ? (
                                <span style={{ fontWeight: 600, color: 'var(--success)' }}>→ {s.cpu.recommended} <span style={{ fontSize: 10 }}>({s.cpu.delta})</span></span>
                              ) : <span style={{ color: 'var(--text-muted)' }}>OK</span>}
                            </td>
                            {/* RAM */}
                            <td style={{ borderLeft: '2px solid #f1f5f9', fontSize: 12 }}>{s.ram?.current_gb || '—'} GB</td>
                            <td>
                              {s.ram?.load !== undefined ? (
                                <span style={{ fontSize: 12, fontWeight: 600, color: s.ram.load < 20 ? 'var(--info)' : 'var(--text-secondary)' }}>
                                  {s.ram.load}%
                                </span>
                              ) : '—'}
                            </td>
                            <td style={{ fontSize: 12 }}>
                              {s.ram?.status === 'scale_down' ? (
                                <span style={{ fontWeight: 600, color: 'var(--success)' }}>→ {s.ram.recommended_gb} GB <span style={{ fontSize: 10 }}>({s.ram.delta_gb})</span></span>
                              ) : <span style={{ color: 'var(--text-muted)' }}>OK</span>}
                            </td>
                            {/* Disk */}
                            <td style={{ borderLeft: '2px solid #f1f5f9', fontSize: 12 }}>{s.disk?.current_total_gb || '—'} GB</td>
                            <td>
                              {s.disk?.util_pct !== undefined ? (
                                <span style={{ fontSize: 12, fontWeight: 600, color: s.disk.util_pct < 20 ? 'var(--info)' : 'var(--text-secondary)' }}>
                                  {s.disk.util_pct}%
                                </span>
                              ) : '—'}
                            </td>
                            <td style={{ fontSize: 11 }}>
                              {s.disk?.status === 'shrink' ? (
                                <span style={{ fontWeight: 600, color: 'var(--success)' }}>{s.disk.recommended_action}</span>
                              ) : <span style={{ color: 'var(--text-muted)' }}>OK</span>}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          )}
        </Section>
      )}

      {/* ── Runway Distribution ── */}
      {servers && servers.length > 0 && (() => {
        const buckets = { '0–30d': 0, '31–60d': 0, '61–90d': 0, '91–180d': 0, '181–365d': 0, 'No Risk': 0 }
        servers.forEach(s => {
          const d = sf(s.days_left, 999)
          if (d <= 30)       buckets['0–30d']++
          else if (d <= 60)  buckets['31–60d']++
          else if (d <= 90)  buckets['61–90d']++
          else if (d <= 180) buckets['91–180d']++
          else if (d <= 365) buckets['181–365d']++
          else               buckets['No Risk']++
        })
        const labels  = Object.keys(buckets)
        const values  = Object.values(buckets)
        const colors  = ['#ef4444', '#f97316', '#eab308', '#3b82f6', '#8b5cf6', '#10b981']
        const atRisk  = values.slice(0, 4).reduce((a, b) => a + b, 0)
        return (
          <div className="card" style={{ overflow: 'hidden', marginBottom: 24 }}>
            <div style={{ padding: '16px 20px 4px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h4 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>Runway Distribution</h4>
                <p style={{ margin: '2px 0 0', fontSize: 12, color: 'var(--text-muted)' }}>
                  How many servers exhaust capacity in each time window — based on current growth trend
                </p>
              </div>
              {atRisk > 0 && (
                <span style={{
                  fontSize: 12, fontWeight: 600, padding: '4px 10px', borderRadius: 6,
                  background: 'rgba(239,68,68,0.08)', color: '#ef4444', border: '1px solid rgba(239,68,68,0.2)',
                }}>
                  {atRisk} at risk within 180d
                </span>
              )}
            </div>
            <Plot
              data={[{
                x: labels, y: values, type: 'bar',
                marker: { color: colors, cornerradius: 4 },
                hovertemplate: '%{x}: <b>%{y} servers</b><extra></extra>',
                text: values.map(v => v > 0 ? v : ''),
                textposition: 'outside',
              }]}
              layout={{
                height: 220, margin: { t: 8, b: 40, l: 44, r: 16 },
                paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
                font: { family: 'Plus Jakarta Sans', size: 11, color: '#8A7A68' },
                xaxis: { gridcolor: 'rgba(28,20,16,0.06)' },
                yaxis: { gridcolor: 'rgba(28,20,16,0.06)', title: { text: 'Servers', font: { size: 11 } } },
              }}
              config={{ displayModeBar: false, responsive: true }}
              style={{ width: '100%' }}
            />
          </div>
        )
      })()}

      {/* ── Database Growth ── */}
      {databases && databases.length > 0 && (
        <Section
          title="🗄 Database Growth"
          subtitle="Storage trends and growth rates — how fast each database is consuming disk space"
          exportHref={buildExportUrl('databases', filters)}
        >
          <div className="card" style={{ overflow: 'hidden' }}>
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Server</th><th>Database</th><th>Type</th><th>Size</th>
                    <th>Growth/Day</th><th>Acceleration</th><th>Suggestion</th><th style={{ width: 140 }}>Trend</th>
                  </tr>
                </thead>
                <tbody>
                  {databases.map((d, i) => (
                    <tr key={i}>
                      <td style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: 12 }}>{d.server_name}</td>
                      <td style={{ fontSize: 12 }}>{d.db_name}</td>
                      <td><span className="badge badge-none">{d.db_type}</span></td>
                      <td style={{ fontSize: 12 }}>{d.size_display}</td>
                      <td style={{
                        fontSize: 12, fontWeight: 600,
                        color: d.growth_display?.includes('High') ? 'var(--critical)' : 'var(--text-secondary)',
                      }}>{d.growth_display}</td>
                      <td>
                        {d.growth_acceleration === 'Accelerating' ? (
                          <span style={{
                            display: 'inline-flex', alignItems: 'center', gap: 4,
                            fontSize: 11, fontWeight: 700, color: '#ef4444',
                            background: 'rgba(239,68,68,0.08)', padding: '2px 8px',
                            borderRadius: 6, border: '1px solid rgba(239,68,68,0.2)',
                          }}>
                            ↑ {d.growth_multiplier > 0 ? `${d.growth_multiplier}×` : 'New growth'}
                          </span>
                        ) : d.growth_acceleration === 'Decelerating' ? (
                          <span style={{
                            display: 'inline-flex', alignItems: 'center', gap: 4,
                            fontSize: 11, fontWeight: 600, color: '#10b981',
                            background: 'rgba(16,185,129,0.08)', padding: '2px 8px',
                            borderRadius: 6, border: '1px solid rgba(16,185,129,0.2)',
                          }}>
                            ↓ Slowing
                          </span>
                        ) : (
                          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>→ Stable</span>
                        )}
                      </td>
                      <td>
                        <span className={`badge ${d.suggestion === 'High Growth' ? 'badge-urgent' : d.suggestion === 'Steady' ? 'badge-medium' : d.suggestion === 'Shrinking' ? 'badge-low' : 'badge-none'}`}>
                          {d.suggestion}
                        </span>
                      </td>
                      <td>
                        {d.trend && d.trend.length > 1 && (
                          <Plot
                            data={[{
                              y: d.trend, type: 'scatter', mode: 'lines',
                              line: { color: '#3b82f6', width: 1.5 },
                            }]}
                            layout={{
                              height: 36, width: 120,
                              margin: { t: 2, b: 2, l: 2, r: 2 },
                              paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
                              xaxis: { visible: false }, yaxis: { visible: false },
                            }}
                            config={{ displayModeBar: false, staticPlot: true }}
                          />
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </Section>
      )}

      {/* ── DB Growth vs Disk Free Scatter ── */}
      {diskCorr && diskCorr.length > 0 && (
        <Section
          title="💾 DB Growth vs Disk Free"
          subtitle="Each dot is a server — top-left (high growth, low free space) is the danger zone: disk will fill soon"
        >
          <div className="card" style={{ overflow: 'hidden' }}>
            <Plot
              data={[{
                x: diskCorr.map(d => d.growth_gb_day),
                y: diskCorr.map(d => d.free_gb),
                text: diskCorr.map(d => d.server_name),
                mode: 'markers', type: 'scatter',
                marker: {
                  color: diskCorr.map(d => d.storage_days < 30 ? '#ef4444' : d.storage_days < 90 ? '#f59e0b' : '#10b981'),
                  size: 10, opacity: 0.8,
                  line: { width: 1.5, color: 'white' },
                },
                hovertemplate: '<b>%{text}</b><br>Growth: %{x:.2f} GB/day<br>Free: %{y:.1f} GB<extra></extra>',
              }]}
              layout={{
                ...CHART_LAYOUT, height: 340,
                xaxis: { title: { text: 'DB Growth (GB/day)', font: { size: 11 } }, gridcolor: 'rgba(28,20,16,0.06)' },
                yaxis: { title: { text: 'Free Disk (GB)', font: { size: 11 } }, gridcolor: 'rgba(28,20,16,0.06)' },
              }}
              config={CHART_CONFIG}
              style={{ width: '100%' }}
            />
          </div>
        </Section>
      )}

      {/* Empty State */}
      {(!servers || servers.length === 0) && (
        <div style={{ textAlign: 'center', padding: '80px 0', color: 'var(--text-muted)' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>📊</div>
          <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>No capacity data yet</div>
          <div style={{ fontSize: 13 }}>Fetch data from Zabbix to see forecasts and recommendations.</div>
        </div>
      )}
    </div>
    </CapacityErrorBoundary>
  )
}
