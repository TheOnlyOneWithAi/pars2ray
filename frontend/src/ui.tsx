import type { FormEvent, ReactNode } from 'react'
import type { TranslationKey } from './i18n'

export type T = (key: TranslationKey) => string

const paths: Record<string, ReactNode> = {
  dashboard: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
  nodes: <><rect x="4" y="4" width="16" height="6" rx="2"/><rect x="4" y="14" width="16" height="6" rx="2"/><path d="M8 7h.01M8 17h.01M12 7h5M12 17h5"/></>,
  routes: <><circle cx="5" cy="6" r="2"/><circle cx="19" cy="18" r="2"/><path d="M7 6h4a3 3 0 0 1 3 3v6a3 3 0 0 0 3 3"/><path d="m16 15 3 3-3 3"/></>,
  protocols: <><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18"/></>,
  experiments: <><path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3"/><path d="M8 15h8"/></>,
  optimizer: <><path d="m12 3 1.7 4.3L18 9l-4.3 1.7L12 15l-1.7-4.3L6 9l4.3-1.7L12 3Z"/><path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z"/></>,
  users: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></>,
  subscriptions: <><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 9h10M7 13h7"/></>,
  billing: <><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20M6 15h2"/></>,
  settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21H9.6v-.1A1.7 1.7 0 0 0 8.5 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1.1-.4H3V9.6h.1A1.7 1.7 0 0 0 4.6 8.5a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1.1V3h4v.1A1.7 1.7 0 0 0 15.5 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9c.15.38.36.73.66 1 .3.28.69.42 1.1.4h.1v4h-.1A1.7 1.7 0 0 0 19.4 15Z"/></>,
  refresh: <><path d="M20 11a8 8 0 1 0-2.34 5.66"/><path d="M20 4v7h-7"/></>,
  search: <><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>,
  close: <><path d="M18 6 6 18M6 6l12 12"/></>,
  menu: <><path d="M4 6h16M4 12h16M4 18h16"/></>,
  more: <><circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/></>,
  plus: <><path d="M12 5v14M5 12h14"/></>,
  check: <><path d="m5 12 4 4L19 6"/></>,
  copy: <><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></>,
}

export function Icon({ name, size = 18 }: { name: string; size?: number }) {
  return <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>{paths[name] ?? paths.dashboard}</svg>
}

export function Badge({ value }: { value: string }) { return <span className={`badge badge-${value.toLowerCase().replaceAll('_', '-')}`}><i />{value.replaceAll('_', ' ')}</span> }
export function Progress({ value, warn = false }: { value: number; warn?: boolean }) { return <div className="progress"><span className={warn && value > 80 ? 'warn' : ''} style={{ width: `${Math.max(0, Math.min(value, 100))}%` }} /></div> }
export function Empty({ t }: { t: T }) { return <div className="empty-state"><span>—</span><p>{t('noRecords')}</p></div> }
export function Spinner() { return <span className="spinner" aria-label="loading" /> }

export function MetricCard({ label, value, hint, tone = 'blue', icon }: { label: string; value: string | number; hint: string; tone?: string; icon: string }) {
  return <article className={`metric-card tone-${tone}`}><div className="metric-head"><span className="metric-icon"><Icon name={icon} /></span><span className="metric-trend">{hint}</span></div><strong>{value}</strong><span className="metric-label">{label}</span></article>
}

export function Panel({ title, eyebrow, action, children, className = '' }: { title: string; eyebrow?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={`panel ${className}`}><header className="panel-head"><div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}<h2>{title}</h2></div>{action}</header>{children}</section>
}

export function Modal({ title, children, onClose, wide = false }: { title: string; children: ReactNode; onClose: () => void; wide?: boolean }) {
  return <div className="modal-backdrop" role="presentation" onMouseDown={event => { if (event.currentTarget === event.target) onClose() }}><section className={`modal ${wide ? 'modal-wide' : ''}`} role="dialog" aria-modal="true"><header><h2>{title}</h2><button className="icon-btn" onClick={onClose}><Icon name="close" /></button></header>{children}</section></div>
}

export function Confirm({ t, title, destructive = false, onConfirm, onClose }: { t: T; title: string; destructive?: boolean; onConfirm: () => Promise<void>; onClose: () => void }) {
  async function submit(event: FormEvent) { event.preventDefault(); await onConfirm(); onClose() }
  return <Modal title={t('confirmAction')} onClose={onClose}><form onSubmit={submit} className="modal-body"><p className="confirm-title">{title}</p>{destructive && <p className="muted">{t('irreversible')}</p>}<div className="form-actions"><button type="button" className="button ghost" onClick={onClose}>{t('cancel')}</button><button className={`button ${destructive ? 'danger' : 'primary'}`}>{t('confirm')}</button></div></form></Modal>
}

export function Field({ label, children, className = '' }: { label: string; children: ReactNode; className?: string }) { return <label className={`field ${className}`}><span>{label}</span>{children}</label> }

export function formatBytes(value: number) {
  if (!value) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1)
  return `${(value / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`
}

export function formatDate(value: string | null, locale = 'en') {
  if (!value) return '—'
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

export function ago(value: string | null, locale = 'en') {
  if (!value) return '—'
  const diff = Math.round((new Date(value).getTime() - Date.now()) / 60000)
  const formatter = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' })
  if (Math.abs(diff) < 60) return formatter.format(diff, 'minute')
  return formatter.format(Math.round(diff / 60), 'hour')
}

export function LineChart({ values, secondary = [] }: { values: number[]; secondary?: number[] }) {
  const all = [...values, ...secondary]
  const max = Math.max(...all, 1)
  const min = Math.min(...all, 0)
  const points = (items: number[]) => items.map((value, index) => `${items.length === 1 ? 50 : index / (items.length - 1) * 100},${48 - (value - min) / Math.max(max - min, 1) * 42}`).join(' ')
  return <div className="line-chart"><svg viewBox="0 0 100 50" preserveAspectRatio="none"><defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#5b8cff" stopOpacity=".28"/><stop offset="1" stopColor="#5b8cff" stopOpacity="0"/></linearGradient></defs>{values.length > 1 && <><polygon points={`0,50 ${points(values)} 100,50`} fill="url(#area)"/><polyline points={points(values)} className="chart-primary"/></>}{secondary.length > 1 && <polyline points={points(secondary)} className="chart-secondary"/>}</svg></div>
}
