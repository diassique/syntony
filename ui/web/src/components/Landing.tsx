import { Logo } from './Logo'

const GITHUB = 'https://github.com/diassique/syntony'

const STATS = [
  { v: '13 hrs/wk', l: 'physician time lost to prior auth (AMA)' },
  { v: '→ ~4 min', l: 'a negotiated case on Syntony' },
  { v: '$15B', l: '10-yr savings projected by CMS' },
  { v: '72h / 7d', l: 'CMS-0057-F response mandate (2026)' },
]

const STEPS = [
  { n: '01', t: 'Intake frames the case', d: 'A clinic agent assembles a structured, FHIR-shaped request from the chart — no raw PHI leaves the room.' },
  { n: '02', t: 'Counsel catches mistakes', d: 'A coding agent validates codes, signatures and docs, fixing the mismatches that cause most denials — before submission.' },
  { n: '03', t: 'Payer reviews necessity', d: 'A payer agent in a different account checks medical-necessity policy and asks for what is missing.' },
  { n: '04', t: 'Human on the edge cases', d: 'Borderline cases escalate to a human Medical Director, added to the room in one click. Every step is audited.' },
]

const MOAT = [
  { t: 'Cross-org consent', d: 'Two independent organizations connect via a bilateral, approved contact — not a shared login or a brittle integration.' },
  { t: 'Mention-scoped privacy', d: 'Each side keeps its internal strategy on a private event channel the counterparty never sees — even in the shared room.' },
  { t: 'Unified audit trail', d: 'Every message, tool call and decision is recorded as a typed, replayable event stream for both parties.' },
]

const TECH = ['Band agentic mesh', 'LangGraph', 'Pydantic AI', 'Anthropic Claude', 'Letta', 'AI/ML API', 'Featherless']

export default function Landing() {
  return (
    <div className="bg-grid min-h-full text-[#e6e6e6]">
      {/* nav */}
      <nav className="mx-auto flex max-w-6xl items-center gap-3 px-6 py-5">
        <Logo size={26} />
        <span className="text-lg font-semibold">Syntony</span>
        <div className="ml-auto flex items-center gap-5 text-sm text-[#9fb0cc]">
          <a href="#how" className="hidden transition-colors hover:text-white sm:inline">How it works</a>
          <a href={GITHUB} target="_blank" className="hidden transition-colors hover:text-white sm:inline">GitHub</a>
          <a href="#/live" className="rounded-lg bg-gradient-to-r from-violet-500 to-cyan-400 px-3.5 py-1.5 font-medium text-[#0b0e14] transition-opacity hover:opacity-90">
            Live demo →
          </a>
        </div>
      </nav>

      {/* hero */}
      <header className="mx-auto max-w-4xl px-6 pt-16 pb-20 text-center">
        <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-[#243049] bg-[#0c1322]/60 px-3 py-1 text-xs text-[#9fb0cc]">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> Band of Agents Hackathon · Regulated track
        </div>
        <h1 className="text-5xl font-bold leading-[1.05] tracking-tight sm:text-6xl">
          Agents that <span className="brand-text">tune to the same frequency</span>.
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-[#9fb0cc]">
          Syntony is a coordination protocol for AI agents across organizations. Its first
          application: cross-org <span className="text-white">prior authorization</span> — a clinic and a
          payer settle a case in minutes, in a shared room, without passing raw PHI, with a human on the edge cases
          and a full audit trail.
        </p>
        <div className="mt-9 flex items-center justify-center gap-3">
          <a href="#/live" className="rounded-xl bg-gradient-to-r from-violet-500 to-cyan-400 px-5 py-3 font-semibold text-[#0b0e14] transition-opacity hover:opacity-90">
            Watch it live →
          </a>
          <a href={GITHUB} target="_blank" className="rounded-xl border border-[#28324a] px-5 py-3 font-medium text-[#cdd8ee] transition-colors hover:border-[#3a4a6b]">
            View source
          </a>
        </div>
      </header>

      {/* stats */}
      <section className="mx-auto grid max-w-5xl grid-cols-2 gap-px overflow-hidden rounded-2xl border border-[#1a2236] bg-[#1a2236] md:grid-cols-4">
        {STATS.map((s) => (
          <div key={s.l} className="bg-[#0a0e18] px-5 py-7 text-center">
            <div className="brand-text text-2xl font-bold">{s.v}</div>
            <div className="mt-1.5 text-xs leading-snug text-[#7d8aa3]">{s.l}</div>
          </div>
        ))}
      </section>

      {/* how it works */}
      <section id="how" className="mx-auto max-w-6xl px-6 py-24">
        <h2 className="text-center text-3xl font-bold tracking-tight">How a case flows</h2>
        <p className="mx-auto mt-3 max-w-xl text-center text-[#9fb0cc]">
          Heterogeneous agents across two accounts, coordinated over the Band mesh.
        </p>
        <div className="mt-12 grid gap-5 md:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((s) => (
            <div key={s.n} className="rounded-2xl border border-[#1a2236] bg-[#0b1019] p-5 transition-colors hover:border-[#2a3a57]">
              <div className="brand-text text-sm font-bold">{s.n}</div>
              <h3 className="mt-2 font-semibold text-[#e6e6e6]">{s.t}</h3>
              <p className="mt-2 text-sm leading-relaxed text-[#8a96ad]">{s.d}</p>
            </div>
          ))}
        </div>
      </section>

      {/* moat */}
      <section className="border-y border-[#141a2a] bg-[#080b12]">
        <div className="mx-auto max-w-6xl px-6 py-24">
          <h2 className="text-center text-3xl font-bold tracking-tight">Why it needs a mesh</h2>
          <p className="mx-auto mt-3 max-w-xl text-center text-[#9fb0cc]">
            Remove Band and the whole thing collapses — consent, privacy and audit are the point.
          </p>
          <div className="mt-12 grid gap-5 md:grid-cols-3">
            {MOAT.map((m) => (
              <div key={m.t} className="rounded-2xl border border-[#1a2236] bg-[#0b1019] p-6">
                <h3 className="font-semibold text-white">{m.t}</h3>
                <p className="mt-2 text-sm leading-relaxed text-[#8a96ad]">{m.d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* tech */}
      <section className="mx-auto max-w-6xl px-6 py-20 text-center">
        <div className="text-xs uppercase tracking-[0.2em] text-[#5c6a85]">Built with</div>
        <div className="mt-5 flex flex-wrap items-center justify-center gap-2.5">
          {TECH.map((t) => (
            <span key={t} className="rounded-full border border-[#222d45] bg-[#0c1322] px-3.5 py-1.5 text-sm text-[#aebbd4]">{t}</span>
          ))}
        </div>
      </section>

      {/* footer */}
      <footer className="border-t border-[#141a2a]">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-6 py-8 text-sm text-[#6b7790] sm:flex-row">
          <div className="flex items-center gap-2"><Logo size={20} /> Syntony · MIT</div>
          <div className="flex items-center gap-5">
            <a href="#/live" className="transition-colors hover:text-white">Live demo</a>
            <a href={GITHUB} target="_blank" className="transition-colors hover:text-white">GitHub</a>
          </div>
        </div>
      </footer>
    </div>
  )
}
