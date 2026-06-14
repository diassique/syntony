import { useEffect, useState } from 'react'
import Landing from './components/Landing'
import Dashboard from './components/Dashboard'
import Auth from './components/Auth'
import Console from './components/Console'
import { AuthProvider, useAuth } from './auth'

/** Tiny dependency-free hash router. */
function useHashRoute(): string {
  const [hash, setHash] = useState(() => window.location.hash)
  useEffect(() => {
    const onChange = () => setHash(window.location.hash)
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return hash
}

function Splash() {
  return (
    <div className="flex min-h-full items-center justify-center">
      <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-faint">Loading…</span>
    </div>
  )
}

function Routes() {
  const route = useHashRoute()
  const { user, loading } = useAuth()

  if (route.startsWith('#/live')) return <Dashboard />
  if (route.startsWith('#/login')) return <Auth mode="login" />
  if (route.startsWith('#/signup')) return <Auth mode="signup" />
  if (route.startsWith('#/app')) {
    if (loading) return <Splash /> // wait for session restore before deciding
    if (!user) { window.location.hash = '#/login'; return <Splash /> }
    return <Console />
  }
  return <Landing />
}

export default function App() {
  return (
    <AuthProvider>
      <Routes />
    </AuthProvider>
  )
}
