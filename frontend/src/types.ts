export type Page = 'dashboard' | 'nodes' | 'ai-inbounds' | 'users' | 'settings'
export type Locale = 'en' | 'fa' | 'ru'

export type Node = {
  id: number
  node_key: string
  country: string
  endpoint: string
  status: string
  score: number
  cpu_percent: number
  memory_percent: number
  traffic_rx_bytes: number
  traffic_tx_bytes: number
  latency_ms: number
  core: string
  core_version: string
  agent_version: string
  capabilities: Record<string, unknown>
  last_seen_at: string | null
  created_at: string
}

export type Dashboard = {
  node_count: number
  online_nodes: number
  network_health: number
  traffic: { rx_bytes: number; tx_bytes: number }
  current_best_route: string | null
  ai_status: string
  mode: string
  user_count: number
  subscription_count: number
}

export type Route = {
  id: number
  name: string
  node_keys: string[]
  core: string
  protocol: string
  transport: string
  status: string
  score: number
  is_active: boolean
  is_golden: boolean
  consecutive_wins: number
  updated_at: string
}

export type Experiment = { id: number; candidate_id: string; node_keys: string[]; core: string; protocol: string; transport: string; score: number; latency_ms: number; jitter_ms: number; packet_loss_percent: number; throughput_mbps: number; stability_percent: number; level: string; decision: string; created_at: string }
export type Decision = { id: number; current_score: number; proposed_score: number; action: string; candidate_id: string | null; reason: string; ai_called: boolean; model: string; input_tokens: number; cached_tokens: number; output_tokens: number; created_at: string }
export type Candidate = { candidate_id: string; path: string[]; core: string; protocol: string; transport: string; settings: Record<string, unknown>; score?: number }
export type NodeMetric = { id: number; latency_ms: number; jitter_ms: number; packet_loss_percent: number; throughput_mbps: number; cpu_percent: number; memory_percent: number; stability_percent: number; measured_at: string }
export type TelemetryPoint = { timestamp: string; rx_bytes: number; tx_bytes: number; samples: number }
export type TrafficBreakdown = { node_key: string; country: string; rx_bytes: number; tx_bytes: number; samples: number }
export type User = { id: number; username: string; email: string | null; is_active: boolean; role: string }
export type Plan = { id: number; name: string; quota_gb: number; duration_days: number; max_devices: number; price_minor: number; enabled: boolean }
export type Subscription = { id: number; user_id: number; plan_id: number; node_keys: string[]; enabled: boolean; used_gb: number; expires_at: string; created_at: string }
export type SystemSetting = { key: string; is_secret: boolean; updated_at: string }
export type NationalMode = { mode: string; failures: number; successes: number }
export type AuditLog = { id: number; action: string; actor_username: string; resource_type: string; resource_id: string; ip_address: string; created_at: string }
export type TokenPair = { access_token: string; refresh_token: string; token_type: string; expires_in: number }
