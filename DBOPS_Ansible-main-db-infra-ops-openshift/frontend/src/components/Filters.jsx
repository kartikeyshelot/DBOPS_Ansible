import React, { useState, useEffect, useRef } from 'react'

export default function Filters({ filters, setFilters, options }) {
  if (!options) return null

  // Debounced search: local state updates instantly (responsive typing),
  // but the actual filter only propagates after 350ms of idle.
  const [searchLocal, setSearchLocal] = useState(filters.search || '')
  const debounceRef = useRef(null)

  useEffect(() => {
    // Sync local state when filters are cleared externally
    setSearchLocal(filters.search || '')
  }, [filters.search])

  const handleSearchChange = (value) => {
    setSearchLocal(value)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setFilters(prev => ({ ...prev, search: value || undefined }))
    }, 350)
  }

  // Cleanup on unmount
  useEffect(() => () => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
  }, [])

  const update = (key, value) => {
    setFilters(prev => ({ ...prev, [key]: value || undefined }))
  }

  return (
    <div style={{
      display: 'flex', gap: 10, marginBottom: 24, flexWrap: 'wrap',
      alignItems: 'center',
    }}>
      <input
        className="input"
        type="text"
        placeholder="🔍  Search servers..."
        value={searchLocal}
        onChange={e => handleSearchChange(e.target.value)}
        style={{ maxWidth: 220 }}
      />
      {[
        { key: 'app_code', label: 'All AppCodes', items: options.app_codes },
        { key: 'criticality', label: 'All Criticality', items: options.criticalities },
        { key: 'environment', label: 'All Environments', items: options.environments },
        { key: 'priority', label: 'All Priorities', items: ['URGENT', 'HIGH', 'MEDIUM', 'LOW', 'NONE'] },
      ].map(f => (
        <select
          key={f.key}
          className="select"
          value={filters[f.key] || ''}
          onChange={e => update(f.key, e.target.value)}
          style={{ minWidth: 140 }}
        >
          <option value="">{f.label}</option>
          {(f.items || []).map(v => <option key={v} value={v}>{v}</option>)}
        </select>
      ))}
      {(Object.values(filters).some(Boolean) || searchLocal) && (
        <button
          className="btn-secondary"
          onClick={() => {
            setSearchLocal('')
            setFilters({})
          }}
          style={{ fontSize: 12, padding: '6px 12px' }}
        >
          ✕ Clear
        </button>
      )}
    </div>
  )
}
