import React from 'react'
import Plot from 'react-plotly.js'
import { useAnalyticsBundle } from '../hooks/useData'

function Section({ title, subtitle, children, exportHref }) {
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
          }}>
            ⬇ Export CSV
          </a>
        )}
      </div>
      {children}
    </div>
  )
}

function MetricCard({ label, value, color, subtitle }) {
  return (
    <div className="kpi-card">
      <div className="kpi-label">{label}</div>
      <div style={{
        fontFamily: 'Outfit', fontSize: 28, fontWeight: 700,
        color: color || 'var(--text-primary)', lineHeight: 1, letterSpacing: '-0.03em',
      }}>{value}</div>
      {subtitle && <div style={{ fontSize: 12, color: 'var(--ink-muted)' }}>{subtitle}</div>}
    </div>
  )
}

function ChartSkeleton({ height = 200 }) {
  return (
    <div className="card" style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden', position: 'relative' }}>
      <div style={{
        position: 'absolute', inset: 0,
        background: 'linear-gradient(90deg, var(--bg-canvas) 25%, var(--bg-card) 50%, var(--bg-canvas) 75%)',
        backgroundSize: '200% 100%', animation: 'shimmer 1.5s infinite',
      }} />
      <style>{`@keyframes shimmer { 0% { background-position: 200% 0 } 100% { background-position: -200% 0 } }`}</style>
    </div>
  )
}

function KpiSkeleton() {
  return (
    <div className="kpi-card" style={{ position: 'relative', overflow: 'hidden', minHeight: 80 }}>
      <div style={{
        position: 'absolute', inset: 0,
        background: 'linear-gradient(90deg, var(--bg-canvas) 25%, var(--bg-card) 50%, var(--bg-canvas) 75%)',
        backgroundSize: '200% 100%', animation: 'shimmer 1.5s infinite',
      }} />
    </div>
  )
}

const STABILITY_COLORS = { Volatile: '#ef4444', Moderate: '#f59e0b', Stable: '#10b981' }
const MTTR_COLORS = { Slow: '#ef4444', Moderate: '#f59e0b', Fast: '#10b981' }

export default function Analytics({ filters }) {
  const { data: bundle, isLoading, isError, error } = useAnalyticsBundle(filters)

  const envComp        = bundle?.env_comparison
  const utilDist       = bundle?.utilization_dist
  const alertVel       = bundle?.alert_velocity
  const stability      = bundle?.stability
  const mttr           = bundle?.mttr
  const correlated     = bundle?.correlated_failures
  const heatmap        = bundle?.alert_heatmap
  const topAlerters    = bundle?.top_alerters
  const alertCategories = bundle?.alert_categories

  return (
    <div>
      {isError && (
        <div style={{ textAlign: 'center', padding: '80px 0', color: 'var(--text-muted)' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>⚠️</div>
          <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4, color: 'var(--text-primary)' }}>
            Failed to load analytics
          </div>
          <div style={{ fontSize: 13, marginBottom: 8 }}>
            The analytics engine encountered an error. Try refreshing the data.
          </div>
          {error?.message && (
            <div style={{
              fontSize: 11, fontFamily: 'monospace', background: 'var(--bg-canvas)',
              padding: 12, borderRadius: 8, maxWidth: 500, margin: '0 auto', textAlign: 'left',
              border: '1px solid var(--border)',
            }}>
              {error.message}
            </div>
          )}
        </div>
      )}

      {isLoading && (
        <>
          <Section title="🏢 Environment Comparison" subtitle="Loading…">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
              {[0,1,2].map(i => <KpiSkeleton key={i} />)}
            </div>
          </Section>
          <Section title="📊 Fleet Utilization" subtitle="Loading…">
            <ChartSkeleton height={220} />
          </Section>
          <Section title="📈 Alert Velocity" subtitle="Loading…">
            <ChartSkeleton height={220} />
          </Section>
          <Section title="⚡ Stability & MTTR" subtitle="Loading…">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <ChartSkeleton height={220} />
              <ChartSkeleton height={220} />
            </div>
          </Section>
          <Section title="🍩 Alert Categories" subtitle="Loading…">
            <ChartSkeleton height={280} />
          </Section>
        </>
      )}

      {/* ── Environment Comparison ── */}
      {envComp && envComp.length > 0 && (
        <Section title="🏢 Environment Comparison" subtitle="Production vs Non-Production fleet health">
          <div className="stagger-in" style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.min(envComp.length, 4)}, 1fr)`, gap: 16, marginBottom: 16 }}>
            {envComp.map((env, i) => (
              <div key={i} className="card card-padded" style={{ borderLeft: `3px solid ${env.environment === 'Production' ? 'var(--critical)' : 'var(--info)'}` }}>
                <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>{env.environment}</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 13 }}>
                  <div>
                    <div className="kpi-label">Servers</div>
                    <div style={{ fontFamily: 'Outfit', fontSize: 22, fontWeight: 700 }}>{env.server_count}</div>
                  </div>
                  <div>
                    <div className="kpi-label">Healthy</div>
                    <div style={{
                      fontFamily: 'Outfit', fontSize: 22, fontWeight: 700,
                      color: env.healthy_pct > 70 ? 'var(--success)' : env.healthy_pct > 40 ? 'var(--warning)' : 'var(--critical)',
                    }}>{env.healthy_pct}%</div>
                  </div>
                  <div>
                    <div className="kpi-label">Avg Load</div>
                    <div style={{ fontWeight: 600 }}>{env.avg_load}%</div>
                  </div>
                  <div>
                    <div className="kpi-label">Avg Alerts</div>
                    <div style={{ fontWeight: 600 }}>{env.avg_alerts}</div>
                  </div>
                  <div>
                    <div className="kpi-label">Urgent</div>
                    <div style={{ fontWeight: 600, color: env.urgent_count > 0 ? 'var(--critical)' : 'var(--text-muted)' }}>{env.urgent_count}</div>
                  </div>
                  <div>
                    <div className="kpi-label">Runway</div>
                    <div style={{ fontWeight: 600, color: env.avg_runway_days < 60 ? 'var(--critical)' : 'var(--text-muted)' }}>
                      {env.avg_runway_days === 999 ? '∞' : `${env.avg_runway_days}d`}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* ── Utilization Distribution ── */}
      {utilDist && utilDist.buckets && utilDist.buckets.length > 0 && (
        <Section title="📊 Utilization Distribution" subtitle="How fleet capacity is spread across load ranges">
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 20 }}>
            <div className="card" style={{ overflow: 'hidden' }}>
              <Plot
                data={[{
                  x: utilDist.buckets.map(b => b.range),
                  y: utilDist.buckets.map(b => b.count),
                  type: 'bar',
                  marker: {
                    color: utilDist.buckets.map(b => {
                      const r = b.range
                      if (r.includes('90') || r.includes('80')) return '#ef4444'
                      if (r.includes('60')) return '#f59e0b'
                      if (r.includes('0-10')) return '#3b82f6'
                      return '#10b981'
                    }),
                    cornerradius: 4,
                  },
                  hovertemplate: '%{x}: %{y} servers<extra></extra>',
                }]}
                layout={{
                  height: 260, margin: { t: 12, b: 40, l: 44, r: 16 },
                  paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
                  font: { family: 'Plus Jakarta Sans', size: 11, color: '#8A7A68' },
                  xaxis: { gridcolor: 'rgba(28,20,16,0.06)' },
                  yaxis: { gridcolor: 'rgba(28,20,16,0.06)', title: { text: 'Servers', font: { size: 11 } } },
                }}
                config={{ displayModeBar: false, responsive: true }}
                style={{ width: '100%' }}
              />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {utilDist.stats && [
                { label: 'Mean Load', value: `${utilDist.stats.mean}%`, color: utilDist.stats.mean > 70 ? 'var(--warning)' : undefined },
                { label: 'Median',    value: `${utilDist.stats.median}%` },
                { label: 'P90',       value: `${utilDist.stats.p90}%`,  color: utilDist.stats.p90 > 85 ? 'var(--critical)' : undefined },
                { label: 'P95',       value: `${utilDist.stats.p95}%`,  color: utilDist.stats.p95 > 90 ? 'var(--critical)' : undefined },
                { label: 'Std Dev',   value: `${utilDist.stats.std}%` },
              ].map(m => (
                <div key={m.label} className="kpi-card" style={{ padding: '12px 16px' }}>
                  <div className="kpi-label">{m.label}</div>
                  <div style={{ fontFamily: 'Outfit', fontSize: 20, fontWeight: 700, color: m.color || 'var(--text-primary)' }}>{m.value}</div>
                </div>
              ))}
            </div>
          </div>
        </Section>
      )}

      {/* ── Alert Velocity — full width now that Noise Ratio is removed ── */}
      {alertVel && alertVel.length > 0 && (
        <Section
          title="🚀 Alert Velocity"
          subtitle="Servers where alert frequency is accelerating — compares the last 3 days against the prior 3 days. A positive velocity means more alerts are firing now than before and warrants investigation."
          exportHref="/api/export/events"
        >
          <div className="card" style={{ overflow: 'hidden' }}>
            <table className="data-table">
              <thead>
                <tr><th>Server</th><th>Last 3d</th><th>Prior 3d</th><th>Velocity</th><th>Acceleration</th></tr>
              </thead>
              <tbody>
                {alertVel.slice(0, 15).map((s, i) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: 12 }}>{s.server_name}</td>
                    <td style={{ fontSize: 12 }}>{s.recent_3d}</td>
                    <td style={{ fontSize: 12 }}>{s.prior_3d}</td>
                    <td>
                      <span style={{
                        display: 'inline-flex', alignItems: 'center', gap: 4,
                        padding: '2px 8px', borderRadius: 20, fontSize: 11, fontWeight: 600,
                        background: s.velocity > 5 ? 'var(--critical-bg)' : 'var(--warning-bg)',
                        color: s.velocity > 5 ? 'var(--critical)' : 'var(--warning)',
                      }}>
                        ↑ +{s.velocity}
                      </span>
                    </td>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                      {s.acceleration_pct > 0 ? `+${s.acceleration_pct?.toFixed(0)}% vs prior` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}

      {/* ── Two-column: Stability + MTTR ── */}
      {((stability && stability.length > 0) || (mttr && mttr.servers && mttr.servers.length > 0)) && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 32 }}>
          {stability && stability.length > 0 && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                <div>
                  <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>📉 Load Stability</h3>
                  <p style={{ margin: '2px 0 0', fontSize: 12, color: 'var(--text-muted)' }}>
                    Most volatile servers — high load variance over time
                  </p>
                </div>
                <a href="/api/export/stability" download style={{
                  padding: '5px 12px', borderRadius: 6, fontSize: 12, fontWeight: 500,
                  background: 'var(--bg-canvas)', border: '1px solid var(--border)',
                  color: 'var(--text-secondary)', textDecoration: 'none', flexShrink: 0,
                }}>⬇ CSV</a>
              </div>
              <div className="card" style={{ overflow: 'hidden' }}>
                <table className="data-table">
                  <thead>
                    <tr><th>Server</th><th>Score</th><th>Avg</th><th>Range</th><th>Status</th></tr>
                  </thead>
                  <tbody>
                    {stability.slice(0, 10).map((s, i) => (
                      <tr key={i}>
                        <td style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: 12 }}>{s.server_name}</td>
                        <td>
                          <span style={{
                            fontFamily: 'Outfit', fontWeight: 700, fontSize: 14,
                            color: STABILITY_COLORS[s.classification],
                          }}>{s.stability_score}</span>
                        </td>
                        <td style={{ fontSize: 12 }}>{s.avg_load}%</td>
                        <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{s.min_load}–{s.max_load}%</td>
                        <td>
                          <span className="badge" style={{
                            background: `${STABILITY_COLORS[s.classification]}15`,
                            color: STABILITY_COLORS[s.classification],
                          }}>{s.classification}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {mttr && mttr.servers && mttr.servers.length > 0 && (
            <div>
              <div style={{ marginBottom: 12 }}>
                <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>⏱ Mean Time to Recovery</h3>
                <p style={{ margin: '2px 0 0', fontSize: 12, color: 'var(--text-muted)' }}>
                  Fleet avg: {mttr.fleet_avg_hours}h — slowest recoveries first
                </p>
              </div>
              <div className="card" style={{ overflow: 'hidden' }}>
                <table className="data-table">
                  <thead>
                    <tr><th>Server</th><th>Avg (h)</th><th>Median (h)</th><th>Incidents</th><th>Speed</th></tr>
                  </thead>
                  <tbody>
                    {mttr.servers.slice(0, 10).map((s, i) => (
                      <tr key={i}>
                        <td style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: 12 }}>{s.server_name}</td>
                        <td style={{ fontSize: 13, fontWeight: 600, color: MTTR_COLORS[s.classification] }}>{s.avg_hours}h</td>
                        <td style={{ fontSize: 12 }}>{s.median_hours}h</td>
                        <td style={{ fontSize: 12 }}>{s.incident_count}</td>
                        <td>
                          <span className="badge" style={{
                            background: `${MTTR_COLORS[s.classification]}15`,
                            color: MTTR_COLORS[s.classification],
                          }}>{s.classification}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Correlated Failures ── */}
      {correlated && correlated.length > 0 && (
        <Section title="🔗 Correlated Failures" subtitle="Servers that alert within the same 30-minute window — suggests shared infrastructure">
          <div className="card" style={{ overflow: 'hidden' }}>
            <table className="data-table">
              <thead>
                <tr><th>Server A</th><th>Server B</th><th>Co-occurrences</th><th>Shared Problems</th><th>Likely Cause</th></tr>
              </thead>
              <tbody>
                {correlated.map((c, i) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: 12 }}>{c.server_a}</td>
                    <td style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: 12 }}>{c.server_b}</td>
                    <td>
                      <span style={{
                        fontFamily: 'Outfit', fontWeight: 700, fontSize: 14,
                        color: c.co_occurrence_count >= 5 ? 'var(--critical)' : 'var(--warning)',
                      }}>{c.co_occurrence_count}</span>
                    </td>
                    <td style={{ fontSize: 11, color: 'var(--text-muted)', maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {c.shared_problems?.join(', ') || '—'}
                    </td>
                    <td>
                      <span className={`badge ${c.co_occurrence_count >= 5 ? 'badge-urgent' : 'badge-medium'}`}>
                        {c.likely_cause}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}

      {/* ── Alert Categories Donut ── */}
      {alertCategories && alertCategories.total > 0 && (() => {
        const CAT_COLORS = {
          Database: '#6366f1', Disk: '#f97316', Memory: '#3b82f6',
          CPU: '#ef4444', Service: '#10b981', Network: '#f59e0b', Other: '#94a3b8',
        }

        // Category descriptions — explains what each slice actually means
        const CAT_DESCRIPTIONS = {
          CPU:      'CPU load, processor utilization, high load averages, run-queue depth, and iowait issues reported by Zabbix.',
          Memory:   'RAM pressure, swap usage, heap exhaustion, and out-of-memory events.',
          Disk:     'Filesystem space warnings, VFS usage, low free space, partition or volume mount issues.',
          Database: 'MSSQL, PostgreSQL, MySQL, or Oracle-specific alerts — log growth, replication lag, transaction log full, DB size thresholds.',
          Service:  'Windows/Linux service failures, process not running, agent connectivity, open port checks, and listener failures.',
          Network:  'NIC link-down events, packet loss, ping failures, bandwidth thresholds, and interface throughput alerts.',
          Other:    'Alerts whose problem name did not match any of the above keyword patterns. These are typically custom Zabbix triggers unique to your environment — check the Raw Events export to identify what they are and whether they should be reclassified.',
        }

        const cats    = Object.entries(alertCategories.categories).sort((a, b) => b[1] - a[1])
        const labels  = cats.map(([k]) => k)
        const values  = cats.map(([, v]) => v)
        const colors  = labels.map(l => CAT_COLORS[l] || '#94a3b8')
        const topCat  = cats[0]
        const otherCount = alertCategories.categories['Other'] || 0
        const otherPct   = alertCategories.total > 0 ? ((otherCount / alertCategories.total) * 100).toFixed(0) : 0

        return (
          <Section
            title="🍩 What Are Alerts Actually About?"
            subtitle={`${alertCategories.total.toLocaleString()} total alerts classified — dominant type: ${topCat?.[0]} (${((topCat?.[1] / alertCategories.total) * 100).toFixed(0)}%). Tells you where to invest: storage, tuning, or compute.`}
            exportHref="/api/export/events"
          >
            <div className="card" style={{ overflow: 'hidden' }}>
              <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap' }}>
                <Plot
                  data={[{
                    labels, values, type: 'pie', hole: 0.55,
                    marker: { colors },
                    textinfo: 'percent',
                    textposition: 'inside',
                    hovertemplate: '<b>%{label}</b><br>%{value} alerts (%{percent})<extra></extra>',
                    sort: false,
                  }]}
                  layout={{
                    height: 280, width: 300,
                    margin: { t: 16, b: 16, l: 16, r: 16 },
                    paper_bgcolor: 'transparent',
                    font: { family: 'Plus Jakarta Sans', size: 12, color: '#8A7A68' },
                    showlegend: false,
                    annotations: [{
                      text: `${alertCategories.total.toLocaleString()}<br>alerts`,
                      x: 0.5, y: 0.5, xanchor: 'center', yanchor: 'middle',
                      showarrow: false,
                      font: { size: 14, color: '#1e293b', family: 'Outfit' },
                    }],
                  }}
                  config={{ displayModeBar: false }}
                />
                {/* Legend with counts and tooltips */}
                <div style={{ flex: 1, padding: '8px 24px', minWidth: 200 }}>
                  {cats.map(([cat, count]) => (
                    <div key={cat} style={{
                      display: 'flex', alignItems: 'center', gap: 10,
                      padding: '7px 0', borderBottom: '1px solid var(--border-light)',
                    }}>
                      <div style={{
                        width: 10, height: 10, borderRadius: 3, flexShrink: 0,
                        background: CAT_COLORS[cat] || '#94a3b8',
                      }} />
                      <span style={{ flex: 1, fontSize: 13, fontWeight: 500 }}>
                        {cat}
                        {cat === 'Other' && (
                          <span title={CAT_DESCRIPTIONS.Other} style={{
                            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                            width: 14, height: 14, borderRadius: '50%', fontSize: 9, fontWeight: 700,
                            background: 'var(--bg-canvas)', border: '1px solid var(--border)',
                            color: 'var(--text-muted)', cursor: 'help', marginLeft: 5,
                            verticalAlign: 'middle',
                          }}>?</span>
                        )}
                      </span>
                      <span style={{ fontSize: 13, fontWeight: 700, minWidth: 40, textAlign: 'right' }}>
                        {count.toLocaleString()}
                      </span>
                      <div style={{ width: 80, background: 'var(--bg-canvas)', borderRadius: 4, height: 6 }}>
                        <div style={{
                          width: `${(count / alertCategories.total * 100).toFixed(0)}%`,
                          height: '100%', borderRadius: 4,
                          background: CAT_COLORS[cat] || '#94a3b8',
                        }} />
                      </div>
                      <span style={{ fontSize: 11, color: 'var(--text-muted)', minWidth: 36, textAlign: 'right' }}>
                        {(count / alertCategories.total * 100).toFixed(0)}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* "Other" explanation callout — only shown when Other is >5% */}
              {otherCount > 0 && otherPct >= 5 && (
                <div style={{
                  margin: '0 20px 16px',
                  padding: '10px 14px',
                  borderRadius: 8,
                  background: 'rgba(148,160,166,0.08)',
                  border: '1px solid rgba(148,160,166,0.25)',
                  display: 'flex', gap: 10, alignItems: 'flex-start',
                }}>
                  <span style={{ fontSize: 16, flexShrink: 0 }}>ℹ️</span>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                    <strong style={{ color: 'var(--text-primary)' }}>
                      "Other" ({otherCount.toLocaleString()} alerts, {otherPct}%):
                    </strong>{' '}
                    These alerts did not match the keyword patterns for CPU, Memory, Disk, Database, Service, or Network.
                    They are typically <em>custom Zabbix triggers</em> specific to your environment — application-level checks,
                    business logic monitors, or non-standard metric names. Use the{' '}
                    <a href="/api/export/events" download style={{ color: 'var(--info)', textDecoration: 'none', fontWeight: 500 }}>
                      Raw Events export ↓
                    </a>{' '}
                    to inspect their <code>problem_name</code> values and decide whether they warrant a new category.
                  </div>
                </div>
              )}
            </div>
          </Section>
        )
      })()}

      {/* ── Alert Timing Heatmap ── */}
      {heatmap && heatmap.matrix && heatmap.matrix.length > 0 && (() => {
        const days  = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
        const hours = Array.from({ length: 24 }, (_, i) => `${String(i).padStart(2,'0')}:00`)
        const z = Array.from({ length: 7 }, () => Array(24).fill(0))
        heatmap.matrix.forEach(({ day_index, hour, count }) => {
          if (day_index >= 0 && day_index < 7 && hour >= 0 && hour < 24)
            z[day_index][hour] = count
        })
        return (
          <Section
            title="🕐 Alert Timing Heatmap"
            subtitle={`When do problems happen? ${heatmap.total_events?.toLocaleString()} events${heatmap.peak ? ` — busiest: ${heatmap.peak.day} ${heatmap.peak.hour}:00 (${heatmap.peak.count} alerts)` : ''}`}
          >
            <div className="card" style={{ overflow: 'hidden' }}>
              <Plot
                data={[{
                  z, x: hours, y: days,
                  type: 'heatmap',
                  colorscale: [
                    [0,   'rgba(16,185,129,0.05)'],
                    [0.2, '#fef9c3'],
                    [0.5, '#fbbf24'],
                    [0.8, '#ef4444'],
                    [1,   '#7f1d1d'],
                  ],
                  showscale: true,
                  hovertemplate: '%{y} %{x}: <b>%{z} alerts</b><extra></extra>',
                  colorbar: { thickness: 10, len: 0.6, title: { text: 'Alerts', side: 'right', font: { size: 11 } } },
                }]}
                layout={{
                  height: 220, margin: { t: 12, b: 48, l: 44, r: 60 },
                  paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
                  font: { family: 'Plus Jakarta Sans', size: 11, color: '#8A7A68' },
                  xaxis: { tickangle: -45, nticks: 12 },
                  yaxis: { autorange: 'reversed' },
                }}
                config={{ displayModeBar: false, responsive: true }}
                style={{ width: '100%' }}
              />
            </div>
            <p style={{ margin: '8px 0 0', fontSize: 12, color: 'var(--text-muted)' }}>
              Use this to schedule maintenance windows in quiet periods and ensure on-call staffing during peak alert hours.
            </p>
          </Section>
        )
      })()}

      {/* ── Top Alerting Servers ── */}
      {topAlerters && topAlerters.length > 0 && (() => {
        const SEV_ORDER  = ['Disaster','High','Average','Warning','Info','Not classified']
        const SEV_COLORS_MAP = {
          Disaster: '#ef4444', High: '#f97316', Average: '#eab308',
          Warning: '#7c66dc', Info: '#889096', 'Not classified': '#cbd5e1',
        }
        const severities = [...new Set(topAlerters.flatMap(s => Object.keys(s.by_severity)))]
          .sort((a, b) => SEV_ORDER.indexOf(a) - SEV_ORDER.indexOf(b))

        const traces = severities.map(sev => ({
          name: sev, type: 'bar', orientation: 'h',
          y: topAlerters.map(s => s.server_name),
          x: topAlerters.map(s => s.by_severity[sev] || 0),
          marker: { color: SEV_COLORS_MAP[sev] || '#889096' },
          hovertemplate: `<b>%{y}</b><br>${sev}: %{x}<extra></extra>`,
        }))

        return (
          <Section
            title="📣 Top Alerting Servers"
            subtitle="Servers generating the most alerts — broken down by severity. High noise/warning share → tune thresholds. High disaster/high share → investigate root cause."
            exportHref="/api/export/top-alerters"
          >
            <div className="card" style={{ overflow: 'hidden' }}>
              <Plot
                data={traces}
                layout={{
                  barmode: 'stack',
                  height: Math.max(260, topAlerters.length * 28 + 60),
                  margin: { t: 12, b: 40, l: 180, r: 60 },
                  paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
                  font: { family: 'Plus Jakarta Sans', size: 11, color: '#8A7A68' },
                  xaxis: { title: { text: 'Alert Count', font: { size: 11 } }, gridcolor: 'rgba(28,20,16,0.06)' },
                  yaxis: { autorange: 'reversed' },
                  legend: { orientation: 'h', y: -0.12, x: 0 },
                  showlegend: true,
                }}
                config={{ displayModeBar: false, responsive: true }}
                style={{ width: '100%' }}
              />
            </div>
          </Section>
        )
      })()}

      {/* Empty state */}
      {!isLoading && !isError && (!envComp || envComp.length === 0) && (!alertVel || alertVel.length === 0) && (
        <div style={{ textAlign: 'center', padding: '80px 0', color: 'var(--text-muted)' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>📈</div>
          <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>No analytics data yet</div>
          <div style={{ fontSize: 13 }}>Fetch data from Zabbix to see advanced analytics and insights.</div>
        </div>
      )}
    </div>
  )
}
