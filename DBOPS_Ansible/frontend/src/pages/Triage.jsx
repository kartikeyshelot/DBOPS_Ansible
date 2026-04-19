import React, { useState } from 'react'
import { useRecurringIssues, useTriage, useServers } from '../hooks/useData'
import DrillDown from '../components/DrillDown'

const STATUS_BADGE = {
  'Open': 'badge badge-open',
  'In Progress': 'badge badge-in-progress',
  'Fixed': 'badge badge-fixed',
  "Won't Fix": 'badge badge-none',
}

export default function Triage({ filters }) {
  const { data: recurring } = useRecurringIssues(filters)
  const { data: triage } = useTriage()
  const { data: servers } = useServers(filters)

  const [drillServer, setDrillServer] = useState(null)

  const openDrill = (server) => {
    const s = servers?.find(sv => sv.name === (server.server_name || server))
    setDrillServer({
      name: server.server_name || server,
      triageStatus: s?.triage_status || server.status || 'Open',
    })
  }
  const closeDrill = () => setDrillServer(null)

  // Build triage list from ALL servers, merging triage status
  const triageList = servers ? servers.map(server => {
    const triageInfo = triage?.[server.name]
    return {
      server_name: server.name,
      status: triageInfo?.status || server.triage_status || 'Open',
      notes: triageInfo?.notes || '',
      updated_at: triageInfo?.updated_at || null,
      priority: server.priority || 'NONE',
      risk_category: server.risk_category || 'Unknown',
      current_load: server.current_load || 0,
    }
  }).sort((a, b) => {
    const order = { URGENT: 0, HIGH: 1, MEDIUM: 2, LOW: 3, NONE: 4 }
    return (order[a.priority] ?? 5) - (order[b.priority] ?? 5)
  }) : []

  return (
    <div>
      {/* Two Column: Recurring + Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 32 }}>
        {/* Recurring Issues */}
        {recurring && recurring.length > 0 && (
          <div className="card" style={{ overflow: 'hidden' }}>
            <div style={{ padding: '16px 20px 12px' }}>
              <h4 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>🔄 Recurring Issues</h4>
              <p style={{ margin: '2px 0 0', fontSize: 12, color: 'var(--text-muted)' }}>
                Same problem on the same server — tune or fix
              </p>
            </div>
            <div style={{ maxHeight: 320, overflowY: 'auto' }}>
              <table className="data-table">
                <thead><tr><th>Server</th><th>Problem</th><th>Count</th></tr></thead>
                <tbody>
                  {recurring.slice(0, 15).map((r, i) => (
                    <tr key={i}>
                      <td style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: 12 }}>{r.server_name}</td>
                      <td style={{ fontSize: 12, maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {r.problem_name}
                      </td>
                      <td>
                        <span style={{
                          fontWeight: 700, fontSize: 13,
                          color: r.count > 10 ? 'var(--critical)' : r.count > 5 ? 'var(--warning)' : 'var(--text-primary)',
                        }}>{r.count}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Triage Stats */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div className="kpi-card">
            <div className="kpi-label">Triage Summary</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 8 }}>
              {['Open', 'In Progress', 'Fixed', "Won't Fix"].map(st => {
                const count = triageList.filter(t => t.status === st).length
                return (
                  <div key={st} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span className={STATUS_BADGE[st]}>{st}</span>
                    <span style={{ fontFamily: 'Outfit', fontSize: 20, fontWeight: 700 }}>{count}</span>
                  </div>
                )
              })}
            </div>
          </div>

          <div className="kpi-card" style={{ flex: 1 }}>
            <div className="kpi-label">Priority Breakdown</div>
            <div style={{ display: 'flex', gap: 16, marginTop: 12, flexWrap: 'wrap' }}>
              {['URGENT', 'HIGH', 'MEDIUM', 'LOW'].map(pri => {
                const count = triageList.filter(t => t.priority === pri).length
                return (
                  <div key={pri} style={{ textAlign: 'center' }}>
                    <div style={{
                      fontFamily: 'Outfit', fontSize: 24, fontWeight: 700,
                      color: { URGENT: 'var(--critical)', HIGH: 'var(--warning)', MEDIUM: 'var(--info)', LOW: 'var(--success)' }[pri],
                    }}>{count}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 500 }}>{pri}</div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Triage Table */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>🏷 All Triaged Servers</h3>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{triageList.length} entries</span>
        </div>
        <div className="card" style={{ overflow: 'hidden' }}>
          <div style={{ maxHeight: 500, overflowY: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Server</th><th>Priority</th><th>Status</th>
                  <th>Load</th><th>Notes</th><th>Updated</th><th></th>
                </tr>
              </thead>
              <tbody>
                {triageList.map((t, i) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{t.server_name}</td>
                    <td>
                      <span className={`badge badge-${t.priority?.toLowerCase()}`}>{t.priority}</span>
                    </td>
                    <td><span className={STATUS_BADGE[t.status] || 'badge badge-none'}>{t.status}</span></td>
                    <td style={{ fontSize: 12 }}>{(t.current_load || 0).toFixed(1)}%</td>
                    <td style={{
                      fontSize: 12, maxWidth: 220, overflow: 'hidden',
                      textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      color: t.notes ? 'var(--text-primary)' : 'var(--text-muted)',
                      fontStyle: t.notes ? 'normal' : 'italic',
                    }} title={t.notes}>
                      {t.notes || 'No notes'}
                    </td>
                    <td style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                      {t.updated_at ? new Date(t.updated_at).toLocaleDateString() : '—'}
                    </td>
                    <td>
                      <button
                        className="btn-secondary"
                        onClick={() => openDrill(t)}
                        style={{ fontSize: 11, padding: '4px 10px' }}
                      >
                        Drill ↗
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {triageList.length === 0 && (
            <div style={{ textAlign: 'center', padding: '48px 0', color: 'var(--text-muted)', fontSize: 14 }}>
              No triage entries yet. Open a server drill-down and set a triage status.
            </div>
          )}
        </div>
      </div>

      {/* DrillDown */}
      {drillServer && (
        <DrillDown serverName={drillServer.name} triageStatus={drillServer.triageStatus} onClose={closeDrill} />
      )}
    </div>
  )
}
