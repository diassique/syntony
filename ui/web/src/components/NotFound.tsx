/** 404 — shown for any path the client router doesn't recognise. Clinical Bone styling,
 *  links back into the app. (The server returns the SPA shell with 200 for client routes;
 *  this is the visible not-found state.) */
import { Wordmark } from './Logo'

export default function NotFound() {
  return (
    <div className="flex min-h-full flex-col bg-bone">
      <nav className="border-b border-line/70">
        <div className="mx-auto flex max-w-6xl items-center px-6 py-4">
          <a href="/" className="flex items-center"><Wordmark height={22} /></a>
        </div>
      </nav>

      <div className="flex flex-1 items-center justify-center px-6 py-20">
        <div className="w-full max-w-lg text-center">
          <div className="font-mono text-[88px] font-medium leading-none tabular-nums tracking-tight text-ink">
            4<span className="text-coral">0</span>4
          </div>
          <div className="mx-auto mt-6 h-px w-16 bg-line" />
          <h1 className="mt-6 font-display text-2xl font-medium tracking-tight text-ink">
            This page isn't on the mesh.
          </h1>
          <p className="mx-auto mt-3 max-w-sm text-ink-soft">
            The URL you followed doesn't resolve to a Syntony page — it may have moved, or never existed.
          </p>

          <div className="mt-8 flex flex-wrap items-center justify-center gap-3 font-mono text-[11px] uppercase tracking-[0.12em]">
            <a href="/" className="rounded-sm bg-pine px-4 py-2.5 text-bone transition-colors hover:bg-pine-deep">
              Back to home
            </a>
            <a href="/app" className="rounded-sm border border-ink/25 px-4 py-2.5 text-ink transition-colors hover:border-ink/60">
              Open the console
            </a>
            <a href="/live" className="rounded-sm border border-line px-4 py-2.5 text-ink-soft transition-colors hover:border-pine/40 hover:text-pine">
              Watch it live
            </a>
          </div>
        </div>
      </div>
    </div>
  )
}
