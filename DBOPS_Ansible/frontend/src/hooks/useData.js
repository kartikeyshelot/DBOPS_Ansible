import React from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getServers, getFleetHealth, getFilterOptions, getNeedsAttention,
  getRecurringIssues,
  getRiskMatrix, getRunwayOverview, getServerForecast, getDatabases,
  getDbDiskCorrelation, getRightSizing,
  getServerDrilldown, updateTriageStatus, getAllTriageStatus,
  triggerFetch, getFetchStatus,
  getAnalyticsBundle, getAdvancedForecast,
  getSeverityTrend,
} from '../api/client'

// Data changes only when a new fetch completes — 5 min stale time prevents
// the flood of re-requests that fires on every browser tab-focus.
const STALE_5MIN  = 5 * 60 * 1000
const STALE_10MIN = 10 * 60 * 1000

// ── Servers ───────────────────────────────────────────────────────────────
export function useServers(filters) {
  return useQuery({
    queryKey: ['servers', filters],
    queryFn: () => getServers(filters),
    staleTime: STALE_5MIN,
  })
}

export function useFleetHealth(filters = {}) {
  return useQuery({
    queryKey: ['health', filters],
    queryFn: () => getFleetHealth(filters),
    staleTime: STALE_5MIN,
  })
}

export function useFilterOptions() {
  return useQuery({
    queryKey: ['filter-options'],
    queryFn: getFilterOptions,
    staleTime: STALE_10MIN,
  })
}

export function useNeedsAttention(filters = {}) {
  return useQuery({
    queryKey: ['needs-attention', filters],
    queryFn: () => getNeedsAttention(filters),
    staleTime: STALE_5MIN,
  })
}

// ── Analytics ─────────────────────────────────────────────────────────────
export function useRecurringIssues(filters = {}) {
  return useQuery({
    queryKey: ['recurring-issues', filters],
    queryFn: () => getRecurringIssues(filters),
    staleTime: STALE_5MIN,
  })
}

export function useRiskMatrix(filters = {}) {
  return useQuery({
    queryKey: ['risk-matrix', filters],
    queryFn: () => getRiskMatrix(filters),
    staleTime: STALE_5MIN,
  })
}

export function useSeverityTrend(filters = {}) {
  return useQuery({
    queryKey: ['severity-trend', filters],
    queryFn: () => getSeverityTrend(filters),
    staleTime: STALE_5MIN,
  })
}

// ── Forecasts ─────────────────────────────────────────────────────────────
export function useRunwayOverview(filters = {}) {
  return useQuery({
    queryKey: ['runway-overview', filters],
    queryFn: () => getRunwayOverview(filters),
    staleTime: STALE_5MIN,
  })
}

export function useServerForecast(serverName) {
  return useQuery({
    queryKey: ['forecast', serverName],
    queryFn: () => getServerForecast(serverName),
    enabled: !!serverName,
    staleTime: STALE_5MIN,
  })
}

// ── Capacity ──────────────────────────────────────────────────────────────
export function useDatabases(filters = {}) {
  return useQuery({
    queryKey: ['databases', filters],
    queryFn: () => getDatabases(filters),
    staleTime: STALE_5MIN,
  })
}

export function useDbDiskCorrelation(filters = {}) {
  return useQuery({
    queryKey: ['db-disk-correlation', filters],
    queryFn: () => getDbDiskCorrelation(filters),
    staleTime: STALE_5MIN,
  })
}

export function useRightSizing(filters = {}) {
  return useQuery({
    queryKey: ['right-sizing', filters],
    queryFn: () => getRightSizing(filters),
    staleTime: STALE_5MIN,
  })
}

// ── Triage ────────────────────────────────────────────────────────────────
export function useTriage() {
  return useQuery({
    queryKey: ['triage'],
    queryFn: getAllTriageStatus,
    staleTime: STALE_5MIN,
  })
}

export function useDrilldown(serverName) {
  return useQuery({
    queryKey: ['drilldown', serverName],
    queryFn: () => getServerDrilldown(serverName),
    enabled: !!serverName,
    staleTime: STALE_5MIN,
  })
}

export function useUpdateTriage() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ serverName, status, notes }) => updateTriageStatus(serverName, status, notes),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['servers'] })
      queryClient.invalidateQueries({ queryKey: ['triage'] })
      queryClient.invalidateQueries({ queryKey: ['needs-attention'] })
    },
  })
}

// ── Advanced Analytics ────────────────────────────────────────────────────
// All analytics tab data comes through the bundle; useAdvancedForecast is used
// by the DrillDown component for per-server forecast charts.
export function useAdvancedForecast(serverName) {
  return useQuery({
    queryKey: ['advanced-forecast', serverName],
    queryFn: () => getAdvancedForecast(serverName),
    enabled: !!serverName,
    staleTime: STALE_5MIN,
  })
}

// Single-call bundle — the only hook used by the Analytics tab.
export function useAnalyticsBundle(filters = {}) {
  return useQuery({
    queryKey: ['analytics-bundle', filters],
    queryFn: () => getAnalyticsBundle(filters),
    staleTime: STALE_5MIN,
  })
}

// ── Fetch ─────────────────────────────────────────────────────────────────
export function useTriggerFetch() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: triggerFetch,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fetch-status'] })
    },
  })
}

export function useFetchStatus() {
  const queryClient = useQueryClient()
  const prevStatusRef = React.useRef(null)

  const query = useQuery({
    queryKey: ['fetch-status'],
    queryFn: getFetchStatus,
    staleTime: 0,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'running' ? 3000 : false
    },
  })

  // Invalidate all data queries exactly once when running → completed
  React.useEffect(() => {
    const status = query.data?.status
    if (status === 'completed' && prevStatusRef.current === 'running') {
      queryClient.invalidateQueries()
    }
    prevStatusRef.current = status
  }, [query.data?.status, queryClient])

  return query
}
