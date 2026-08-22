import { useRef, useState, type FormEvent } from 'react'
import { api } from './api'
import type { Locale, Node } from './types'
import { Field, Icon, Modal, Panel, type T } from './ui'

type Notify=(message:string,kind?:'success'|'error')=>void
type Props={t:T;locale:Locale;notify:Notify;nodes:Node[];reload:()=>Promise<void>}
const finite=(value:unknown,fallback=0)=>{const n=Number(value);return Number.isFinite(n)?n:fallback}
export function NodeProvisionPage({t,notify,nodes,reload}:Props){
 const [show,setShow]=useState(false);const [testing,setTesting]=useState(false);const [creating,setCreating]=useState(false);const formRef=useRef<HTMLFormElement>(null)
 async function testSSH(){const form=formRef.current;if(!form)return;setTesting(true);const data=new FormData(form);try{await api.testSSH({host:String(data.get('host')).trim(),username:String(data.get('username')).trim(),password:String(data.get('password')||'')});notify(t('completed'))}catch(error){notify(error instanceof Error?error.message:t('failed'),'error')}finally{setTesting(false)}}
 async function create(event:FormEvent<HTMLFormElement>){event.preventDefault();setCreating(true);const form=new FormData(event.currentTarget);try{await api.provisionNode({node_key:String(form.get('node_key')).trim().toUpperCase(),country:String(form.get('country')).trim().toUpperCase(),ssh:{host:String(form.get('host')).trim(),username:String(form.get('username')).trim(),password:String(form.get('password')||'')}});notify(t('completed'));setShow(false);await reload()}catch(error){notify(error instanceof Error?error.message:t('failed'),'error')}finally{setCreating(false)}}
 return <Panel title={t('managedNodes')} eyebrow="INFRASTRUCTURE" className="page-panel" action={<button className="button primary" onClick={()=>setShow(true)}><Icon name="plus" size={15}/>{t('create')}</button>}>
  <div className="table-scroll"><table><thead><tr><th>Node</th><th>Country</th><th>Status</th><th>Core</th><th>Latency</th></tr></thead><tbody>{nodes.map(node=><tr key={node.id}><td><strong>{node.node_key}</strong></td><td>{node.country}</td><td>{node.status}</td><td>{node.core}</td><td>{finite(node.latency_ms).toFixed(0)} ms</td></tr>)}</tbody></table></div>
  {show&&<Modal title={t('create')} onClose={()=>setShow(false)} wide><form ref={formRef} className="modal-body form-grid" onSubmit={create}><Field label={t('name')}><input name="node_key" placeholder="DE1" pattern="[A-Za-z]{2}[0-9]{0,3}" required autoFocus/></Field><Field label={t('country')}><input name="country" placeholder="DE" minLength={2} maxLength={2} required/></Field><Field label="SSH IP / HOST" className="span-2"><input name="host" placeholder="203.0.113.10" required/></Field><Field label="SSH USER"><input name="username" placeholder="root" required/></Field><Field label="SSH PASSWORD"><input name="password" type="password" autoComplete="new-password" required/></Field><div className="form-actions span-2"><button type="button" className="button ghost" disabled={testing||creating} onClick={()=>void testSSH()}>{testing?'Testing…':'Test SSH'}</button><button type="button" className="button ghost" onClick={()=>setShow(false)}>{t('cancel')}</button><button className="button primary" disabled={creating}>{creating?'Provisioning…':'Provision & Install Agent'}</button></div></form></Modal>}
 </Panel>
}
