import { useEffect, useState, type ReactNode } from 'react'
import { Wordmark } from './Logo'
import { useAuth } from '../auth'

const GITHUB = 'https://github.com/diassique/syntony'

/* ── instrument palette (phosphor traces derived from the system palette) ─── */
const CORAL = '#ff5a3c'

const READOUT = [
  { v: '13', u: 'hrs/wk', l: 'physician time lost to prior auth', src: 'AMA' },
  { v: '≈4', u: 'min', l: 'a negotiated case on Syntony', src: 'measured' },
  { v: '15', u: '$B', l: '10-yr savings projected', src: 'CMS' },
  { v: '72', u: 'h/7d', l: 'response mandate', src: 'CMS-0057-F' },
]

const DIAGNOSTIC = [
  { v: '94%', l: 'of physicians report care delays waiting on prior authorization', src: 'AMA · 2024' },
  { v: '1 in 4', l: 'authorizations are delayed by missing or mismatched documentation', src: 'industry' },
  { v: '80.7%', l: 'of appealed Medicare Advantage denials are overturned', src: 'KFF · 2024' },
  { v: '11.5%', l: 'of denials are ever appealed today — most revenue is simply abandoned', src: 'KFF · 2024' },
]

const PATH = [
  { n: '01', t: 'Intake frames', d: 'A clinic agent assembles a structured, FHIR-shaped request from the chart. No raw PHI leaves the room.' },
  { n: '02', t: 'Counsel corrects', d: 'A coding agent validates codes, signatures and documents — fixing the mismatches that cause most denials before submission.' },
  { n: '03', t: 'Payer reviews', d: 'A payer agent in a different organization checks medical-necessity policy and asks only for what is missing.' },
  { n: '04', t: 'Human decides edges', d: 'Borderline cases escalate to a human Medical Director, added to the room in one step. Every move is audited.' },
]

const AGENTS = [
  { ch: 'CH1', role: 'Intake', side: 'provider', fw: 'LangGraph', fn: 'frames a FHIR-shaped request from the chart' },
  { ch: 'CH2', role: 'Eligibility & Benefits', side: 'provider', fw: 'Pydantic AI', fn: 'verifies coverage before anything goes out' },
  { ch: 'CH3', role: 'Counsel', side: 'provider', fw: 'Pydantic AI', fn: 'fixes the codes, signatures & docs that cause denials' },
  { ch: 'CH4', role: 'Provider Appeals', side: 'provider', fw: 'Letta', fn: 'cures the cited denial reason and resubmits' },
  { ch: 'CH5', role: 'Reviewer', side: 'payer', fw: 'Pydantic AI', fn: 'checks medical-necessity policy; asks only for gaps' },
  { ch: 'CH6', role: 'Clinical Guidelines', side: 'payer', fw: 'Pydantic AI', fn: 'applies MCG/InterQual-style criteria, cites them' },
  { ch: 'CH7', role: 'Pharmacy & Formulary', side: 'payer', fw: 'LangGraph', fn: 'checks formulary tier & step-therapy for drugs' },
  { ch: 'CH8', role: 'Compliance & Audit', side: 'payer', fw: 'CrewAI', fn: 'enforces minimum-necessary PHI & specific-reason' },
  { ch: 'CH9', role: 'Member Notification', side: 'payer', fw: 'LangGraph', fn: 'drafts the determination notice & appeal rights' },
  { ch: 'CH10', role: 'Medical Director', side: 'payer', fw: 'Human-in-the-loop', fn: 'adjudicates borderline cases an algorithm should not' },
]

const LAYERS = [
  { n: 'L1', t: 'Protocol', spec: 'typed envelopes · finite-state machine', d: 'A move is legal by construction, or it never happens.' },
  { n: 'L2', t: 'Engine', spec: 'coordinator loop · provider-agnostic LLM seam', d: 'A plain loop over the Band mesh. Any model, one contract.' },
  { n: 'L3', t: 'Domain', spec: 'policy · typed denials · SLA timers', d: 'The prior-auth pack: policy is ground truth.' },
  { n: 'L4', t: 'Console', spec: 'multi-tenant control plane · audit', d: 'A per-organization audit theater — what you log into.' },
]

const TECH = ['Band agentic mesh', 'AI/ML API', 'Anthropic Claude', 'LangGraph', 'Pydantic AI', 'CrewAI', 'Letta', 'PostgreSQL']

/* ── motion: scroll-reveal ─────────────────────────────────────────────── */
function useReveal() {
  useEffect(() => {
    const els = Array.from(document.querySelectorAll<HTMLElement>('[data-reveal]'))
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { els.forEach((e) => e.classList.add('in')); return }
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target) } }),
      { threshold: 0.12, rootMargin: '0px 0px -8% 0px' },
    )
    els.forEach((e) => io.observe(e))
    return () => io.disconnect()
  }, [])
}

/* ── instrument primitives ─────────────────────────────────────────────── */


/* ── Agent theater — the hero's self-running mini-demo ─────────────────────
   Two agents work a real prior-auth case in plain language: messages pass
   between them, the active agent pulses, the step rail fills, it ends APPROVED,
   then loops. Built to be legible to anyone — "the agents do the work." */
const SCRIPT = [
  { side: 'provider', who: 'Clinic agent', text: 'Prior-auth request submitted — MRI lumbar spine.', stage: 'Submit' },
  { side: 'payer', who: 'Payer agent', text: 'Reviewing necessity — physical-therapy notes are missing.', stage: 'Review' },
  { side: 'provider', who: 'Clinic agent', text: 'Conservative-care notes attached and resubmitted.', stage: 'Respond' },
  { side: 'payer', who: 'Payer agent', text: 'Criteria met — authorization approved.', stage: 'Decide' },
] as const

const STAGES = ['Submit', 'Review', 'Respond', 'Decide']

function AgentTheater() {
  // n = how many messages are revealed (0…length). The cycle grows 1→length, holds on the
  // decision, then collapses back to 0 — every step animated, so the frame eases up and down.
  const [n, setN] = useState(1)
  useEffect(() => {
    const atEnd = n >= SCRIPT.length
    const atStart = n === 0
    const delay = atEnd ? 3200 : atStart ? 700 : 1750
    const t = setTimeout(() => setN(atEnd ? 0 : n + 1), delay)
    return () => clearTimeout(t)
  }, [n])

  const last = n >= 1 ? SCRIPT[n - 1] : null
  const decided = n >= SCRIPT.length
  const activeProvider = last?.side === 'provider'

  return (
    <Frame className="bg-paper">
      {/* chrome */}
      <div className="flex items-center justify-between border-b border-line px-4 py-2.5 font-mono text-[10px] uppercase tracking-[0.16em] text-ink-faint">
        <span>case #4821 · live</span>
        <span className="flex items-center gap-1.5"><span className="livedot h-1.5 w-1.5 rounded-full bg-coral" /> {decided ? 'settled' : 'in progress'}</span>
      </div>

      {/* the two agents + the wire between them */}
      <div className="relative px-5 pb-5 pt-6">
        {/* connector wire (absolute, at icon-centre — never affects layout flow) + packet */}
        <div className="absolute left-16 right-16 top-[2.75rem] h-px bg-line">
          {last && (
            <span key={n} className={`absolute top-1/2 h-2.5 w-2.5 -translate-y-1/2 rounded-full ${activeProvider ? 'packet-r' : 'packet-l'}`}
              style={{ background: CORAL, boxShadow: '0 0 8px ' + CORAL }} aria-hidden />
          )}
        </div>
        <div className="relative flex items-start justify-between">
          <AgentNode label="Clinic agent" role="provider side" color="pine" active={activeProvider && !decided} />
          <AgentNode label="Payer agent" role="payer side" color="ink" active={last !== null && !activeProvider && !decided} right />
        </div>
      </div>

      {/* plain-language transcript — each row eases its own height open, so the frame grows smoothly */}
      <div className="border-t border-line px-5 py-3">
        {SCRIPT.map((m, i) => {
          const provider = m.side === 'provider'
          return (
            <RevealRow key={i} open={i < n}>
              <div className={`flex pt-2 ${provider ? 'justify-start' : 'justify-end'}`}>
                <div className={`max-w-[84%] rounded-lg border px-3 py-2 ${provider ? 'border-pine/25 bg-pine/[0.05]' : 'border-ink/15 bg-sunk/70'}`}>
                  <div className="flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.12em] text-ink-faint">
                    <span className={`h-1.5 w-1.5 rounded-full ${provider ? 'bg-pine' : 'bg-ink'}`} />{m.who}
                  </div>
                  <p className="mt-1 break-words text-[13px] leading-snug text-ink">{m.text}</p>
                </div>
              </div>
            </RevealRow>
          )
        })}
      </div>

      {/* step rail + decision */}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-2 border-t border-line px-5 py-3">
        {STAGES.map((s, i) => {
          const reached = i < n
          return (
            <div key={s} className="flex items-center gap-2">
              <span className={`flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.1em] transition-colors duration-300 ${reached ? 'text-pine' : 'text-ink-faint'}`}>
                <span className={`flex h-3.5 w-3.5 items-center justify-center rounded-full text-[8px] transition-colors duration-300 ${reached ? 'bg-pine text-bone' : 'border border-line'}`}>{reached ? '✓' : ''}</span>
                {s}
              </span>
              {i < STAGES.length - 1 && <span className="h-px w-3 bg-line" />}
            </div>
          )
        })}
        {decided && (
          <span className="stamp-in ml-auto rounded-md border-2 border-pine px-2.5 py-1 font-mono text-[11px] font-bold uppercase tracking-[0.14em] text-pine">
            Approved
          </span>
        )}
      </div>
    </Frame>
  )
}

/** A transcript row that eases its own height (and opacity) open/closed — drives the smooth
 *  growth of the whole frame as messages arrive (grid-template-rows 0fr↔1fr). */
function RevealRow({ open, children }: { open: boolean; children: ReactNode }) {
  return (
    // grid-cols-[100%] pins the (otherwise content-sized) implicit column to the container width,
    // so a long message wraps instead of widening the page on narrow screens.
    <div className="grid grid-cols-[100%] transition-[grid-template-rows] duration-[520ms] ease-[cubic-bezier(.2,.7,.2,1)]"
      style={{ gridTemplateRows: open ? '1fr' : '0fr' }}>
      <div className={`min-w-0 overflow-hidden transition-opacity duration-[520ms] ${open ? 'opacity-100' : 'opacity-0'}`}>
        {children}
      </div>
    </div>
  )
}

function AgentNode({ label, role, color, active, right }: {
  label: string; role: string; color: 'pine' | 'ink'; active?: boolean; right?: boolean
}) {
  const c = color === 'pine' ? 'var(--color-pine)' : 'var(--color-ink)'
  return (
    <div className={`flex flex-col gap-1.5 ${right ? 'items-end text-right' : 'items-start'}`}>
      <div className="relative">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl text-bone" style={{ background: c }}>
          <AgentGlyph />
        </span>
        {active && <span className="node-ring absolute inset-0 rounded-xl" style={{ boxShadow: `0 0 0 2px ${c}` }} aria-hidden />}
      </div>
      <div>
        <div className="font-display text-[13px] font-semibold leading-tight">{label}</div>
        <div className="font-mono text-[9px] uppercase tracking-[0.12em] text-ink-faint">{active ? 'working…' : role}</div>
      </div>
    </div>
  )
}

function AgentGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect x="5" y="7" width="14" height="11" rx="2.5" stroke="currentColor" strokeWidth="1.7" />
      <path d="M12 4v3M9 12h0M15 12h0" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

/* ── Privacy theater (§04) — same negotiation, two audit views, side by side ──
   Both panels reveal the SAME shared messages in lockstep; the one private thought
   shows in full on the clinic's panel and as a sealed placeholder on the payer's.
   Same agent-transcript language as the hero. */
const PRIVACY_SCRIPT = [
  { kind: 'room', side: 'provider', who: 'Clinic agent', text: 'Prior-auth request submitted — MRI lumbar spine.' },
  { kind: 'private', side: 'provider', who: 'Clinic agent', text: 'Lead with the failed conservative-care notes; hold the cost argument in reserve.' },
  { kind: 'room', side: 'payer', who: 'Payer agent', text: 'Reviewing necessity — physical-therapy notes are missing.' },
  { kind: 'room', side: 'provider', who: 'Clinic agent', text: 'Conservative-care notes attached and resubmitted.' },
  { kind: 'room', side: 'payer', who: 'Payer agent', text: 'Criteria met — authorization approved.' },
] as const

function PrivacyTheater() {
  const [n, setN] = useState(1)
  useEffect(() => {
    const atEnd = n >= PRIVACY_SCRIPT.length
    const atStart = n === 0
    const delay = atEnd ? 3400 : atStart ? 700 : 1650
    const t = setTimeout(() => setN(atEnd ? 0 : n + 1), delay)
    return () => clearTimeout(t)
  }, [n])
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div data-reveal><PrivacyPanel n={n} viewer="clinic" /></div>
      <div data-reveal style={{ transitionDelay: '90ms' }}><PrivacyPanel n={n} viewer="payer" /></div>
    </div>
  )
}

function PrivacyPanel({ n, viewer }: { n: number; viewer: 'clinic' | 'payer' }) {
  const clinic = viewer === 'clinic'
  return (
    <Frame className="bg-paper">
      <div className="flex items-center justify-between border-b border-line px-4 py-2.5 font-mono text-[10px] uppercase tracking-[0.16em]">
        <span className="flex items-center gap-2 text-ink-soft">
          <span className={`h-2 w-2 rounded-full ${clinic ? 'bg-pine' : 'bg-ink'}`} /> as the {viewer} sees it
        </span>
        <span className="text-ink-faint">audit · #4821</span>
      </div>
      <div className="px-4 py-3">
        {PRIVACY_SCRIPT.map((m, i) => {
          const provider = m.side === 'provider'
          const open = i < n
          if (m.kind === 'private') {
            const owned = provider === clinic // the clinic owns the provider-side private thought
            return (
              <RevealRow key={i} open={open}>
                <div className="flex justify-start pt-2">
                  {owned ? <PrivateBubble text={m.text} /> : <SealedBubble />}
                </div>
              </RevealRow>
            )
          }
          return (
            <RevealRow key={i} open={open}>
              <div className={`flex pt-2 ${provider ? 'justify-start' : 'justify-end'}`}>
                <div className={`max-w-[86%] rounded-lg border px-3 py-2 ${provider ? 'border-pine/25 bg-pine/[0.05]' : 'border-ink/15 bg-sunk/70'}`}>
                  <div className="flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.12em] text-ink-faint">
                    <span className={`h-1.5 w-1.5 rounded-full ${provider ? 'bg-pine' : 'bg-ink'}`} />{m.who}
                  </div>
                  <p className="mt-1 break-words text-[13px] leading-snug text-ink">{m.text}</p>
                </div>
              </div>
            </RevealRow>
          )
        })}
      </div>
    </Frame>
  )
}

function PrivateBubble({ text }: { text: string }) {
  return (
    <div className="max-w-[86%] rounded-lg border border-coral/40 bg-coral/[0.06] px-3 py-2">
      <div className="flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.12em] text-coral"><MiniLock /> private · only the clinic sees this</div>
      <p className="mt-1 break-words text-[13px] italic leading-snug text-ink-soft">{text}</p>
    </div>
  )
}

function SealedBubble() {
  return (
    <div className="max-w-[86%] rounded-lg border border-dashed border-line bg-sunk/50 px-3 py-2">
      <div className="flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.12em] text-ink-faint"><MiniLock /> private reasoning · sealed to the clinic</div>
      <div className="mt-2 flex gap-1 opacity-60" aria-hidden>
        {[46, 70, 32, 58].map((w, i) => <span key={i} style={{ width: w }} className="h-2 rounded-full bg-ink-faint/30" />)}
      </div>
    </div>
  )
}

function MiniLock() {
  return (
    <svg viewBox="0 0 24 24" width="11" height="11" fill="none" aria-hidden>
      <rect x="5" y="11" width="14" height="9" rx="2" fill="currentColor" opacity="0.18" />
      <rect x="5" y="11" width="14" height="9" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M8 11V8a4 4 0 1 1 8 0v3" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  )
}

/** Instrument frame: a hairline box with corner registration ticks. */
function Frame({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`relative border border-ink/15 ${className}`}>
      <Tick className="left-0 top-0 -translate-x-1/2 -translate-y-1/2" />
      <Tick className="right-0 top-0 translate-x-1/2 -translate-y-1/2" />
      <Tick className="bottom-0 left-0 -translate-x-1/2 translate-y-1/2" />
      <Tick className="bottom-0 right-0 translate-x-1/2 translate-y-1/2" />
      {children}
    </div>
  )
}
function Tick({ className = '' }: { className?: string }) {
  return (
    <span className={`pointer-events-none absolute z-10 text-ink-faint ${className}`} aria-hidden>
      <svg width="9" height="9" viewBox="0 0 9 9"><path d="M4.5 0v9M0 4.5h9" stroke="currentColor" strokeWidth="1" /></svg>
    </span>
  )
}

/** Section index marker — "§0X / FIG.0X" instrument label. */
function Index({ n, label }: { n: string; label: string }) {
  return (
    <div data-reveal className="flex items-center gap-3 font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint">
      <span className="text-pine">{n}</span>
      <span className="h-px w-8 bg-line" />
      <span>{label}</span>
    </div>
  )
}

/* ── page ──────────────────────────────────────────────────────────────── */
export default function Landing() {
  useReveal()
  const { user, loading } = useAuth()
  return (
    <div className="min-h-full">
      {/* instrument header */}
      <nav className="sticky top-0 z-30 border-b border-ink/12 bg-bone/85 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-6 py-3.5">
          <Wordmark height={20} />
          <span className="hidden font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint sm:inline">prior-authorization instrument</span>
          <div className="ml-auto flex items-center gap-5 font-mono text-[11px] uppercase tracking-[0.12em] text-ink-soft">
            <a href="#how" className="hidden transition-colors hover:text-pine md:inline">Signal path</a>
            <a href="#agents" className="hidden transition-colors hover:text-pine md:inline">Channels</a>
            <a href="#security" className="hidden transition-colors hover:text-pine md:inline">Privacy</a>
            <a href={GITHUB} target="_blank" rel="noreferrer" className="hidden transition-colors hover:text-pine sm:inline">Source</a>
            {!loading && (user
              ? <a href="#/app" className="font-semibold text-pine transition-colors hover:text-pine-deep">Console →</a>
              : <a href="#/login" className="transition-colors hover:text-pine">Sign in</a>)}
            <a href="#/live" className="flex items-center gap-1.5 rounded-sm bg-ink px-3 py-1.5 text-bone transition-colors hover:bg-pine">
              <span className="livedot h-1.5 w-1.5 rounded-full bg-coral" /> Live
            </a>
          </div>
        </div>
      </nav>

      {/* hero */}
      <header className="border-b border-ink/12">
        <div className="mx-auto grid max-w-6xl items-stretch gap-0 lg:grid-cols-12">
          {/* left: editorial headline */}
          <div className="border-line px-6 py-14 lg:col-span-7 lg:border-r lg:py-20 lg:pr-12">
            <div data-reveal className="mb-7 flex items-center gap-3 font-mono text-[11px] uppercase tracking-[0.2em] text-ink-faint">
              <span className="text-pine">§00</span><span className="h-px w-8 bg-line" /><span>prior authorization · automated</span>
            </div>
            <h1 data-reveal style={{ transitionDelay: '60ms' }} className="font-display text-[2.7rem] font-medium leading-[0.97] tracking-[-0.025em] text-ink sm:text-6xl lg:text-[4.4rem]">
              Prior authorization,<br />
              <span className="relative inline-block tracking-[0.06em] text-pine">
                t&#8202;u&#8202;n&#8202;e&#8202;d
                <span className="rule-draw absolute -bottom-1 left-0 h-[3px] w-full" style={{ background: CORAL }} />
              </span>{' '}
              <span className="tracking-[-0.025em]">to a decision.</span>
            </h1>
            <p data-reveal style={{ transitionDelay: '120ms' }} className="mt-8 max-w-xl text-lg leading-relaxed text-ink-soft">
              Syntony puts an AI agent on the <span className="text-ink">provider's side</span> and the{' '}
              <span className="text-ink">payer's side</span>. They exchange the request, fix the errors that cause
              denials, and reach a decision — a human on the edge cases, every move on the record.
            </p>
            <div data-reveal style={{ transitionDelay: '180ms' }} className="mt-9 flex flex-wrap items-center gap-3">
              <a href="#/live" className="rounded-sm bg-pine px-5 py-3 font-medium text-bone transition-colors hover:bg-pine-deep">Watch it live →</a>
              <a href={GITHUB} target="_blank" rel="noreferrer" className="rounded-sm border border-ink/25 px-5 py-3 font-medium text-ink transition-colors hover:border-ink/60">View source</a>
              <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-faint">two agents · one frequency</span>
            </div>
          </div>

          {/* right: the scope */}
          <div data-reveal style={{ transitionDelay: '140ms' }} className="flex flex-col justify-center bg-sunk/40 px-6 py-12 lg:col-span-5 lg:px-10">
            <AgentTheater />
            <p className="mt-3 text-center font-mono text-[10px] uppercase tracking-[0.16em] text-ink-faint">
              the agents work the case — you watch it settle
            </p>
          </div>
        </div>
      </header>

      {/* readout strip */}
      <section className="border-b border-ink/12 bg-paper">
        <div className="mx-auto max-w-6xl px-6">
          <div className="flex items-center gap-2 border-b border-line py-2 font-mono text-[9px] uppercase tracking-[0.18em] text-ink-faint">
            <span className="h-2 w-px bg-line" /><span>readout</span><span className="ml-auto">measured · cited</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4">
            {READOUT.map((r, i) => (
              <div key={r.l} data-reveal style={{ transitionDelay: `${i * 70}ms` }}
                className={`px-2 py-7 ${i % 2 ? '' : 'border-r border-line'} ${i < 2 ? 'border-b border-line md:border-b-0' : ''} ${i === 2 ? 'md:border-r' : ''} md:px-4`}>
                <div className="font-mono text-[2.6rem] font-medium leading-none tabular-nums tracking-tight text-ink">
                  {r.v}<span className="ml-1 text-base text-ink-faint">{r.u}</span>
                </div>
                <div className="mt-3 text-[13px] leading-snug text-ink-soft">{r.l}</div>
                <div className="mt-1.5 font-mono text-[9px] uppercase tracking-[0.14em] text-ink-faint">— {r.src}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* §01 — diagnostic (the problem) */}
      <section className="mx-auto max-w-6xl px-6 py-20 lg:py-28">
        <Index n="§01" label="diagnostic" />
        <h2 data-reveal className="mt-5 max-w-3xl font-display text-3xl font-medium leading-tight tracking-tight sm:text-[2.6rem]">
          Today, prior auth runs on fax machines and hold music.
        </h2>
        <p data-reveal className="mt-4 max-w-xl text-ink-soft">A request goes out, disappears into a queue, and returns days later — often denied for a missing form. The signal is there; the instrument is missing.</p>

        <div className="mt-12 border-t-2 border-ink/80">
          {DIAGNOSTIC.map((d, i) => (
            <div key={d.l} data-reveal style={{ transitionDelay: `${i * 60}ms` }}
              className="group grid grid-cols-[auto_1fr] items-baseline gap-x-6 gap-y-1 border-b border-line py-5 transition-colors hover:bg-sunk/40 sm:grid-cols-[7rem_1fr_8rem]">
              <div className="font-mono text-3xl font-medium tabular-nums tracking-tight" style={{ color: CORAL }}>{d.v}</div>
              <div className="text-[15px] leading-relaxed text-ink sm:self-center">{d.l}</div>
              <div className="col-start-2 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-faint sm:col-start-3 sm:text-right sm:self-center">{d.src}</div>
            </div>
          ))}
        </div>
      </section>

      {/* §02 — signal path (how it flows) */}
      <section id="how" className="border-y border-ink/12 bg-sunk">
        <div className="mx-auto max-w-6xl px-6 py-20 lg:py-28">
          <Index n="§02" label="signal path" />
          <h2 data-reveal className="mt-5 max-w-2xl font-display text-3xl font-medium tracking-tight sm:text-[2.6rem]">From the order to a decision — in one pass.</h2>

          {/* the path: stations along a baseline */}
          <div className="relative mt-16">
            <div className="absolute left-0 right-0 top-[7px] hidden h-px lg:block flowline" aria-hidden />
            <div className="grid gap-y-10 lg:grid-cols-4 lg:gap-x-8">
              {PATH.map((s, i) => (
                <div key={s.n} data-reveal style={{ transitionDelay: `${i * 80}ms` }} className="relative lg:pr-4">
                  <span className="absolute left-0 top-0 hidden h-3.5 w-3.5 rounded-full border-2 border-pine bg-bone lg:block" />
                  <div className="flex items-baseline gap-3 lg:mt-7">
                    <span className="font-mono text-[13px] text-pine">{s.n}</span>
                    <h3 className="font-display text-lg font-semibold tracking-tight">{s.t}</h3>
                  </div>
                  <p className="mt-2 text-[14px] leading-relaxed text-ink-soft">{s.d}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* §03 — channels (the cast) */}
      <section id="agents" className="mx-auto max-w-6xl px-6 py-20 lg:py-28">
        <Index n="§03" label="channels" />
        <h2 data-reveal className="mt-5 max-w-2xl font-display text-3xl font-medium tracking-tight sm:text-[2.6rem]">Ten specialist agents. Two organizations. One protocol.</h2>
        <p data-reveal className="mt-4 max-w-xl text-ink-soft">Each channel runs the framework that fits its job — heterogeneous by design, interoperable by contract. The mesh doesn't care who built whom.</p>

        <div data-reveal className="mt-12">
          {/* header row */}
          <div className="grid grid-cols-[3.2rem_1fr_auto] items-center gap-x-4 border-y-2 border-ink/80 py-2 font-mono text-[10px] uppercase tracking-[0.16em] text-ink-faint sm:grid-cols-[3.2rem_10rem_1fr_10rem]">
            <span>ch</span><span>role</span><span className="hidden sm:block">function</span><span className="text-right">framework</span>
          </div>
          {AGENTS.map((a, i) => {
            const provider = a.side === 'provider'
            return (
              <div key={a.role} data-reveal style={{ transitionDelay: `${i * 50}ms` }}
                className="group grid grid-cols-[3.2rem_1fr_auto] items-center gap-x-4 gap-y-1 border-b border-line py-4 transition-colors hover:bg-sunk/50 sm:grid-cols-[3.2rem_10rem_1fr_10rem]">
                <span className="flex items-center gap-2 font-mono text-[12px] text-ink-faint">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: provider ? 'var(--color-pine)' : 'var(--color-ink)' }} />{a.ch}
                </span>
                <span className="font-display text-[16px] font-semibold tracking-tight">{a.role}</span>
                <span className="col-span-3 row-start-2 text-[13.5px] leading-snug text-ink-soft sm:col-span-1 sm:col-start-3 sm:row-start-1">{a.fn}</span>
                <span className="col-start-3 row-start-1 text-right font-mono text-[10px] uppercase tracking-[0.1em] text-pine sm:col-start-4">{a.fw}</span>
              </div>
            )
          })}
          <div className="flex items-center justify-between py-3 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-faint">
            <span className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-pine" /> provider side</span>
            <span>one provider-agnostic seam routes every model</span>
            <span className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-ink" /> payer side</span>
          </div>
        </div>
      </section>

      {/* §04 — privacy (dual trace) */}
      <section id="security" className="border-y border-ink/12 bg-sunk">
        <div className="mx-auto max-w-6xl px-6 py-20 lg:py-28">
          <Index n="§04" label="privacy · dual trace" />
          <h2 data-reveal className="mt-5 max-w-2xl font-display text-3xl font-medium tracking-tight sm:text-[2.6rem]">One shared record. Two private channels.</h2>
          <p data-reveal className="mt-4 max-w-xl text-ink-soft">Both organizations see every message and decision. But each side's internal reasoning stays on its own channel — enforced by the mesh, not a policy promise. Same case, two readouts:</p>

          <div className="mt-12"><PrivacyTheater /></div>
          <p className="mt-4 text-center font-mono text-[10px] uppercase tracking-[0.16em] text-ink-faint">
            same messages on both sides — only the <span style={{ color: CORAL }}>private thought</span> differs
          </p>

          <div className="mt-10 grid gap-x-10 gap-y-5 border-t border-line pt-8 sm:grid-cols-3">
            {[
              ['Caught before submission', 'A coding agent fixes missing codes, unsigned orders and absent documents — before the request reaches the payer.'],
              ['A negotiation, not a queue', "The reviewer asks only for what's missing; your side answers automatically. Borderline cases go to a human."],
              ['Audited for compliance', 'Every envelope is appended to a per-org trail with the CMS-0057-F specific reason and SLA clock.'],
            ].map(([t, d], i) => (
              <div key={t} data-reveal style={{ transitionDelay: `${i * 70}ms` }}>
                <h3 className="font-display text-[15px] font-semibold tracking-tight">{t}</h3>
                <p className="mt-2 text-[13.5px] leading-relaxed text-ink-soft">{d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* §05 — recovered revenue (overturn) */}
      <section className="mx-auto max-w-6xl px-6 py-20 lg:py-28">
        <Index n="§05" label="recovered revenue" />
        <div className="mt-6 grid items-center gap-12 lg:grid-cols-12">
          <div data-reveal className="lg:col-span-6">
            <h2 className="font-display text-3xl font-medium tracking-tight sm:text-[2.6rem]">A denial isn't the end of the signal.</h2>
            <p className="mt-4 max-w-lg text-ink-soft">
              When a denial cites a specific, curable reason, the Provider Appeals agent supplies what's missing and
              resubmits automatically. The deny → appeal → <span className="font-semibold text-pine">overturn</span> loop
              turns abandoned claims back into paid care.
            </p>
            <a href="#/live" className="mt-7 inline-block rounded-sm bg-pine px-5 py-3 font-medium text-bone transition-colors hover:bg-pine-deep">See an overturn live →</a>
          </div>
          <div data-reveal style={{ transitionDelay: '90ms' }} className="lg:col-span-6">
            <Frame className="bg-paper">
              <div className="grid grid-cols-2">
                <div className="border-r border-line px-6 py-8">
                  <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-faint">overturned</div>
                  <div className="mt-2 font-mono text-[3.4rem] font-medium leading-none tabular-nums text-pine">80.7<span className="text-2xl">%</span></div>
                  <div className="mt-2 text-[12px] text-ink-soft">of appealed MA denials</div>
                </div>
                <div className="px-6 py-8">
                  <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-faint">appealed</div>
                  <div className="mt-2 font-mono text-[3.4rem] font-medium leading-none tabular-nums" style={{ color: CORAL }}>11.5<span className="text-2xl">%</span></div>
                  <div className="mt-2 text-[12px] text-ink-soft">ever, today</div>
                </div>
              </div>
              <div className="border-t border-line px-6 py-2.5 text-center font-mono text-[9px] uppercase tracking-[0.16em] text-ink-faint">KFF · Medicare Advantage · 2024</div>
            </Frame>
          </div>
        </div>
      </section>

      {/* §06 — architecture rack */}
      <section className="border-y border-ink/12 bg-sunk">
        <div className="mx-auto max-w-6xl px-6 py-20 lg:py-28">
          <Index n="§06" label="how it's built" />
          <h2 data-reveal className="mt-5 max-w-2xl font-display text-3xl font-medium tracking-tight sm:text-[2.6rem]">Four layers, bottom-up. The intelligence stays simple.</h2>
          <p data-reveal className="mt-4 max-w-xl text-ink-soft">A protocol you can audit, an engine that's a plain loop, a domain pack that owns the rules, and a console you can log into. No black-box orchestrator.</p>

          <div data-reveal className="mt-12 border border-ink/15 bg-paper">
            {LAYERS.map((l, i) => (
              <div key={l.n} className={`group grid grid-cols-[3.5rem_1fr] items-center gap-x-5 px-5 py-5 transition-colors hover:bg-sunk/50 sm:grid-cols-[4rem_9rem_1fr_auto] ${i ? 'border-t border-line' : ''}`}>
                <span className="rounded-sm bg-ink px-2 py-1 text-center font-mono text-[12px] font-semibold text-bone">{l.n}</span>
                <h3 className="font-display text-lg font-semibold tracking-tight">{l.t}</h3>
                <p className="col-span-2 row-start-2 text-[13.5px] text-ink-soft sm:col-span-1 sm:col-start-3 sm:row-start-1">{l.d}</p>
                <span className="col-start-2 row-start-2 font-mono text-[10px] uppercase tracking-[0.1em] text-pine sm:col-start-4 sm:row-start-1 sm:text-right">{l.spec}</span>
              </div>
            ))}
          </div>
          <p className="mt-6 flex flex-wrap items-center justify-center gap-x-3 gap-y-1 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-faint">
            built on the <span className="text-ink">Band</span> agentic mesh · 10 specialist agents · 2 real organizations
          </p>
        </div>
      </section>

      {/* CTA */}
      <section className="mx-auto max-w-6xl px-6 py-24 text-center" data-reveal>
        <h2 className="mx-auto max-w-2xl font-display text-3xl font-medium tracking-tight sm:text-[2.6rem]">Watch a prior-auth case settle, live.</h2>
        <p className="mx-auto mt-4 max-w-lg text-ink-soft">Open the demo, or sign in and run a case yourself — a real cross-org negotiation streams into your audit trail, turn by turn.</p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <a href="#/live" className="rounded-sm bg-pine px-6 py-3 font-medium text-bone transition-colors hover:bg-pine-deep">Open the live demo →</a>
          <a href="#/login" className="rounded-sm border border-ink/25 px-6 py-3 font-medium text-ink transition-colors hover:border-ink/60">Sign in to the console</a>
        </div>
      </section>

      {/* tech */}
      <section className="mx-auto max-w-6xl px-6 pb-20 text-center">
        <div className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-faint">Instrumented with</div>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
          {TECH.map((t) => (
            <span key={t} className="rounded-sm border border-line bg-paper px-3 py-1.5 font-mono text-[12px] text-ink-soft transition-colors hover:border-pine/50 hover:text-ink">{t}</span>
          ))}
        </div>
      </section>

      {/* instrument footer */}
      <footer className="border-t border-ink/12 bg-paper">
        <div className="scope-grid h-px w-full opacity-40" aria-hidden />
        <div className="mx-auto grid max-w-6xl gap-8 px-6 py-12 sm:grid-cols-[1.5fr_1fr_1fr]">
          <div>
            <Wordmark height={20} />
            <p className="mt-4 max-w-xs text-[13px] leading-relaxed text-ink-soft">Cross-organization prior authorization between providers and payers — agents tuning to the same frequency.</p>
          </div>
          <FooterCol title="Product" links={[['Live demo', '#/live'], ['Sign in', '#/login'], ['Signal path', '#how'], ['Channels', '#agents']]} />
          <FooterCol title="Project" links={[['GitHub', GITHUB], ['Privacy model', '#security'], ['Architecture', '#']]} external={[GITHUB]} />
        </div>
        <div className="border-t border-line">
          <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-2 px-6 py-5 font-mono text-[11px] uppercase tracking-[0.12em] text-ink-faint sm:flex-row">
            <span>© 2026 Syntony · MIT licensed</span>
            <span className="flex items-center gap-1.5"><span className="livedot h-1.5 w-1.5 rounded-full bg-coral" /> built for the Band of Agents hackathon</span>
          </div>
        </div>
      </footer>
    </div>
  )
}

function FooterCol({ title, links, external = [] }: { title: string; links: [string, string][]; external?: string[] }) {
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-faint">{title}</div>
      <ul className="mt-4 space-y-2.5">
        {links.map(([label, href]) => (
          <li key={label}>
            <a href={href} {...(external.includes(href) ? { target: '_blank', rel: 'noreferrer' } : {})}
              className="text-[13px] text-ink-soft transition-colors hover:text-pine">{label}</a>
          </li>
        ))}
      </ul>
    </div>
  )
}
