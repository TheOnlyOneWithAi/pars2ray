import { useState, type FormEvent } from 'react'
import { api } from './api'
import { NodesPage } from './pages'
import type { Locale, Node } from './types'
import { Field, Icon, Modal, Panel, type T } from './ui'

type Notify = (message: string, kind?: 'success' | 'error') => void
type Props = { t: T; locale: Locale; notify: Notify; nodes: Node[]; reload: () => Promise<void> }
type ProvisionResult = { node_key: string; country: string; endpoint: string; status: string; agent_token: string }

export function NodeProvisionPage({ t, locale, notify, nodes, reload }: Props) {
  const [show, setShow] = useState(false)
  const [result, setResult] = useState<ProvisionResult | null>(null)

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    try {
      const created = await api.provisionNode({
        node_key: String(form.get('node_key')).trim().toUpperCase(),
        country: String(form.get('country')).trim().toUpperCase(),
        endpoint: String(form.get('endpoint')).trim(),
      })
      setResult(created)
      notify(t('completed'))
      await reload()
    } catch (error) {
      notify(error instanceof Error ? error.message : t('failed'), 'error')
    }
  }

  const agentCommand = result
    ? `git clone https://github.com/TheOnlyOneWithAi/pars2ray.git /opt/pars2ray && cd /opt/pars2ray && docker build -t pars2ray-agent ./agent && docker run -d --name pars2ray-agent --restart unless-stopped -e NODE_KEY=${result.node_key} -e COUNTRY=${result.country} -e AGENT_TOKEN=${result.agent_token} -p 9100:9100 pars2ray-agent`
    : ''

  return <>
    <Panel title={t('managedNodes')} eyebrow="INFRASTRUCTURE" className="page-panel" action={<button className="button primary" onClick={() => { setResult(null); setShow(true) }}><Icon name="plus" size={15}/>{t('create')}</button>}>
      <div>{t('managedNodes')} — {t('endpoint')} + {t('agent')} provisioning</div>
    </Panel>
    <NodesPage t={t} locale={locale} notify={notify} nodes={nodes} reload={reload}/>
    {show && <Modal title={result ? t('completed') : t('create')} onClose={() => setShow(false)}>
      {!result ? <form className="modal-body form-grid" onSubmit={create}>
        <Field label={t('name')}><input name="node_key" placeholder="DE1" pattern="[A-Za-z]{2}[0-9]{0,3}" required autoFocus/></Field>
        <Field label={t('country')}><input name="country" placeholder="DE" minLength={2} maxLength={2} required/></Field>
        <Field label={t('endpoint')} className="span-2"><input name="endpoint" type="url" placeholder="https://node.example.com:9100" required/></Field>
        <div className="form-actions span-2"><button type="button" className="button ghost" onClick={() => setShow(false)}>{t('cancel')}</button><button className="button primary">{t('create')}</button></div>
      </form> : <div className="modal-body">
        <p>{t('revealOnce')}</p>
        <Field label="AGENT TOKEN"><textarea readOnly rows={3} value={result.agent_token}/></Field>
        <Field label="INSTALL COMMAND"><textarea readOnly rows={7} value={agentCommand}/></Field>
        <div className="form-actions"><button className="button primary" onClick={() => navigator.clipboard?.writeText(agentCommand)}>{t('create')}</button><button className="button ghost" onClick={() => setShow(false)}>{t('close')}</button></div>
      </div>}
    </Modal>}
  </>
}
