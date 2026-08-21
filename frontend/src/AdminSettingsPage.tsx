import { useEffect, useState } from 'react'
import { api } from './api'
import { Field, Panel, Spinner } from './ui'

type Props = { notify: (message: string, kind?: 'success' | 'error') => void }

export function AdminSettingsPage({ notify }: Props) {
  const [domain, setDomain] = useState('')
  const [email, setEmail] = useState('')
  const [tls, setTls] = useState(true)
  const [html, setHtml] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => { void Promise.all([api.panelDomain(), api.subscriptionHtml()]).then(([proxy, page]) => { setDomain(proxy.domain ?? ''); setEmail(proxy.email ?? ''); setTls(proxy.tls ?? true); setHtml(page.html ?? '') }).catch(error => notify(error instanceof Error ? error.message : 'failed', 'error')) }, [notify])

  async function saveDomain() {
    setBusy(true)
    try { const result = await api.updatePanelDomain({ domain, tls, email: email || undefined }); notify(result.url ?? 'completed') } catch (error) { notify(error instanceof Error ? error.message : 'failed', 'error') } finally { setBusy(false) }
  }
  async function saveHtml() {
    setBusy(true)
    try { await api.updateSubscriptionHtml(html); notify('subscription_page_saved') } catch (error) { notify(error instanceof Error ? error.message : 'failed', 'error') } finally { setBusy(false) }
  }

  return <div className="dashboard-grid">
    <Panel title="Panel domain & SSL" eyebrow="PUBLIC ACCESS" className="page-panel">
      <div className="form-grid">
        <Field label="Domain" className="span-2"><input value={domain} onChange={event => setDomain(event.target.value)} placeholder="panel.example.com" /></Field>
        <Field label="Certificate email" className="span-2"><input value={email} onChange={event => setEmail(event.target.value)} placeholder="admin@example.com" /></Field>
        <label className="check-grid"><span><input type="checkbox" checked={tls} onChange={event => setTls(event.target.checked)} /> Enable automatic HTTPS / Let's Encrypt</span></label>
        <div className="form-actions span-2"><button className="button primary" disabled={busy || !domain.trim()} onClick={() => void saveDomain()}>{busy && <Spinner/>} Apply domain</button></div>
      </div>
      <p className="helper-text">Point the domain's A/AAAA record to this server first. Pars2Ray installs nginx and obtains/renews the certificate automatically.</p>
    </Panel>
    <Panel title="Subscription page HTML" eyebrow="SUPER ADMIN ONLY" className="page-panel">
      <p className="helper-text">Full HTML is allowed. Available placeholders: <code>{'{{title}}'}</code> <code>{'{{username}}'}</code> <code>{'{{expires_at}}'}</code> <code>{'{{token}}'}</code> <code>{'{{subscription_url}}'}</code> <code>{'{{raw_url}}'}</code> <code>{'{{configs}}'}</code> <code>{'{{vless_links}}'}</code> <code>{'{{config_count}}'}</code> <code>{'{{used_gb}}'}</code> <code>{'{{quota_gb}}'}</code> <code>{'{{remaining_gb}}'}</code> <code>{'{{remaining_percent}}'}</code> <code>{'{{days_remaining}}'}</code> <code>{'{{connection_instructions}}'}</code>.</p>
      <p className="helper-text">Use <code>{'{{vless_links}}'}</code> and <code>{'{{connection_instructions}}'}</code> where you want the clickable VLESS links and connection guide to appear. Values are generated server-side for each subscription.</p>
      <textarea value={html} onChange={event => setHtml(event.target.value)} style={{ width: '100%', minHeight: 520, fontFamily: 'monospace' }} spellCheck={false} />
      <div className="form-actions"><button className="button primary" disabled={busy || !html.trim()} onClick={() => void saveHtml()}>{busy && <Spinner/>} Save subscription page</button></div>
    </Panel>
  </div>
}