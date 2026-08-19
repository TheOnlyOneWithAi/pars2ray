import type { Dashboard, Node, Route } from './types'

const base = import.meta.env.VITE_API_URL ?? ''
let access = localStorage.getItem('pars2ray.access') ?? ''

export function setAccess(value: string) { access = value; localStorage.setItem('pars2ray.access', value) }
export function hasAccess() { return Boolean(access) }

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${base}${path}`, { ...options, headers: { 'Content-Type': 'application/json', ...(access ? { Authorization: `Bearer ${access}` } : {}), ...(options.headers ?? {}) } })
  if (!response.ok) throw new Error((await response.json().catch(() => ({ detail: response.statusText }))).detail ?? 'Request failed')
  return response.json() as Promise<T>
}

export const api = {
  dashboard: () => request<Dashboard>('/api/v1/dashboard'),
  nodes: () => request<Node[]>('/api/v1/nodes'),
  routes: () => request<Route[]>('/api/v1/routes'),
  experiments: () => request<any[]>('/api/v1/experiments'),
  decisions: () => request<any[]>('/api/v1/optimizer/decisions'),
  users: () => request<any[]>('/api/v1/users'),
  subscriptions: () => request<any[]>('/api/v1/subscriptions'),
  command: (nodeKey: string, action: string) => request(`/api/v1/nodes/${nodeKey}/${action}`, { method: 'POST', body: JSON.stringify(action === 'benchmark' ? { host: '1.1.1.1', port: 443, attempts: 5 } : {}) }),
  remove: (nodeKey: string) => request(`/api/v1/nodes/${nodeKey}`, { method: 'DELETE' }),
}
