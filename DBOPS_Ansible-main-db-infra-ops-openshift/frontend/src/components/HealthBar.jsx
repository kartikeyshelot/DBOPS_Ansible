import React from 'react'

export default function HealthBar({ health }) {
  if (!health) return null

  const { health_score, urgent_count, high_count, disks_at_risk } = health

  const scoreClass = health_score >= 70 ? 'health-good'
    : health_score >= 40 ? 'health-warn' : 'health-bad'

  return (
    <div className="card" style={{
      padding: '16px 24px',
      marginBottom: 24,
      display: 'flex',
      alignItems: 'center',
      gap: 20,
    }}>
      <div className={`health-score ${scoreClass}`}>
        {health_score}
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 2 }}>Fleet Health Score</div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          Based on load, alerts, disk utilization, and runway across all servers
        </div>
      </div>
      <div style={{ display: 'flex', gap: 24 }}>
        {[
          { label: 'Urgent', value: urgent_count, color: urgent_count > 0 ? 'var(--critical)' : 'var(--text-muted)' },
          { label: 'High', value: high_count, color: high_count > 0 ? 'var(--warning)' : 'var(--text-muted)' },
          { label: 'Disks at Risk', value: disks_at_risk, color: disks_at_risk > 0 ? 'var(--critical)' : 'var(--text-muted)' },
        ].map(m => (
          <div key={m.label} style={{ textAlign: 'center' }}>
            <div style={{
              fontFamily: 'Outfit', fontSize: 20, fontWeight: 700, color: m.color,
              lineHeight: 1,
            }}>{m.value}</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 500, marginTop: 2 }}>{m.label}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
