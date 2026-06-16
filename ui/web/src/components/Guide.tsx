/** Guide — in-app "how to use Syntony" for the console.
 *
 * KEEP CURRENT: whenever a user-facing feature/flow/nav item changes, update this file in the
 * same change (see CLAUDE.md §2 — a stale Guide is a bug). It is the first thing a new user
 * (or a judge) reads to understand what the product does and how to drive it end to end. */

import {
  BookOpen, Users, Inbox, FilePlus2, FolderClosed, Boxes, BarChart3, Settings as SettingsIcon,
  Stethoscope, Gavel, RotateCcw, ShieldCheck, Lock, Clock, Play, FileSearch, ArrowRight, Award,
  SlidersHorizontal,
} from 'lucide-react'
import { Badge, Button } from './ui'

type Go = (view: string) => void

export default function Guide({ onGo }: { onGo?: Go }) {
  return (
    <div className="space-y-10">
      <header className="flex items-start gap-3">
        <span className="mt-0.5 text-pine"><BookOpen size={22} strokeWidth={1.75} /></span>
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight text-ink">How Syntony works</h1>
          <p className="mt-1 max-w-2xl text-[14px] text-ink-soft">
            Syntony runs <strong>prior authorization between a provider and a payer</strong> as a
            cross-organization mesh of AI agents on Band — structured (no raw PHI), with a private
            audit trail per side and a human in the loop on the calls that matter. This page walks
            the whole flow; everything below is real and clickable.
          </p>
        </div>
      </header>

      {/* Two sides */}
      <Section icon={<Users size={16} strokeWidth={1.75} />} title="Two organizations, one case">
        <p className="mb-4 text-[14px] text-ink-soft">
          A case is negotiated between two orgs. Sign in as either demo account (password{' '}
          <code className="rounded bg-sunk px-1 py-0.5 font-mono text-[12px]">syntonydemo24</code>) —
          each side sees only its own private reasoning; the room messages are shared.
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Persona tone="pine" role="Provider (clinic)" email="clinic@demo.syntony"
            does="Submits requests from a patient chart, answers payer info requests, files appeals." />
          <Persona tone="ink" role="Payer (insurer)" email="payer@demo.syntony"
            does="Reviews the request against medical-necessity policy and issues the determination." />
        </div>
      </Section>

      {/* The real flow */}
      <Section icon={<ArrowRight size={16} strokeWidth={1.75} />} title="The end-to-end flow">
        <ol className="space-y-3">
          <Step n={1} title="Pick a patient" who="provider"
            body="Open Patients → choose someone from the clinic roster, or start blank. Each chart carries coverage, an ICD-10 problem list, and documented prior care.">
            {onGo && <GoBtn onClick={() => onGo('patients')}>Open Patients</GoBtn>}
          </Step>
          <Step n={2} title="Build the request — Counsel pre-checks it live" who="provider"
            body="New request auto-fills from the chart. As you type, Provider Counsel validates completeness + code shapes (CPT/HCPCS/ICD) and flags the documentation gaps that cause denials — before you submit.">
            {onGo && <GoBtn onClick={() => onGo('submit')}>New request</GoBtn>}
          </Step>
          <Step n={3} title="Submit → it lands in the payer's worklist" who="provider"
            body="The case parks as ‘Awaiting payer’. Eligibility is verified against the patient's real coverage (270/271-style) on the way." />
          <Step n={4} title="Payer runs the UM review" who="payer"
            body="Open the case from Prior auth and run the review: the Reviewer consults Clinical Guidelines, Compliance and (for drugs) Pharmacy, then returns a recommendation.">
            {onGo && <GoBtn onClick={() => onGo('prior_auth')}>Open worklist</GoBtn>}
          </Step>
          <Step n={5} title="Payer commits a determination" who="payer"
            body="Approve (issues an authorization number), Request more info (pend), Deny with a specific CMS-0057-F reason, or Escalate a borderline case to the human Medical Director." />
          <Step n={6} title="Provider responds — pend or appeal" who="provider"
            body="On a pend, attach the requested documents; on an appealable denial, file an appeal that cures the reason. Reconsideration can overturn the denial." />
          <Step n={7} title="Borderline → human Medical Director" who="payer"
            body="A borderline case pauses for a licensed Medical Director to decide on clinical discretion — the human-in-the-loop the regulation requires." />
        </ol>
      </Section>

      {/* Watch a sample */}
      <Section icon={<Play size={16} strokeWidth={1.75} />} title="Just want to watch?">
        <p className="text-[14px] text-ink-soft">
          Use <strong>Sample run</strong> (Overview or Cases) to launch a fully-automated
          provider↔payer negotiation that streams turn-by-turn into the audit trail — the 30-second
          version of the flow above, no clicking through both sides.
        </p>
      </Section>

      {/* Nav map */}
      <Section icon={<FolderClosed size={16} strokeWidth={1.75} />} title="Where things live">
        <div className="grid gap-2 sm:grid-cols-2">
          <NavRow icon={<Users size={14} strokeWidth={1.75} />} name="Patients" desc="Clinic roster + chart + each patient's PA history" />
          <NavRow icon={<Inbox size={14} strokeWidth={1.75} />} name="Prior auth" desc="The worklist — cases needing your action surface on top" />
          <NavRow icon={<FilePlus2 size={14} strokeWidth={1.75} />} name="New request" desc="The submission form with live Counsel pre-check" />
          <NavRow icon={<FolderClosed size={14} strokeWidth={1.75} />} name="Cases" desc="Every negotiation (incl. Sample runs) + the two-lane Theater" />
          <NavRow icon={<Boxes size={14} strokeWidth={1.75} />} name="Agents" desc="The mesh roster — roles, frameworks, models" />
          <NavRow icon={<BarChart3 size={14} strokeWidth={1.75} />} name="Insights" desc="Outcomes, overturns, turnaround, SLA, denial mix" />
          <NavRow icon={<SlidersHorizontal size={14} strokeWidth={1.75} />} name="Configuration" desc="Payer edits its policy rules + clinical criteria (applied to the next case)" />
          <NavRow icon={<SettingsIcon size={14} strokeWidth={1.75} />} name="Settings" desc="Org + account; compliance PDF / JSON audit export" />
        </div>
      </Section>

      {/* Key concepts */}
      <Section icon={<ShieldCheck size={16} strokeWidth={1.75} />} title="Key concepts">
        <div className="grid gap-3 sm:grid-cols-2">
          <Concept icon={<Lock size={15} strokeWidth={1.75} />} title="Privacy moat"
            body="Room messages reach both orgs; each side's private agent reasoning is sealed to its own org. Log in as each side to see the asymmetry." />
          <Concept icon={<Clock size={15} strokeWidth={1.75} />} title="SLA clock"
            body="Every case shows the CMS-0057-F decision window — 72 hours expedited, 7 days standard — counting down." />
          <Concept icon={<Gavel size={15} strokeWidth={1.75} />} title="Specific denial reason"
            body="A denial always carries a machine-typed reason (step therapy, conservative care, coding…) — what the appeal then targets." />
          <Concept icon={<RotateCcw size={15} strokeWidth={1.75} />} title="Appeal → overturn"
            body="An appealable denial can be cured and reconsidered — modeling the ~80% of appealed denials that get overturned." />
          <Concept icon={<Stethoscope size={15} strokeWidth={1.75} />} title="Real agent frameworks"
            body="Each role's turn runs on a real framework (LangGraph / Pydantic AI) with the model served via the AI/ML gateway; the Medical Director is human." />
          <Concept icon={<FileSearch size={15} strokeWidth={1.75} />} title="AI/ML depth"
            body="Vision/OCR document intake reads a clinical doc into a request; embeddings RAG grounds the guidelines review in retrieved criteria." />
        </div>
      </Section>

      {/* Gold carding */}
      <Section icon={<Award size={16} strokeWidth={1.75} />} title="Gold carding">
        <p className="text-[14px] text-ink-soft">
          A provider with a strong approval track record for a given service earns a{' '}
          <Badge tone="coral">Gold Card</Badge> — an exemption (modeled on Texas HB 3459/3812) that
          <strong> auto-approves</strong> matching requests and skips review entirely. When you build
          a request for a gold-carded provider + service, the pre-check tells you up front, and the
          case is authorized on submit. It's the burden reduction PA reform is reaching for.
        </p>
      </Section>

      <footer className="border-t border-line pt-6 text-[12px] text-ink-faint">
        All patient data is synthetic — no real PHI. Codes (ICD-10/CPT/HCPCS) are real and valid; the
        patients and cases are fictional.
      </footer>
    </div>
  )
}

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="mb-4 flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.14em] text-ink-soft">
        <span className="text-pine">{icon}</span>{title}
      </h2>
      {children}
    </section>
  )
}

function Persona({ tone, role, email, does }: { tone: 'pine' | 'ink'; role: string; email: string; does: string }) {
  return (
    <div className="rounded-md border border-line bg-paper p-4">
      <div className="mb-1 flex items-center gap-2">
        <Badge tone={tone}>{role}</Badge>
      </div>
      <p className="font-mono text-[12px] text-ink">{email}</p>
      <p className="mt-1.5 text-[13px] text-ink-soft">{does}</p>
    </div>
  )
}

function Step({ n, title, who, body, children }: { n: number; title: string; who: 'provider' | 'payer'; body: string; children?: React.ReactNode }) {
  return (
    <li className="flex gap-3">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-pine/10 font-mono text-[12px] font-bold text-pine ring-1 ring-pine/20">{n}</span>
      <div className="min-w-0 flex-1 rounded-md border border-line bg-paper p-4">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-[14px] font-semibold text-ink">{title}</h3>
          <Badge tone={who === 'provider' ? 'pine' : 'ink'}>{who}</Badge>
        </div>
        <p className="mt-1 text-[13px] text-ink-soft">{body}</p>
        {children && <div className="mt-3">{children}</div>}
      </div>
    </li>
  )
}

function GoBtn({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <Button size="sm" variant="secondary" trailingIcon={<ArrowRight size={13} strokeWidth={1.75} />} onClick={onClick}>{children}</Button>
  )
}

function NavRow({ icon, name, desc }: { icon: React.ReactNode; name: string; desc: string }) {
  return (
    <div className="flex items-start gap-2.5 rounded-sm border border-line bg-paper px-3 py-2.5">
      <span className="mt-0.5 text-ink-soft">{icon}</span>
      <div>
        <p className="text-[13px] font-medium text-ink">{name}</p>
        <p className="text-[12px] text-ink-faint">{desc}</p>
      </div>
    </div>
  )
}

function Concept({ icon, title, body }: { icon: React.ReactNode; title: string; body: string }) {
  return (
    <div className="rounded-md border border-line bg-paper p-4">
      <div className="mb-1.5 flex items-center gap-2 text-ink">
        <span className="text-pine">{icon}</span>
        <h3 className="text-[14px] font-semibold">{title}</h3>
      </div>
      <p className="text-[13px] text-ink-soft">{body}</p>
    </div>
  )
}
