import { useRef, useState, type FormEvent } from 'react'
import { api } from './api'
import { NodesPage } from './pages'
import type { Locale, Node } from './types'
import { Field, Modal, Panel, type T, Icon } from './ui'

type Notify = (message: string, kind?: 'success' | 'error') => void
type Props = { t: T; locale: Locale; notify: Notify; nodes: Node[]; reload: () => Promise<void> }

export function NodeProvisionPage({ t, locale, notify, nodes, reload }: Props) {
  const [show, setShow] = useState(false)
  const [testing, setTesting] = useState(false)
  const [creating, setCreating] = useState(false)
  const [aiNode, setAiNode] = useState('')
  const [aiBusy, setAiBusy] = useState(false)
  const formRef = useRef<HTMLFormElement>(null)

  async function testSSH() {
    const form = formRef.current
    if (!form) return
    setTesting(true)
    const data = new FormData(form)
    try {
      await api.testSSH({ host: String(data.get('host')).trim(), port: Number(data.get('port') || 22), username: String(data.get('username')).trim(), password: String(data.get('password') || ''), private_key: String(data.get('private_key') || '') })
      notify(t('completed'))
    } catch (error) { notify(error instanceof Error ? error.message : t('failed'), 'error') } finally { setTesting(false) }
  }

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setCreating(true)
    const form = new FormData(event.currentTarget)
    try {
      await api.provisionNode({ node_key: String(form.get('node_key')).trim().toUpperCase(), country: String(form.get('country')).trim().toUpperCase(), endpoint: String(form.get('endpoint')).trim(), ssh: { host: String(form.get('host')).trim(), port: Number(form.get('port') || 22), username: String(form.get('username')).trim(), password: String(form.get('password') || ''), private_key: String(form.get('private_key') || '') } })
      notify(t('completed')); setShow(false); await reload()
    } catch (error) { notify(error instanceof Error ? error.message : t('failed'), 'error') } finally { setCreating(false) }
  }

  async function optimizeExistingInbound() {
    if (!aiNode) return
    setAiBusy(true)
    try {
      const result = await api.configureNodeWithAI(aiNode, true)
      notify(`${aiNode}: ${result.updates.length} inbound(s) updated`)
      await reload()
    } catch (error) { notify(error instanceof Error ? error.message : t('failed'), 'error') } finally { setAiBusy(false) }
  }

  return <>
    <Panel title={t('managedNodes')} eyebrow="INFRASTRUCTURE" className="page-panel" action={<button className="button primary" onClick={() => setShow(true)}><Icon name="plus" size={15}/>{t('create')}</button>}>
      <div>{t('managedNodes')} — SSH provisioning and automatic agent installation</div>
    </Panel>
    <Panel title="AI Inbound Optimizer" eyebrow="SAFE CONFIGURATION" className="page-panel">
      <div className="toolbar"><select value={aiNode} onChange={event => setAiNode(event.target.value)}><option value="">Select node</option>{nodes.map(node => <option key={node.node_key} value={node.node_key}>{node.node_key} · {node.core}</option>)}</select><button className="button primary" disabled={!aiNode || aiBusy} onClick={() => void optimizeExistingInbound()}>{aiBusy ? 'Optimizing…' : 'AI Optimize Existing Inbounds'}</button></div>
      <small>AI may update protocol/transport on existing inbound tags only. It cannot create, delete, retag, or change credentials.</small>
    </Panel>
    <NodesPage t={t} locale={locale} notify={notify} nodes={nodes} reload={reload}/>
    {show && <Modal title={t('create')} onClose={() => setShow(false)} wide><form ref={formRef} className="modal-body form-grid" onSubmit={create}>
      <Field label={t('name')}><input name="node_key" placeholder="DE1" pattern="[A-Za-z]{2}[0-9]{0,3}" required autoFocus/></Field>
      <Field label={t('country')}><input name="country" placeholder="DE" minLength={2} maxLength={2} required/></Field>
      <Field label={t('endpoint')} className="span-2"><input name="endpoint" type="url" placeholder="http://NODE_IP:9100" required/></Field>
      <Field label="SSH HOST"><input name="host" placeholder="203.0.113.10" required/></Field>
      <Field label="SSH PORT"><input name="port" type="number" min={1} max={65535} defaultValue={22} required/></Field>
      <Field label="SSH USER"><input name="username" placeholder="root" required/></Field>
      <Field label="SSH PASSWORD"><input name="password" type="password" autoComplete="off"/></Field>
      <Field label="SSH PRIVATE KEY" className="span-2"><textarea name="private_key" rows={6} placeholder="Optional OpenSSH private key; use password or key"/></Field>
      <div className="form-actions span-2"><button type="button" className="button ghost" disabled={testing || creating} onClick={() => void testSSH()}>{testing ? 'Testing…' : 'Test SSH'}</button><button type="button" className="button ghost" onClick={() => setShow(false)}>{t('cancel')}</button><button className="button primary" disabled={creating}>{creating ? 'Provisioning…' : 'Provision & Install Agent'}</button></div>
    </form></Modal>}
  </>
}
