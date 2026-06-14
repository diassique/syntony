/** Authenticated console — the post-login home. Shows the identity/org restored from
 * /me and is the surface future platform features (API keys, projects, runs) hang off. */

import { useAuth } from '../auth'
import { Logo } from './Logo'

export default function Console() {
  const { user, org, logout } = useAuth()
  if (!user) return null // App guards this route; this is just for type-narrowing.

  return (
    <div className="min-h-full">
      <nav className="border-b border-line/70 bg-bone/85 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center gap-3 px-6 py-4">
          <a href="#/" className="flex items-center gap-3">
            <Logo size={24} className="text-ink" />
            <span className="font-display text-[17px] font-semibold tracking-tight">Syntony</span>
          </a>
          <span className="rounded-md border border-line bg-paper px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-faint">console</span>
          <div className="ml-auto flex items-center gap-5 font-mono text-[11px] uppercase tracking-[0.12em] text-ink-soft">
            <a href="#/live" className="transition-colors hover:text-ink">Live demo</a>
            <button onClick={logout} className="transition-colors hover:text-coral">Sign out</button>
          </div>
        </div>
      </nav>

      <main className="mx-auto max-w-5xl px-6 py-12">
        <div className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-faint">Signed in</div>
        <h1 className="mt-3 font-display text-4xl font-medium tracking-tight text-ink">
          {greeting(user.name, user.email)}
        </h1>
        <p className="mt-3 max-w-xl text-ink-soft">
          You're connected to the Syntony control plane. This is where your organization's projects,
          agent credentials, runs and audit trail will live.
        </p>

        <div className="mt-10 grid gap-5 sm:grid-cols-2">
          <Card label="Account">
            <Row k="Name" v={user.name || '—'} />
            <Row k="Email" v={user.email} mono />
            <Row k="User ID" v={user.id} mono faint />
          </Card>
          <Card label="Organization">
            {org ? (
              <>
                <Row k="Name" v={org.name} />
                <Row k="Slug" v={org.slug} mono />
                <Row k="Plan" v={org.plan} badge />
              </>
            ) : (
              <p className="text-[14px] text-ink-soft">No organization on this account yet.</p>
            )}
          </Card>
        </div>

        <div className="mt-8 rounded-2xl border border-dashed border-line bg-sunk/40 p-6">
          <div className="font-mono text-[11px] uppercase tracking-[0.16em] text-ink-faint">Coming next</div>
          <p className="mt-2 max-w-2xl text-[14px] leading-relaxed text-ink-soft">
            API keys · encrypted Band/LLM credentials · projects (domain packs) · live runs with a
            per-org audit trail and usage metering — all already modeled in the control plane.
          </p>
        </div>
      </main>
    </div>
  )
}

function greeting(name: string, email: string): string {
  const who = name?.trim() || email.split('@')[0]
  return `Hello, ${who}.`
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
