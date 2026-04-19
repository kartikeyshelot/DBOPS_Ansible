import React, { useState, useMemo } from 'react'

const PRI_BADGE = {
  URGENT: 'badge badge-urgent',
  HIGH: 'badge badge-high',
  MEDIUM: 'badge badge-medium',
  LOW: 'badge badge-low',
  NONE: 'badge badge-none',
}

function LoadBar({ value }) {
  const v = typeof value === 'number' && !isNaN(value) ? value : 0
  const color = v > 80 ? 'var(--critical)' : v > 60 ? 'var(--warning)' : 'var(--success)'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 100 }}>
      <div className="progress-bar" style={{ flex: 1 }}>
        <div className="progress-fill" style={{ width: `${Math.min(v, 100)}%`, background: color }} />
      </div>
      <span style={{ fontSize: 12, fontWeight: 600, color, minWidth: 36, textAlign: 'right' }}>
        {v.toFixed(1)}%
      </span>
    </div>
  )
}

export default function ServerTable({ servers, onSelect }) {
  const [sortField, setSortField] = useState('priority')
  const [sortAsc, setSortAsc] = useState(true)
  const priOrder = { URGENT: 0, HIGH: 1, MEDIUM: 2, LOW: 3, NONE: 4 }

  const sorted = useMemo(() => {
    if (!servers) return []
    return [...servers].sort((a, b) => {
      let va = a[sortField], vb = b[sortField]
      if (sortField === 'priority') { va = priOrder[va] ?? 5; vb = priOrder[vb] ?? 5 }
      if (typeof va === 'string') return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va)
      return sortAsc ? va - vb : vb - va
    })
  }, [servers, sortField, sortAsc])

  const toggleSort = (field) => {
    if (sortField === field) setSortAsc(!sortAsc)
    else { setSortField(field); setSortAsc(true) }
  }

  const SortTh = ({ field, children, style }) => (
    <th
      onClick={() => toggleSort(field)}
      style={{ ...style, cursor: 'pointer', userSelect: 'none' }}
    >
      {children}
      {sortField === field && (
        <span style={{ marginLeft: 4, opacity: 0.6 }}>{sortAsc ? '↑' : '↓'}</span>
      )}
    </th>
  )

  return (
    <div className="card" style={{ overflow: 'hidden' }}>
      <div style={{ overflowX: 'auto' }}>
        <table className="data-table">
          <thead>
            <tr>
              <SortTh field="name">Server</SortTh>
              <SortTh field="resource_type">Type</SortTh>
              <SortTh field="current_load">Load</SortTh>
              <SortTh field="total_alerts">Alerts</SortTh>
              <SortTh field="priority">Priority</SortTh>
              <th>Risk</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((s, i) => (
              <tr
                key={s.name + '-' + i}
                onClick={() => onSelect?.(s)}
                style={{ cursor: onSelect ? 'pointer' : 'default' }}
              >
                <td style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{s.name}</td>
                <td>{s.resource_type}</td>
                <td><LoadBar value={s.current_load} /></td>
                <td>
                  <span style={{
                    fontWeight: 600,
                    color: s.total_alerts > 5 ? 'var(--critical)' : s.total_alerts > 0 ? 'var(--text-primary)' : 'var(--text-muted)',
                  }}>
                    {s.total_alerts}
                  </span>
                </td>
                <td><span className={PRI_BADGE[s.priority] || PRI_BADGE.NONE}>{s.priority}</span></td>
                <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={s.risk_category}>
                  {s.risk_category}
                </td>
                <td style={{ fontSize: 12 }}>{s.action}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {(!sorted || sorted.length === 0) && (
          <div style={{ textAlign: 'center', padding: '48px 0', color: 'var(--text-muted)', fontSize: 14 }}>
            No servers match the current filters.
          </div>
        )}
      </div>
    </div>
  )
}
