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
export interface Org { id: string; name: string; slug: string; plan: string; kind: 'provider' | 'payer' }
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
  urgency: string | null
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
  payload: { message?: string; reasoning?: string; outcome?: string; pa_event?: string; denial_reason?: string; framework?: string; via?: string }
  created_at: string
}

export interface RunDetail {
  run: RunSummary
  events: AuditEvent[]
}

export interface StartRunResult { run_id: string; case_name: string; status: string }

export const runsApi = {
  list: () => request<RunSummary[]>('/api/runs', { auth: true }),
  get: (id: string) => request<RunDetail>(`/api/runs/${id}`, { auth: true }),
  /** Kick off a live negotiation; returns the run id immediately (it streams in). */
  start: (caseName?: string) =>
    request<StartRunResult>('/api/runs/start', { method: 'POST', auth: true, body: caseName ? { case_name: caseName } : {} }),
  /** Document intake (AI/ML vision/OCR/STT): extract a request from an image/PDF/audio and run it. */
  intake: (body: { image?: string; document_url?: string; audio_url?: string; sample?: boolean; dictation_sample?: boolean }) =>
    request<{ run_id: string; status: string; extracted: { procedure: string; code: string; diagnoses: string[]; urgent: boolean } }>(
      '/api/runs/intake', { method: 'POST', auth: true, body }),
  /** Human-in-the-loop: the payer Medical Director resolves a paused borderline case. */
  decide: (id: string, outcome: 'APPROVE' | 'DENY') =>
    request<{ run_id: string; outcome: string; status: string }>(`/api/runs/${id}/decide`, { method: 'POST', auth: true, body: { outcome } }),
  /** Aggregate metrics across the org's runs (for the Insights view). */
  insights: () => request<Insights>('/api/runs/insights', { auth: true }),
  /** Download the case's audit trail as a compliance PDF (authed binary fetch → Blob). */
  exportPdf: async (id: string, retry = true): Promise<Blob> => {
    const res = await fetch(`/api/runs/${id}/export.pdf`, {
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
      credentials: 'include',
    })
    if (res.status === 401 && retry && (await refreshSession())) return runsApi.exportPdf(id, false)
    if (!res.ok) throw new ApiError(res.status, `export failed (${res.status})`)
    return res.blob()
  },
}

export interface Insights {
  cases: number
  decided: number
  approvals: number
  denials: number
  approval_rate: number
  overturns: number
  avg_turns: number
  avg_turnaround_sec: number
  expedited: number
  standard: number
  within_sla: number
  past_sla: number
  denial_reasons: { reason: string; count: number }[]
  agents: { author: string; runs: number }[]
  frameworks: { via: string; count: number }[]
  on_framework_rate: number
}

export interface AgentInfo {
  id: string
  name: string
  side: 'provider' | 'payer' | 'neutral'
  framework: string
  model: string | null
  acts_in: string[]
  human: boolean
}

export const agentsApi = {
  /** The agent roster powering the mesh (roles, frameworks, models). */
  list: () => request<{ agents: AgentInfo[] }>('/api/agents', { auth: true }),
}

// ---- AI/ML API telemetry (what the mesh uses from the AI/ML gateway) -----------

export interface AimlFeature {
  key: string
  label: string
  status: 'in_use' | 'supported'
  detail: string
  metric: string | null
}

export interface AimlSurface {
  gateway: { base_url: string; key_env: string; openai_compatible: boolean; catalog_models: number; app_models: string[] }
  roles: { id: string; name: string; side: string; framework: string; model: string | null; reasoning_effort: string | null; human: boolean }[]
  features: AimlFeature[]
  usage: { models: { model: string; turns: number }[]; via: { via: string; count: number }[] }
  totals: { runs: number; model_turns: number; tokens_in: number; tokens_out: number; tokens_total: number; criteria: number; embedding_dim: number }
}

export const aimlApi = {
  /** What this app uses from the AI/ML API, grounded in real run telemetry. */
  get: () => request<AimlSurface>('/api/aiml', { auth: true }),
}

// ---- interactive prior-auth workflow (the real two-sided, form-driven flow) ----

export interface PrecheckReport {
  ready: boolean
  blocking_issues: string[]
  completeness_issues: string[]
  coding_issues: string[]
  policy_on_file: boolean
  missing_required_docs: string[]
  missing_step_therapy_docs: string[]
  advisories: string[]
  gold_card?: { provider_name: string; procedure_code: string; basis: string } | null
}

export interface PaOptions {
  supporting_doc_types: { id: string; label: string }[]
  known_procedures: { system: string; code: string; display: string }[]
  denial_reasons: string[]
}

export interface PaTimelineItem {
  turn: number
  author: string
  kind: string
  visibility: 'room' | 'private_event'
  message: string
  reasoning: string
  pa_event?: string | null
  outcome?: string | null
  denial_reason?: string | null
  auth_number?: string | null
  overturned?: boolean | null
  hitl?: boolean | null
  gold_card?: boolean | null
  via?: string | null
  framework?: string | null
}

export interface PaSummary {
  run_id: string
  status: string
  mode: string
  side: 'provider' | 'payer' | null
  case: string
  patient_ref: string
  urgency: string | null
  outcome: string | null
  turns: number
  started_at: string | null
  sla_deadline: string | null
  actions: string[]
}

export interface PaRecommendation {
  outcome?: string
  reason_code?: string | null
  reasons?: string[]
  escalate?: boolean
  suggested_action?: string
}

export interface PaDetail extends PaSummary {
  fsm_state: string | null
  request: PaRequestShape
  auth_number: string
  timeline: PaTimelineItem[]
  recommendation?: PaRecommendation
}

export interface PaRequestShape {
  patient_ref: string
  procedure: { system: string; code: string; display: string }
  diagnoses: { system: string; code: string; display: string }[]
  clinical_justification: string
  supporting_docs: string[]
  ordering_provider: { npi: string; name: string; signed: boolean }
  urgency: string
  member_id?: string
  health_plan?: string
  units?: number
  place_of_service?: string
}

export type PaForm = Record<string, unknown>

export const paApi = {
  options: () => request<PaOptions>('/api/pa/options', { auth: true }),
  precheck: (form: PaForm) => request<PrecheckReport>('/api/pa/precheck', { method: 'POST', auth: true, body: { form } }),
  submit: (form: PaForm, patientId?: string | null) =>
    request<{ run_id: string; status: string }>('/api/pa/submit', { method: 'POST', auth: true, body: { form, patient_id: patientId ?? null } }),
  worklist: () => request<{ items: PaSummary[] }>('/api/pa/worklist', { auth: true }),
  get: (id: string) => request<PaDetail>(`/api/pa/${id}`, { auth: true }),
  review: (id: string) => request<{ status: string }>(`/api/pa/${id}/review`, { method: 'POST', auth: true }),
  decide: (id: string, body: { action: string; reason_code?: string | null; note?: string }) =>
    request<{ status: string }>(`/api/pa/${id}/decide`, { method: 'POST', auth: true, body }),
  respond: (id: string, docs: string[]) => request<{ status: string }>(`/api/pa/${id}/respond`, { method: 'POST', auth: true, body: { docs } }),
  appeal: (id: string, docs: string[]) => request<{ status: string }>(`/api/pa/${id}/appeal`, { method: 'POST', auth: true, body: { docs } }),
  accept: (id: string) => request<{ status: string }>(`/api/pa/${id}/accept`, { method: 'POST', auth: true }),
  mdDecide: (id: string, outcome: 'APPROVE' | 'DENY', note = '') =>
    request<{ status: string }>(`/api/pa/${id}/md-decide`, { method: 'POST', auth: true, body: { outcome, note } }),
}

// ---- synthetic patient charts (clinic EHR roster) ----

export interface PatientSummary {
  id: string
  mrn: string
  name: string
  dob: string
  sex: string
  conditions: number
  coverage: { payer: string; plan_type: string; member_id: string; status: string } | null
}

export interface PatientChart {
  patient: { id: string; mrn: string; given_name: string; family_name: string; name: string; dob: string; sex: string; address: string; phone: string }
  coverage: { payer: string; plan_type: string; member_id: string; group_number: string; status: string; period_start: string; period_end: string } | null
  conditions: { system: string; code: string; display: string; status: string; onset: string }[]
  treatments: { kind: string; doc_token: string; description: string; date: string; outcome: string }[]
  cases: { run_id: string; case: string; status: string; outcome: string | null; urgency: string | null; started_at: string | null }[]
}

export const patientsApi = {
  list: () => request<{ patients: PatientSummary[] }>('/api/patients', { auth: true }),
  get: (id: string) => request<PatientChart>(`/api/patients/${id}`, { auth: true }),
}

// ---- configuration editors (payer edits its policy + clinical criteria) ----

export interface PolicyRule {
  procedure_code: string
  required_diagnosis_prefixes: string[]
  required_docs: string[]
  step_therapy_docs: string[]
  red_flag_prefixes: string[]
  auto_approve: boolean
}

export interface CriterionItem { slug: string; text: string }

export const configApi = {
  policy: () => request<{ editable: boolean; rules: PolicyRule[] }>('/api/config/policy', { auth: true }),
  savePolicy: (r: PolicyRule) => request<PolicyRule>('/api/config/policy', { method: 'POST', auth: true, body: r }),
  deletePolicy: (code: string) => request<{ deleted: string }>(`/api/config/policy/${encodeURIComponent(code)}`, { method: 'DELETE', auth: true }),
  criteria: () => request<{ editable: boolean; criteria: CriterionItem[] }>('/api/config/criteria', { auth: true }),
  saveCriterion: (c: CriterionItem) => request<CriterionItem>('/api/config/criteria', { method: 'POST', auth: true, body: c }),
  deleteCriterion: (slug: string) => request<{ deleted: string }>(`/api/config/criteria/${encodeURIComponent(slug)}`, { method: 'DELETE', auth: true }),
}

/** Human label for a workflow status. */
export const PA_STATUS_LABEL: Record<string, string> = {
  awaiting_payer: 'Awaiting payer',
  awaiting_payer_decision: 'Awaiting decision',
  awaiting_provider: 'Action needed',
  awaiting_human: 'Medical Director',
  succeeded: 'Decided',
  failed: 'Failed',
  running: 'Running',
}
