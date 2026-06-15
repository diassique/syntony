/** Select — a fully custom listbox (not a native <select>), so the open menu is styled to the
 *  system. Sizes mirror <Button> exactly, so the two line up at equal height side by side.
 *  The chevron flips on open. Keyboard: Enter/Space/↓/↑ open; ↓/↑/Home/End move; Enter picks;
 *  Esc/Tab close. Closes on outside-click. ARIA: combobox trigger + listbox/option, with
 *  aria-activedescendant tracking the highlighted row. */
import { useEffect, useId, useRef, useState } from 'react'
import { Check, ChevronDown } from 'lucide-react'
import { cx } from './cx'

export interface SelectOption {
  label: string
  value: string
  disabled?: boolean
}

export type SelectSize = 'sm' | 'md' | 'lg'

// Same vertical metrics as Button (py + text + leading) → identical control height.
const SIZES: Record<SelectSize, string> = {
  sm: 'py-1.5 pl-3 pr-2.5 text-[13px]',
  md: 'py-2 pl-3 pr-2.5 text-[14px]',
  lg: 'py-3 pl-4 pr-3 text-[15px]',
}

export interface SelectProps {
  options: SelectOption[]
  value: string
  onValueChange?: (value: string) => void
  size?: SelectSize
  disabled?: boolean
  placeholder?: string
  align?: 'start' | 'end'
  className?: string
  'aria-label'?: string
}

export function Select({
  options, value, onValueChange, size = 'md', disabled = false,
  placeholder = 'Select…', align = 'start', className, ...aria
}: SelectProps) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const baseId = useId()

  const selectedIndex = options.findIndex((o) => o.value === value)
  const selected = selectedIndex >= 0 ? options[selectedIndex] : undefined

  const step = (from: number, dir: 1 | -1) => {
    const n = options.length
    for (let k = 1; k <= n; k++) {
      const i = (from + dir * k + n * k) % n
      if (!options[i]?.disabled) return i
    }
    return from
  }
  const firstEnabled = () => (options.findIndex((o) => !o.disabled) + options.length) % options.length

  const openMenu = () => {
    if (disabled) return
    setActive(selectedIndex >= 0 && !options[selectedIndex]?.disabled ? selectedIndex : firstEnabled())
    setOpen(true)
  }
  const choose = (i: number) => {
    const o = options[i]
    if (!o || o.disabled) return
    onValueChange?.(o.value)
    setOpen(false)
  }

  // outside-click + Escape
  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => { if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  // keep the highlighted row in view
  useEffect(() => {
    if (!open || !listRef.current) return
    const el = listRef.current.children[active] as HTMLElement | undefined
    el?.scrollIntoView({ block: 'nearest' })
  }, [open, active])

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (disabled) return
    if (!open) {
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); openMenu() }
      return
    }
    switch (e.key) {
      case 'Escape': case 'Tab': setOpen(false); break
      case 'ArrowDown': e.preventDefault(); setActive((a) => step(a, 1)); break
      case 'ArrowUp': e.preventDefault(); setActive((a) => step(a, -1)); break
      case 'Home': e.preventDefault(); setActive(firstEnabled()); break
      case 'End': e.preventDefault(); setActive(step(0, -1)); break
      case 'Enter': case ' ': e.preventDefault(); choose(active); break
    }
  }

  return (
    <div ref={rootRef} className={cx('relative inline-block', className)}>
      <button
        type="button"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={`${baseId}-list`}
        aria-activedescendant={open ? `${baseId}-opt-${active}` : undefined}
        aria-label={aria['aria-label']}
        disabled={disabled}
        onClick={() => (open ? setOpen(false) : openMenu())}
        onKeyDown={onKeyDown}
        className={cx(
          'inline-flex w-full min-w-[11rem] items-center justify-between gap-2 rounded-sm border border-line bg-paper font-medium leading-tight text-ink transition-colors',
          'hover:border-pine/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pine/30 focus-visible:ring-offset-2 focus-visible:ring-offset-bone',
          'disabled:cursor-not-allowed disabled:opacity-60',
          SIZES[size],
        )}
      >
        <span className={cx('truncate', !selected && 'text-ink-faint')}>{selected ? selected.label : placeholder}</span>
        <ChevronDown size={14} strokeWidth={1.75} aria-hidden
          className={cx('shrink-0 text-ink-faint transition-transform duration-200', open && 'rotate-180')} />
      </button>

      {open && (
        <ul
          ref={listRef}
          id={`${baseId}-list`}
          role="listbox"
          tabIndex={-1}
          className={cx(
            'animate-rise absolute z-40 mt-1.5 max-h-64 min-w-full overflow-auto rounded-sm border border-line bg-paper p-1',
            'shadow-[0_20px_50px_-24px_rgba(14,19,17,0.55)]',
            align === 'end' ? 'right-0' : 'left-0',
          )}
        >
          {options.map((o, i) => {
            const isSelected = o.value === value
            const isActive = i === active
            return (
              <li
                key={o.value}
                id={`${baseId}-opt-${i}`}
                role="option"
                aria-selected={isSelected}
                aria-disabled={o.disabled || undefined}
                onMouseEnter={() => !o.disabled && setActive(i)}
                onClick={() => choose(i)}
                className={cx(
                  'flex cursor-pointer items-center justify-between gap-3 rounded-[3px] px-2.5 py-1.5 text-[13px] transition-colors',
                  o.disabled && 'cursor-not-allowed opacity-50',
                  isActive ? 'bg-pine/[0.08]' : '',
                  isSelected ? 'font-medium text-pine' : 'text-ink-soft',
                )}
              >
                <span className="truncate">{o.label}</span>
                {isSelected && <Check size={14} strokeWidth={2} aria-hidden className="shrink-0 text-pine" />}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
