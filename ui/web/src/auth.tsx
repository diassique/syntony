/** Auth context: holds the signed-in identity, restores it from a stored token on
 * load, and exposes login/signup/logout. Wrap the app in <AuthProvider>. */

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { authApi, getToken, setToken, type Org, type User } from './api'

interface AuthState {
  user: User | null
  org: Org | null
  loading: boolean // true while we restore a session from a stored token
  login: (email: string, password: string) => Promise<void>
  signup: (body: { email: string; password: string; name?: string; org_name?: string }) => Promise<void>
  logout: () => void
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

  // Restore the session: if we hold a token, ask /me who we are (and drop it if stale).
  useEffect(() => {
    if (!getToken()) {
      setLoading(false)
      return
    }
    authApi.me()
      .then((r) => { setUser(r.user); setOrg(r.org) })
      .catch(() => setToken(null))
      .finally(() => setLoading(false))
  }, [])

  async function login(email: string, password: string): Promise<void> {
    const r = await authApi.login({ email, password })
    setToken(r.token); setUser(r.user); setOrg(r.org)
  }

  async function signup(body: { email: string; password: string; name?: string; org_name?: string }): Promise<void> {
    const r = await authApi.signup(body)
    setToken(r.token); setUser(r.user); setOrg(r.org)
  }

  function logout(): void {
    setToken(null); setUser(null); setOrg(null)
    window.location.hash = '#/login'
  }

  return (
    <AuthContext.Provider value={{ user, org, loading, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  )
}
