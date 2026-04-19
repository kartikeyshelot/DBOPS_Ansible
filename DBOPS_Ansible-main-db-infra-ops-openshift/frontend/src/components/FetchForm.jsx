import React, { useState, useEffect } from 'react'
import { useTriggerFetch, useFetchStatus } from '../hooks/useData'
import { useQueryClient } from '@tanstack/react-query'

export default function FetchForm({ onClose }) {
  const [url,   setUrl]   = useState('https://zabbix.com/api_jsonrpc.php')
  const [token, setToken] = useState('')
  const [group, setGroup] = useState('PAASDB')
  const [days,  setDays]  = useState(30)

  const fetchMutation = useTriggerFetch()
  const { data: fetchStatus } = useFetchStatus()
  const queryClient = useQueryClient()

  const isRunning  = fetchStatus?.status === 'running'
  const isComplete = fetchStatus?.status === 'completed'
  const isFailed   = fetchStatus?.status?.startsWith('failed')

  // When fetch transitions to completed, refresh all data and show success
  const [justCompleted, setJustCompleted] = useState(false)
  useEffect(() => {
    if (isComplete && fetchMutation.isSuccess) {
      setJustCompleted(true)
      queryClient.invalidateQueries()
    }
  }, [isComplete, fetchMutation.isSuccess, queryClient])

  const handleFetch = () => {
    setJustCompleted(false)
    fetchMutation.mutate({
      zabbix_url:   url,
      zabbix_token: token,
      zabbix_group: group,
      days_back:    days,
    })
  }

  // Elapsed time display while running
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    if (!isRunning) { setElapsed(0); return }
    const t = setInterval(() => setElapsed(s => s + 1), 1000)
    return () => clearInterval(t)
  }, [isRunning])

  const fmtElapsed = (s) => s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`

  return (
    <div className="card-padded" style={{ position: 'relative' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
        <div>
          <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700 }}>Data Source Configuration</h3>
          <p style={{ margin: '4px 0 0', fontSize: 11, color: 'var(--ink-muted)', fontFamily: 'IBM Plex Mono', letterSpacing: '0.03em' }}>
            Connect to your Zabbix API to load infrastructure data.
          </p>
        </div>
        {onClose && (
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 18, color: 'var(--ink-muted)', padding: 4 }}>✕</button>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
        <div style={{ gridColumn: 'span 2' }}>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--ink-muted)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Zabbix URL
          </label>
          <input className="input" type="text" value={url} onChange={e => setUrl(e.target.value)} placeholder="https://zabbix.example.com/api_jsonrpc.php" disabled={isRunning} />
        </div>
        <div style={{ gridColumn: 'span 2' }}>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--ink-muted)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            API Token
          </label>
          <input className="input" type="password" value={token} onChange={e => setToken(e.target.value)} placeholder="Enter your Zabbix auth token" disabled={isRunning} />
        </div>
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--ink-muted)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Host Group
          </label>
          <input className="input" type="text" value={group} onChange={e => setGroup(e.target.value)} disabled={isRunning} />
        </div>
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--ink-muted)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Days of History
          </label>
          <input className="input" type="number" min={7} max={90} value={days} onChange={e => setDays(Number(e.target.value))} disabled={isRunning} />
        </div>
      </div>

      <button
        className="btn-primary"
        onClick={handleFetch}
        disabled={isRunning || !token}
        style={{ width: '100%' }}
      >
        {isRunning ? `⏳ Fetching data… (${fmtElapsed(elapsed)})` : '⚡ Fetch New Data'}
      </button>

      {/* Running state — non-blocking progress indicator */}
      {isRunning && (
        <div style={{ marginTop: 12, padding: '12px 14px', borderRadius: 'var(--radius-sm)', background: 'rgba(59,130,246,0.08)', border: '1px solid rgba(59,130,246,0.2)', fontSize: 13 }}>
          <div style={{ fontWeight: 600, color: 'var(--info)', marginBottom: 4 }}>
            Fetching from Zabbix — working in the background
          </div>
          <div style={{ color: 'var(--ink-muted)', lineHeight: 1.5 }}>
            Pulling {days} days of data for group <strong>{group}</strong>.<br />
            The page remains usable. This panel will update automatically when done.
          </div>
          {/* Simple animated progress bar */}
          <div style={{ marginTop: 10, height: 4, borderRadius: 2, background: 'rgba(59,130,246,0.15)', overflow: 'hidden' }}>
            <div style={{
              height: '100%', borderRadius: 2,
              background: 'var(--info)',
              width: '40%',
              animation: 'slide 1.5s ease-in-out infinite alternate',
            }} />
          </div>
          <style>{`@keyframes slide { from { margin-left: 0; } to { margin-left: 60%; } }`}</style>
        </div>
      )}

      {/* Error from POST /api/fetch itself (e.g. 409 already running) */}
      {fetchMutation.isError && (
        <div style={{ marginTop: 12, padding: '10px 14px', borderRadius: 'var(--radius-sm)', background: 'var(--critical-bg)', color: 'var(--critical)', fontSize: 13, fontWeight: 500 }}>
          {fetchMutation.error?.response?.data?.detail || fetchMutation.error?.message}
        </div>
      )}

      {/* Error reported by the background task */}
      {isFailed && !isRunning && (
        <div style={{ marginTop: 12, padding: '10px 14px', borderRadius: 'var(--radius-sm)', background: 'var(--critical-bg)', color: 'var(--critical)', fontSize: 13, fontWeight: 500 }}>
          Fetch failed: {fetchStatus.status?.replace('failed: ', '')}
        </div>
      )}

      {/* Success */}
      {justCompleted && (
        <div style={{ marginTop: 12, padding: '10px 14px', borderRadius: 'var(--radius-sm)', background: 'var(--success-bg)', color: 'var(--success)', fontSize: 13, fontWeight: 500 }}>
          ✓ Data loaded — {fetchStatus?.server_count ?? '?'} servers. All charts updated.
        </div>
      )}
    </div>
  )
}
