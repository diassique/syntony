/** Interactive prior-authorization workflow — the real two-sided, form-driven flow.
 *
 * Three surfaces, all org-scoped:
 *  - <PaSubmit>   provider fills a real PA request; Counsel pre-checks it live before submit.
 *  - <PaWorklist> the org's cases (provider: my submissions; payer: my review queue).
 *  - <PaCase>     one case: request, timeline, and the side-aware action panel (run review,
 *                 commit a determination, respond to a pend, appeal, or the MD verdict).
 *
 * This is the counterpart to the autoplay "Sample run": here humans on each side act, and the
 * same L1 FSM resumes between their actions. Clinical Bone primitives + lucide icons throughout. */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  FilePlus2, Inbox, ArrowLeft, Plus, X, Check, ShieldCheck, ShieldAlert, Clock,
  Stethoscope, Gavel, Send, RotateCcw, FileSearch, AlertTriangle, Loader2, CheckCircle2,
  Users, Award, Lock,
} from 'lucide-react'
import {
  paApi, patientsApi, PA_STATUS_LABEL,
  type PaOptions, type PrecheckReport, type PaSummary, type PaDetail, type PaForm,
  type PaTimelineItem, type PatientSummary, type PatientChart,
} from '../api'
import { Badge, Button, Input, Select, type BadgeTone } from './ui'

// ---- small shared bits ---------------------------------------------------------

const STATUS_TONE: Record<string, BadgeTone> = {
  awaiting_payer: 'ink',
  awaiting_payer_decision: 'coral',
  awaiting_provider: 'coral',
  awaiting_human: 'coral',
  succeeded: 'pine',
  failed: 'neutral',
  running: 'neutral',
}

function StatusBadge({ status, outcome }: { status: string; outcome?: string | null }) {
  if (status === 'succeeded' && outcome) {
    return <Badge tone={outcome === 'APPROVE' ? 'pine' : 'coral'}>{outcome === 'APPROVE' ? 'Approved' : 'Denied'}</Badge>
  }
  return <Badge tone={STATUS_TONE[status] ?? 'neutral'}>{PA_STATUS_LABEL[status] ?? status}</Badge>
}

/** CMS-0057-F SLA clock: 72h expedited / 7d standard, counting down (red once past). */
function Sla({ deadline, urgency, done }: { deadline: string | null; urgency: string | null; done?: boolean }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (done) return
    const t = setInterval(() => setNow(Date.now()), 30_000)
    return () => clearInterval(t)
  }, [done])
  if (!deadline) return null
  const ms = new Date(deadline).getTime() - now
  const past = ms < 0
  const hrs = Math.floor(Math.abs(ms) / 3_600_000)
  const label = hrs >= 48 ? `${Math.floor(hrs / 24)}d ${hrs % 24}h` : `${hrs}h`
  const window = urgency === 'expedited' ? 'Expedited · 72h' : 'Standard · 7d'
  return (
    <span className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-[0.1em]">
      <Clock size={11} strokeWidth={1.75} aria-hidden />
      <span className="text-ink-faint">{window}</span>
      {!done && <span className={past ? 'text-coral' : 'text-ink-soft'}>· {past ? `${label} over` : `${label} left`}</span>}
    </span>
  )
}

function sideTone(side: string | null): BadgeTone {
  return side === 'provider' ? 'pine' : side === 'payer' ? 'ink' : 'neutral'
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[12px] text-ink-faint">{hint}</span>}
    </label>
  )
}

function SectionTitle({ icon, title, subtitle, right }: { icon: React.ReactNode; title: string; subtitle?: string; right?: React.ReactNode }) {
  return (
    <div className="mb-6 flex items-start justify-between gap-4">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 text-pine">{icon}</span>
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight text-ink">{title}</h1>
          {subtitle && <p className="mt-0.5 text-[13px] text-ink-soft">{subtitle}</p>}
        </div>
      </div>
      {right}
    </div>
  )
}

// ================================================================================
//  PaSubmit — the provider request form with live Counsel pre-check
// ================================================================================

interface FormState {
  patient_ref: string
  member_id: string
  health_plan: string
  units: string
  place_of_service: string
  urgency: string
  procedure: { system: string; code: string; display: string }
  diagnoses: { code: string; display: string }[]
  clinical_justification: string
  supporting_docs: string[]
  ordering_provider: { npi: string; name: string; signed: boolean }
}

const EMPTY_FORM: FormState = {
  patient_ref: '',
  member_id: '',
  health_plan: 'Medicare Advantage',
  units: '1',
  place_of_service: '',
  urgency: 'routine',
  procedure: { system: 'CPT', code: '', display: '' },
  diagnoses: [{ code: '', display: '' }],
  clinical_justification: '',
  supporting_docs: [],
  ordering_provider: { npi: '', name: '', signed: false },
}

function toForm(f: FormState): PaForm {
  return {
    ...f,
    units: Number(f.units) || 1,
    diagnoses: f.diagnoses.filter((d) => d.code.trim()),
  }
}

export function PaSubmit({ onSubmitted, initialPatientId }: { onSubmitted: (runId: string) => void; initialPatientId?: string | null }) {
  const [opts, setOpts] = useState<PaOptions | null>(null)
  const [roster, setRoster] = useState<PatientSummary[]>([])
  const [patientId, setPatientId] = useState<string>('')
  const [f, setF] = useState<FormState>(EMPTY_FORM)
  const [report, setReport] = useState<PrecheckReport | null>(null)
  const [checking, setChecking] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const seq = useRef(0)

  useEffect(() => { paApi.options().then(setOpts).catch(() => {}) }, [])
  useEffect(() => { patientsApi.list().then((r) => setRoster(r.patients)).catch(() => {}) }, [])

  // Pull a chart and auto-fill the request (demographics + coverage + problem list + on-file docs).
  const pickPatient = (id: string) => {
    setPatientId(id)
    if (!id) return
    patientsApi.get(id).then((c: PatientChart) => {
      setF((p) => ({
        ...p,
        patient_ref: c.patient.mrn,
        member_id: c.coverage?.member_id ?? '',
        health_plan: c.coverage?.plan_type ?? p.health_plan,
        diagnoses: c.conditions.length
          ? c.conditions.map((x) => ({ code: x.code, display: x.display }))
          : [{ code: '', display: '' }],
        supporting_docs: Array.from(new Set(c.treatments.map((t) => t.doc_token).filter(Boolean))),
      }))
    }).catch(() => {})
  }
  useEffect(() => { if (initialPatientId) pickPatient(initialPatientId) }, [initialPatientId])

  // Live pre-check: debounce edits, then run Counsel's completeness/coding/policy check.
  useEffect(() => {
    if (!f.procedure.code.trim()) { setReport(null); return }
    const id = ++seq.current
    setChecking(true)
    const t = setTimeout(() => {
      paApi.precheck(toForm(f))
        .then((r) => { if (id === seq.current) setReport(r) })
        .catch(() => { if (id === seq.current) setReport(null) })
        .finally(() => { if (id === seq.current) setChecking(false) })
    }, 500)
    return () => clearTimeout(t)
  }, [f])

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setF((p) => ({ ...p, [k]: v }))
  const setProc = (patch: Partial<FormState['procedure']>) => setF((p) => ({ ...p, procedure: { ...p.procedure, ...patch } }))
  const setDx = (i: number, patch: Partial<{ code: string; display: string }>) =>
    setF((p) => ({ ...p, diagnoses: p.diagnoses.map((d, j) => (j === i ? { ...d, ...patch } : d)) }))
  const toggleDoc = (id: string) =>
    setF((p) => ({ ...p, supporting_docs: p.supporting_docs.includes(id)
      ? p.supporting_docs.filter((x) => x !== id) : [...p.supporting_docs, id] }))

  const submit = async () => {
    setSubmitting(true); setError(null)
    try {
      const { run_id } = await paApi.submit(toForm(f), patientId || null)
      onSubmitted(run_id)
    } catch (e) {
      setError(String((e as Error)?.message || e))
    } finally {
      setSubmitting(false)
    }
  }

  const ready = report?.ready === true

  return (
    <div>
      <SectionTitle icon={<FilePlus2 size={22} strokeWidth={1.75} />} title="New prior-authorization request"
        subtitle="Fill the request as a provider would. Counsel pre-checks it for the gaps that cause denials — before it ever reaches the payer." />

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-6">
          {/* Patient from chart */}
          <Card title="Patient from chart" right={
            <Select aria-label="Pick a patient" size="sm" value={patientId} placeholder="Pick a patient…"
              onValueChange={pickPatient}
              options={roster.map((p) => ({ label: `${p.name} · ${p.mrn}${p.coverage ? ` · ${p.coverage.plan_type}` : ''}`, value: p.id }))} />
          }>
            <p className="text-[13px] text-ink-soft">
              {patientId
                ? 'Chart loaded — demographics, coverage, problem list and on-file documents pre-filled below. Order the service and sign.'
                : 'Pick a patient to auto-fill from their chart, or fill the request manually.'}
            </p>
          </Card>

          {/* Patient + coverage */}
          <Card title="Patient & coverage">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Patient reference" hint="Synthetic only — no real PHI."><Input value={f.patient_ref} onChange={(e) => set('patient_ref', e.target.value)} placeholder="synthetic-patient-001" /></Field>
              <Field label="Member ID"><Input value={f.member_id} onChange={(e) => set('member_id', e.target.value)} placeholder="MBR-000000" /></Field>
              <Field label="Health plan"><Input value={f.health_plan} onChange={(e) => set('health_plan', e.target.value)} /></Field>
              <Field label="Urgency">
                <Select value={f.urgency} onValueChange={(v) => set('urgency', v)}
                  options={[{ label: 'Standard (routine)', value: 'routine' }, { label: 'Expedited (urgent)', value: 'urgent' }]} />
              </Field>
            </div>
          </Card>

          {/* Procedure */}
          <Card title="Requested service" right={
            <Select aria-label="Known procedures" size="sm" value="" placeholder="Quick-fill…"
              onValueChange={(code) => {
                const p = opts?.known_procedures.find((x) => x.code === code)
                if (p) setProc({ system: p.system, code: p.code, display: p.display })
              }}
              options={(opts?.known_procedures ?? []).map((p) => ({ label: `${p.code} — ${p.display}`, value: p.code }))} />
          }>
            <div className="grid gap-4 sm:grid-cols-[120px_1fr]">
              <Field label="System">
                <Select value={f.procedure.system} onValueChange={(v) => setProc({ system: v })}
                  options={[{ label: 'CPT', value: 'CPT' }, { label: 'HCPCS', value: 'HCPCS' }]} />
              </Field>
              <Field label="Procedure code" hint="CPT = 5 digits · HCPCS = letter + 4 digits"><Input value={f.procedure.code} onChange={(e) => setProc({ code: e.target.value.toUpperCase() })} placeholder="72148" /></Field>
            </div>
            <div className="mt-4 grid gap-4 sm:grid-cols-[1fr_120px]">
              <Field label="Description"><Input value={f.procedure.display} onChange={(e) => setProc({ display: e.target.value })} placeholder="MRI lumbar spine w/o contrast" /></Field>
              <Field label="Units"><Input type="number" min={1} value={f.units} onChange={(e) => set('units', e.target.value)} /></Field>
            </div>
            <div className="mt-4">
              <Field label="Place of service (POS)" hint="e.g. 11 office · 22 outpatient hospital"><Input value={f.place_of_service} onChange={(e) => set('place_of_service', e.target.value)} placeholder="11" /></Field>
            </div>
          </Card>

          {/* Diagnoses */}
          <Card title="Diagnoses (ICD-10-CM)">
            <div className="space-y-3">
              {f.diagnoses.map((d, i) => (
                <div key={i} className="grid grid-cols-[120px_1fr_auto] items-center gap-3">
                  <Input value={d.code} onChange={(e) => setDx(i, { code: e.target.value.toUpperCase() })} placeholder="M54.5" />
                  <Input value={d.display} onChange={(e) => setDx(i, { display: e.target.value })} placeholder="Low back pain" />
                  <button type="button" aria-label="Remove diagnosis" className="rounded-sm p-2 text-ink-faint hover:bg-sunk hover:text-coral"
                    onClick={() => set('diagnoses', f.diagnoses.length > 1 ? f.diagnoses.filter((_, j) => j !== i) : f.diagnoses)}>
                    <X size={15} strokeWidth={1.75} />
                  </button>
                </div>
              ))}
              <Button variant="secondary" size="sm" leadingIcon={<Plus size={14} strokeWidth={1.75} />}
                onClick={() => set('diagnoses', [...f.diagnoses, { code: '', display: '' }])}>Add diagnosis</Button>
            </div>
          </Card>

          {/* Ordering provider */}
          <Card title="Ordering provider">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Provider name"><Input value={f.ordering_provider.name} onChange={(e) => setF((p) => ({ ...p, ordering_provider: { ...p.ordering_provider, name: e.target.value } }))} placeholder="Dr. Rivera" /></Field>
              <Field label="NPI" hint="10-digit National Provider Identifier"><Input value={f.ordering_provider.npi} onChange={(e) => setF((p) => ({ ...p, ordering_provider: { ...p.ordering_provider, npi: e.target.value } }))} placeholder="1000000007" /></Field>
            </div>
            <label className="mt-4 flex cursor-pointer items-center gap-2 text-[14px] text-ink">
              <input type="checkbox" checked={f.ordering_provider.signed} className="h-4 w-4 accent-pine"
                onChange={(e) => setF((p) => ({ ...p, ordering_provider: { ...p.ordering_provider, signed: e.target.checked } }))} />
              Order is signed by the ordering provider
            </label>
          </Card>

          {/* Clinical justification */}
          <Card title="Clinical justification">
            <textarea value={f.clinical_justification} onChange={(e) => set('clinical_justification', e.target.value)}
              rows={4} placeholder="e.g. 6 weeks of failed conservative therapy; persistent radiculopathy with positive SLR."
              className="w-full rounded-sm border border-line bg-paper px-3 py-2 text-[14px] text-ink placeholder:text-ink-faint focus-visible:border-pine/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pine/30" />
          </Card>

          {/* Supporting documents */}
          <Card title="Supporting documentation">
            <div className="grid gap-2 sm:grid-cols-2">
              {(opts?.supporting_doc_types ?? []).map((d) => (
                <label key={d.id} className="flex cursor-pointer items-start gap-2 rounded-sm border border-line bg-paper px-3 py-2 text-[13px] text-ink hover:border-pine/30">
                  <input type="checkbox" checked={f.supporting_docs.includes(d.id)} onChange={() => toggleDoc(d.id)} className="mt-0.5 h-4 w-4 accent-pine" />
                  <span>{d.label}</span>
                </label>
              ))}
            </div>
          </Card>
        </div>

        {/* Sticky pre-check panel */}
        <div className="lg:sticky lg:top-8 lg:self-start">
          <PrecheckPanel report={report} checking={checking} />
          {error && <p className="mt-3 text-[13px] text-coral">{error}</p>}
          <Button className="mt-4 w-full" size="lg" loading={submitting} disabled={!ready || submitting}
            leadingIcon={report?.gold_card ? <Award size={15} strokeWidth={1.75} /> : <Send size={15} strokeWidth={1.75} />} onClick={submit}>
            {!ready ? 'Resolve issues to submit' : report?.gold_card ? 'Submit — auto-approves' : 'Submit to payer'}
          </Button>
          <p className="mt-2 text-center text-[11px] text-ink-faint">
            {report?.gold_card ? 'Gold-carded provider — authorized on submit, no review.' : "The request enters the payer's worklist for review."}
          </p>
        </div>
      </div>
    </div>
  )
}

function Card({ title, right, children }: { title: string; right?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="rounded-md border border-line bg-paper/60 p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-soft">{title}</h2>
        {right}
      </div>
      {children}
    </section>
  )
}

function PrecheckPanel({ report, checking }: { report: PrecheckReport | null; checking: boolean }) {
  return (
    <div className="rounded-md border border-line bg-paper p-5">
      <div className="mb-3 flex items-center gap-2">
        <FileSearch size={16} strokeWidth={1.75} className="text-pine" />
        <h2 className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-soft">Counsel pre-check</h2>
        {checking && <Loader2 size={13} className="animate-spin text-ink-faint" />}
      </div>
      {!report ? (
        <p className="text-[13px] text-ink-faint">Enter a procedure code to run the pre-submit check.</p>
      ) : (
        <div className="space-y-3 text-[13px]">
          {report.gold_card && (
            <div className="rounded-sm border border-coral/40 bg-coral/[0.06] p-3">
              <div className="flex items-center gap-2 font-medium text-coral">
                <Award size={15} strokeWidth={1.75} /> Gold-carded — auto-approves
              </div>
              <p className="mt-1 text-ink-soft">
                {report.gold_card.provider_name} is exempt for {report.gold_card.procedure_code} ({report.gold_card.basis}). This request is authorized on submit, skipping review.
              </p>
            </div>
          )}
          <div className={`flex items-center gap-2 font-medium ${report.ready ? 'text-pine' : 'text-coral'}`}>
            {report.ready ? <ShieldCheck size={16} strokeWidth={1.75} /> : <ShieldAlert size={16} strokeWidth={1.75} />}
            {report.ready ? 'Ready to submit' : 'Fix before submitting'}
          </div>
          {report.blocking_issues.length > 0 && (
            <ul className="space-y-1">
              {report.blocking_issues.map((i, k) => (
                <li key={k} className="flex items-start gap-2 text-coral"><AlertTriangle size={13} className="mt-0.5 shrink-0" strokeWidth={1.75} />{i}</li>
              ))}
            </ul>
          )}
          {report.advisories.length > 0 && (
            <div className="rounded-sm border border-line bg-sunk/60 p-3 text-ink-soft">
              <p className="mb-1 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-faint">Likely payer outcome</p>
              <ul className="space-y-1">{report.advisories.map((a, k) => <li key={k}>{a}</li>)}</ul>
            </div>
          )}
          {report.ready && report.advisories.length === 0 && (
            <p className="text-ink-soft">No gaps detected — this request meets the documentation criteria on file.</p>
          )}
        </div>
      )}
    </div>
  )
}

// ================================================================================
//  PaWorklist — the org's cases
// ================================================================================

export function PaWorklist({ onOpen, onNew }: { onOpen: (id: string) => void; onNew?: () => void }) {
  const [items, setItems] = useState<PaSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => paApi.worklist().then((r) => setItems(r.items)).catch((e) => setError(String(e?.message || e))), [])
  useEffect(() => {
    load()
    const t = setInterval(load, 4000)
    return () => clearInterval(t)
  }, [load])

  const actionable = (items ?? []).filter((i) => i.actions.length > 0)
  const rest = (items ?? []).filter((i) => i.actions.length === 0)

  const isProvider = !!onNew  // a provider files requests; a payer only reviews them
  return (
    <div>
      <SectionTitle icon={<Inbox size={22} strokeWidth={1.75} />}
        title={isProvider ? 'Prior authorization' : 'Review queue'}
        subtitle={isProvider
          ? 'Your prior-auth requests and where each one stands. Cases needing your action surface at the top.'
          : 'Incoming prior-auth requests to review. Cases needing your decision surface at the top.'}
        right={onNew && <Button variant="secondary" size="sm" leadingIcon={<FilePlus2 size={14} strokeWidth={1.75} />} onClick={onNew}>New request</Button>} />
      {error && <p className="mb-4 text-[13px] text-coral">{error}</p>}
      {items === null ? (
        <p className="text-[13px] text-ink-faint">Loading…</p>
      ) : items.length === 0 ? (
        <Empty onNew={onNew} />
      ) : (
        <div className="space-y-6">
          {actionable.length > 0 && <Group label="Needs your action" items={actionable} onOpen={onOpen} highlight />}
          {rest.length > 0 && <Group label="All cases" items={rest} onOpen={onOpen} />}
        </div>
      )}
    </div>
  )
}

function Empty({ onNew }: { onNew?: () => void }) {
  return (
    <div className="rounded-md border border-dashed border-line bg-paper/60 p-10 text-center">
      <Inbox size={28} strokeWidth={1.5} className="mx-auto mb-3 text-ink-faint" />
      <p className="text-[14px] text-ink-soft">{onNew ? 'No prior-auth cases yet.' : 'No requests to review yet.'}</p>
      {onNew && <Button className="mt-4" size="sm" leadingIcon={<FilePlus2 size={14} strokeWidth={1.75} />} onClick={onNew}>Submit a request</Button>}
    </div>
  )
}

function Group({ label, items, onOpen, highlight }: { label: string; items: PaSummary[]; onOpen: (id: string) => void; highlight?: boolean }) {
  return (
    <div>
      <h2 className="mb-2 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-faint">{label}</h2>
      <div className="overflow-hidden rounded-md border border-line">
        {items.map((it, i) => (
          <button key={it.run_id} onClick={() => onOpen(it.run_id)}
            className={`flex w-full items-center gap-4 px-4 py-3 text-left transition-colors hover:bg-sunk/60 ${i > 0 ? 'border-t border-line' : ''} ${highlight ? 'bg-coral/[0.03]' : 'bg-paper'}`}>
            <Badge tone={sideTone(it.side)}>{it.side}</Badge>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[14px] font-medium text-ink">{it.case || '—'}</p>
              <p className="truncate text-[12px] text-ink-faint">{it.patient_ref}</p>
            </div>
            <Sla deadline={it.sla_deadline} urgency={it.urgency} done={it.status === 'succeeded' || it.status === 'failed'} />
            <StatusBadge status={it.status} outcome={it.outcome} />
          </button>
        ))}
      </div>
    </div>
  )
}

// ================================================================================
//  PaCase — one case: request, timeline, and the side-aware action panel
// ================================================================================

export function PaCase({ runId, onBack, docLabels }: { runId: string; onBack: () => void; docLabels?: Record<string, string> }) {
  const [d, setD] = useState<PaDetail | null>(null)
  const [opts, setOpts] = useState<PaOptions | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => paApi.get(runId).then(setD).catch((e) => setError(String(e?.message || e))), [runId])
  useEffect(() => { paApi.options().then(setOpts).catch(() => {}) }, [])
  useEffect(() => {
    load()
    const t = setInterval(() => { if (!busy) load() }, 3000)
    return () => clearInterval(t)
  }, [load, busy])

  const labels = useMemo(() => {
    const m: Record<string, string> = { ...(docLabels ?? {}) }
    for (const x of opts?.supporting_doc_types ?? []) m[x.id] = x.label
    return m
  }, [opts, docLabels])

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true); setError(null)
    try { await fn(); await load() }
    catch (e) { setError(String((e as Error)?.message || e)) }
    finally { setBusy(false) }
  }

  if (!d) return <p className="text-[13px] text-ink-faint">{error ?? 'Loading…'}</p>
  const done = d.status === 'succeeded' || d.status === 'failed'

  return (
    <div>
      <button onClick={onBack} className="mb-4 inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.12em] text-ink-faint hover:text-ink">
        <ArrowLeft size={13} strokeWidth={1.75} /> Worklist
      </button>

      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-[20px] font-semibold tracking-tight text-ink">{d.case || 'Prior-auth case'}</h1>
          <p className="mt-0.5 text-[13px] text-ink-soft">Patient {d.request.patient_ref || '—'} · {d.request.health_plan || 'plan'}</p>
        </div>
        <div className="flex items-center gap-3">
          <Sla deadline={d.sla_deadline} urgency={d.urgency} done={done} />
          <Badge tone={sideTone(d.side)}>{d.side}</Badge>
          <StatusBadge status={d.status} outcome={d.outcome} />
        </div>
      </div>

      {error && <p className="mb-4 text-[13px] text-coral">{error}</p>}

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          <ActionPanel d={d} opts={opts} busy={busy} act={act} />
          <Timeline items={d.timeline} />
        </div>
        <div className="lg:sticky lg:top-8 lg:self-start">
          <RequestCard d={d} labels={labels} />
        </div>
      </div>
    </div>
  )
}

function RequestCard({ d, labels }: { d: PaDetail; labels: Record<string, string> }) {
  const r = d.request
  return (
    <div className="rounded-md border border-line bg-paper p-5 text-[13px]">
      <h2 className="mb-3 font-mono text-[11px] uppercase tracking-[0.14em] text-ink-soft">Request</h2>
      <dl className="space-y-2">
        <Row k="Procedure" v={`${r.procedure.system} ${r.procedure.code} — ${r.procedure.display}`} />
        <Row k="Diagnoses" v={r.diagnoses.map((x) => `${x.code}${x.display ? ` (${x.display})` : ''}`).join(', ') || '—'} />
        <Row k="Urgency" v={r.urgency} />
        <Row k="Units" v={String(r.units ?? 1)} />
        {r.member_id && <Row k="Member" v={r.member_id} />}
        {r.place_of_service && <Row k="POS" v={r.place_of_service} />}
        <Row k="Provider" v={`${r.ordering_provider.name}${r.ordering_provider.signed ? ' · signed' : ' · UNSIGNED'}`} />
        {d.auth_number && <Row k="Authorization" v={d.auth_number} />}
      </dl>
      {r.clinical_justification && (
        <p className="mt-3 border-t border-line pt-3 text-ink-soft">{r.clinical_justification}</p>
      )}
      <div className="mt-3 border-t border-line pt-3">
        <p className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-faint">Documents</p>
        {r.supporting_docs.length === 0 ? <p className="text-ink-faint">None attached</p> : (
          <div className="flex flex-wrap gap-1.5">
            {r.supporting_docs.map((x) => <Badge key={x} tone="pine">{labels[x] ?? x}</Badge>)}
          </div>
        )}
      </div>
    </div>
  )
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex gap-3">
      <dt className="w-24 shrink-0 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-faint">{k}</dt>
      <dd className="flex-1 text-ink">{v}</dd>
    </div>
  )
}

// ---- the action panel (what this side can do now) ------------------------------

function ActionPanel({ d, opts, busy, act }: {
  d: PaDetail; opts: PaOptions | null; busy: boolean; act: (fn: () => Promise<unknown>) => Promise<void>
}) {
  const a = d.actions
  if (a.includes('review')) return <PayerReview d={d} busy={busy} act={act} />
  if (a.includes('decide')) return <PayerDecide d={d} opts={opts} busy={busy} act={act} />
  if (a.includes('md_decide')) return <MdDecide d={d} busy={busy} act={act} />
  if (a.includes('respond')) return <ProviderRespond d={d} opts={opts} busy={busy} act={act} />
  if (a.includes('appeal')) return <ProviderAppeal d={d} opts={opts} busy={busy} act={act} />
  if (d.status === 'succeeded') return <Resolved d={d} />
  return <Waiting d={d} />
}

function Panel({ tone = 'pine', icon, title, children }: { tone?: 'pine' | 'coral'; icon: React.ReactNode; title: string; children: React.ReactNode }) {
  const ring = tone === 'coral' ? 'border-coral/40 bg-coral/[0.04]' : 'border-pine/30 bg-pine/[0.04]'
  return (
    <section className={`rounded-md border p-5 ${ring}`}>
      <div className="mb-3 flex items-center gap-2 text-ink">
        <span className={tone === 'coral' ? 'text-coral' : 'text-pine'}>{icon}</span>
        <h2 className="text-[15px] font-semibold tracking-tight">{title}</h2>
      </div>
      {children}
    </section>
  )
}

function PayerReview({ d, busy, act }: { d: PaDetail; busy: boolean; act: (fn: () => Promise<unknown>) => Promise<void> }) {
  return (
    <Panel icon={<Stethoscope size={17} strokeWidth={1.75} />} title="Utilization review">
      <p className="mb-4 text-[13px] text-ink-soft">Run the UM review: the Reviewer consults Clinical Guidelines, Compliance{d.request.procedure.system === 'HCPCS' ? ', and Pharmacy' : ''}, then returns a recommendation for your determination.</p>
      <Button loading={busy} leadingIcon={<FileSearch size={15} strokeWidth={1.75} />} onClick={() => act(() => paApi.review(d.run_id))}>Run UM review</Button>
    </Panel>
  )
}

function PayerDecide({ d, opts, busy, act }: { d: PaDetail; opts: PaOptions | null; busy: boolean; act: (fn: () => Promise<unknown>) => Promise<void> }) {
  const rec = d.recommendation
  const [action, setAction] = useState(rec?.suggested_action ?? 'APPROVE')
  const [reason, setReason] = useState(rec?.reason_code ?? (opts?.denial_reasons[0] ?? 'NOT_MEDICALLY_NECESSARY'))
  const [note, setNote] = useState('')
  const needsReason = action === 'DENY' || action === 'REQUEST_INFO'
  return (
    <Panel icon={<Gavel size={17} strokeWidth={1.75} />} title="Determination">
      {rec && (
        <div className="mb-4 rounded-sm border border-line bg-sunk/60 p-3 text-[13px]">
          <p className="mb-1 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-faint">Reviewer recommendation</p>
          <p className="font-medium text-ink">{rec.outcome}{rec.reason_code ? ` · ${rec.reason_code}` : ''}</p>
          {(rec.reasons ?? []).map((r, k) => <p key={k} className="mt-0.5 text-ink-soft">{r}</p>)}
        </div>
      )}
      <div className="space-y-3">
        <Field label="Decision">
          <Select value={action} onValueChange={setAction} options={[
            { label: 'Approve', value: 'APPROVE' },
            { label: 'Request more information (pend)', value: 'REQUEST_INFO' },
            { label: 'Deny — specific reason', value: 'DENY' },
            { label: 'Escalate to Medical Director', value: 'ESCALATE' },
          ]} />
        </Field>
        {needsReason && (
          <Field label="Reason (CMS-0057-F specific reason)">
            <Select value={reason} onValueChange={setReason}
              options={(opts?.denial_reasons ?? []).map((r) => ({ label: r, value: r }))} />
          </Field>
        )}
        <Field label="Note (optional)">
          <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Rationale for the determination" />
        </Field>
        <Button loading={busy} variant={action === 'DENY' ? 'signal' : 'primary'}
          leadingIcon={<Check size={15} strokeWidth={1.75} />}
          onClick={() => act(() => paApi.decide(d.run_id, { action, reason_code: needsReason ? reason : null, note }))}>
          Commit determination
        </Button>
      </div>
    </Panel>
  )
}

function MdDecide({ d, busy, act }: { d: PaDetail; busy: boolean; act: (fn: () => Promise<unknown>) => Promise<void> }) {
  const [note, setNote] = useState('')
  return (
    <Panel tone="coral" icon={<Gavel size={17} strokeWidth={1.75} />} title="Medical Director review">
      <p className="mb-4 text-[13px] text-ink-soft">A borderline case the Reviewer escalated. As the licensed Medical Director, exercise clinical discretion the automated policy can't.</p>
      <Field label="Rationale (optional)"><Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Clinical rationale" /></Field>
      <div className="mt-3 flex gap-2">
        <Button loading={busy} leadingIcon={<Check size={15} strokeWidth={1.75} />} onClick={() => act(() => paApi.mdDecide(d.run_id, 'APPROVE', note))}>Approve</Button>
        <Button loading={busy} variant="signal" onClick={() => act(() => paApi.mdDecide(d.run_id, 'DENY', note))}>Uphold denial</Button>
      </div>
    </Panel>
  )
}

function DocPicker({ opts, value, onChange }: { opts: PaOptions | null; value: string[]; onChange: (v: string[]) => void }) {
  const toggle = (id: string) => onChange(value.includes(id) ? value.filter((x) => x !== id) : [...value, id])
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {(opts?.supporting_doc_types ?? []).map((x) => (
        <label key={x.id} className="flex cursor-pointer items-start gap-2 rounded-sm border border-line bg-paper px-3 py-2 text-[13px] text-ink hover:border-pine/30">
          <input type="checkbox" checked={value.includes(x.id)} onChange={() => toggle(x.id)} className="mt-0.5 h-4 w-4 accent-pine" />
          <span>{x.label}</span>
        </label>
      ))}
    </div>
  )
}

function ProviderRespond({ d, opts, busy, act }: { d: PaDetail; opts: PaOptions | null; busy: boolean; act: (fn: () => Promise<unknown>) => Promise<void> }) {
  const [docs, setDocs] = useState<string[]>([])
  return (
    <Panel tone="coral" icon={<Send size={17} strokeWidth={1.75} />} title="Information requested">
      <p className="mb-4 text-[13px] text-ink-soft">The payer pended this case for more documentation. Attach the requested documents and it returns for reconsideration.</p>
      <DocPicker opts={opts} value={docs} onChange={setDocs} />
      <Button className="mt-4" loading={busy} disabled={docs.length === 0} leadingIcon={<Send size={15} strokeWidth={1.75} />}
        onClick={() => act(() => paApi.respond(d.run_id, docs))}>Submit documents</Button>
    </Panel>
  )
}

function ProviderAppeal({ d, opts, busy, act }: { d: PaDetail; opts: PaOptions | null; busy: boolean; act: (fn: () => Promise<unknown>) => Promise<void> }) {
  const [docs, setDocs] = useState<string[]>([])
  const reason = d.timeline.slice().reverse().find((t) => t.denial_reason)?.denial_reason
  return (
    <Panel tone="coral" icon={<RotateCcw size={17} strokeWidth={1.75} />} title="Denied — appeal available">
      {reason && <p className="mb-2 text-[13px]"><Badge tone="coral">{reason}</Badge></p>}
      <p className="mb-4 text-[13px] text-ink-soft">Attach the documents that cure the denial reason and file for reconsideration — or accept the determination.</p>
      <DocPicker opts={opts} value={docs} onChange={setDocs} />
      <div className="mt-4 flex gap-2">
        <Button loading={busy} disabled={docs.length === 0} leadingIcon={<RotateCcw size={15} strokeWidth={1.75} />}
          onClick={() => act(() => paApi.appeal(d.run_id, docs))}>File appeal</Button>
        <Button variant="secondary" loading={busy} onClick={() => act(() => paApi.accept(d.run_id))}>Accept denial</Button>
      </div>
    </Panel>
  )
}

function Resolved({ d }: { d: PaDetail }) {
  const ok = d.outcome === 'APPROVE'
  return (
    <Panel tone={ok ? 'pine' : 'coral'} icon={ok ? <CheckCircle2 size={17} strokeWidth={1.75} /> : <ShieldAlert size={17} strokeWidth={1.75} />}
      title={ok ? 'Authorization approved' : 'Determination: denied'}>
      <p className="text-[13px] text-ink-soft">
        {ok ? `The request is approved${d.auth_number ? ` — authorization #${d.auth_number}` : ''}.` : 'The request was denied. The full rationale and the appeal rights are in the timeline.'}
      </p>
    </Panel>
  )
}

function Waiting({ d }: { d: PaDetail }) {
  const msg = d.side === 'provider'
    ? 'Submitted — the payer is reviewing. This case will update when the payer acts.'
    : 'Waiting on the other side. This case will update when there is a new action.'
  return (
    <div className="rounded-md border border-dashed border-line bg-paper/60 p-5 text-[13px] text-ink-soft">
      <Clock size={16} strokeWidth={1.75} className="mb-2 text-ink-faint" />{msg}
    </div>
  )
}

// ---- timeline ------------------------------------------------------------------

function fmtTime(iso?: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return isNaN(d.getTime()) ? '' : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

/** The case transcript as a two-party chat: provider on the left, payer on the right. Messages
 *  scroll inside a fixed-height frame so a long negotiation never stretches the page. Each bubble
 *  carries its time + PA-event badges; the side's own private reasoning shows beneath its bubble. */
function Timeline({ items }: { items: PaTimelineItem[] }) {
  const room = items.filter((i) => i.visibility === 'room')
  const priv = useMemo(() => {
    const m = new Map<number, string>()
    for (const i of items) if (i.visibility === 'private_event' && i.reasoning) m.set(i.turn, i.reasoning)
    return m
  }, [items])
  const scrollRef = useRef<HTMLDivElement>(null)
  // keep the latest message in view as the live case streams in (scrolls the frame, not the page)
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [room.length])
  if (room.length === 0) return null

  return (
    <section className="overflow-hidden rounded-xl border border-line bg-paper">
      <header className="flex items-center justify-between border-b border-line bg-bone/40 px-4 py-2.5">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-soft">Case timeline</h2>
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint">{room.length} messages</span>
      </header>
      <div ref={scrollRef} className="max-h-[58vh] space-y-3 overflow-y-auto px-4 py-4">
        {room.map((e, i) => {
          const provider = e.author.startsWith('provider')
          const reasoning = priv.get(e.turn)
          return (
            <div key={`${e.turn}-${i}`} className={`flex flex-col ${provider ? 'items-start' : 'items-end'}`}>
              <div className={`max-w-[85%] rounded-2xl border px-3.5 py-2.5 ${
                provider ? 'rounded-tl-sm border-pine/20 bg-pine/[0.05]' : 'rounded-tr-sm border-ink/15 bg-sunk/60'}`}>
                <div className="mb-1 flex items-center gap-2">
                  <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${provider ? 'bg-pine' : 'bg-ink'}`} aria-hidden />
                  <span className="text-[12.5px] font-semibold text-ink">{authorLabel(e.author)}</span>
                  {e.created_at && <span className="ml-auto pl-2 font-mono text-[10px] tabular-nums text-ink-faint">{fmtTime(e.created_at)}</span>}
                </div>
                {e.message && <p className="text-[13px] leading-snug text-ink">{e.message}</p>}
                {(e.pa_event || e.outcome || e.gold_card || e.overturned || e.hitl || e.denial_reason) && (
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    {e.pa_event && <Badge tone="neutral">{e.pa_event.replace(/_/g, ' ').toLowerCase()}</Badge>}
                    {e.outcome && <Badge tone={e.outcome === 'APPROVE' ? 'pine' : 'coral'}>{e.outcome}</Badge>}
                    {e.gold_card && <Badge tone="coral">gold card</Badge>}
                    {e.overturned && <Badge tone="pine">overturned</Badge>}
                    {e.hitl && <Badge tone="ink">human</Badge>}
                    {e.denial_reason && <Badge tone="coral">{e.denial_reason}</Badge>}
                  </div>
                )}
                {e.auth_number && <p className="mt-1.5 font-mono text-[11px] text-pine">Authorization #{e.auth_number}</p>}
                {reasoning && (
                  <p className="mt-2 border-t border-line/70 pt-2 text-[11.5px] italic leading-snug text-ink-faint">
                    <Lock size={10} strokeWidth={1.75} className="mr-1 inline -translate-y-px" />{reasoning}
                  </p>
                )}
              </div>
              {e.via && <span className="mt-1 px-1 font-mono text-[9px] uppercase tracking-[0.1em] text-ink-faint">{e.via.replace(/_/g, ' ')}</span>}
            </div>
          )
        })}
      </div>
    </section>
  )
}

// ================================================================================
//  PatientsView — the clinic's synthetic roster + chart + PA history
// ================================================================================

export function PatientsView({ onOpenCase, onNewRequest }: { onOpenCase: (runId: string) => void; onNewRequest: (patientId: string) => void }) {
  const [roster, setRoster] = useState<PatientSummary[] | null>(null)
  const [openId, setOpenId] = useState<string | null>(null)
  useEffect(() => { patientsApi.list().then((r) => setRoster(r.patients)).catch(() => {}) }, [])

  if (openId) return <PatientChartView id={openId} onBack={() => setOpenId(null)} onOpenCase={onOpenCase} onNewRequest={onNewRequest} />

  return (
    <div>
      <SectionTitle icon={<Users size={22} strokeWidth={1.75} />} title="Patients"
        subtitle="Synthetic clinic roster (no real PHI). Open a chart for coverage, problem list, prior care, and PA history." />
      {roster === null ? <p className="text-[13px] text-ink-faint">Loading…</p> : roster.length === 0 ? (
        <div className="rounded-md border border-dashed border-line bg-paper/60 p-10 text-center text-[14px] text-ink-soft">
          No patients on this organization's roster.
        </div>
      ) : (
        <div className="overflow-hidden rounded-md border border-line">
          {roster.map((p, i) => (
            <button key={p.id} onClick={() => setOpenId(p.id)}
              className={`flex w-full items-center gap-4 bg-paper px-4 py-3 text-left transition-colors hover:bg-sunk/60 ${i > 0 ? 'border-t border-line' : ''}`}>
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-pine/10 font-mono text-[11px] font-bold text-pine ring-1 ring-pine/20">
                {p.name.split(' ').map((x) => x[0]).slice(0, 2).join('')}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[14px] font-medium text-ink">{p.name}</p>
                <p className="truncate font-mono text-[11px] text-ink-faint">{p.mrn} · DOB {p.dob} · {p.sex}</p>
              </div>
              {p.coverage && <Badge tone="ink">{p.coverage.plan_type}</Badge>}
              <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-faint">{p.conditions} dx</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function PatientChartView({ id, onBack, onOpenCase, onNewRequest }: {
  id: string; onBack: () => void; onOpenCase: (runId: string) => void; onNewRequest: (patientId: string) => void
}) {
  const [c, setC] = useState<PatientChart | null>(null)
  useEffect(() => { patientsApi.get(id).then(setC).catch(() => {}) }, [id])
  if (!c) return <p className="text-[13px] text-ink-faint">Loading…</p>
  const p = c.patient

  return (
    <div>
      <button onClick={onBack} className="mb-4 inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.12em] text-ink-faint hover:text-ink">
        <ArrowLeft size={13} strokeWidth={1.75} /> Patients
      </button>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-[20px] font-semibold tracking-tight text-ink">{p.name}</h1>
          <p className="mt-0.5 font-mono text-[12px] text-ink-faint">{p.mrn} · DOB {p.dob} · {p.sex}{p.address ? ` · ${p.address}` : ''}</p>
        </div>
        <Button size="sm" leadingIcon={<FilePlus2 size={14} strokeWidth={1.75} />} onClick={() => onNewRequest(id)}>New PA request</Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-6">
          <Card title="Coverage (eligibility)">
            {c.coverage ? (
              <dl className="space-y-2 text-[13px]">
                <Row k="Payer" v={c.coverage.payer} />
                <Row k="Plan" v={c.coverage.plan_type} />
                <Row k="Member ID" v={c.coverage.member_id} />
                <Row k="Group" v={c.coverage.group_number || '—'} />
                <Row k="Status" v={c.coverage.status} />
                <Row k="Period" v={[c.coverage.period_start, c.coverage.period_end].filter(Boolean).join(' → ') || '—'} />
              </dl>
            ) : <p className="text-[13px] text-ink-faint">No coverage on file.</p>}
          </Card>

          <Card title="Problem list (ICD-10)">
            {c.conditions.length === 0 ? <p className="text-[13px] text-ink-faint">None.</p> : (
              <ul className="space-y-2 text-[13px]">
                {c.conditions.map((x, k) => (
                  <li key={k} className="flex items-center gap-2"><Badge tone="neutral">{x.code}</Badge><span className="text-ink">{x.display}</span></li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Documented prior care">
            {c.treatments.length === 0 ? <p className="text-[13px] text-ink-faint">None on file.</p> : (
              <ul className="space-y-3 text-[13px]">
                {c.treatments.map((t, k) => (
                  <li key={k} className="border-l-2 border-line pl-3">
                    <div className="flex items-center gap-2">
                      <Badge tone="pine">{t.doc_token}</Badge>
                      {t.date && <span className="font-mono text-[10px] text-ink-faint">{t.date}</span>}
                      {t.outcome && <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-faint">{t.outcome}</span>}
                    </div>
                    <p className="mt-0.5 text-ink-soft">{t.description}</p>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="lg:sticky lg:top-8 lg:self-start">
          <div className="rounded-md border border-line bg-paper p-5">
            <h2 className="mb-3 font-mono text-[11px] uppercase tracking-[0.14em] text-ink-soft">Prior-auth history</h2>
            {c.cases.length === 0 ? <p className="text-[13px] text-ink-faint">No PA cases yet.</p> : (
              <div className="space-y-2">
                {c.cases.map((r) => (
                  <button key={r.run_id} onClick={() => onOpenCase(r.run_id)}
                    className="flex w-full items-center gap-2 rounded-sm border border-line bg-bone/40 px-3 py-2 text-left text-[12px] hover:border-pine/30">
                    <span className="min-w-0 flex-1 truncate text-ink">{r.case || 'PA case'}</span>
                    <StatusBadge status={r.status} outcome={r.outcome} />
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

const AUTHOR_NAMES: Record<string, string> = {
  'provider.intake': 'Provider Intake',
  'provider.eligibility': 'Eligibility & Benefits',
  'provider.counsel': 'Provider Counsel',
  'provider.appeals': 'Provider Appeals',
  'payer.reviewer': 'Payer Reviewer',
  'payer.guidelines': 'Clinical Guidelines',
  'payer.compliance': 'Compliance & Audit',
  'payer.pharmacy': 'Pharmacy & Formulary',
  'payer.notification': 'Member Notification',
  'payer.medical_director': 'Medical Director',
}
function authorLabel(a: string): string {
  return AUTHOR_NAMES[a] ?? a
}
