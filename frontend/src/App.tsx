import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { api, clearSession, hasAccess, isMockMode, setSession } from './api'
import { direction, translate, type TranslationKey } from './i18n'
import { AdminSettingsPage } from './AdminSettingsPage'
import { AiSettingsPanel } from './AiSettingsPanel'
import { NodeProvisionPage } from './NodeProvisionPage'
import { TrafficUsersPage } from './TrafficUsersPage'
import { AiInboundsPage } from './AiInboundsPage'
import { ControlDashboardPage } from './ControlDashboardPage'
import { ControlPlanePage } from './ControlPlanePage'
import type { Dashboard, Locale, Node, Page, TelemetryPoint, TrafficBreakdown } from './types'
import { Icon, Spinner } from './ui'

const pages: Page[] = ['dashboard', 'nodes', 'ai-inbounds', 'users', 'control', 'settings']
function initialPage(): Page { const hash = location.hash.replace('#/', '') as Page; return pages.includes(hash) ? hash : 'dashboard' }

export default function App() {
  const [page, setPageState] = useState<Page>(initialPage())
  const [locale, setLocaleState] = useState<Locale>((localStorage.getItem('pars2ray.locale') as Locale) || 'en')
  const [dashboard, setDashboard] = useState<Dashboard | null>(null)
  const [nodes, setNodes] = useState<Node[]>([])
  const [telemetry, setTelemetry] = useState<TelemetryPoint[]>([])
  const [trafficBreakdown, setTrafficBreakdown] = useState<TrafficBreakdown[]>([])
  const [loading, setLoading] = useState(hasAccess())
  const [bootError, setBootError] = useState('')
  const [sidebar, setSidebar] = useState(false)
  const [toasts, setToasts] = useState<{ id: number; message: string; kind: 'success'|'error' }[]>([])
  const t = useCallback((key: TranslationKey) => translate(locale, key), [locale])
  const notify = useCallback((message: string, kind: 'success'|'error' = 'success') => { const id = Date.now() + Math.random(); setToasts(items => [...items, { id, message, kind }]); window.setTimeout(() => setToasts(items => items.filter(item => item.id !== id)), 4500) }, [])
  const loadAll = useCallback(async () => {
    setBootError('')
    try {
      const [dashboardResult, nodesResult, telemetryResult, breakdownResult] = await Promise.all([api.dashboard(), api.nodes(), api.telemetry().catch(() => []), api.trafficBreakdown().catch(() => [])])
      setDashboard(dashboardResult); setNodes(nodesResult); setTelemetry(telemetryResult); setTrafficBreakdown(breakdownResult)
    } catch (error) {
      const message = error instanceof Error ? error.message : t('failed')
      if (!isMockMode() && !hasAccess()) { clearSession(); location.reload(); return }
      setBootError(message)
      throw error
    }
  }, [t])
  const loadLive = useCallback(async () => { const [dashboardResult, nodesResult, telemetryResult, breakdownResult] = await Promise.all([api.dashboard(), api.nodes(), api.telemetry().catch(() => []), api.trafficBreakdown().catch(() => [])]); setDashboard(dashboardResult); setNodes(nodesResult); setTelemetry(telemetryResult); setTrafficBreakdown(breakdownResult) }, [])
  useEffect(() => { document.documentElement.lang = locale; document.documentElement.dir = direction(locale); localStorage.setItem('pars2ray.locale', locale) }, [locale])
  useEffect(() => { if (!hasAccess()) { setLoading(false); return }; void loadAll().catch(error => notify(error instanceof Error ? error.message : t('failed'), 'error')).finally(() => setLoading(false)); const interval = window.setInterval(() => void loadLive().catch(() => undefined), 30000); return () => window.clearInterval(interval) }, [loadAll, loadLive, notify, t])
  function setPage(next: Page) { setPageState(next); location.hash = `/${String(next)}`; setSidebar(false) }
  if (!hasAccess()) return <Login locale={locale} setLocale={setLocaleState} t={t}/>
  if (loading || (!dashboard && !bootError)) return <div className="boot"><div className="logo-mark"><span>P</span></div><Spinner/><p>{t('loading')}</p></div>
  if (!dashboard && bootError) return <div className="boot"><div className="logo-mark"><span>P</span></div><div className="boot-error"><h2>Pars2Ray could not load the control plane</h2><p>{bootError.replaceAll('_',' ')}</p><div className="row-actions"><button className="button primary" onClick={() => { setLoading(true); void loadAll().catch(() => undefined).finally(() => setLoading(false)) }}>Retry</button><button className="button ghost" onClick={() => { clearSession(); location.reload() }}>Sign in again</button></div></div></div>
  const currentDashboard = dashboard
  if (!currentDashboard) return null
  const common = { t, locale, notify }; const pageName = page as string; let content
  if (pageName === 'dashboard') content = <ControlDashboardPage {...common} dashboard={currentDashboard} nodes={nodes} telemetry={telemetry} trafficBreakdown={trafficBreakdown} openPage={setPage}/>
  else if (pageName === 'nodes') content = <NodeProvisionPage {...common} nodes={nodes} reload={loadAll}/>
  else if (pageName === 'ai-inbounds') content = <AiInboundsPage {...common}/>
  else if (pageName === 'users') content = <TrafficUsersPage {...common}/>
  else if (pageName === 'control') content = <ControlPlanePage notify={notify}/>
  else content = <><AiSettingsPanel {...common}/><AdminSettingsPage notify={notify}/></>
  return <div className="app-shell"><aside className={`sidebar ${sidebar ? 'open' : ''}`}><div className="brand"><div className="logo-mark"><span>P</span></div><div><strong>Pars2Ray</strong><small>CONTROL PLANE</small></div><button className="mobile-close" onClick={() => setSidebar(false)}><Icon name="close"/></button></div><nav>{pages.map(item => { const name = String(item); return <button key={name} className={pageName === name ? 'active' : ''} onClick={() => setPage(item)}><Icon name={name}/><span>{name === 'ai-inbounds' ? 'AI Inbounds' : name === 'users' ? 'Users' : name === 'control' ? 'Control' : t(item as TranslationKey)}</span>{pageName === name && <i/>}</button> })}</nav><div className="sidebar-footer"><div><span className="live-dot"/><strong>{isMockMode() ? 'Demo mode' : t('masterOnline')}</strong></div><small>{isMockMode() ? 'Local test data' : t('production')}</small></div></aside>{sidebar && <button className="sidebar-scrim" aria-label="close" onClick={() => setSidebar(false)}/>}<main className="main"><header className="topbar"><div className="title-group"><button className="menu-button" onClick={() => setSidebar(true)}><Icon name="menu"/></button><div><span className="breadcrumb">PARS2RAY / {nameLabel(pageName, t).toUpperCase()}</span><h1>{nameLabel(pageName, t)}</h1></div></div><div className="top-actions"><span className={`mode-indicator ${isMockMode() ? 'demo' : currentDashboard.mode.toLowerCase()}`}><i/>{isMockMode() ? 'DEMO' : currentDashboard.mode}</span><button className="icon-btn refresh-button" title={t('refresh')} onClick={() => void loadAll().then(() => notify(t('completed'))).catch(() => undefined)}><Icon name="refresh"/></button><LocalePicker locale={locale} setLocale={setLocaleState}/><details className="account-menu"><summary><span className="avatar">SA</span></summary><div><span>Super Admin</span><small>{isMockMode() ? 'Local demo' : 'Control plane'}</small><button onClick={() => void api.logout().finally(() => location.reload())}>{t('signOut')}</button></div></details></div></header><div className="page-content">{content}</div></main><div className="toast-stack">{toasts.map(toast => <div className={`toast ${toast.kind}`} key={toast.id}><span>{toast.kind === 'success' ? <Icon name="check" size={16}/> : '!'}</span><p>{toast.message.replaceAll('_',' ')}</p><button onClick={() => setToasts(items => items.filter(item => item.id !== toast.id))}><Icon name="close" size={14}/></button></div>)}</div></div>
}
function nameLabel(page: string, t: (key: TranslationKey) => string) { return page === 'ai-inbounds' ? 'AI Inbounds' : page === 'users' ? 'Users' : page === 'control' ? 'Control' : t(page as TranslationKey) }
function LocalePicker({ locale, setLocale }: { locale: Locale; setLocale: (locale: Locale) => void }) { return <select className="locale-picker" value={locale} onChange={event => setLocale(event.target.value as Locale)} aria-label="Language"><option value="en">EN</option><option value="fa">فا</option><option value="ru">RU</option></select> }
function Login({ locale, setLocale, t }: { locale: Locale; setLocale: (locale: Locale) => void; t: (key: TranslationKey) => string }) {
  const [submitting, setSubmitting] = useState(false); const [error, setError] = useState(''); const year = useMemo(() => new Date().getFullYear(), [])
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setSubmitting(true); setError(''); const form = new FormData(event.currentTarget); try { setSession(await api.login(String(form.get('username')), String(form.get('password')))); location.reload() } catch (caught) { setError(caught instanceof Error ? caught.message : t('failed')); setSubmitting(false) } }
  return <div className="login-page"><div className="login-glow one"/><div className="login-glow two"/><section className="login-card"><header><div className="brand"><div className="logo-mark"><span>P</span></div><div><strong>Pars2Ray</strong><small>CONTROL PLANE</small></div></div><LocalePicker locale={locale} setLocale={setLocaleState}/></header><div className="login-title"><span>{t('authorizedOnly')}</span><h1>{t('signIn')}</h1><p>{t('sessionAccess')}</p></div><form onSubmit={submit}><label><span>{t('username')}</span><input name="username" autoComplete="username" minLength={3} required autoFocus/></label><label><span>{t('password')}</span><input name="password" type="password" autoComplete="current-password" minLength={12} required/></label>{error && <p className="login-error">{error.replaceAll('_',' ')}</p>}<button className="button primary wide" disabled={submitting}>{submitting && <Spinner/>}{t('signIn')}</button></form><footer><span>© {year} Pars2Ray</span><span className="secure-session"><i/>{t('production')}</span></footer></section></div>
}