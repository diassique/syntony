/** Auth context: holds the signed-in identity and bootstraps the session from the
 * httpOnly refresh cookie on load (no token in localStorage). Exposes login/signup/logout.
 * Wrap the app in <AuthProvider>. */

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { authApi, type Org, type User } from './api'

interface AuthState {
  user: User | null
  org: Org | null
  loading: boolean // true while we restore a session from the refresh cookie
  login: (email: string, password: string) => Promise<void>
  signup: (body: { email: string; password: string; name?: string; org_name?: string }) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [org, setOrg] = useState<Org | null>(null)
  const [loading, setLoading] = useState(true)

  // Restore the session: the refresh cookie (if any) yields a fresh access token + identity.
  useEffect(() => {
    authApi.refresh()
      .then((r) => { if (r) { setUser(r.user); setOrg(r.org) } })
      .finally(() => setLoading(false))
  }, [])

  async function login(email: string, password: string): Promise<void> {
    const r = await authApi.login({ email, password })
    setUser(r.user); setOrg(r.org)
  }

  async function signup(body: { email: string; password: string; name?: string; org_name?: string }): Promise<void> {
    const r = await authApi.signup(body)
    setUser(r.user); setOrg(r.org)
  }

  async function logout(): Promise<void> {
    try { await authApi.logout() } finally {
      setUser(null); setOrg(null)
      window.location.hash = '#/login'
    }
  }

  return (
    <AuthContext.Provider value={{ user, org, loading, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  )
}
