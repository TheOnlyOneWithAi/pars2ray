import { useEffect, useState } from 'react'
import { api } from './api'

const arrayOf = (value: unknown): Array<Record<string, unknown>> => Array.isArray(value) ? value.filter(item => item && typeof item === 'object') as Array<Record<string, unknown>> : []
const itemsOf = (value: unknown): Array<Record<string, unknown>> => { if (Array.isArray(value)) return arrayOf(value); if (value && typeof value === 'object') { const raw = value as Record<string, unknown>; return arrayOf(raw.items) } return [] }
const rulesOf = (value: unknown): Array<Record<string, unknown>> => { if (Array.isArray(value)) return arrayOf(value); if (value && typeof value === 'object') return arrayOf((value as Record<string, unknown>).rules); return [] }

export function ControlPlanePage({ notify }: { notify: (message: string, kind?: 'success'|'error') => void }) {
  const [outbounds, setOutbounds] = useState<Array<Record<string, unknown>>>([])
  const [rules, setRules] = useState<Array<Record<string, unknown>>>([])
  const [balancers, setBalancers] = useState<Array<Record<string, unknown>>>([])
  const [fallbacks, setFallbacks] = useState<Array<Record<string, unknown>>>([])
  const [tag, setTag] = useState('direct')
  const [protocol, setProtocol] = useState('freedom')
  const [routeOutbound, setRouteOutbound] = useState('direct')
  const [domain, setDomain] = useState('')
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    try {
      const [ob, rr, bb, ff] = await Promise.all([api.outbounds(), api.routingRules(), api.balancers(), api.fallbacks()])
      setOutbounds(itemsOf(ob)); setRules(rulesOf(rr)); setBalancers(itemsOf(bb)); setFallbacks(itemsOf(ff))
    } catch (error) { notify(error instanceof Error ? error.message : 'control plane load failed', 'error') } finally { setLoading(false) }
  }
  useEffect(() => { void load() }, [])

  async function addOutbound() {
    try { await api.createOutbound({ tag: tag.trim(), protocol, settings: {} }); notify('Outbound created'); setTag(''); await load() }
    catch (error) { notify(error instanceof Error ? error.message : 'outbound create failed', 'error') }
  }
  async function removeOutbound(id: string) {
    try { await api.deleteOutbound(id); notify('Outbound deleted'); await load() }
    catch (error) { notify(error instanceof Error ? error.message : 'outbound delete failed', 'error') }
  }
  async function addRule() {
    if (!domain.trim() || !routeOutbound.trim()) return notify('Domain and outbound are required', 'error')
    try { await api.createRoutingRule({ domain: [domain.trim()], outboundTag: routeOutbound.trim() }); notify('Routing rule created'); setDomain(''); await load() }
    catch (error) { notify(error instanceof Error ? error.message : 'routing rule create failed', 'error') }
  }
  async function removeRule(id: string) {
    try { await api.deleteRoutingRule(id); notify('Routing rule deleted'); await load() }
    catch (error) { notify(error instanceof Error ? error.message : 'routing rule delete failed', 'error') }
  }
  async function replaceList(kind: 'balancers'|'fallbacks', value: Array<Record<string, unknown>>) {
    try { if (kind === 'balancers') await api.replaceBalancers(value); else await api.replaceFallbacks(value); notify(`${kind} updated`); await load() }
    catch (error) { notify(error instanceof Error ? error.message : `${kind} update failed`, 'error') }
  }

  if (loading) return <section className="panel"><h2>Control Plane</h2><p>Loading resources…</p></section>
  return <div className="stack">
    <section className="panel"><div className="panel-header"><div><span className="eyebrow">Xray / sing-box</span><h2>Outbounds</h2><p>Real outbound resources used when node configuration is composed.</p></div></div><div className="form-grid"><input className="input" placeholder="Tag" value={tag} onChange={e => setTag(e.target.value)}/><select className="input" value={protocol} onChange={e => setProtocol(e.target.value)}><option>freedom</option><option>blackhole</option><option>dns</option><option>http</option><option>socks</option><option>vmess</option><option>vless</option><option>trojan</option><option>shadowsocks</option><option>wireguard</option><option>loopback</option></select><button className="button primary" onClick={() => void addOutbound()} disabled={!tag.trim()}>Add outbound</button></div><div className="list">{outbounds.map(item => <div className="list-row" key={String(item.id ?? item.tag)}><div><strong>{String(item.tag ?? '')}</strong><small>{String(item.protocol ?? '')}</small></div><button className="button danger" onClick={() => void removeOutbound(String(item.id ?? item.tag ?? ''))}>Delete</button></div>)}</div></section>
    <section className="panel"><div className="panel-header"><div><span className="eyebrow">Traffic policy</span><h2>Routing rules</h2></div></div><div className="form-grid"><input className="input" placeholder="domain.example" value={domain} onChange={e => setDomain(e.target.value)}/><select className="input" value={routeOutbound} onChange={e => setRouteOutbound(e.target.value)}>{outbounds.map(item => <option key={String(item.id ?? item.tag)} value={String(item.tag ?? '')}>{String(item.tag ?? '')}</option>)}</select><button className="button primary" onClick={() => void addRule()}>Add rule</button></div><div className="list">{rules.map(item => <div className="list-row" key={String(item.id ?? Math.random())}><div><strong>{JSON.stringify(item.domain ?? item.ip ?? [])}</strong><small>→ {String(item.outboundTag ?? '')}</small></div><button className="button danger" onClick={() => void removeRule(String(item.id ?? ''))}>Delete</button></div>)}</div></section>
    <section className="panel"><div className="panel-header"><div><span className="eyebrow">Traffic distribution</span><h2>Balancers</h2><p>{balancers.length} configured.</p></div><button className="button ghost" onClick={() => void replaceList('balancers', balancers)}>Save</button></div></section>
    <section className="panel"><div className="panel-header"><div><span className="eyebrow">Inbound recovery</span><h2>Fallbacks</h2><p>{fallbacks.length} configured.</p></div><button className="button ghost" onClick={() => void replaceList('fallbacks', fallbacks)}>Save</button></div></section>
  </div>
}
