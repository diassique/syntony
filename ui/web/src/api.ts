/** Client for the control-plane API.
 *
 * Auth model (industry standard for SPAs): a short-lived access token is held in MEMORY
 * (never localStorage — so XSS can't exfiltrate it) and sent as a Bearer header. The
 * long-lived refresh token lives in an httpOnly, Secure, SameSite=Strict cookie the JS
 * never sees; it's rotated on every /refresh and revocable server-side. On a 401 we
 * transparently refresh once (single-flight) and retry. */

let accessToken: string | null = null

export function getAccessToken(): string | null {
  return accessToken
}

export interface User { id: string; email: string; name: string }
export interface Org { id: string; name: string; slug: string; plan: string }
export interface AuthResult { token: string; expires_in: number; user: User; org: Org | null }

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

async function request<T>(path: string, opts: RequestOpts = {}, allowRefresh = true): Promise<T> {
  const headers: Record<string, string> = {}
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json'
  if (opts.auth && accessToken) headers['Authorization'] = `Bearer ${accessToken}`
  const res = await fetch(path, {
    method: opts.method ?? 'GET',
    headers,
    credentials: 'include', // send/receive the refresh cookie on /api/auth
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  })
  // access token expired? silently refresh once, then retry the original request.
  if (res.status === 401 && opts.auth && allowRefresh) {
    if (await refreshSession()) return request<T>(path, opts, false)
  }
  const text = await res.text()
  const data = text ? JSON.parse(text) : null
  if (!res.ok) throw new ApiError(res.status, extractDetail(data) ?? `request failed (${res.status})`)
  return data as T
}

/** FastAPI errors: `detail` is a string for our HTTPExceptions or a list of {msg} for 422. */
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

let refreshInFlight: Promise<AuthResult | null> | null = null

/** Exchange the refresh cookie for a fresh access token (single-flight). Returns the
 * session (also used to bootstrap on load) or null if there's no valid session. */
export function refreshSession(): Promise<AuthResult | null> {
  refreshInFlight ??= (async () => {
    try {
      const res = await fetch('/api/auth/refresh', { method: 'POST', credentials: 'include' })
      if (!res.ok) { accessToken = null; return null }
      const data = (await res.json()) as AuthResult
      accessToken = data.token
      return data
    } catch {
      accessToken = null
      return null
    }
  })().finally(() => { refreshInFlight = null })
  return refreshInFlight
}

function capture(r: AuthResult): AuthResult {
  accessToken = r.token
  return r
}

export const authApi = {
  signup: (body: { email: string; password: string; name?: string; org_name?: string }) =>
    request<AuthResult>('/api/auth/signup', { method: 'POST', body }).then(capture),
  login: (body: { email: string; password: string }) =>
    request<AuthResult>('/api/auth/login', { method: 'POST', body }).then(capture),
  me: () => request<AuthResult>('/api/auth/me', { auth: true }),
  refresh: refreshSession,
  logout: () => request<void>('/api/auth/logout', { method: 'POST' }).finally(() => { accessToken = null }),
}

export interface RunSummary {
  id: string
  case_name: string
  status: string
  final_state: string | null
  outcome: string | null
  turns: number
  room_id: string | null
  started_at: string
  ended_at: string | null
  events: number
  private_events: number
}

export interface AuditEvent {
  turn: number
  author: string
  kind: string
  visibility: 'room' | 'private_event'
  payload: { message?: string; reasoning?: string; outcome?: string }
  created_at: string
}

export interface RunDetail {
  run: RunSummary
  events: AuditEvent[]
}

export const runsApi = {
  list: () => request<RunSummary[]>('/api/runs', { auth: true }),
  get: (id: string) => request<RunDetail>(`/api/runs/${id}`, { auth: true }),
}
