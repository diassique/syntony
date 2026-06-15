/** Button — the primary action primitive of the Clinical Bone system.
 *
 *  Variants: `primary` (pine), `secondary` (hairline outline), `ghost` (quiet),
 *  `signal` (coral — live / high-emphasis actions only). Sizes: sm / md / lg.
 *  Supports `loading` (shows a spinner + disables) and leading/trailing icons.
 *  Forwards its ref and spreads native <button> props, so it drops in anywhere. */
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { Loader2 } from 'lucide-react'
import { cx } from './cx'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'signal'
export type ButtonSize = 'sm' | 'md' | 'lg'

const VARIANTS: Record<ButtonVariant, string> = {
  primary: 'bg-pine text-bone hover:bg-pine-deep',
  secondary: 'border border-ink/25 text-ink hover:border-ink/55 hover:bg-ink/[0.03]',
  ghost: 'text-ink-soft hover:bg-sunk/70 hover:text-ink',
  signal: 'bg-coral text-bone hover:bg-coral/90',
}

const SIZES: Record<ButtonSize, string> = {
  sm: 'gap-1.5 px-3 py-1.5 text-[13px]',
  md: 'gap-2 px-4 py-2 text-[14px]',
  lg: 'gap-2 px-5 py-3 text-[15px]',
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  leadingIcon?: ReactNode
  trailingIcon?: ReactNode
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'primary', size = 'md', loading = false, leadingIcon, trailingIcon, className, children, disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cx(
        // transparent border in the base so borderless variants keep the same box height
        // as bordered controls (e.g. <Select>) sitting beside them.
        'inline-flex items-center justify-center rounded-sm border border-transparent font-medium leading-tight transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pine/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bone',
        'disabled:cursor-not-allowed disabled:opacity-60',
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 size={15} className="animate-spin" aria-hidden /> : leadingIcon}
      {children}
      {!loading && trailingIcon}
    </button>
  )
})
