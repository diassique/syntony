/** Input — a single-line text field matching the system (hairline border, pine focus ring).
 *  Forwards its ref and spreads native <input> props. Pair with a <label> for accessibility. */
import { forwardRef, type InputHTMLAttributes } from 'react'
import { cx } from './cx'

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { invalid, className, ...rest },
  ref,
) {
  return (
    <input
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cx(
        'w-full rounded-sm border bg-paper px-3 py-2 text-[14px] text-ink placeholder:text-ink-faint transition-colors',
        'focus-visible:outline-none focus-visible:ring-2',
        invalid
          ? 'border-coral/50 focus-visible:border-coral focus-visible:ring-coral/30'
          : 'border-line hover:border-pine/30 focus-visible:border-pine/50 focus-visible:ring-pine/30',
        'disabled:cursor-not-allowed disabled:opacity-60',
        className,
      )}
      {...rest}
    />
  )
})
