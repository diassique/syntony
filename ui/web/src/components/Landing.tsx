import { useEffect, type ReactNode } from 'react'
import { Logo } from './Logo'

const GITHUB = 'https://github.com/diassique/syntony'

const STATS = [
  { v: '13 hrs', u: '/wk', l: 'physician time lost to prior auth — AMA' },
  { v: '≈4', u: 'min', l: 'a negotiated case on Syntony' },
  { v: '$15', u: 'B', l: '10-yr savings projected by CMS' },
  { v: '72h', u: '/7d', l: 'CMS-0057-F response mandate, 2026' },
]

const STEPS = [
  { n: '01', t: 'Intake frames the case', d: 'A clinic agent assembles a structured, FHIR-shaped request from the chart — no raw PHI leaves the room.' },
  { n: '02', t: 'Counsel catches mistakes', d: 'A coding agent validates codes, signatures and documents, fixing the mismatches that cause most denials — before submission.' },
  { n: '03', t: 'Payer reviews necessity', d: 'A payer agent, in a different organization, checks medical-necessity policy and asks only for what is missing.' },
  { n: '04', t: 'Human on the edge cases', d: 'Borderline cases escalate to a human Medical Director, added to the room in one step. Every move is audited.' },
]

const MOAT = [
  { t: 'Cross-org consent', d: 'Two independent organizations connect through a bilateral, approved contact — not a shared login or a brittle point-to-point integration.' },
  { t: 'Mention-scoped privacy', d: "Each side keeps its internal strategy on a private event channel the counterparty never sees — even inside the shared room." },
  { t: 'Unified audit trail', d: 'Every message, tool call and decision is recorded as a typed, replayable event stream — for both parties, by construction.' },
]

const TECH = ['Band agentic mesh', 'AI/ML API', 'Anthropic Claude', 'LangGraph', 'Pydantic AI', 'Letta', 'Featherless', 'PostgreSQL']

/** Reveal [data-reveal] elements as they scroll into view (no-op under reduced motion). */
function useReveal() {
  useEffect(() => {
    const els = Array.from(document.querySelectorAll<HTMLElement>('[data-reveal]'))
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      els.forEach((e) => e.classList.add('in'))
      return
    }
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target) } }),
      { threshold: 0.12, rootMargin: '0px 0px -8% 0px' },
    )
    els.forEach((e) => io.observe(e))
    return () => io.disconnect()
  }, [])
}

function Kicker({ children }: { children: ReactNode }) {
  return <div className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-faint">{children}</div>
}

function HeroDiagram() {
  const ledger = [
    { n: '00', who: 'intake', k: 'CASE_OPEN' },
    { n: '01', who: 'counsel', k: 'PROPOSAL', to: '→ payer' },
    { n: '02', who: 'reviewer', k: 'ESCALATION', warn: true },
    { n: '03', who: 'medical director', k: 'DECISION', ok: true },
  ]
  return (
    <div data-reveal style={{ transitionDelay: '120ms' }}>
      <div className="rounded-2xl border border-line bg-paper p-6 shadow-[0_1px_0_rgba(14,19,17,0.03),0_30px_60px_-40px_rgba(14,19,17,0.35)]">
        <div className="mb-6 flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.16em] text-ink-faint">
          <span>shared band room</span>
          <span className="flex items-center gap-1.5"><span className="livedot h-1.5 w-1.5 rounded-full bg-coral" /> live</span>
        </div>

        {/* clinic ── resonance ── payer */}
        <div className="flex items-center justify-between">
          <div className="flex flex-col items-center gap-2">
            <span className="h-3 w-3 rounded-full bg-pine" />
            <div className="text-center"><div className="text-sm font-semibold">Clinic</div><div className="font-mono text-[10px] uppercase tracking-wider text-ink-faint">provider</div></div>
          </div>

          <div className="relative mx-4 h-px flex-1 bg-line">
            <span className="ring absolute left-1/2 top-1/2 h-9 w-9 -translate-x-1/2 -translate-y-1/2 rounded-full border border-pine/40" />
            <span className="ring absolute left-1/2 top-1/2 h-9 w-9 -translate-x-1/2 -translate-y-1/2 rounded-full border border-pine/40" style={{ animationDelay: '1.1s' }} />
            <span className="packet absolute top-1/2 h-2 w-2 -translate-y-1/2 rounded-full bg-coral" />
            <span className="absolute left-1/2 top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-ink" />
          </div>

          <div className="flex flex-col items-center gap-2">
            <span className="h-3 w-3 rounded-full border-2 border-ink bg-paper" />
            <div className="text-center"><div className="text-sm font-semibold">Payer</div><div className="font-mono text-[10px] uppercase tracking-wider text-ink-faint">reviewer</div></div>
          </div>
        </div>

        {/* live audit ledger */}
        <div className="mt-6 border-t border-line pt-4 font-mono text-[11px] leading-relaxed">
          {ledger.map((r) => (
            <div key={r.n} className="flex items-center gap-3 py-0.5">
              <span className="text-ink-faint">{r.n}</span>
              <span className="text-ink-soft">{r.who}</span>
              <span className={`ml-auto ${r.warn ? 'text-coral' : r.ok ? 'text-pine' : 'text-ink'}`}>
                {r.k}{r.to ? <span className="text-ink-faint"> {r.to}</span> : null}
              </span>
            </div>
          ))}
        </div>
      </div>
      <p className="mt-3 text-center font-mono text-[10px] uppercase tracking-[0.16em] text-ink-faint">
        a private <span className="text-coral">thought</span> stays with its sender — the audit channel
      </p>
    </div>
  )
}

export default function Landing() {
  useReveal()
  return (
    <div className="min-h-full">
      {/* nav */}
      <nav className="sticky top-0 z-20 border-b border-line/70 bg-bone/85 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-6 py-4">
          <Logo size={24} className="text-ink" />
          <span className="font-display text-[17px] font-semibold tracking-tight">Syntony</span>
          <div className="ml-auto flex items-center gap-6 font-mono text-[11px] uppercase tracking-[0.12em] text-ink-soft">
            <a href="#how" className="hidden transition-colors hover:text-ink sm:inline">How it works</a>
            <a href={GITHUB} target="_blank" rel="noreferrer" className="hidden transition-colors hover:text-ink sm:inline">GitHub</a>
            <a href="#/live" className="rounded-md bg-pine px-3.5 py-2 text-bone transition-colors hover:bg-pine-deep">Live demo →</a>
          </div>
        </div>
      </nav>

      {/* hero */}
      <header className="mx-auto grid max-w-6xl items-center gap-12 px-6 pb-24 pt-16 lg:grid-cols-12 lg:gap-10 lg:pt-24">
        <div className="lg:col-span-7">
          <div data-reveal className="mb-6 flex items-center gap-2">
            <span className="livedot h-1.5 w-1.5 rounded-full bg-coral" />
            <Kicker>Cross-org agent coordination · Regulated</Kicker>
          </div>
          <h1 data-reveal style={{ transitionDelay: '60ms' }} className="font-display text-5xl font-medium leading-[0.98] tracking-[-0.02em] text-ink sm:text-6xl lg:text-[4.5rem]">
            Prior authorization,<br />settled in{' '}
            <span className="relative whitespace-nowrap text-pine">
              minutes
              <span className="rule-draw absolute -bottom-1.5 left-0 h-[4px] w-full bg-coral" />
            </span>.
          </h1>
          <p data-reveal style={{ transitionDelay: '120ms' }} className="mt-8 max-w-xl text-lg leading-relaxed text-ink-soft">
            Syntony is a coordination protocol for AI agents that work <span className="text-ink">across organizations</span>.
            A clinic and a payer settle one case in a shared room — without passing raw PHI, with a human on the
            edge cases, and a full audit trail.
          </p>
          <div data-reveal style={{ transitionDelay: '180ms' }} className="mt-9 flex flex-wrap items-center gap-3">
            <a href="#/live" className="rounded-lg bg-pine px-5 py-3 font-medium text-bone transition-colors hover:bg-pine-deep">Watch it live →</a>
            <a href={GITHUB} target="_blank" rel="noreferrer" className="rounded-lg border border-ink/20 px-5 py-3 font-medium text-ink transition-colors hover:border-ink/50">View source</a>
          </div>
        </div>
        <div className="lg:col-span-5">
          <HeroDiagram />
        </div>
      </header>

      {/* stats */}
      <section className="border-y border-line bg-paper">
        <div className="mx-auto grid max-w-6xl grid-cols-2 md:grid-cols-4">
          {STATS.map((s, i) => (
            <div key={s.l} data-reveal style={{ transitionDelay: `${i * 70}ms` }}
              className={`px-6 py-9 ${i % 2 ? '' : 'border-r border-line'} ${i < 2 ? 'border-b border-line md:border-b-0' : ''} ${i === 2 ? 'md:border-r' : ''}`}>
              <div className="font-mono text-4xl font-medium tabular-nums tracking-tight text-ink">
                {s.v}<span className="text-ink-faint">{s.u}</span>
              </div>
              <div className="mt-2 text-[13px] leading-snug text-ink-soft">{s.l}</div>
            </div>
          ))}
        </div>
      </section>

      {/* how it works */}
      <section id="how" className="mx-auto max-w-6xl px-6 py-24">
        <div data-reveal>
          <Kicker>§ 01 — How a case flows</Kicker>
          <h2 className="mt-4 max-w-2xl font-display text-3xl font-medium tracking-tight sm:text-4xl">
            Heterogeneous agents, two organizations, one negotiated outcome.
          </h2>
        </div>
        <div className="mt-14 grid gap-px border-t border-line sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((s, i) => (
            <div key={s.n} data-reveal style={{ transitionDelay: `${i * 70}ms` }}
              className="group relative border-t-2 border-transparent pt-6 transition-colors hover:border-pine lg:pr-6">
              <div className="font-mono text-[13px] text-ink-faint">{s.n}</div>
              <h3 className="mt-3 font-display text-lg font-semibold tracking-tight">{s.t}</h3>
              <p className="mt-2 text-[14px] leading-relaxed text-ink-soft">{s.d}</p>
            </div>
          ))}
        </div>
      </section>

      {/* moat */}
      <section className="border-y border-line bg-sunk">
        <div className="mx-auto max-w-6xl px-6 py-24">
          <div data-reveal>
            <Kicker>§ 02 — Why it needs a mesh</Kicker>
            <h2 className="mt-4 max-w-2xl font-display text-3xl font-medium tracking-tight sm:text-4xl">
              Remove the mesh and the whole thing collapses.
            </h2>
            <p className="mt-3 max-w-xl text-ink-soft">Consent, privacy and audit aren't features bolted on — they're the reason this can't be a single linear pipeline.</p>
          </div>
          <div className="mt-12 grid gap-6 md:grid-cols-3">
            {MOAT.map((m, i) => (
              <div key={m.t} data-reveal style={{ transitionDelay: `${i * 70}ms` }} className="rounded-2xl border border-line bg-paper p-6">
                <div className="mb-4 flex h-8 w-8 items-center justify-center rounded-md border border-line font-mono text-[12px] text-pine">{String(i + 1).padStart(2, '0')}</div>
                <h3 className="font-display text-lg font-semibold tracking-tight">{m.t}</h3>
                <p className="mt-2 text-[14px] leading-relaxed text-ink-soft">{m.d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="mx-auto max-w-6xl px-6 py-24 text-center" data-reveal>
        <h2 className="mx-auto max-w-2xl font-display text-3xl font-medium tracking-tight sm:text-4xl">
          See two organizations negotiate a case, live.
        </h2>
        <div className="mt-8 flex items-center justify-center gap-3">
          <a href="#/live" className="rounded-lg bg-pine px-6 py-3 font-medium text-bone transition-colors hover:bg-pine-deep">Open the live demo →</a>
          <a href={GITHUB} target="_blank" rel="noreferrer" className="rounded-lg border border-ink/20 px-6 py-3 font-medium text-ink transition-colors hover:border-ink/50">View source</a>
        </div>
      </section>

      {/* tech */}
      <section className="mx-auto max-w-6xl px-6 pb-20 text-center">
        <Kicker>Built with</Kicker>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
          {TECH.map((t) => (
            <span key={t} className="rounded-md border border-line bg-paper px-3 py-1.5 font-mono text-[12px] text-ink-soft">{t}</span>
          ))}
        </div>
      </section>

      {/* footer */}
      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-6 py-8 font-mono text-[11px] uppercase tracking-[0.12em] text-ink-faint sm:flex-row">
          <div className="flex items-center gap-2 text-ink-soft"><Logo size={18} className="text-ink" /> Syntony · MIT · agents tuning to the same frequency</div>
          <div className="flex items-center gap-6">
            <a href="#/live" className="transition-colors hover:text-ink">Live demo</a>
            <a href={GITHUB} target="_blank" rel="noreferrer" className="transition-colors hover:text-ink">GitHub</a>
          </div>
        </div>
      </footer>
    </div>
  )
}
