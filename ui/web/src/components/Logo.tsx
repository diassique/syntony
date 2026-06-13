export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden>
      <defs>
        <linearGradient id="syntony-g" x1="2" y1="2" x2="30" y2="30" gradientUnits="userSpaceOnUse">
          <stop stopColor="#a78bfa" />
          <stop offset="1" stopColor="#22d3ee" />
        </linearGradient>
      </defs>
      <circle cx="16" cy="16" r="2.6" fill="url(#syntony-g)" />
      <path d="M10 16a6 6 0 0 1 12 0" stroke="url(#syntony-g)" strokeWidth="2.1" strokeLinecap="round" />
      <path d="M6 16a10 10 0 0 1 20 0" stroke="url(#syntony-g)" strokeWidth="2.1" strokeLinecap="round" opacity="0.5" />
    </svg>
  )
}
