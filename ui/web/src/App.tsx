import { useEffect } from 'react'
import Landing from './components/Landing'
import Dashboard from './components/Dashboard'
import Auth from './components/Auth'
import Console from './components/Console'
import { AuthProvider, useAuth } from './auth'
import { usePathname, Redirect, interceptLinks } from './router'

function Splash() {
  return (
    <div className="flex min-h-full items-center justify-center">
      <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-faint">Loading…</span>
    </div>
  )
}

function Routes() {
  const path = usePathname()
  const { user, loading } = useAuth()

  if (path === '/live') return <Dashboard />
  if (path === '/login') return <Auth mode="login" />
  if (path === '/signup') return <Auth mode="signup" />
  if (path === '/app' || path.startsWith('/app/')) {
    if (loading) return <Splash /> // wait for session restore before deciding
    if (!user) return <Redirect to="/login" />
    return <Console />
  }
  return <Landing />
}

export default function App() {
  useEffect(() => { interceptLinks() }, [])
  return (
    <AuthProvider>
      <Routes />
    </AuthProvider>
  )
}
