import { useEffect, useState } from 'react'
import type { Locale } from './types'
import type { T } from './ui'
import { Icon, Panel } from './ui'

type Props = { t: T; locale: Locale; notify: (message: string, kind?: 'success'|'error') => void }
const access = () => localStorage.getItem('pars2ray.access') ?? ''
async function setting(key: string, value: string) { const response = await fetch(`/api/v1/system/settings/${encodeURIComponent(key)}`, { method:'PUT', headers:{'Content-Type':'application/json',Authorization:`Bearer ${access()}`}, body:JSON.stringify({value}) }); if(!response.ok){const body=await response.json().catch(()=>({}));throw new Error(body.detail??`request_failed_${response.status}`)} }

export function AiSettingsPanel({ notify }: Props) {
 const [enabled,setEnabled]=useState(false);const [configured,setConfigured]=useState(false);const [model,setModel]=useState('gpt-5-mini');const [key,setKey]=useState('');const [saving,setSaving]=useState(false)
 async function load(){const response=await fetch('/api/v1/system/ai-status',{headers:{Authorization:`Bearer ${access()}`}});if(!response.ok)throw new Error('ai_status_unavailable');const data=await response.json() as {enabled:boolean;configured:boolean;model:string};setEnabled(data.enabled);setConfigured(data.configured);setModel(data.model)}
 useEffect(()=>{void load().catch(error=>notify(error instanceof Error?error.message:'ai_status_unavailable','error'))},[])
 async function save(){setSaving(true);try{await setting('ai.enabled',String(enabled));await setting('ai.model',model.trim());if(key.trim())await setting('ai.api_key',key.trim());setKey('');setConfigured(true);notify('AI settings saved.');await load()}catch(error){notify(error instanceof Error?error.message:'save_failed','error')}finally{setSaving(false)}}
 return <Panel title="AI Optimizer" eyebrow="OPTIONAL · SERVER-SIDE" className="page-panel"><div className="settings-layout single"><section className="settings-section"><div className="setting-row"><div><span>AI usage</span><small>{enabled?'AI decisions are allowed':'Local optimizer only'}</small></div><label className="switch"><input type="checkbox" checked={enabled} onChange={event=>setEnabled(event.target.checked)}/><i/></label></div><div className="setting-row"><div><span>OpenAI API key</span><small>{configured?'Saved on backend':'Not configured'}</small></div><input type="password" value={key} onChange={event=>setKey(event.target.value)} placeholder={configured?'Enter a new key':'sk-…'} autoComplete="off"/></div><div className="setting-row"><div><span>Model</span></div><input value={model} onChange={event=>setModel(event.target.value)} placeholder="gpt-5-mini"/></div><div className="form-actions"><button className="button primary" disabled={saving||!model.trim()||(enabled&&!configured&&!key.trim())} onClick={()=>void save()}>{saving?'Saving…':<><Icon name="check" size={15}/> Save AI settings</>}</button></div></section></div></Panel>
}
