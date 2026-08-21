import { useState } from 'react'
import type { Route } from './types'
import { api } from './api'
import { Panel, Spinner } from './ui'

export function ProtocolConfigPage({ routes, notify }: { routes: Route[]; notify: (message: string, kind?: 'success' | 'error') => void }) {
  const [busy, setBusy] = useState<number | null>(null)
  const [result, setResult] = useState<Record<number, unknown>>({})
  async function build(route: Route, apply: boolean) {
    setBusy(route.id)
    try { const value = await api.buildRouteConfig(route.id, { apply }); setResult(items => ({ ...items, [route.id]: value.config })); notify(apply ? `applied_${route.name}` : `generated_${route.name}`) } catch (error) { notify(error instanceof Error ? error.message : 'failed', 'error') } finally { setBusy(null) }
  }
  return <Panel title="Protocol configuration generator" eyebrow="VLESS · VMESS · TROJAN · SHADOWSOCKS · HYSTERIA2" className="page-panel">
    <div className="table-scroll"><table><thead><tr><th>Route</th><th>Protocol</th><th>Transport</th><th>Core</th><th>Actions</th></tr></thead><tbody>{routes.map(route => <tr key={route.id}><td><strong>{route.name}</strong></td><td><span className="mono-pill">{route.protocol}</span></td><td>{route.transport}</td><td>{route.core}</td><td><div className="row-actions"><button onClick={() => void build(route, false)} disabled={busy === route.id}>{busy === route.id && <Spinner/>} Generate</button><button onClick={() => void build(route, true)} disabled={busy === route.id}>Generate + apply</button></div>{result[route.id] && <pre style={{ maxWidth: 760, maxHeight: 360, overflow: 'auto' }}>{JSON.stringify(result[route.id], null, 2)}</pre>}</td></tr>)}</tbody></table></div>
  </Panel>
}
