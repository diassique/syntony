/** Dropdown — a click-to-open menu of actions (distinct from <Select>, which picks a value).
 *  Closes on outside-click and Escape. Items can be buttons (onSelect) or links (href), and
 *  may be `disabled` or `danger`. Pass any node as the `trigger` (usually a <Button>).
 *
 *  Intentionally lightweight for the hackathon base; arrow-key roving focus can be layered on
 *  later without changing this API. */
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { cx } from './cx'

export interface DropdownItem {
  label: ReactNode
  onSelect?: () => void
  href?: string
  icon?: ReactNode
  disabled?: boolean
  danger?: boolean
}

export interface DropdownProps {
  trigger: ReactNode
  items: DropdownItem[]
  align?: 'start' | 'end'
  className?: string
}

export function Dropdown({ trigger, items, align = 'start', className }: DropdownProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div ref={ref} className={cx('relative inline-block', className)}>
      <div onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open} className="contents">
        {trigger}
      </div>
      {open && (
        <div
          role="menu"
          className={cx(
            'animate-rise absolute z-40 mt-2 min-w-[12rem] overflow-hidden rounded-sm border border-line bg-paper py-1',
            'shadow-[0_20px_50px_-24px_rgba(14,19,17,0.5)]',
            align === 'end' ? 'right-0' : 'left-0',
          )}
        >
          {items.map((it, i) => {
            const cls = cx(
              'flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] transition-colors',
              it.disabled
                ? 'cursor-not-allowed text-ink-faint'
                : it.danger
                  ? 'text-coral hover:bg-coral/[0.06]'
                  : 'text-ink hover:bg-sunk/70',
            )
            const body = (<>{it.icon}{it.label}</>)
            if (it.href && !it.disabled) {
              return (
                <a key={i} role="menuitem" href={it.href} className={cls} onClick={() => setOpen(false)}>
                  {body}
                </a>
              )
            }
            return (
              <button
                key={i}
                type="button"
                role="menuitem"
                disabled={it.disabled}
                className={cls}
                onClick={() => { it.onSelect?.(); setOpen(false) }}
              >
                {body}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
