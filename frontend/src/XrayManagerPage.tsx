import { useEffect, useMemo, useState } from 'react'
import type { Route } from './types'
import { Panel, Spinner } from './ui'

const protocols = ['vless', 'vmess', 'trojan', 'shadowsocks', 'hysteria2']
const transports = ['tcp', 'websocket', 'grpc', 'httpupgrade', 'xhttp', 'quic', 'kcp']
const security = ['none', 'tls', 'reality']

async function call<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('pars2ray.access') ?? ''
  const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(options.headers ?? {}) } })
  if (!response.ok) throw new Error((await response.json().catch(() => ({ detail: response.statusText }))).detail ?? `request_failed_${response.status}`)
  return response.json() as Promise<T>
}

export function XrayManagerPage({ routes, notify }: { routes: Route[]; notify: (message: string, kind?: 'success' | 'error') => void }) {
  const [selected, setSelected] = useState<Route | null>(routes[0] ?? null)
  const [config, setConfig] = useState<Record<string, unknown>>({})
  const [raw, setRaw] = useState('{}')
  const [busy, setBusy] = useState(false)
  const [validation, setValidation] = useState<{ ok: boolean; errors: string[] } | null>(null)
  const [clients, setClients] = useState('[{"id":"00000000-0000-4000-8000-000000000001","email":"client-01"}]')
  const route = selected

  useEffect(() => { if (!route) return; setBusy(true); call<{ config: Record<string, unknown> }>(`/api/v1/xray/routes/${route.id}`).then(value => { setConfig(value.config ?? {}); setRaw(JSON.stringify(value.config ?? {}, null, 2)); setValidation(null) }).catch(error => notify(error instanceof Error ? error.message : 'load_failed', 'error')).finally(() => setBusy(false)) }, [route?.id])
  const currentSecurity = String(config.security ?? (config.tls ? 'tls' : 'none'))
  const reality = (config.reality as Record<string, unknown> | undefined) ?? {}
  const clientCount = useMemo(() => { try { return JSON.parse(clients).length } catch { return 0 } }, [clients])

  function setField(key: string, value: unknown) { const next = { ...config, [key]: value }; setConfig(next); setRaw(JSON.stringify(next, null, 2)); setValidation(null) }
  function parseRaw(): Record<string, unknown> | null { try { const next = JSON.parse(raw) as Record<string, unknown>; setConfig(next); return next } catch { notify('Invalid JSON', 'error'); return null } }
  async function validate() { if (!route) return; const next = parseRaw(); if (!next) return; setBusy(true); try { const result = await call<{ ok: boolean; errors: string[] }>(`/api/v1/xray/routes/${route.id}/validate`, { method: 'POST', body: JSON.stringify({ config: next }) }); setValidation(result); notify(result.ok ? 'Configuration valid' : result.errors.join(', '), result.ok ? 'success' : 'error') } catch (error) { notify(error instanceof Error ? error.message : 'validation_failed', 'error') } finally { setBusy(false) } }
  async function save(apply: boolean) { if (!route) return; const next = parseRaw(); if (!next) return; setBusy(true); try { await call(`/api/v1/xray/routes/${route.id}`, { method: 'PUT', body: JSON.stringify({ core: route.core, protocol: route.protocol, transport: route.transport, node_keys: route.node_keys, config: next }) }); if (apply) await call(`/api/v1/routes/${route.id}/build-config`, { method: 'POST', body: JSON.stringify({ apply: true, clients: JSON.parse(clients) }) }); notify(apply ? 'Saved and applied to managed nodes' : 'Configuration saved') } catch (error) { notify(error instanceof Error ? error.message : 'save_failed', 'error') } finally { setBusy(false) } }

  return <div className="dashboard-grid">
    <Panel title="Xray Manager" eyebrow="3X-UI LEVEL CONFIGURATION" className="wide-panel">
      <div className="toolbar"><select value={route?.id ?? ''} onChange={event => setSelected(routes.find(item => item.id === Number(event.target.value)) ?? null)}>{routes.map(item => <option key={item.id} value={item.id}>{item.name} · {item.protocol} · {item.transport}</option>)}</select><span className="samples-label">{clientCount} clients in build</span></div>
      {!route ? <p>No routes available. Create a route first.</p> : <>
        <div className="form-grid" style={{ marginTop: 16 }}>
          <label><span>Protocol</span><select value={route.protocol} disabled>{protocols.map(item => <option key={item}>{item}</option>)}</select></label>
          <label><span>Transport</span><select value={route.transport} onChange={event => setField('transport', event.target.value)}>{transports.map(item => <option key={item}>{item}</option>)}</select></label>
          <label><span>Security</span><select value={currentSecurity} onChange={event => setField('security', event.target.value)}>{security.map(item => <option key={item}>{item}</option>)}</select></label>
          <label><span>Port</span><input type="number" min="1" max="65535" value={Number(config.port ?? 443)} onChange={event => setField('port', Number(event.target.value))}/></label>
          <label><span>Server name / Host</span><input value={String(config.server_name ?? config.host ?? '')} onChange={event => setField('server_name', event.target.value)}/></label>
          <label><span>Path</span><input value={String(config.path ?? '/')} onChange={event => setField('path', event.target.value)}/></label>
          <label><span>gRPC service</span><input value={String(config.service_name ?? 'pars2ray')} onChange={event => setField('service_name', event.target.value)}/></label>
          <label><span>Client JSON</span><input value={clients} onChange={event => setClients(event.target.value)}/></label>
        </div>
        {currentSecurity === 'reality' && <div className="form-grid" style={{ marginTop: 12 }}><label><span>REALITY destination</span><input value={String(reality.dest ?? 'www.cloudflare.com:443')} onChange={event => setField('reality', { ...reality, dest: event.target.value })}/></label><label><span>Private key</span><input type="password" value={String(reality.private_key ?? '')} onChange={event => setField('reality', { ...reality, private_key: event.target.value })}/></label><label><span>Short ID</span><input value={String(reality.short_id ?? '')} onChange={event => setField('reality', { ...reality, short_id: event.target.value })}/></label><label><span>Fingerprint</span><input value={String(reality.fingerprint ?? 'chrome')} onChange={event => setField('reality', { ...reality, fingerprint: event.target.value })}/></label></div>}
        <div className="row-actions" style={{ marginTop: 16 }}><button onClick={() => setField('sniffing', !Boolean(config.sniffing))}>{config.sniffing ? 'Disable sniffing' : 'Enable sniffing'}</button><button onClick={() => setField('mux', !Boolean(config.mux))}>{config.mux ? 'Disable mux' : 'Enable mux'}</button><button onClick={() => setField('fallbacks', config.fallbacks ? undefined : [{ dest: 8080, xver: 1 }])}>{config.fallbacks ? 'Remove fallback' : 'Add fallback'}</button></div>
        <textarea value={raw} onChange={event => setRaw(event.target.value)} spellCheck={false} style={{ width: '100%', minHeight: 360, marginTop: 16, fontFamily: 'monospace' }}/>
        <div className="form-actions"><button className="button ghost" disabled={busy} onClick={() => void validate()}>{busy && <Spinner/>}Validate</button><button className="button ghost" disabled={busy} onClick={() => void save(false)}>Save</button><button className="button primary" disabled={busy} onClick={() => void save(true)}>Save + Apply</button></div>
        {validation && <pre>{JSON.stringify(validation, null, 2)}</pre>}
      </>}
    </Panel>
  </div>
}
