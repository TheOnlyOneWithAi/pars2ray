import { Component, Suspense, lazy, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'
import './compact-ui.css'

const App = lazy(() => import('./App'))

class BootstrapErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  render() {
    if (this.state.error) {
      return <div className="boot"><div className="logo-mark"><span>P</span></div><div className="boot-error"><h2>Pars2Ray could not start</h2><p>{this.state.error.message || 'Frontend runtime error'}</p><div className="row-actions"><button className="button primary" onClick={() => location.reload()}>Retry</button><button className="button ghost" onClick={() => { localStorage.removeItem('pars2ray.access'); localStorage.removeItem('pars2ray.refresh'); location.reload() }}>Clear session</button></div></div></div>
    }
    return this.props.children
  }
}

createRoot(document.getElementById('root')!).render(
  <BootstrapErrorBoundary>
    <Suspense fallback={<div className="boot"><div className="logo-mark"><span>P</span></div><p>Loading Pars2Ray…</p></div>}>
      <App />
    </Suspense>
  </BootstrapErrorBoundary>,
)
