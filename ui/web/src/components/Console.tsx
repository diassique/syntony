/** Authenticated console — "Case Theater".
 *
 * A sidebar dashboard for one organization. Overview gives metrics + onboarding + recent
 * cases; Cases lists every negotiation; opening one drops into the Theater — a two-lane
 * provider↔payer timeline where your side's private agent reasoning is revealed (and locked
 * to you) while the counterparty's reasoning shows only as a sealed placeholder. That
 * asymmetry — visible at a glance — is the cross-org privacy moat. */

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  LayoutDashboard, FolderClosed, Boxes, BarChart3, Settings as SettingsIcon,
  Play, Upload, Copy, Check, ExternalLink, FileText, Braces,
  Lock, Clock, RotateCcw, Gavel, ChevronRight, Loader2, Inbox, FilePlus2, Users, BookOpen, SlidersHorizontal,
  Cpu, Sparkles, Mic,
} from 'lucide-react'
import { runsApi, agentsApi, aimlApi, type AgentInfo, type AimlSurface, type AuditEvent, type Insights, type RunDetail, type RunSummary } from '../api'
import { useAuth } from '../auth'
import { Wordmark } from './Logo'
import { Badge, Button, Select } from './ui'
import { PaSubmit, PaWorklist, PaCase, PatientsView } from './PriorAuth'
import Guide from './Guide'
import Config from './Config'

type View = 'overview' | 'guide' | 'patients' | 'prior_auth' | 'submit' | 'cases' | 'agents' | 'insights' | 'aiml' | 'config' | 'settings'

export default function Console() {
  const { user, org, logout } = useAuth()
  const [runs, setRuns] = useState<RunSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<View>('overview')
  const [openRun, setOpenRun] = useState<string | null>(null)
  const [openPa, setOpenPa] = useState<string | null>(null)
  const [preselectPatient, setPreselectPatient] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)

  const refresh = () => runsApi.list().then(setRuns).catch((e) => setError(String(e?.message || e)))
  useEffect(() => { refresh() }, [])

  if (!user) return null // App guards this route.

  // Role-gate: a section restricted to the other side falls back to Overview (defense-in-depth;
  // the nav already hides it). Provider manages patients/files requests; payer sets policy.
  const kind: 'provider' | 'payer' = org?.kind ?? 'provider'
  const restricted: Partial<Record<View, 'provider' | 'payer'>> =
    { patients: 'provider', submit: 'provider', config: 'payer' }
  const activeView: View = restricted[view] && restricted[view] !== kind ? 'overview' : view

  const open = (id: string) => setOpenRun(id)
  const go = (v: View) => { setOpenRun(null); setOpenPa(null); if (v !== 'submit') setPreselectPatient(null); setView(v) }
  const openPaCase = (id: string) => { setOpenRun(null); setOpenPa(id) }
  const onSubmitted = (id: string) => { setView('prior_auth'); setOpenPa(id) }
  const newRequestFor = (patientId: string) => { setPreselectPatient(patientId); setOpenPa(null); setView('submit') }

  // Trigger a real cross-org negotiation, then drop straight into its Theater to watch it stream.
  const runLiveCase = async (caseName?: string) => {
    if (starting) return
    setStarting(true)
    setError(null)
    try {
      const { run_id } = await runsApi.start(caseName)
      setOpenRun(run_id)
      refresh()
    } catch (e) {
      setError(String((e as Error)?.message || e))
    } finally {
      setStarting(false)
    }
  }

  // Document intake (AI/ML vision/OCR): extract a request from an uploaded image / sample, then run it.
  const runIntake = async (payload: { image?: string; sample?: boolean; dictation_sample?: boolean }) => {
    if (starting) return
    setStarting(true)
    setError(null)
    try {
      const { run_id } = await runsApi.intake(payload)
      setOpenRun(run_id)
      refresh()
    } catch (e) {
      setError(String((e as Error)?.message || e))
    } finally {
      setStarting(false)
    }
  }

  return (
    <div className="md:flex md:min-h-screen">
      <Sidebar org={org} user={user} view={activeView} onNav={go} onSignOut={logout} />
      <main className="min-w-0 flex-1 bg-bone">
        <div className="mx-auto max-w-5xl px-6 py-10 sm:px-10">
          {openRun ? (
            <Theater runId={openRun} orgName={org?.name ?? 'Your organization'}
              onBack={() => setOpenRun(null)} onComplete={refresh} />
          ) : openPa ? (
            <PaCase runId={openPa} onBack={() => setOpenPa(null)} />
          ) : activeView === 'submit' ? (
            <PaSubmit onSubmitted={onSubmitted} initialPatientId={preselectPatient} />
          ) : activeView === 'prior_auth' ? (
            <PaWorklist onOpen={openPaCase} onNew={kind === 'provider' ? () => go('submit') : undefined} />
          ) : activeView === 'patients' ? (
            <PatientsView onOpenCase={openPaCase} onNewRequest={newRequestFor} />
          ) : activeView === 'guide' ? (
            <Guide onGo={(v) => go(v as View)} />
          ) : activeView === 'config' ? (
            <Config />
          ) : activeView === 'overview' ? (
            <Overview user={user} org={org} runs={runs} error={error} onOpen={open}
              onSeeAll={() => go('cases')} onRunCase={runLiveCase} onIntake={runIntake} starting={starting}
              canIntake={kind === 'provider'} />
          ) : activeView === 'cases' ? (
            <Cases runs={runs} error={error} onOpen={open} onRunCase={runLiveCase} onIntake={runIntake}
              starting={starting} canIntake={kind === 'provider'} />
          ) : activeView === 'agents' ? (
            <AgentsView />
          ) : activeView === 'insights' ? (
            <InsightsView />
          ) : activeView === 'aiml' ? (
            <AimlView />
          ) : (
            <Settings user={user} org={org} />
          )}
        </div>
      </main>
    </div>
  )
}

/** Demo scenarios the "Run a live case" control can launch (first = the headline). */
const SCENARIOS: { id: string; label: string }[] = [
  { id: 'humira_step_therapy_denied', label: 'Denial → appeal → overturn' },
  { id: 'cauda_equina_urgent', label: 'Urgent — expedited 72h SLA' },
  { id: 'mri_lumbar_dx_mismatch', label: 'Borderline → human review' },
]

/** Primary call-to-action: pick a scenario and launch a real provider↔payer negotiation that
 * streams in live. The scenario select sits beside the button (defaults to the headline case). */
function RunCaseButton({ onRunCase, starting, subtle }: { onRunCase: (caseName?: string) => void; starting: boolean; subtle?: boolean }) {
  const [scenario, setScenario] = useState(SCENARIOS[0].id)
  return (
    <div className="inline-flex items-center gap-2">
      <Select aria-label="Scenario" size="md" value={scenario} disabled={starting}
        onValueChange={setScenario}
        options={SCENARIOS.map((s) => ({ label: s.label, value: s.id }))} />
      <Button variant={subtle ? 'secondary' : 'signal'} size="md" loading={starting}
        leadingIcon={<Play size={14} className="fill-current" strokeWidth={0} aria-hidden />}
        onClick={() => onRunCase(scenario)}>
        {starting ? 'Starting…' : 'Sample run'}
      </Button>
    </div>
  )
}

/** Document intake: upload a clinical document image (AI/ML vision reads it) or use a sample. */
function IntakeButton({ onIntake, starting }: { onIntake: (p: { image?: string; sample?: boolean; dictation_sample?: boolean }) => void; starting: boolean }) {
  const fileRef = useRef<HTMLInputElement>(null)
  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    const reader = new FileReader()
    reader.onload = () => onIntake({ image: String(reader.result) })
    reader.readAsDataURL(f)
    e.target.value = ''
  }
  return (
    <div className="inline-flex items-center gap-2">
      <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={onFile} />
      <Button variant="secondary" disabled={starting} onClick={() => fileRef.current?.click()}
        leadingIcon={<Upload size={14} strokeWidth={1.75} aria-hidden />}>
        Intake from document
      </Button>
      <button onClick={() => onIntake({ sample: true })} disabled={starting}
        className="font-mono text-[11px] uppercase tracking-[0.12em] text-ink-soft transition-colors hover:text-pine disabled:opacity-60">
        use sample
      </button>
      <span className="text-line">·</span>
      <button onClick={() => onIntake({ dictation_sample: true })} disabled={starting}
        title="Synthesize a spoken order (AI/ML TTS) and transcribe it (AI/ML speech-to-text)"
        className="inline-flex items-center gap-1 font-mono text-[11px] uppercase tracking-[0.12em] text-ink-soft transition-colors hover:text-pine disabled:opacity-60">
        <Mic size={12} strokeWidth={1.75} aria-hidden /> dictate
      </button>
    </div>
  )
}

/* ─── sidebar ─────────────────────────────────────────────────────────────── */
function Sidebar({ org, user, view, onNav, onSignOut }: {
  org: { name: string; plan: string; kind?: 'provider' | 'payer' } | null
  user: { email: string; name: string }
  view: View
  onNav: (v: View) => void
  onSignOut: () => void
}) {
  // `only` gates a section to one side of the exchange. A provider (clinic/hospital) manages
  // patients + files requests; a payer (insurer) reviews them + sets policy. Shared sections
  // have no `only`. Role comes from org.kind (see OrgKind on the backend).
  const kind = org?.kind ?? 'provider'
  const allItems: { id: View; label: string; icon: typeof LayoutDashboard; only?: 'provider' | 'payer' }[] = [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard },
    { id: 'patients', label: 'Patients', icon: Users, only: 'provider' },
    { id: 'prior_auth', label: kind === 'payer' ? 'Review queue' : 'Prior auth', icon: Inbox },
    { id: 'submit', label: 'New request', icon: FilePlus2, only: 'provider' },
    { id: 'cases', label: 'Cases', icon: FolderClosed },
    { id: 'agents', label: 'Agents', icon: Boxes },
    { id: 'insights', label: 'Insights', icon: BarChart3 },
    { id: 'aiml', label: 'AI/ML API', icon: Cpu },
    { id: 'config', label: 'Configuration', icon: SlidersHorizontal, only: 'payer' },
    { id: 'guide', label: 'Guide', icon: BookOpen },
    { id: 'settings', label: 'Settings', icon: SettingsIcon },
  ]
  const items = allItems.filter((it) => !it.only || it.only === kind)
  return (
    <aside className="border-b border-line bg-paper/70 backdrop-blur md:sticky md:top-0 md:flex md:h-screen md:w-64 md:shrink-0 md:flex-col md:border-b-0 md:border-r">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <a href="#/" className="flex items-center">
          <Wordmark height={22} />
        </a>
        <span className="rounded-md border border-line px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.16em] text-ink-faint">console</span>
      </div>

      {org && (
        <div className="mx-5 mb-4 rounded-xl border border-line bg-bone/60 px-3.5 py-3">
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-pine/10 font-mono text-[12px] font-bold text-pine ring-1 ring-pine/25">
              {org.name.slice(0, 1).toUpperCase()}
            </span>
            <div className="min-w-0">
              <div className="truncate text-[13px] font-semibold leading-tight">{org.name}</div>
              <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-pine">{org.plan} plan</div>
            </div>
          </div>
          <div className="mt-2.5 flex items-center gap-1.5 border-t border-line pt-2 font-mono text-[9px] uppercase tracking-[0.12em] text-ink-faint">
            <span className="livedot h-1.5 w-1.5 rounded-full bg-pine" /> connected to the mesh
          </div>
        </div>
      )}

      <nav className="flex gap-1 px-3 md:flex-col">
        {items.map((it) => (
          <button key={it.id} onClick={() => onNav(it.id)}
            className={`flex flex-1 items-center gap-2.5 rounded-lg px-3 py-2 text-left font-mono text-[12px] uppercase tracking-[0.1em] transition-colors md:flex-none ${
              view === it.id ? 'bg-pine/10 text-pine' : 'text-ink-soft hover:bg-sunk/60 hover:text-ink'
            }`}>
            <it.icon size={15} strokeWidth={1.75} className="shrink-0" />
            {it.label}
          </button>
        ))}
      </nav>

      <div className="mt-auto hidden border-t border-line px-5 py-4 md:block">
        <div className="truncate font-mono text-[11px] text-ink-soft">{user.email}</div>
        <div className="mt-2 flex items-center gap-4 font-mono text-[11px] uppercase tracking-[0.1em]">
          <a href="#/live" className="text-ink-soft transition-colors hover:text-ink">Live demo</a>
          <button onClick={onSignOut} className="text-ink-soft transition-colors hover:text-coral">Sign out</button>
        </div>
      </div>
    </aside>
  )
}

/* ─── overview ────────────────────────────────────────────────────────────── */
function Overview({ user, org, runs, error, onOpen, onSeeAll, onRunCase, onIntake, starting, canIntake }: {
  user: { name: string; email: string }
  org: { name: string } | null
  runs: RunSummary[] | null
  error: string | null
  onOpen: (id: string) => void
  onSeeAll: () => void
  onRunCase: (caseName?: string) => void
  onIntake: (p: { image?: string; sample?: boolean; dictation_sample?: boolean }) => void
  starting: boolean
  canIntake: boolean
}) {
  const m = useMetrics(runs)
  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Kicker>{org ? org.name : 'Signed in'}</Kicker>
          <h1 className="mt-3 font-display text-4xl font-medium tracking-tight text-ink">
            Hello, {user.name?.trim() || user.email.split('@')[0]}.
          </h1>
        </div>
        <div className="flex flex-col items-end gap-2 pt-1">
          <RunCaseButton onRunCase={onRunCase} starting={starting} />
          {canIntake && <IntakeButton onIntake={onIntake} starting={starting} />}
        </div>
      </div>

      <Quickstart hasRuns={!!runs && runs.length > 0} onOpenLatest={() => runs && runs[0] && onOpen(runs[0].id)}
        onRunCase={onRunCase} onIntake={onIntake} starting={starting} canIntake={canIntake} />

      {error && <Banner>{error}</Banner>}

      <div className="mt-8 grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-line bg-line lg:grid-cols-4">
        {runs === null ? (
          [0, 1, 2, 3].map((i) => (
            <div key={i} className="bg-paper px-5 py-6">
              <span className="skeleton block h-8 w-16 rounded" />
              <span className="skeleton mt-3 block h-2.5 w-20 rounded" />
            </div>
          ))
        ) : (
          <>
            <Metric label="Cases" value={m.cases} />
            <Metric label="Approval rate" value={m.approvalRate} suffix="%" dim={m.decided === 0} />
            <Metric label="Avg turns" value={m.avgTurns} oneDecimal />
            <Metric label="Private notes" value={m.privateEvents} accent />
          </>
        )}
      </div>

      <div className="mt-10 mb-4 flex items-baseline justify-between">
        <h2 className="font-display text-xl font-semibold tracking-tight">Recent cases</h2>
        {runs && runs.length > 3 && (
          <button onClick={onSeeAll} className="font-mono text-[11px] uppercase tracking-[0.12em] text-pine hover:text-pine-deep">View all →</button>
        )}
      </div>
      <CaseList runs={runs ? runs.slice(0, 4) : null} onOpen={onOpen} />
    </>
  )
}

function Quickstart({ hasRuns, onOpenLatest, onRunCase, onIntake, starting, canIntake }: {
  hasRuns: boolean; onOpenLatest: () => void; onRunCase: (caseName?: string) => void
  onIntake: (p: { image?: string; sample?: boolean; dictation_sample?: boolean }) => void; starting: boolean; canIntake: boolean
}) {
  const KEY = 'syntony.console.quickstart'
  const [dismissed, setDismissed] = useState(() => localStorage.getItem(KEY) === '1')
  if (dismissed) return null
  const close = () => { localStorage.setItem(KEY, '1'); setDismissed(true) }
  return (
    <div className="mt-7 rounded-2xl border border-pine/25 bg-pine/[0.04] p-5">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-pine">Quickstart</span>
        <button onClick={close} className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint hover:text-ink">dismiss</button>
      </div>
      <ol className="mt-4 grid gap-3 sm:grid-cols-3">
        <Step n="1" done title="Organization connected" body="Your side is on the mesh with an encrypted agent credential." />
        <Step n="2" title={canIntake ? 'Run it or read a document' : 'Run a live case'}
          body={canIntake
            ? 'Launch a live provider↔payer negotiation — or drop in a clinical document and let AI/ML read it.'
            : 'Launch a live provider↔payer negotiation and watch it stream into your audit, decision by decision.'} />
        <Step n="3" title="Privacy by design" body="You see every message, but only your own agents' private reasoning." />
      </ol>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <RunCaseButton onRunCase={onRunCase} starting={starting} />
        {canIntake && <IntakeButton onIntake={onIntake} starting={starting} />}
        {hasRuns && (
          <button onClick={onOpenLatest}
            className="rounded-lg border border-pine/40 px-4 py-2 text-[13px] font-medium text-pine transition-colors hover:bg-pine/[0.06]">
            Open latest case →
          </button>
        )}
      </div>
    </div>
  )
}

function Step({ n, title, body, done }: { n: string; title: string; body: string; done?: boolean }) {
  return (
    <li className="flex gap-3">
      <span className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full font-mono text-[10px] ${
        done ? 'bg-pine text-bone' : 'border border-pine/40 text-pine'}`}>
        {done ? '✓' : n}
      </span>
      <div>
        <div className="text-[13px] font-semibold leading-tight">{title}</div>
        <div className="mt-1 text-[12px] leading-snug text-ink-soft">{body}</div>
      </div>
    </li>
  )
}

/* ─── cases ───────────────────────────────────────────────────────────────── */
function Cases({ runs, error, onOpen, onRunCase, onIntake, starting, canIntake }: {
  runs: RunSummary[] | null; error: string | null; onOpen: (id: string) => void
  onRunCase: (caseName?: string) => void
  onIntake: (p: { image?: string; sample?: boolean; dictation_sample?: boolean }) => void; starting: boolean; canIntake: boolean
}) {
  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Kicker>Audit</Kicker>
          <h1 className="mt-3 font-display text-3xl font-medium tracking-tight text-ink">Cases</h1>
        </div>
        <div className="flex flex-col items-end gap-2 pt-1">
          <RunCaseButton onRunCase={onRunCase} starting={starting} subtle />
          {canIntake && <IntakeButton onIntake={onIntake} starting={starting} />}
        </div>
      </div>
      <p className="mt-3 max-w-xl text-ink-soft">Every prior-authorization negotiation your organization took part in, scoped to what your side is allowed to see.</p>
      {error && <Banner>{error}</Banner>}
      <div className="mt-8"><CaseList runs={runs} onOpen={onOpen} onRunCase={onRunCase} starting={starting} /></div>
    </>
  )
}

function CaseList({ runs, onOpen, onRunCase, starting }: {
  runs: RunSummary[] | null; onOpen: (id: string) => void
  onRunCase?: () => void; starting?: boolean
}) {
  if (!runs)
    return (
      <div className="space-y-2.5">
        {[0, 1, 2].map((i) => (
          <div key={i} className="flex items-center gap-4 rounded-xl border border-line bg-paper px-5 py-4">
            <span className="skeleton h-2.5 w-2.5 rounded-full" />
            <div className="min-w-0 flex-1 space-y-2">
              <span className="skeleton block h-3.5 w-40 rounded" />
              <span className="skeleton block h-2.5 w-24 rounded" />
            </div>
            <span className="skeleton h-5 w-16 rounded" />
          </div>
        ))}
      </div>
    )
  if (runs.length === 0)
    return (
      <div className="rounded-2xl border border-dashed border-line bg-sunk/40 p-10 text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full border border-line bg-paper">
          <span className="livedot h-2.5 w-2.5 rounded-full bg-coral" />
        </div>
        <div className="font-display text-lg font-semibold">No cases yet</div>
        <p className="mx-auto mt-2 max-w-sm text-[14px] text-ink-soft">Run a live provider↔payer negotiation — it streams in here, audited for your organization.</p>
        {onRunCase && <div className="mt-5 flex justify-center"><RunCaseButton onRunCase={onRunCase} starting={!!starting} /></div>}
      </div>
    )
  return (
    <div className="space-y-2.5">
      {runs.map((r, i) => {
        const running = r.status === 'running'
        return (
          <button key={r.id} onClick={() => onOpen(r.id)} style={{ animationDelay: `${i * 50}ms` }}
            className="animate-rise lift group flex w-full items-center gap-4 rounded-xl border border-line bg-paper px-5 py-4 text-left hover:border-pine/40">
            <StatusDot status={r.status} />
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="truncate font-display text-[15px] font-semibold">{caseTitle(r.case_name)}</span>
                {r.urgency === 'expedited' && <ExpeditedChip />}
              </div>
              <div className="font-mono text-[11px] text-ink-faint">
                {running ? <span className="text-coral">running…</span>
                  : r.status === 'awaiting_human' ? <span className="text-coral">awaiting review…</span>
                  : fmtTime(r.started_at)} · {r.turns} turns
              </div>
            </div>
            <div className="ml-auto flex items-center gap-2">
              {running ? <LivePill /> : r.status === 'awaiting_human' ? <AwaitingPill /> : <OutcomeBadge outcome={r.outcome} />}
              <span className="hidden font-mono text-[10px] uppercase tracking-[0.1em] text-ink-faint sm:inline">{r.events} msgs</span>
              {r.private_events > 0 && <LockChip n={r.private_events} />}
              <ChevronRight size={15} className="shrink-0 text-ink-faint transition-transform group-hover:translate-x-0.5" />
            </div>
          </button>
        )
      })}
    </div>
  )
}

function ExpeditedChip() {
  return (
    <span className="flex items-center gap-1 rounded-md border border-coral/40 bg-coral/[0.06] px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.1em] text-coral">
      <Clock size={11} strokeWidth={2} /> 72h
    </span>
  )
}

/* ─── theater (the wow) ───────────────────────────────────────────────────── */
/** Pulsing "LIVE" pill shown while a negotiation is still streaming in. */
function LivePill() {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-coral/40 bg-coral/[0.06] px-3 py-1 font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-coral">
      <span className="relative flex h-2 w-2">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-coral opacity-75" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-coral" />
      </span>
      Live
    </span>
  )
}

/** Shown while a borderline case is paused for the human Medical Director. */
function AwaitingPill() {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-coral/40 bg-coral/[0.06] px-3 py-1 font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-coral">
      <span className="h-2 w-2 rounded-full bg-coral" /> Awaiting review
    </span>
  )
}

/** Human-in-the-loop decision panel: the payer's Medical Director approves or denies a
 *  borderline case that the automated policy escalated. */
function HitlPanel({ events, canDecide, deciding, onDecide }: {
  events: AuditEvent[]; canDecide: boolean; deciding: boolean; onDecide: (o: 'APPROVE' | 'DENY') => void
}) {
  const esc = [...events].reverse().find((e) => e.visibility === 'room' && (e.payload.pa_event === 'ESCALATED_TO_MD' || e.payload.denial_reason))
  return (
    <div className="animate-rise mt-5 rounded-xl border-2 border-coral/40 bg-coral/[0.05] p-5">
      <div className="flex items-center gap-2">
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-coral text-bone"><Gavel size={13} /></span>
        <span className="font-display text-[15px] font-semibold text-ink">Awaiting Medical Director</span>
        <span className="ml-auto font-mono text-[10px] uppercase tracking-[0.14em] text-coral">human-in-the-loop</span>
      </div>
      <p className="mt-2 text-[13px] leading-relaxed text-ink-soft">
        This case is borderline — the automated policy escalated it for a human decision rather than auto-denying.
      </p>
      {esc?.payload.message && <p className="mt-2 border-l-2 border-coral/40 pl-3 text-[13px] italic text-ink">“{esc.payload.message}”</p>}
      {canDecide ? (
        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="primary" loading={deciding} onClick={() => onDecide('APPROVE')}>Approve authorization</Button>
          <Button variant="secondary" disabled={deciding} onClick={() => onDecide('DENY')}>Uphold denial</Button>
        </div>
      ) : (
        <p className="mt-3 font-mono text-[11px] uppercase tracking-[0.12em] text-ink-faint">awaiting the payer's Medical Director to decide</p>
      )}
    </div>
  )
}

/** Copyable run id — a small audit-y affordance (click to copy the full UUID). */
function RunIdChip({ id }: { id: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard?.writeText(id).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1400) }).catch(() => {})
  }
  return (
    <button onClick={copy} title="Copy run id"
      className="inline-flex items-center gap-1.5 rounded-md border border-line bg-paper px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-faint transition-colors hover:border-pine/40 hover:text-ink">
      run {id.slice(0, 8)}
      {copied ? <Check size={12} className="text-pine" /> : <Copy size={12} />}
    </button>
  )
}

function Theater({ runId, orgName, onBack, onComplete }: {
  runId: string; orgName: string; onBack: () => void; onComplete?: () => void
}) {
  const [detail, setDetail] = useState<RunDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [deciding, setDeciding] = useState(false)
  const [exporting, setExporting] = useState(false)
  // Poll while the run is RUNNING so a live negotiation streams in turn by turn; stop once it
  // finishes (and refresh the caller's list). A finished run opened from the list fetches once.
  useEffect(() => {
    setDetail(null)
    setError(null)
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    let errs = 0
    let done = false
    const poll = async () => {
      try {
        const d = await runsApi.get(runId)
        if (cancelled) return
        setDetail(d)
        errs = 0
        if (d.run.status === 'running') {
          timer = setTimeout(poll, 1500)
        } else if (!done) {
          done = true
          onComplete?.()
        }
      } catch (e) {
        if (cancelled) return
        if (++errs <= 3) { timer = setTimeout(poll, 1500); return }  // tolerate a transient hiccup
        setError(String((e as Error)?.message || e))
      }
    }
    poll()
    return () => { cancelled = true; if (timer) clearTimeout(timer) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId])

  // group events by turn (room message + my private reasoning); derive which side is "me".
  // Hooks must run unconditionally, so compute before any early return.
  const turns = useMemo(() => groupByTurn(detail?.events ?? []), [detail])
  const mySide = useMemo(() => {
    const ev = detail?.events ?? []
    const mine = ev.find((e) => e.visibility === 'private_event')
    return sideOf(mine?.author ?? ev[0]?.author ?? 'provider')
  }, [detail])
  const counterparty = mySide === 'provider' ? 'the payer' : 'the provider'

  const back = (
    <button onClick={onBack} className="font-mono text-[11px] uppercase tracking-[0.12em] text-ink-soft transition-colors hover:text-ink">← All cases</button>
  )
  if (error) return <div>{back}<Banner>{error}</Banner></div>
  if (!detail) return <div>{back}<p className="mt-6 font-mono text-[12px] text-ink-faint">Loading case…</p></div>

  const { run } = detail
  const live = run.status === 'running'
  const awaiting = run.status === 'awaiting_human'
  const overturned = detail.events.some((e) => e.payload.pa_event === 'DECISION_OVERTURNED')

  const decide = async (outcome: 'APPROVE' | 'DENY') => {
    setDeciding(true)
    try {
      await runsApi.decide(run.id, outcome)
      setDetail(await runsApi.get(run.id))
      onComplete?.()
    } catch (e) {
      setError(String((e as Error)?.message || e))
    } finally {
      setDeciding(false)
    }
  }

  const exportPdf = async () => {
    setExporting(true)
    try {
      downloadBlob(await runsApi.exportPdf(run.id), `audit-${run.case_name}-${run.id.slice(0, 8)}.pdf`)
    } catch (e) {
      setError(String((e as Error)?.message || e))
    } finally {
      setExporting(false)
    }
  }
  const exportJson = () => {
    const blob = new Blob([JSON.stringify(detail, null, 2)], { type: 'application/json' })
    downloadBlob(blob, `audit-${run.case_name}-${run.id.slice(0, 8)}.json`)
  }

  return (
    <div>
      {back}
      <div className="mt-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <Kicker>Case · prior authorization</Kicker>
          <h1 className="mt-2 font-display text-3xl font-medium tracking-tight text-ink">{caseTitle(run.case_name)}</h1>
        </div>
        {live ? <LivePill /> : awaiting ? <AwaitingPill /> : <DecisionBadge outcome={run.outcome} state={run.final_state} />}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11px] text-ink-faint">
        <span>{turns.length} turns</span><span>·</span>
        <span>{fmtTime(run.started_at)}</span><span>·</span>
        <span>{run.events} messages</span><span>·</span>
        <span className="text-coral">{run.private_events} private to you</span>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <RunIdChip id={run.id} />
        {run.room_id && (
          <a href={`/?room=${run.room_id}#/live`} target="_blank" rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-md border border-line bg-paper px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-soft transition-colors hover:border-pine/40 hover:text-pine">
            <ExternalLink size={12} /> view Band room
          </a>
        )}
        <button onClick={exportPdf} disabled={exporting} title="Download audit PDF"
          className="inline-flex items-center gap-1.5 rounded-md border border-line bg-paper px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-soft transition-colors hover:border-pine/40 hover:text-pine disabled:opacity-60">
          {exporting ? <Loader2 size={12} className="animate-spin" /> : <FileText size={12} />} {exporting ? 'exporting…' : 'PDF'}
        </button>
        <button onClick={exportJson} title="Download audit JSON"
          className="inline-flex items-center gap-1.5 rounded-md border border-line bg-paper px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-soft transition-colors hover:border-pine/40 hover:text-pine">
          <Braces size={12} /> JSON
        </button>
      </div>

      <SlaBanner run={run} />
      {overturned && <OverturnBanner />}
      {awaiting && <HitlPanel events={detail.events} canDecide={mySide === 'payer'} deciding={deciding} onDecide={decide} />}

      <Lanes mySide={mySide} myOrg={orgName} />

      {live && turns.length === 0 && (
        <p className="mt-4 flex items-center gap-2 font-mono text-[12px] text-ink-faint">
          <Loader2 size={13} className="animate-spin" /> Negotiating across the mesh — turns will appear as they're posted…
        </p>
      )}

      <ol className="relative mt-2">
        {/* the spine */}
        <div className="pointer-events-none absolute bottom-2 left-[7px] top-2 w-px bg-line sm:left-1/2 sm:-translate-x-1/2" />
        {turns.map((t, i) => (
          <TurnRow key={t.turn} t={t} mySide={mySide} myOrg={orgName} counterparty={counterparty} index={i} />
        ))}
      </ol>

      <p className="mt-6 flex items-center justify-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-faint">
        <Lock size={11} strokeWidth={1.75} className="text-coral" /> private reasoning is scoped to its own organization — never the other side
      </p>
    </div>
  )
}

/** Shown when a denial was appealed and overturned — the golden prior-auth outcome. */
function OverturnBanner() {
  return (
    <div className="animate-rise mt-4 overflow-hidden rounded-xl border border-pine/30 bg-pine/[0.05] p-4">
      <div className="flex items-center gap-2">
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-pine text-bone"><RotateCcw size={13} /></span>
        <span className="font-display text-[15px] font-semibold text-pine">Denial overturned on appeal</span>
      </div>
      <p className="mt-2 text-[13px] leading-relaxed text-ink-soft">
        Provider Appeals addressed the specific denial reason and the payer reconsidered.
        <span className="font-semibold text-ink"> 80.7%</span> of appealed Medicare Advantage denials are
        overturned — yet only <span className="font-semibold text-ink">11.5%</span> are ever appealed
        <span className="font-mono text-[11px] text-ink-faint"> (KFF, 2024)</span>.
      </p>
    </div>
  )
}

/** CMS-0057-F decision-time SLA: 72h expedited / 7 calendar days standard. */
function SlaBanner({ run }: { run: RunSummary }) {
  const expedited = run.urgency === 'expedited'
  const hours = expedited ? 72 : 168
  const deadline = new Date(new Date(run.started_at).getTime() + hours * 3_600_000)
  const ended = run.ended_at ? new Date(run.ended_at) : null
  const met = ended ? ended <= deadline : true
  return (
    <div className={`mt-5 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border px-4 py-2.5 ${
      expedited ? 'border-coral/30 bg-coral/[0.04]' : 'border-line bg-sunk/40'}`}>
      <Clock size={13} strokeWidth={1.75} className={expedited ? 'text-coral' : 'text-ink-soft'} />
      <span className="font-display text-[13px] font-semibold">{expedited ? 'Expedited' : 'Standard'}</span>
      <span className="text-[13px] text-ink-soft">decision due within {expedited ? '72 hours' : '7 calendar days'}</span>
      <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-faint">CMS-0057-F</span>
      {ended && (
        <span className={`ml-auto rounded-md px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.1em] ${
          met ? 'bg-pine/10 text-pine' : 'bg-coral/10 text-coral'}`}>
          {met ? 'within SLA' : 'past SLA'}
        </span>
      )}
    </div>
  )
}

function Lanes({ mySide, myOrg }: { mySide: string; myOrg: string }) {
  const left = { label: mySide === 'provider' ? myOrg : 'Provider', dot: 'bg-pine', isYou: mySide === 'provider' }
  const right = { label: mySide === 'payer' ? myOrg : 'Payer', dot: 'bg-ink', isYou: mySide === 'payer' }
  return (
    <div className="mt-8 mb-4 hidden items-center justify-between border-y border-line py-2.5 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-soft sm:flex">
      <span className="flex items-center gap-2"><span className={`h-2 w-2 rounded-full ${left.dot}`} />{left.label}{left.isYou && <YouTag />}</span>
      <span className="text-ink-faint">shared case room</span>
      <span className="flex items-center gap-2">{right.label}{right.isYou && <YouTag />}<span className={`h-2 w-2 rounded-full ${right.dot}`} /></span>
    </div>
  )
}

type Turn = { turn: number; room?: AuditEvent; mine?: AuditEvent }

function TurnRow({ t, mySide, myOrg, counterparty, index }: {
  t: Turn; mySide: string; myOrg: string; counterparty: string; index: number
}) {
  const room = t.room
  if (!room) return null
  const side = sideOf(room.author)
  const isMine = side === mySide
  const isDecision = !!room.payload.outcome
  const node = side === 'provider' ? 'bg-pine' : 'bg-ink'

  const content = (
    <div style={{ animationDelay: `${index * 70}ms` }} className="animate-rise space-y-2">
      <div className={`rounded-xl border bg-paper px-4 py-3 ${isDecision ? 'border-pine/40 shadow-[0_10px_30px_-20px_rgba(11,94,79,0.7)]' : 'border-line'}`}>
        <div className="flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em]">
          <span className="text-ink-soft">{prettyAuthor(room.author)}</span>
          <span className="rounded bg-sunk px-1.5 py-0.5 text-ink-faint">
            {room.payload.pa_event ? prettyEvent(room.payload.pa_event) : room.kind.toLowerCase().replace(/_/g, ' ')}
          </span>
          {room.payload.outcome && <OutcomeBadge outcome={room.payload.outcome} />}
          {room.payload.denial_reason && (
            <span className="rounded bg-coral/10 px-1.5 py-0.5 text-coral">{prettyReason(room.payload.denial_reason)}</span>
          )}
          {room.payload.framework && (
            <span title={room.payload.via ? `produced via ${room.payload.via}` : undefined}
              className="ml-auto rounded bg-pine/[0.07] px-1.5 py-0.5 text-pine">{prettyFramework(room.payload.framework)}</span>
          )}
        </div>
        <p className="mt-1.5 text-[14px] leading-relaxed text-ink">{room.payload.message || '—'}</p>
      </div>
      {isMine
        ? t.mine && <PrivateNote text={t.mine.payload.reasoning || ''} org={myOrg} />
        : <SealedNote org={counterparty} />}
    </div>
  )

  return (
    <li className="relative grid grid-cols-1 py-3 pl-7 sm:grid-cols-2 sm:gap-10 sm:pl-0">
      <span className={`absolute left-[3px] top-5 h-3 w-3 rounded-full ring-4 ring-bone ${node} sm:left-1/2 sm:-translate-x-1/2`} />
      <div className={isMine ? 'sm:col-start-1' : 'sm:col-start-2 sm:row-start-1'}>{content}</div>
    </li>
  )
}

function PrivateNote({ text, org }: { text: string; org: string }) {
  return (
    <div className="rounded-xl border border-coral/35 bg-coral/[0.05] px-4 py-2.5">
      <div className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-coral">
        <Lock size={11} strokeWidth={1.75} /> private · only {org} sees this
      </div>
      <p className="mt-1 text-[13px] italic leading-relaxed text-ink-soft">{text || '—'}</p>
    </div>
  )
}

function SealedNote({ org }: { org: string }) {
  return (
    <div className="rounded-xl border border-dashed border-line bg-sunk/40 px-4 py-2.5">
      <div className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint">
        <Lock size={11} strokeWidth={1.75} /> private reasoning · sealed to {org}
      </div>
      <div className="mt-1.5 flex gap-1 opacity-60" aria-hidden>
        {[40, 64, 28, 52].map((w, i) => <span key={i} style={{ width: w }} className="h-2 rounded-full bg-ink-faint/30" />)}
      </div>
    </div>
  )
}

/* ─── insights ──────────────────────────────────────────────────────────────
   Audit analytics aggregated server-side over the org's runs: outcomes, overturns,
   turnaround, SLA adherence, denial-reason mix, and per-agent participation. */
function InsightsView() {
  const [data, setData] = useState<Insights | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    runsApi.insights().then(setData).catch((e) => setError(String(e?.message || e)))
  }, [])

  return (
    <>
      <Kicker>Audit analytics</Kicker>
      <h1 className="mt-3 font-display text-3xl font-medium tracking-tight text-ink">Insights</h1>
      <p className="mt-3 max-w-xl text-ink-soft">Outcomes, turnaround, SLA adherence and where decisions turn — aggregated across every case your organization took part in.</p>
      {error && <Banner>{error}</Banner>}

      {!data ? (
        <div className="mt-8 grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-line bg-line lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="bg-paper px-5 py-6"><span className="skeleton block h-8 w-16 rounded" /><span className="skeleton mt-3 block h-2.5 w-20 rounded" /></div>
          ))}
        </div>
      ) : data.cases === 0 ? (
        <div className="mt-8 rounded-2xl border border-dashed border-line bg-sunk/40 p-10 text-center">
          <div className="font-display text-lg font-semibold">No data yet</div>
          <p className="mx-auto mt-2 max-w-sm text-[14px] text-ink-soft">Run a few cases and the analytics populate here.</p>
        </div>
      ) : (
        <>
          <div className="mt-8 grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-line bg-line lg:grid-cols-4">
            <Metric label="Cases" value={data.cases} />
            <Metric label="Approval rate" value={data.approval_rate} suffix="%" dim={data.decided === 0} />
            <Metric label="Overturns" value={data.overturns} accent />
            <TurnaroundTile sec={data.avg_turnaround_sec} />
          </div>

          <div className="mt-8 grid gap-6 lg:grid-cols-2">
            <Panel title="Outcomes">
              <SegBar segments={[['bg-pine', data.approvals], ['bg-coral', data.denials], ['bg-ink-faint/30', data.cases - data.decided]]} />
              <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 font-mono text-[11px] text-ink-soft">
                <Legend dot="bg-pine" label={`${data.approvals} approved`} />
                <Legend dot="bg-coral" label={`${data.denials} denied`} />
                {data.overturns > 0 && <Legend dot="bg-pine/50" label={`${data.overturns} overturned`} />}
              </div>
            </Panel>

            <Panel title="CMS-0057-F SLA adherence">
              <SegBar segments={[['bg-pine', data.within_sla], ['bg-coral', data.past_sla]]} />
              <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-1 font-mono text-[11px] text-ink-soft">
                <Legend dot="bg-pine" label={`${data.within_sla} within SLA`} />
                <Legend dot="bg-coral" label={`${data.past_sla} past SLA`} />
                <span className="ml-auto text-ink-faint">{data.expedited} expedited · {data.standard} standard</span>
              </div>
            </Panel>

            <Panel title="Denial reasons">
              {data.denial_reasons.length
                ? <BarList items={data.denial_reasons.map((d) => ({ label: prettyReason(d.reason), value: d.count }))} tone="coral" />
                : <p className="text-[13px] text-ink-soft">No adverse determinations recorded.</p>}
            </Panel>

            <Panel title="Agent participation">
              <BarList items={data.agents.map((a) => ({ label: prettyAuthor(a.author), value: a.runs }))} tone="pine" />
            </Panel>

            <Panel title="Agent execution · provenance">
              {data.frameworks.length ? (
                <>
                  <div className="mb-4 font-mono text-[11px] text-ink-soft">
                    <span className="text-pine">{data.on_framework_rate}%</span> of turns ran on a real framework
                  </div>
                  <BarList items={data.frameworks.map((f) => ({ label: prettyFramework(f.via), value: f.count }))} tone="pine" />
                </>
              ) : (
                <p className="text-[13px] text-ink-soft">No framework provenance recorded yet.</p>
              )}
            </Panel>
          </div>
        </>
      )}
    </>
  )
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-line bg-paper p-5">
      <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-faint">{title}</div>
      <div className="mt-4">{children}</div>
    </div>
  )
}

function SegBar({ segments }: { segments: [string, number][] }) {
  const total = segments.reduce((s, [, n]) => s + n, 0) || 1
  return (
    <div className="flex h-3 overflow-hidden rounded-full bg-sunk">
      {segments.map(([cls, n], i) => (n > 0 ? <div key={i} className={cls} style={{ width: `${(n / total) * 100}%` }} /> : null))}
    </div>
  )
}

function Legend({ dot, label }: { dot: string; label: string }) {
  return <span className="flex items-center gap-1.5"><span className={`h-2 w-2 rounded-full ${dot}`} />{label}</span>
}

function BarList({ items, tone }: { items: { label: string; value: number }[]; tone: 'pine' | 'coral' }) {
  const max = Math.max(...items.map((i) => i.value), 1)
  const bar = tone === 'coral' ? 'bg-coral' : 'bg-pine'
  return (
    <div className="space-y-2.5">
      {items.map((it, i) => (
        <div key={i} className="flex items-center gap-3">
          <span className="w-36 shrink-0 truncate text-[12px] text-ink-soft">{it.label}</span>
          <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-sunk">
            <div className={`h-full rounded-full ${bar}`} style={{ width: `${(it.value / max) * 100}%` }} />
          </div>
          <span className="w-6 shrink-0 text-right font-mono text-[11px] tabular-nums text-ink">{it.value}</span>
        </div>
      ))}
    </div>
  )
}

function TurnaroundTile({ sec }: { sec: number }) {
  const [n, u] = fmtDuration(sec)
  return (
    <div className="group relative bg-paper px-5 py-6 transition-colors hover:bg-bone/50">
      <span className="absolute inset-x-0 top-0 h-0.5 bg-pine opacity-0 transition-opacity duration-300 group-hover:opacity-100" aria-hidden />
      <div className="font-mono text-[34px] font-medium leading-none tabular-nums tracking-tight text-ink">{n}<span className="text-ink-faint">{u}</span></div>
      <div className="mt-2 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-faint">Avg turnaround</div>
    </div>
  )
}

function fmtDuration(sec: number): [string, string] {
  if (!sec) return ['—', '']
  if (sec < 90) return [String(sec), 's']
  if (sec < 5400) return [String(Math.round(sec / 60)), 'm']
  if (sec < 172800) return [String(Math.round(sec / 3600)), 'h']
  return [String(Math.round(sec / 86400)), 'd']
}

/* ─── agents / mesh ─────────────────────────────────────────────────────────
   Showcases the multi-agent roster: who is on the mesh, the framework + model that
   backs each role, and the protocol states they act in. Grouped by organization. */
function AgentsView() {
  const [agents, setAgents] = useState<AgentInfo[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    agentsApi.list().then((r) => setAgents(r.agents)).catch((e) => setError(String(e?.message || e)))
  }, [])

  const all = agents ?? []
  const provider = all.filter((a) => a.side === 'provider')
  const payer = all.filter((a) => a.side === 'payer')
  const neutral = all.filter((a) => a.side === 'neutral')
  const frameworks = new Set(all.map((a) => a.framework)).size

  return (
    <>
      <Kicker>The mesh</Kicker>
      <h1 className="mt-3 font-display text-3xl font-medium tracking-tight text-ink">Agents</h1>
      <p className="mt-3 max-w-xl text-ink-soft">Every specialist on the mesh — heterogeneous frameworks and models, one protocol — collaborating across two organizations on each case.</p>
      {error && <Banner>{error}</Banner>}

      <div className="mt-8 grid grid-cols-3 gap-px overflow-hidden rounded-2xl border border-line bg-line">
        {agents === null ? (
          [0, 1, 2].map((i) => (
            <div key={i} className="bg-paper px-5 py-6"><span className="skeleton block h-8 w-12 rounded" /><span className="skeleton mt-3 block h-2.5 w-20 rounded" /></div>
          ))
        ) : (
          <>
            <Metric label="Agents" value={all.length} />
            <Metric label="Frameworks" value={frameworks} />
            <Metric label="Organizations" value={2} accent />
          </>
        )}
      </div>

      {agents === null ? (
        <p className="mt-8 font-mono text-[12px] text-ink-faint">Loading roster…</p>
      ) : (
        <div className="mt-10 grid gap-x-6 gap-y-8 lg:grid-cols-2">
          <AgentColumn title="Provider organization" side="provider" agents={provider} />
          <AgentColumn title="Payer organization" side="payer" agents={payer} />
          {neutral.length > 0 && <AgentColumn title="Governance" side="neutral" agents={neutral} />}
        </div>
      )}
    </>
  )
}

function AgentColumn({ title, side, agents }: { title: string; side: string; agents: AgentInfo[] }) {
  const dot = side === 'provider' ? 'bg-pine' : side === 'payer' ? 'bg-ink' : 'bg-coral'
  return (
    <div>
      <div className="mb-3 flex items-center gap-2 border-b border-line pb-2 font-mono text-[10px] uppercase tracking-[0.16em] text-ink-soft">
        <span className={`h-2 w-2 rounded-full ${dot}`} /> {title}
        <span className="ml-auto text-ink-faint">{agents.length} agents</span>
      </div>
      <div className="space-y-2.5">
        {agents.map((a, i) => <AgentCard key={a.id} a={a} index={i} />)}
      </div>
    </div>
  )
}

function AgentCard({ a, index }: { a: AgentInfo; index: number }) {
  const accent = a.side === 'provider' ? 'bg-pine' : a.side === 'payer' ? 'bg-ink' : 'bg-coral'
  return (
    <div style={{ animationDelay: `${index * 50}ms` }}
      className="animate-rise lift relative overflow-hidden rounded-xl border border-line bg-paper p-4">
      <span className={`absolute inset-y-0 left-0 w-0.5 ${accent}`} aria-hidden />
      <div className="flex items-center justify-between gap-2">
        <span className="font-display text-[15px] font-semibold">{a.name}</span>
        {a.human
          ? <Badge tone="coral">human · HITL</Badge>
          : <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-pine">{a.framework.replace(/_/g, ' ')}</span>}
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-faint">
        <span>{a.id}</span>
        {a.model && <span className="text-ink-soft">{a.model}</span>}
      </div>
      <div className="mt-2.5 flex flex-wrap gap-1">
        {a.acts_in.map((s) => (
          <span key={s} className="rounded bg-sunk px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.1em] text-ink-faint">{s.toLowerCase()}</span>
        ))}
      </div>
    </div>
  )
}

/* ─── AI/ML API ───────────────────────────────────────────────────────────── */
function AimlView() {
  const [s, setS] = useState<AimlSurface | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    aimlApi.get().then(setS).catch((e) => setError(String(e?.message || e)))
  }, [])

  const n = (x: number) => x.toLocaleString('en-US')
  const t = s?.totals
  const turnsByModel = new Map((s?.usage.models ?? []).map((m) => [m.model, m.turns]))

  return (
    <>
      <div className="flex items-center gap-2">
        <Sparkles size={15} strokeWidth={1.75} className="text-pine" />
        <Kicker>Powered by AI/ML API</Kicker>
      </div>
      <h1 className="mt-3 font-display text-3xl font-medium tracking-tight text-ink">AI/ML API</h1>
      <p className="mt-3 max-w-2xl text-ink-soft">
        Every agent on the mesh — across both organizations — reasons through a single{' '}
        <strong>AI/ML API</strong> gateway: one OpenAI-compatible endpoint, one key, many models.
        These numbers are live, summed from this organization's audited runs.
      </p>
      {error && <Banner>{error}</Banner>}

      {/* the gateway */}
      <div className="mt-8 rounded-2xl border border-pine/25 bg-pine/[0.04] p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <Cpu size={18} strokeWidth={1.75} className="text-pine" />
            <span className="font-display text-[16px] font-semibold">The gateway</span>
          </div>
          <code className="rounded-md border border-line bg-paper px-2.5 py-1 font-mono text-[12px] text-ink-soft">
            {s ? s.gateway.base_url : '…'}
          </code>
        </div>
        <div className="mt-3 flex flex-wrap gap-2 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-faint">
          <span className="rounded bg-sunk px-2 py-1">OpenAI-compatible</span>
          <span className="rounded bg-sunk px-2 py-1">1 key · {s ? s.gateway.key_env : 'AIML_API_KEY'}</span>
          <span className="rounded bg-sunk px-2 py-1">{s ? n(s.gateway.catalog_models) : '—'} models in catalog</span>
        </div>
        {s && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {s.gateway.app_models.map((m) => (
              <span key={m} className="flex items-center gap-1.5 rounded-lg border border-pine/30 bg-paper px-2.5 py-1 font-mono text-[11px] text-pine">
                {m}
                {turnsByModel.get(m) ? <span className="text-ink-faint">· {n(turnsByModel.get(m)!)} turns</span> : null}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* live totals */}
      <div className="mt-6 grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-line bg-line lg:grid-cols-4">
        {!s ? (
          [0, 1, 2, 3].map((i) => (
            <div key={i} className="bg-paper px-5 py-6"><span className="skeleton block h-8 w-16 rounded" /><span className="skeleton mt-3 block h-2.5 w-20 rounded" /></div>
          ))
        ) : (
          <>
            <Metric label="Model turns" value={t!.model_turns} />
            <Metric label="Tokens in" value={t!.tokens_in} />
            <Metric label="Tokens out" value={t!.tokens_out} accent />
            <Metric label="Models used" value={s.gateway.app_models.length} />
          </>
        )}
      </div>

      {/* feature matrix */}
      <h2 className="mt-10 mb-4 font-display text-xl font-semibold tracking-tight">Features in use</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        {(s?.features ?? []).map((f) => (
          <div key={f.key} className="lift rounded-xl border border-line bg-paper p-4">
            <div className="flex items-center justify-between gap-2">
              <span className="font-display text-[14px] font-semibold">{f.label}</span>
              <Badge tone={f.status === 'in_use' ? 'pine' : 'ink'}>{f.status === 'in_use' ? 'in use' : 'supported'}</Badge>
            </div>
            <p className="mt-1.5 text-[12.5px] leading-snug text-ink-soft">{f.detail}</p>
            {f.metric && <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.12em] text-pine">{f.metric}</p>}
          </div>
        ))}
        {!s && [0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-24 rounded-xl" />)}
      </div>

      {/* per-role model map */}
      {s && (
        <>
          <h2 className="mt-10 mb-4 font-display text-xl font-semibold tracking-tight">Model per role</h2>
          <div className="overflow-hidden rounded-xl border border-line">
            {s.roles.map((r, i) => (
              <div key={r.id} className={`flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2.5 ${i % 2 ? 'bg-sunk/30' : 'bg-paper'}`}>
                <span className={`h-2 w-2 shrink-0 rounded-full ${r.side === 'provider' ? 'bg-pine' : r.side === 'payer' ? 'bg-ink' : 'bg-coral'}`} />
                <span className="min-w-[150px] text-[13px] font-medium">{r.name}</span>
                <span className="font-mono text-[11px] text-ink-soft">{r.human ? 'human · HITL' : (r.model ?? '—')}</span>
                <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-faint">{r.framework.replace(/_/g, ' ')}</span>
                {r.reasoning_effort && <span className="ml-auto rounded bg-pine/10 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.1em] text-pine">effort: {r.reasoning_effort}</span>}
              </div>
            ))}
          </div>
        </>
      )}
    </>
  )
}

/* ─── settings ────────────────────────────────────────────────────────────── */
function Settings({ user, org }: { user: { name: string; email: string; id: string }; org: { name: string; slug: string; plan: string } | null }) {
  return (
    <>
      <Kicker>Settings</Kicker>
      <h1 className="mt-3 font-display text-3xl font-medium tracking-tight text-ink">Account &amp; organization</h1>
      <div className="mt-8 grid gap-5 sm:grid-cols-2">
        <Card label="Account">
          <Row k="Name" v={user.name || '—'} />
          <Row k="Email" v={user.email} mono />
          <Row k="User ID" v={user.id} mono faint />
        </Card>
        <Card label="Organization">
          {org ? (<>
            <Row k="Name" v={org.name} />
            <Row k="Slug" v={org.slug} mono />
            <Row k="Plan" v={org.plan} badge />
          </>) : <p className="text-[14px] text-ink-soft">No organization on this account yet.</p>}
        </Card>
      </div>
      <div className="mt-8 rounded-2xl border border-dashed border-line bg-sunk/40 p-6">
        <div className="font-mono text-[11px] uppercase tracking-[0.16em] text-ink-faint">Coming next</div>
        <p className="mt-2 max-w-2xl text-[14px] leading-relaxed text-ink-soft">
          API keys · encrypted Band/LLM credentials · team members · usage &amp; billing — all already modeled in the control plane.
        </p>
      </div>
    </>
  )
}

/* ─── shared bits ─────────────────────────────────────────────────────────── */
function useMetrics(runs: RunSummary[] | null) {
  return useMemo(() => {
    const r = runs ?? []
    const withOutcome = r.filter((x) => x.outcome)
    const approvals = withOutcome.filter((x) => x.outcome === 'APPROVE').length
    const cases = r.length
    return {
      cases,
      decided: withOutcome.length,
      approvalRate: withOutcome.length ? Math.round((approvals / withOutcome.length) * 100) : 0,
      avgTurns: cases ? r.reduce((s, x) => s + x.turns, 0) / cases : 0,
      privateEvents: r.reduce((s, x) => s + x.private_events, 0),
    }
  }, [runs])
}

function Metric({ label, value, suffix, oneDecimal, accent, dim }: {
  label: string; value: number; suffix?: string; oneDecimal?: boolean; accent?: boolean; dim?: boolean
}) {
  const shown = useCountUp(value)
  const text = dim ? '—' : (oneDecimal ? shown.toFixed(1) : Math.round(shown).toString())
  return (
    <div className="group relative bg-paper px-5 py-6 transition-colors hover:bg-bone/50">
      <span className={`absolute inset-x-0 top-0 h-0.5 opacity-0 transition-opacity duration-300 group-hover:opacity-100 ${accent ? 'bg-coral' : 'bg-pine'}`} aria-hidden />
      <div className={`font-mono text-[34px] font-medium leading-none tabular-nums tracking-tight ${accent ? 'text-coral' : 'text-ink'}`}>
        {text}{!dim && suffix ? <span className="text-ink-faint">{suffix}</span> : null}
      </div>
      <div className="mt-2 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-faint">{label}</div>
    </div>
  )
}

function useCountUp(target: number, duration = 850): number {
  const [v, setV] = useState(0)
  const raf = useRef(0)
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { setV(target); return }
    const start = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      setV(target * (1 - Math.pow(1 - t, 3)))
      if (t < 1) raf.current = requestAnimationFrame(tick)
      else setV(target)
    }
    raf.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf.current)
  }, [target, duration])
  return v
}

function OutcomeBadge({ outcome }: { outcome: string | null }) {
  if (!outcome) return null
  const approve = outcome === 'APPROVE'
  return (
    <span className={`rounded px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.1em] ${
      approve ? 'bg-pine/10 text-pine' : 'bg-coral/10 text-coral'}`}>
      {approve ? 'approved' : outcome.toLowerCase()}
    </span>
  )
}

function DecisionBadge({ outcome, state }: { outcome: string | null; state: string | null }) {
  if (!outcome) return <span className="rounded-lg border border-line px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.12em] text-ink-soft">{state ?? '—'}</span>
  const approve = outcome === 'APPROVE'
  return (
    <span className={`flex items-center gap-2 rounded-lg px-3.5 py-2 font-display text-sm font-semibold ${
      approve ? 'bg-pine text-bone' : 'bg-coral text-bone'}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${approve ? 'bg-bone' : 'bg-bone'}`} />
      {approve ? 'Approved' : outcome.charAt(0) + outcome.slice(1).toLowerCase()}
    </span>
  )
}

function LockChip({ n }: { n: number }) {
  return (
    <span className="flex items-center gap-1 rounded-md border border-coral/40 bg-coral/5 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.1em] text-coral">
      <Lock size={11} strokeWidth={1.75} /> {n}
    </span>
  )
}

function YouTag() {
  return <span className="rounded bg-pine/15 px-1 py-0.5 text-[8px] font-bold text-pine">YOU</span>
}

function StatusDot({ status }: { status: string }) {
  const c = status === 'succeeded' ? 'bg-pine'
    : status === 'failed' ? 'bg-coral'
    : status === 'awaiting_human' ? 'bg-coral'
    : 'bg-ink-faint'
  return <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${c}`} />
}

function Kicker({ children }: { children: React.ReactNode }) {
  return <div className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-faint">{children}</div>
}

function Banner({ children }: { children: React.ReactNode }) {
  return <div className="mt-6 rounded-md border border-coral/40 bg-coral/5 px-3 py-2 text-[13px] text-coral">{children}</div>
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

function caseTitle(s: string): string {
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function prettyAuthor(a: string): string {
  return a.split('.').map((p) => p.replace(/\b\w/g, (c) => c.toUpperCase())).join(' · ')
}

function prettyEvent(e: string): string {
  return e.toLowerCase().replace(/_/g, ' ')
}

function prettyReason(r: string): string {
  return r.toLowerCase().replace(/_/g, ' ')
}

function prettyFramework(f: string): string {
  return { pydantic_ai: 'Pydantic AI', langgraph: 'LangGraph', human: 'Human', 'aiml-gateway': 'AI/ML', fallback: 'fallback' }[f]
    || f.replace(/_/g, ' ')
}

function sideOf(author: string): string {
  return author.split('.')[0]
}

function groupByTurn(events: AuditEvent[]): Turn[] {
  const by = new Map<number, Turn>()
  for (const e of events) {
    const slot = by.get(e.turn) ?? { turn: e.turn }
    if (e.visibility === 'private_event') slot.mine = e
    else slot.room = e
    by.set(e.turn, slot)
  }
  return [...by.values()].sort((a, b) => a.turn - b.turn)
}

function fmtTime(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

function Card({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-line bg-paper p-6">
      <div className="mb-4 font-mono text-[11px] uppercase tracking-[0.16em] text-pine">{label}</div>
      <div className="space-y-3">{children}</div>
    </div>
  )
}

function Row({ k, v, mono, faint, badge }: { k: string; v: string; mono?: boolean; faint?: boolean; badge?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-ink-faint">{k}</span>
      {badge ? (
        <span className="rounded-md border border-pine/30 bg-pine/5 px-2 py-0.5 font-mono text-[11px] uppercase tracking-[0.1em] text-pine">{v}</span>
      ) : (
        <span className={`truncate text-right text-[14px] ${mono ? 'font-mono' : ''} ${faint ? 'text-ink-faint' : 'text-ink'}`}>{v}</span>
      )}
    </div>
  )
}
