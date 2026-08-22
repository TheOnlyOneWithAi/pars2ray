import { useEffect, useState } from 'react'
import { api } from './api'
import { Empty, Field, Icon, Modal, Panel, type T } from './ui'

type Candidate={candidate_id:string;path:string[];core:string;protocol:string;transport:string;settings:Record<string,unknown>;score:number;node:{node_key:string;country:string;endpoint:string;core:string;latency_ms:number}}

export function AiInboundsPage({t,notify}:{t:T;notify:(message:string,kind?:'success'|'error')=>void}){
 const [items,setItems]=useState<Candidate[]>([]);const [selected,setSelected]=useState<Candidate|null>(null);const [name,setName]=useState('');const [loading,setLoading]=useState(false)
 async function load(){setLoading(true);try{const r=await api.aiInboundRecommendations(12);setItems(r.candidates)}catch(e){notify(e instanceof Error?e.message:t('failed'),'error')}finally{setLoading(false)}}
 useEffect(()=>{void load()},[])
 async function choose(){if(!selected)return;try{await api.selectAiInbound({candidate_id:selected.candidate_id,node_key:selected.node.node_key,core:selected.core,protocol:selected.protocol,transport:selected.transport,port:443,security:'reality',name:name.trim()||`${selected.protocol}-${selected.node.node_key}`,config:{security:'reality',server_name:'www.cloudflare.com',reality:{fingerprint:'chrome'}}});notify('Inbound created and applied to node');setSelected(null);setName('');await load()}catch(e){notify(e instanceof Error?e.message:t('failed'),'error')}}
 return <Panel title="AI Inbounds" eyebrow="AI GENERATED · OPERATOR SELECTS" className="page-panel" action={<button className="button ghost" onClick={()=>void load()}><Icon name="refresh" size={15}/>Refresh</button>}>
  <p className="muted">AI generates inbound candidates from live node health. Nothing is applied until you choose a candidate.</p>
  <div className="protocol-grid">{items.map(item=><article className="protocol-card" key={item.candidate_id}><header><div><strong>{item.protocol.toUpperCase()} · {item.transport}</strong><small>{item.core} · {item.node.country} · {item.node.node_key}</small></div><span className="score-value">{item.score.toFixed(1)}</span></header><div className="detail-list"><div><span>Latency</span><strong>{item.node.latency_ms.toFixed(0)} ms</strong></div><div><span>Endpoint</span><code>{item.node.endpoint}</code></div><div><span>Security</span><strong>REALITY</strong></div></div><button className="button primary wide" onClick={()=>setSelected(item)}>Use this inbound</button></article>)}</div>{!items.length&&!loading&&<Empty t={t}/>} 
  {selected&&<Modal title="Select inbound" onClose={()=>setSelected(null)}><div className="modal-body form-grid"><Field label="Inbound name" className="span-2"><input value={name} onChange={e=>setName(e.target.value)} placeholder={`${selected.protocol}-${selected.node.node_key}`}/></Field><div className="detail-list span-2"><div><span>Node</span><strong>{selected.node.node_key}</strong></div><div><span>Protocol</span><strong>{selected.protocol}</strong></div><div><span>Transport</span><strong>{selected.transport}</strong></div><div><span>Score</span><strong>{selected.score.toFixed(1)}</strong></div></div><div className="form-actions span-2"><button className="button ghost" onClick={()=>setSelected(null)}>Cancel</button><button className="button primary" onClick={()=>void choose()}>Create & apply</button></div></div></Modal>}
 </Panel>
}
