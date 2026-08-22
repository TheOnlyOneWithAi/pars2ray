import { useState, type FormEvent } from 'react'
import { api } from './api'
import type { User } from './types'
import { Field, Icon, Panel, type T } from './ui'

type Props = { t: T; notify: (message: string, kind?: 'success' | 'error') => void }

export function RulesPage({ t, notify }: Props) {
  const [busy, setBusy] = useState(false)
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true)
    const data = new FormData(event.currentTarget)
    try {
      await api.createUser({ username: String(data.get('username')).trim(), email: String(data.get('email')).trim() || null, password: String(data.get('password')), role: String(data.get('role')), is_active: true })
      event.currentTarget.reset(); notify('Admin created')
    } catch (error) { notify(error instanceof Error ? error.message : t('failed'), 'error') } finally { setBusy(false) }
  }
  return <div className="simple-page">
    <Panel title="Admins & Rules" eyebrow="ACCESS CONTROL" className="simple-panel">
      <div className="simple-actions"><span className="simple-help">Create an admin with one form. Role controls what the account can manage.</span></div>
      <form className="simple-form" onSubmit={create}>
        <Field label="Username"><input name="username" minLength={3} required autoComplete="username" /></Field>
        <Field label="Email"><input name="email" type="email" /></Field>
        <Field label="Password"><input name="password" type="password" minLength={12} required autoComplete="new-password" /></Field>
        <Field label="Role"><select name="role" defaultValue="ADMIN"><option value="ADMIN">Admin</option><option value="OPERATOR">Operator</option><option value="RESELLER">Reseller</option></select></Field>
        <div className="simple-submit"><button className="button primary" disabled={busy}><Icon name="plus" size={15}/>{busy ? 'Creating…' : 'Create admin'}</button></div>
      </form>
    </Panel>
    <Panel title="Quick rules" eyebrow="SIMPLE POLICY" className="simple-panel">
      <div className="rule-list"><div><strong>ADMIN</strong><span>Users, subscriptions, nodes and operational management.</span></div><div><strong>OPERATOR</strong><span>Operational work without account administration.</span></div><div><strong>RESELLER</strong><span>Create subscriptions for assigned customers.</span></div></div>
    </Panel>
  </div>
}
