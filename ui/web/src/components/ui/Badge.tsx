/** Badge — a small mono status chip. Tones map to the system's semantic colors:
 *  neutral, pine (provider / positive), ink (payer), coral (signal / alert). */
import { type ReactNode } from 'react'
import { cx } from './cx'

export type BadgeTone = 'neutral' | 'pine' | 'ink' | 'coral'

const TONES: Record<BadgeTone, string> = {
  neutral: 'border-line bg-sunk text-ink-faint',
  pine: 'border-pine/30 bg-pine/10 text-pine',
  ink: 'border-ink/20 bg-ink/[0.06] text-ink',
  coral: 'border-coral/40 bg-coral/10 text-coral',
}

export interface BadgeProps {
  tone?: BadgeTone
  children: ReactNode
  className?: string
}

export function Badge({ tone = 'neutral', children, className }: BadgeProps) {
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1 rounded-sm border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.1em]',
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}
