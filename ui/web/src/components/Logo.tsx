/** Resonance mark — concentric arcs "tuning to the same frequency".
 *  Monochrome: strokes inherit currentColor (ink); the core is pine. */
export function Logo({ size = 28, className }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden className={className}>
      <circle cx="16" cy="16" r="2.5" fill="#0b5e4f" />
      <path d="M10.5 16a5.5 5.5 0 0 1 11 0" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M6.5 16a9.5 9.5 0 0 1 19 0" stroke="currentColor" strokeWidth="2" strokeLinecap="round" opacity="0.32" />
    </svg>
  )
}
