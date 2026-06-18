/**
 * Tiny dependency-free path router (History API).
 *
 * Replaces the old hash router: every page now has a real URL (`/app/agents`, `/pitch-deck`, …),
 * so deep links, refresh, and browser back/forward all work. The server serves index.html for any
 * unknown path (SPA fallback in ui/server.py), then this router renders the matching view.
 *
 * - `usePathname()` / `useLocation()` subscribe to navigation and re-render on change.
 * - `navigate(to)` pushes (or replaces) a history entry — usable from anywhere, hooks or not.
 * - `<Redirect to>` navigates in an effect (safe to render).
 * - `interceptLinks()` (called once) turns ordinary `<a href="/…">` clicks into SPA navigations,
 *   so components keep using plain anchors. In-page `#anchors`, external links, new-tab and
 *   download links are left to the browser.
 */
import { useEffect, useSyncExternalStore } from 'react'

const listeners = new Set<() => void>()
const emit = () => listeners.forEach((l) => l())

function subscribe(cb: () => void): () => void {
  listeners.add(cb)
  window.addEventListener('popstate', cb)
  return () => { listeners.delete(cb); window.removeEventListener('popstate', cb) }
}

/** Navigate to an in-app path. No-op if already there. `replace` swaps the current entry. */
export function navigate(to: string, opts?: { replace?: boolean }): void {
  if (to === window.location.pathname + window.location.search + window.location.hash) return
  if (opts?.replace) window.history.replaceState(null, '', to)
  else window.history.pushState(null, '', to)
  emit()
}

/** Current `pathname` (re-renders on navigation). */
export function usePathname(): string {
  return useSyncExternalStore(subscribe, () => window.location.pathname, () => '/')
}

/** Current `pathname + search` (re-renders on navigation). Use when a view reads query params. */
export function useLocation(): string {
  return useSyncExternalStore(
    subscribe,
    () => window.location.pathname + window.location.search,
    () => '/',
  )
}

/** Declarative redirect — safe to render; navigates after commit. */
export function Redirect({ to }: { to: string }): null {
  useEffect(() => { navigate(to, { replace: true }) }, [to])
  return null
}

/** One-time global handler: same-origin `/…` anchor clicks become SPA navigations. */
export function interceptLinks(): void {
  if ((window as unknown as { __syntonyLinks?: boolean }).__syntonyLinks) return
  ;(window as unknown as { __syntonyLinks?: boolean }).__syntonyLinks = true
  document.addEventListener('click', (e) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
    const a = (e.target as HTMLElement | null)?.closest('a')
    if (!a) return
    const href = a.getAttribute('href')
    if (!href || !href.startsWith('/')) return            // only internal absolute paths; leaves #anchors + externals
    if (a.target && a.target !== '_self') return           // _blank etc. → let the browser open it
    if (a.hasAttribute('download') || a.origin !== window.location.origin) return
    e.preventDefault()
    navigate(href)
  })
}
