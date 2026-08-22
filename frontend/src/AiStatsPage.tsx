import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { MetricCard, Panel, type T, Icon } from './ui'

type Props = { t: T; notify: (message: string, kind?: 'success' | 'error') => void }
type Decision = { action: string; ai_called: boolean; model?: string; input_tokens?: number; output_tokens?: number; cached_tokens?: number; created_at?: string }

export function AiStatsPage({ t, notify }: Props) {
  const [items, setItems] = useState<Decision[]>([])
  const [loading, setLoading] = useState(true)
  useEffect(() => { void api.decisions().then(result => setItems(result as Decision[])).catch(error => notify(error instanceof Error ? error.message : t('failed'), 'error')).finally(() => setLoading(false)) }, [notify, t])
  const stats = useMemo(() => ({ total: items.length, ai: items.filter(item => item.ai_called).length, keep: items.filter(item => item.action === 'KEEP').length, tokens: items.reduce((sum, item) => sum + Number(item.input_tokens || 0) + Number(item.output_tokens || 0), 0) }), [items])
  return <div className="simple-page">
    <div className="metric-grid simple-metrics"><MetricCard label="Decisions" value={stats.total} hint="total" icon="optimizer"/><MetricCard label="AI calls" value={stats.ai} hint="executed" tone="violet" icon="optimizer"/><MetricCard label="KEEP" value={stats.keep} hint="safe decisions" tone="green" icon="check"/><MetricCard label="Tokens" value={stats.tokens.toLocaleString()} hint="input + output" tone="amber" icon="dashboard"/></div>
    <Panel title="AI decision history" eyebrow="AI STATS" action={<button className="button ghost" onClick={() => { setLoading(true); void api.decisions().then(result => setItems(result as Decision[])).catch(error => notify(error instanceof Error ? error.message : t('failed'), 'error')).finally(() => setLoading(false)) }}><Icon name="refresh" size={14}/>Refresh</button>} className="simple-panel">
      {loading ? <div className="simple-empty">Loading…</div> : items.length === 0 ? <div className="simple-empty">No AI decisions yet.</div> : <div className="table-scroll"><table><thead><tr><th>Action</th><th>AI</th><th>Model</th><th>Tokens</th><th>Created</th></tr></thead><tbody>{items.map((item, index) => <tr key={`${item.created_at}-${index}`}><td><strong>{item.action}</strong></td><td>{item.ai_called ? 'Yes' : 'No'}</td><td>{item.model || 'Local policy'}</td><td>{(Number(item.input_tokens || 0) + Number(item.output_tokens || 0)).toLocaleString()}</td><td>{item.created_at ? new Date(item.created_at).toLocaleString() : '—'}</td></tr>)}</tbody></table></div>}
    </Panel>
  </div>
}
