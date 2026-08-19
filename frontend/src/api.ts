import type { AuditLog, Candidate, Dashboard, Decision, Experiment, NationalMode, Node, NodeMetric, Plan, Route, Subscription, SystemSetting, TelemetryPoint, TokenPair, User } from './types'

const base = import.meta.env.VITE_API_URL ?? ''
const ACCESS_KEY = 'pars2ray.access'
const REFRESH_KEY = 'pars2ray.refresh'
let access = localStorage.getItem(ACCESS_KEY) ?? ''
let refresh = localStorage.getItem(REFRESH_KEY) ?? ''
let refreshRequest: Promise<boolean> | null = null

export function setSession(tokens: TokenPair) {
  access = tokens.access_token
  refresh = tokens.refresh_token
  localStorage.setItem(ACCESS_KEY, access)
  localStorage.setItem(REFRESH_KEY, refresh)
}

export function clearSession() {
  access = ''
  refresh = ''
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

export function hasAccess() { return Boolean(access) }

async function renew(): Promise<boolean> {
  if (!refresh) return false
  if (!refreshRequest) {
    refreshRequest = fetch(`${base}/api/v1/auth/refresh`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token: refresh }),
    }).then(async response => {
      if (!response.ok) return false
      setSession(await response.json() as TokenPair)
      return true
    }).catch(() => false).finally(() => { refreshRequest = null })
  }
  return refreshRequest
}

async function request<T>(path: string, options: RequestInit = {}, retried = false): Promise<T> {
  const response = await fetch(`${base}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(access ? { Authorization: `Bearer ${access}` } : {}), ...(options.headers ?? {}) },
  })
  if (response.status === 401 && !retried && await renew()) return request<T>(path, options, true)
  if (response.status === 401) clearSession()
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText })) as { detail?: string }
    throw new Error(body.detail ?? `request_failed_${response.status}`)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  login: (username: string, password: string) => request<TokenPair>('/api/v1/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  logout: () => request<{ ok: boolean }>('/api/v1/auth/logout', { method: 'POST', body: JSON.stringify({ refresh_token: refresh }) }).finally(clearSession),
  dashboard: () => request<Dashboard>('/api/v1/dashboard'),
  telemetry: (hours = 24) => request<TelemetryPoint[]>(`/api/v1/dashboard/telemetry?hours=${hours}`),
  nodes: () => request<Node[]>('/api/v1/nodes'),
  nodeMetrics: (nodeKey: string, limit = 60) => request<NodeMetric[]>(`/api/v1/nodes/${nodeKey}/metrics?limit=${limit}`),
  routes: () => request<Route[]>('/api/v1/routes'),
  createRoute: (payload: { name: string; node_keys: string[]; core: string; protocol: string; transport: string; config: Record<string, unknown> }) => request<Route>('/api/v1/routes', { method: 'POST', body: JSON.stringify(payload) }),
  activateRoute: (id: number) => request<{ ok: boolean }>(`/api/v1/routes/${id}/activate`, { method: 'POST' }),
  experiments: () => request<Experiment[]>('/api/v1/experiments'),
  promoteExperiment: (id: number, level: string) => request<{ ok: boolean }>(`/api/v1/experiments/${id}/promote?level=${encodeURIComponent(level)}`, { method: 'POST' }),
  decisions: () => request<Decision[]>('/api/v1/optimizer/decisions'),
  candidates: () => request<{ candidates: Candidate[]; mode: string }>('/api/v1/optimizer/candidates'),
  decide: (payload: Record<string, unknown>) => request<{ action: string; reason: string; ai_called: boolean }>('/api/v1/optimizer/decide', { method: 'POST', body: JSON.stringify(payload) }),
  users: () => request<User[]>('/api/v1/users'),
  createUser: (payload: Record<string, unknown>) => request<User>('/api/v1/users', { method: 'POST', body: JSON.stringify(payload) }),
  updateUser: (id: number, payload: Record<string, unknown>) => request<User>(`/api/v1/users/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  plans: () => request<Plan[]>('/api/v1/plans'),
  createPlan: (payload: Record<string, unknown>) => request<Plan>('/api/v1/plans', { method: 'POST', body: JSON.stringify(payload) }),
  subscriptions: () => request<Subscription[]>('/api/v1/subscriptions'),
  createSubscription: (payload: Record<string, unknown>) => request<{ id: number; token: string; expires_at: string }>('/api/v1/subscriptions', { method: 'POST', body: JSON.stringify(payload) }),
  command: (nodeKey: string, action: string) => request<Record<string, unknown>>(`/api/v1/nodes/${nodeKey}/${action}`, { method: 'POST', body: JSON.stringify(action === 'benchmark' ? { host: '1.1.1.1', port: 443, attempts: 5 } : {}) }),
  removeNode: (nodeKey: string) => request<{ ok: boolean }>(`/api/v1/nodes/${nodeKey}`, { method: 'DELETE' }),
  auditLogs: () => request<AuditLog[]>('/api/v1/audit-logs'),
  settings: () => request<SystemSetting[]>('/api/v1/system/settings'),
  updateSetting: (key: string, value: string) => request<{ ok: boolean }>(`/api/v1/system/settings/${encodeURIComponent(key)}`, { method: 'PUT', body: JSON.stringify({ value }) }),
  nationalMode: () => request<NationalMode>('/api/v1/national-mode'),
  createApiKey: (name: string, scopes: string[]) => request<{ key: string; warning: string }>(`/api/v1/api-keys?name=${encodeURIComponent(name)}`, { method: 'POST', body: JSON.stringify(scopes) }),
}
