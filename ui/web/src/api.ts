/** Thin client for the control-plane API (control/api.py).
 *
 * Same-origin: the SPA is served by the FastAPI app that also mounts /api/auth,
 * so relative paths just work in dev (with a Vite proxy) and in prod. The session
 * token is a JWT kept in localStorage and sent as a Bearer header. */

const TOKEN_KEY = 'syntony.token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export interface User {
  id: string
  email: string
  name: string
}

export interface Org {
  id: string
  name: string
  slug: string
  plan: string
}

export interface AuthResult {
  token: string
  user: User
  org: Org | null
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

interface RequestOpts {
  method?: string
  body?: unknown
  auth?: boolean
}

async function request<T>(path: string, opts: RequestOpts = {}): Promise<T> {
  const headers: Record<string, string> = {}
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json'
  if (opts.auth) {
    const token = getToken()
    if (token) headers['Authorization'] = `Bearer ${token}`
  }
  const res = await fetch(path, {
    method: opts.method ?? 'GET',
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  })
  const text = await res.text()
  const data = text ? JSON.parse(text) : null
  if (!res.ok) {
    throw new ApiError(res.status, extractDetail(data) ?? `request failed (${res.status})`)
  }
  return data as T
}

/** FastAPI puts errors in `detail` — a string for our HTTPExceptions, or a list of
 * {loc, msg} objects for request-validation (422) failures. */
function extractDetail(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null
  const detail = (data as { detail?: unknown }).detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((d) => (d && typeof d === 'object' ? (d as { msg?: string }).msg : null))
      .filter(Boolean).join('; ') || null
  }
  return null
}

export const authApi = {
  signup: (body: { email: string; password: string; name?: string; org_name?: string }) =>
    request<AuthResult>('/api/auth/signup', { method: 'POST', body }),
  login: (body: { email: string; password: string }) =>
    request<AuthResult>('/api/auth/login', { method: 'POST', body }),
  me: () => request<AuthResult>('/api/auth/me', { auth: true }),
}
