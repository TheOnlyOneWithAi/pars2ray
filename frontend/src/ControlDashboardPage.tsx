import { type CSSProperties } from 'react'
import { Panel, MetricCard, Badge, Empty, LineChart, Progress, formatBytes, formatDate, type T } from './ui'
import type { Dashboard, Locale, Node, TelemetryPoint, TrafficBreakdown } from './types'

type HealthStyle = CSSProperties & { '--health'?: string }

const finite = (value: unknown, fallback = 0) => {
 const number = Number(value)
 return Number.isFinite(number) ? number : fallback
}

export function ControlDashboardPage({t,locale,dashboard,nodes,telemetry,trafficBreakdown,openPage}:{t:T;locale:Locale;dashboard:Dashboard;nodes:Node[];telemetry:TelemetryPoint[];trafficBreakdown:TrafficBreakdown[];openPage:(page:'nodes'|'ai-inbounds'|'users')=>void}){
 const nodeCount = finite(dashboard.node_count)
 const onlineNodes = finite(dashboard.online_nodes)
 const networkHealth = Math.max(0, Math.min(100, finite(dashboard.network_health)))
 const rxBytes = finite(dashboard.traffic?.rx_bytes)
 const txBytes = finite(dashboard.traffic?.tx_bytes)
 const userCount = finite(dashboard.user_count)
 const online = nodeCount ? Math.round(onlineNodes / nodeCount * 100) : 0
 return <><div className="metric-grid"><MetricCard label="Nodes" value={nodeCount} hint={`${online}% online`} tone="green" icon="nodes"/><MetricCard label="Network health" value={`${networkHealth.toFixed(1)}%`} hint="Live" tone="blue" icon="dashboard"/><MetricCard label="Total traffic" value={formatBytes(rxBytes+txBytes)} hint="RX + TX" tone="violet" icon="nodes"/><MetricCard label="Client users" value={userCount} hint="Profiles" tone="amber" icon="users"/></div><div className="dashboard-grid"><Panel title="Network traffic" eyebrow="24H TELEMETRY" className="chart-panel">{telemetry.length?<><div className="chart-summary"><div><strong>{formatBytes(telemetry.reduce((s,p)=>s+finite(p.rx_bytes),0))}</strong><span>RX</span></div><div><strong>{formatBytes(telemetry.reduce((s,p)=>s+finite(p.tx_bytes),0))}</strong><span>TX</span></div></div><LineChart values={telemetry.map(p=>finite(p.rx_bytes))} secondary={telemetry.map(p=>finite(p.tx_bytes))}/><div className="chart-axis"><span>{formatDate(telemetry[0].timestamp,locale)}</span><span>{formatDate(telemetry.at(-1)!.timestamp,locale)}</span></div></>:<Empty t={t}/>}</Panel><Panel title="AI inbound engine" eyebrow="OPERATOR CONTROL" className="posture-panel"><div className="health-gauge" style={{'--health':`${networkHealth*3.6}deg`} as HealthStyle}><div><strong>{networkHealth.toFixed(0)}</strong><span>/ 100</span></div></div><div className="active-route"><span>Automation boundary</span><strong>AI recommends only</strong><small>Nothing is applied until you select an inbound.</small></div><button className="button primary wide" onClick={()=>openPage('ai-inbounds')}>Generate best inbounds</button></Panel><Panel title="Node health" eyebrow="LIVE INVENTORY" className="wide-panel" action={<button className="button ghost" onClick={()=>openPage('nodes')}>View</button>}><div className="table-scroll"><table><thead><tr><th>Name</th><th>Country</th><th>Status</th><th>CPU</th><th>Memory</th><th>Latency</th><th>Score</th></tr></thead><tbody>{nodes.slice(0,10).map(node=><tr key={node.id}><td><strong>{node.node_key}</strong></td><td>{node.country}</td><td><Badge value={node.status}/></td><td><Progress value={finite(node.cpu_percent)}/></td><td><Progress value={finite(node.memory_percent)}/></td><td>{finite(node.latency_ms).toFixed(0)} ms</td><td><strong>{finite(node.score).toFixed(1)}</strong></td></tr>)}</tbody></table></div>{!nodes.length&&<Empty t={t}/>}</Panel><Panel title="Traffic by node" eyebrow="PERSISTED COUNTERS" className="wide-panel"><div className="table-scroll"><table><thead><tr><th>Name</th><th>Country</th><th>RX</th><th>TX</th><th>Total</th></tr></thead><tbody>{trafficBreakdown.slice(0,10).map(item=><tr key={item.node_key}><td><strong>{item.node_key}</strong></td><td>{item.country}</td><td>{formatBytes(finite(item.rx_bytes))}</td><td>{formatBytes(finite(item.tx_bytes))}</td><td>{formatBytes(finite(item.rx_bytes)+finite(item.tx_bytes))}</td></tr>)}</tbody></table></div>{!trafficBreakdown.length&&<Empty t={t}/>}</Panel></div></>
}
