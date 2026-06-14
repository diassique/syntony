/** Login / signup page (one component, two modes). Clinical Bone styling to match
 * the landing. On success the auth context is populated and we route to #/app. */

import { useEffect, useState, type FormEvent } from 'react'
import { ApiError } from '../api'
import { useAuth } from '../auth'
import { Logo } from './Logo'

export default function Auth({ mode }: { mode: 'login' | 'signup' }) {
  const { user, login, signup } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [orgName, setOrgName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const isSignup = mode === 'signup'

  // Already signed in → no reason to be on this page.
  useEffect(() => { if (user) window.location.hash = '#/app' }, [user])

  async function onSubmit(e: FormEvent): Promise<void> {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      if (isSignup) {
        await signup({ email, password, name: name || undefined, org_name: orgName || undefined })
      } else {
        await login(email, password)
      }
      window.location.hash = '#/app'
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-full flex-col">
      <nav className="border-b border-line/70">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-6 py-4">
          <a href="#/" className="flex items-center gap-3">
            <Logo size={24} className="text-ink" />
            <span className="font-display text-[17px] font-semibold tracking-tight">Syntony</span>
          </a>
        </div>
      </nav>

      <div className="flex flex-1 items-center justify-center px-6 py-16">
        <div className="w-full max-w-sm">
          <div className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-faint">
            {isSignup ? 'Create account' : 'Sign in'}
          </div>
          <h1 className="mt-3 font-display text-3xl font-medium tracking-tight text-ink">
            {isSignup ? 'Start coordinating agents.' : 'Welcome back.'}
          </h1>

          <form onSubmit={onSubmit} className="mt-8 space-y-4">
            {isSignup && (
              <Field label="Name" optional>
                <input className={inputCls} type="text" value={name} autoComplete="name"
                  onChange={(e) => setName(e.target.value)} placeholder="Ada Lovelace" />
              </Field>
            )}
            <Field label="Email">
              <input className={inputCls} type="email" required value={email} autoComplete="email"
                onChange={(e) => setEmail(e.target.value)} placeholder="you@org.com" />
            </Field>
            <Field label="Password">
              <input className={inputCls} type="password" required minLength={isSignup ? 8 : undefined}
                value={password} autoComplete={isSignup ? 'new-password' : 'current-password'}
                onChange={(e) => setPassword(e.target.value)} placeholder={isSignup ? 'at least 8 characters' : '••••••••'} />
            </Field>
            {isSignup && (
              <Field label="Organization" optional>
                <input className={inputCls} type="text" value={orgName}
                  onChange={(e) => setOrgName(e.target.value)} placeholder="Acme Health" />
              </Field>
            )}

            {error && (
              <div className="rounded-md border border-coral/40 bg-coral/5 px-3 py-2 text-[13px] text-coral">{error}</div>
            )}

            <button type="submit" disabled={busy}
              className="w-full rounded-lg bg-pine px-5 py-3 font-medium text-bone transition-colors hover:bg-pine-deep disabled:opacity-60">
              {busy ? 'Working…' : isSignup ? 'Create account →' : 'Sign in →'}
            </button>
          </form>

          <p className="mt-6 text-[13px] text-ink-soft">
            {isSignup ? 'Already have an account? ' : "Don't have an account? "}
            <a href={isSignup ? '#/login' : '#/signup'} className="font-medium text-pine hover:text-pine-deep">
              {isSignup ? 'Sign in' : 'Create one'}
            </a>
          </p>
        </div>
      </div>
    </div>
  )
}

const inputCls =
  'w-full rounded-lg border border-line bg-paper px-3.5 py-2.5 text-[15px] text-ink outline-none ' +
  'placeholder:text-ink-faint focus:border-pine focus:ring-2 focus:ring-pine/15'

function Field({ label, optional, children }: { label: string; optional?: boolean; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.12em] text-ink-soft">
        {label}{optional && <span className="text-ink-faint normal-case tracking-normal">· optional</span>}
      </span>
      {children}
    </label>
  )
}
