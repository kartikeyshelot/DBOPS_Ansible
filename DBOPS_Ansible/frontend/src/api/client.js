import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// ── Shared filter param builder ──────────────────────────────────────────
function filterParams(filters = {}) {
  const params = {}
  if (filters.search)      params.search      = filters.search
  if (filters.priority)    params.priority     = filters.priority
  if (filters.environment) params.environment  = filters.environment
  if (filters.app_code)    params.app_code     = filters.app_code
  if (filters.criticality) params.criticality  = filters.criticality
  if (filters.tag_key)     params.tag_key      = filters.tag_key
  if (filters.tag_value)   params.tag_value    = filters.tag_value
  return params
}

// ── Fetch ─────────────────────────────────────────────────────────────────
export const triggerFetch = (data) =>
  api.post('/fetch', data, { timeout: 15000 }).then(r => r.data)
export const getFetchStatus = () => api.get('/fetch/status').then(r => r.data)

// ── Servers ───────────────────────────────────────────────────────────────
export const getServers        = (filters = {}) => api.get('/servers', { params: filterParams(filters) }).then(r => r.data)
export const getFilterOptions  = ()              => api.get('/servers/filters').then(r => r.data)
export const getFleetHealth    = (filters = {}) => api.get('/health', { params: filterParams(filters) }).then(r => r.data)
export const getNeedsAttention = (filters = {}) => api.get('/needs-attention', { params: filterParams(filters) }).then(r => r.data)
export const getProfiles       = (filters = {}) => api.get('/profiles', { params: filterParams(filters) }).then(r => r.data)
export const getRightSizing    = (filters = {}) => api.get('/right-sizing', { params: filterParams(filters) }).then(r => r.data)
export const getRisingProblems = (filters = {}) => api.get('/rising-problems', { params: filterParams(filters) }).then(r => r.data)
export const getRecurringIssues = (filters = {}) => api.get('/recurring-issues', { params: filterParams(filters) }).then(r => r.data)
export const getRiskMatrix      = (filters = {}) => api.get('/risk-matrix', { params: filterParams(filters) }).then(r => r.data)
export const getSeverityTrend   = (filters = {}) => api.get('/severity-trend', { params: filterParams(filters) }).then(r => r.data)

// ── Forecasts ─────────────────────────────────────────────────────────────
export const getRunwayOverview = (filters = {}) => api.get('/forecasts/runway', { params: filterParams(filters) }).then(r => r.data)
export const getServerForecast = (name) =>
  api.get(`/forecasts/${encodeURIComponent(name)}`).then(r => r.data)

// ── Triage ────────────────────────────────────────────────────────────────
export const updateTriageStatus = (serverName, status, notes = null) =>
  api.patch(`/triage/${encodeURIComponent(serverName)}`, { status, notes }).then(r => r.data)
export const getAllTriageStatus  = () => api.get('/triage').then(r => r.data)
export const getServerDrilldown = (name) =>
  api.get(`/drilldown/${encodeURIComponent(name)}`).then(r => r.data)

// ── Disks & Databases ─────────────────────────────────────────────────────
export const getDisks = (filters = {}) =>
  api.get('/disks', { params: filterParams(filters) }).then(r => r.data)
export const getDatabases = (filters = {}) =>
  api.get('/databases', { params: filterParams(filters) }).then(r => r.data)
export const getDbDiskCorrelation = (filters = {}) =>
  api.get('/databases/disk-correlation', { params: filterParams(filters) }).then(r => r.data)

// ── Advanced Analytics ────────────────────────────────────────────────────
// The Analytics tab calls only the bundle endpoint — one request for all data.
// Individual endpoints remain available for direct API usage / curl / Swagger.
export const getAnalyticsBundle    = (filters = {}) =>
  api.get('/analytics/bundle', { params: filterParams(filters), timeout: 120000 }).then(r => r.data)
export const getAdvancedForecast   = (name) =>
  api.get(`/analytics/forecast/${encodeURIComponent(name)}`).then(r => r.data)

// ── Colour maps ───────────────────────────────────────────────────────────
export const COLORS = {
  URGENT: '#E5484D', HIGH: '#F76B15', MEDIUM: '#3E63DD', LOW: '#30A46C', NONE: '#889096',
}
export const SEV_COLORS = {
  Disaster: '#E5484D', High: '#F76B15', Average: '#E5A500', Warning: '#7C66DC', Info: '#889096',
}
export const PROFILE_COLORS = {
  'Balanced': '#30A46C', 'Thrasher (High Load)': '#E5484D', 'Zombie (High Res, Low Load)': '#3E63DD',
}
